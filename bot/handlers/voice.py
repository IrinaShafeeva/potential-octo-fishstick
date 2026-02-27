import asyncio
import json
import logging
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_memory import memory_preview_kb, memory_fantasy_kb, chapter_select_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.loader import bot
from bot.services.stt import transcribe_voice
from bot.services.ai_editor import clean_transcript, edit_memoir, fantasy_edit_memoir
from bot.services.timeline import extract_timeline
from bot.services.classifier import classify_chapter
from bot.services.style_profiler import update_style_profile
from bot.services.character_extractor import extract_characters
from bot.services.thread_summarizer import refresh_thread_summary
from bot.services.clarifier import ask_clarification

router = Router()
logger = logging.getLogger(__name__)

MIN_VOICE_DURATION = 3
STT_CONFIDENCE_THRESHOLD = 0.3
MAX_CLARIFICATION_ROUNDS = 3


def _clarification_kb(memory_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Другой вопрос", callback_data=f"other_clarif:{memory_id}"),
        InlineKeyboardButton(text="⏭ Без уточнений", callback_data=f"skip_clarif:{memory_id}"),
    ]])


class MemoryStates(StatesGroup):
    waiting_edit_text = State()
    waiting_text_memory = State()
    waiting_new_chapter = State()


def _detect_gender(text: str) -> str | None:
    """Detect author gender from Russian text by analysing first-person verb forms.

    Returns 'female', 'male', or None if unclear.
    """
    t = text.lower()
    sentences = re.split(r'[.!?\n]', t)
    fem = 0
    masc = 0
    for sent in sentences:
        if 'я' not in sent:
            continue
        # Feminine past tense: -ла, -лась
        if re.search(r'\w+(?:лась|ла)\b', sent):
            fem += 1
        # Masculine past tense: -л or -лся but NOT -ла/-лась
        elif re.search(r'\w+л(?!а|и|о|сь)\b', sent):
            masc += 1
    if fem > masc:
        return 'female'
    if masc > fem:
        return 'male'
    return None


# ── Core pipeline helpers ──

async def _fetch_user_context(user_id: int) -> dict:
    """Fetch author context needed by the editor (one DB session)."""
    async with async_session() as session:
        repo = Repository(session)
        known_characters = await repo.get_characters(user_id)
        known_places = await repo.get_places_with_counts(user_id)
        style_notes = await repo.get_style_notes(user_id)
        chapters = await repo.get_chapters(user_id)
        gender = await repo.get_gender(user_id)
    return {
        "known_characters": known_characters,
        "known_places": known_places,
        "style_notes": style_notes,
        "chapters": chapters,
        "gender": gender,
    }


async def _classify_chapter(cleaned: str, chapters: list) -> tuple[str | None, str | None]:
    """Return (chapter_suggestion, thread_summary) for the cleaned text."""
    if not chapters:
        return None, None
    chapters_dicts = [
        {"title": ch.title, "period_hint": ch.period_hint or ""}
        for ch in chapters
    ]
    classification = await classify_chapter(
        cleaned, {"type": "unknown", "value": ""}, chapters_dicts
    )
    suggestion = classification.get("chapter_suggestion")
    thread_summary = None
    if suggestion:
        for ch in chapters:
            if ch.title == suggestion:
                thread_summary = ch.thread_summary
                break
    return suggestion, thread_summary


async def _run_editor_and_preview(
    message,  # Message or CallbackQuery.message (bot's message)
    processing_msg,
    memory_id: int,
    cleaned: str,
    qa_thread: list[dict],
    source_question_id: str | None,
    state: FSMContext | None,
    ctx: dict,
    *,
    user_telegram_id: int | None = None,
) -> None:
    """Classify → edit (with QA context) → timeline → update memory → show preview."""
    chapter_suggestion, thread_summary = await _classify_chapter(cleaned, ctx["chapters"])

    # Run strict and fantasy editors in parallel
    author_gender = ctx.get("gender")
    edited, fantasy_text = await asyncio.gather(
        edit_memoir(
            cleaned,
            ctx["known_characters"],
            ctx["known_places"],
            ctx["style_notes"],
            qa_thread or None,
            author_gender,
        ),
        fantasy_edit_memoir(cleaned, qa_thread or None, thread_summary, author_gender),
    )

    strict_text = edited.get("edited_memoir_text", cleaned)
    time_hint = await extract_timeline(strict_text)

    async with async_session() as session:
        repo = Repository(session)
        await repo.update_memory_after_edit(
            memory_id=memory_id,
            edited_text=strict_text,
            fantasy_text=fantasy_text or None,
            title=edited.get("title", ""),
            tags=edited.get("tags", []),
            people=edited.get("people", []),
            places=edited.get("places", []),
            time_hint_type=time_hint.get("type"),
            time_hint_value=time_hint.get("value"),
            time_confidence=time_hint.get("confidence"),
            chapter_suggestion=chapter_suggestion,
        )
        await repo.clear_clarification_state(memory_id)

        # Mark question answered — prefer FSM data, fall back to source_question_id lookup
        question_log_id = None
        if state:
            data = await state.get_data()
            question_log_id = data.get("answering_question_log_id")
        if question_log_id:
            await repo.mark_question_answered(question_log_id, memory_id)
        elif source_question_id:
            tg_id = user_telegram_id or getattr(getattr(message, "from_user", None), "id", None)
            if tg_id:
                user = await repo.get_user(tg_id)
                if user:
                    await repo.mark_question_answered_by_source(user.id, source_question_id, memory_id)

    if state:
        await state.clear()

    title = edited.get("title", "Воспоминание")
    chapter_line = f"\n📁 Предлагаю главу: <b>{chapter_suggestion}</b>" if chapter_suggestion else ""

    # Always show strict version first; fantasy available via button if it exists
    preview = strict_text[:1500] + ("…" if len(strict_text) > 1500 else "")
    await processing_msg.edit_text(
        f"<b>{title}</b>{chapter_line}\n\n{preview}",
        reply_markup=memory_preview_kb(memory_id, has_fantasy=bool(fantasy_text)),
    )


async def _process_and_preview(
    message: Message,
    raw_transcript: str,
    audio_file_id: str | None = None,
    source_question_id: str | None = None,
    state: FSMContext | None = None,
) -> None:
    """Full pipeline for a new memory: clean → clarify → edit → preview."""
    processing_msg = await message.answer("⏳ Обрабатываю текст…")
    try:
        await _pipeline(
            message, processing_msg, raw_transcript,
            audio_file_id, source_question_id, state,
        )
    except Exception as e:
        logger.error("Processing pipeline error: %s", e, exc_info=True)
        await processing_msg.edit_text(
            "Что-то пошло не так при обработке. Попробуйте ещё раз. 🙏"
        )
        if state:
            await state.clear()


async def _pipeline(
    message: Message,
    processing_msg,
    raw_transcript: str,
    audio_file_id: str | None,
    source_question_id: str | None,
    state: FSMContext | None,
) -> None:
    cleaned = await clean_transcript(raw_transcript)
    await processing_msg.edit_text("⏳ Читаю историю…")

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user_id = user.id

    ctx = await _fetch_user_context(user_id)

    # Auto-detect gender from cleaned text and save if not yet known
    if not ctx.get("gender"):
        detected = _detect_gender(cleaned)
        if detected:
            async with async_session() as session:
                repo = Repository(session)
                await repo.set_user_gender(user_id, detected)
            ctx["gender"] = detected

    # Ask clarifier before editing — if a question is needed, park the story in DB
    clarification = await ask_clarification(cleaned, [])

    # Create the draft memory (with or without clarification pending)
    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.create_memory(
            user_id=user_id,
            audio_file_id=audio_file_id,
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned,
            source_question_id=source_question_id,
        )

    if not clarification.get("is_complete"):
        question = clarification["question"]
        thread = [{"role": "question", "text": question}]
        async with async_session() as session:
            repo = Repository(session)
            await repo.set_clarification_state(memory.id, thread, 1)
        await processing_msg.edit_text(f"💬 {question}", reply_markup=_clarification_kb(memory.id))
        if state:
            await state.clear()
        return

    # No clarification needed — run editor immediately
    await processing_msg.edit_text("⏳ Редактирую для книги…")
    await _run_editor_and_preview(
        message, processing_msg, memory.id, cleaned, [], source_question_id, state, ctx,
    )


async def _handle_clarification_answer(
    message: Message,
    state: FSMContext | None,
    answer_text: str,
    pending: object,  # Memory ORM object
) -> None:
    """Process user's answer to a clarification question."""
    thread = json.loads(pending.clarification_thread or "[]")
    thread.append({"role": "answer", "text": answer_text})
    current_round = pending.clarification_round
    cleaned = pending.cleaned_transcript or ""

    processing_msg = await message.answer("⏳ Думаю…")

    # Ask clarifier for next action (if still within round limit)
    if current_round < MAX_CLARIFICATION_ROUNDS:
        clarification = await ask_clarification(cleaned, thread)
        if not clarification.get("is_complete"):
            question = clarification["question"]
            thread.append({"role": "question", "text": question})
            async with async_session() as session:
                repo = Repository(session)
                await repo.set_clarification_state(pending.id, thread, current_round + 1)
            await processing_msg.edit_text(f"💬 {question}", reply_markup=_clarification_kb(pending.id))
            return

    # "История полная" or max rounds — compile and show preview
    await processing_msg.edit_text("⏳ Редактирую для книги…")
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        user_id = user.id

    ctx = await _fetch_user_context(user_id)
    await _run_editor_and_preview(
        message, processing_msg, pending.id, cleaned, thread,
        pending.source_question_id, state, ctx,
    )


# ── Voice handler ──

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext) -> None:
    if message.voice.duration < MIN_VOICE_DURATION:
        await message.answer("Запись слишком короткая. Расскажите подробнее!")
        return

    processing_msg = await message.answer("⏳ Распознаю речь…")

    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_bytes = file_bytes.read()

    stt_result = await transcribe_voice(audio_bytes)
    raw_transcript = stt_result["text"]
    confidence = stt_result["confidence"]

    if not raw_transcript or confidence < STT_CONFIDENCE_THRESHOLD:
        await processing_msg.edit_text(
            "Не удалось разобрать запись. Попробуйте записать ещё раз в тихом месте. 🔇"
        )
        return

    await processing_msg.delete()

    # Check DB for pending clarification — voice = clarification answer
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        pending = await repo.get_pending_clarification_memory(user.id)
        is_over_limit = not user.is_premium and user.memories_count >= settings.free_memories_limit

    if pending:
        await _handle_clarification_answer(message, state, raw_transcript, pending)
        return

    if is_over_limit:
        await message.answer(
            f"В бесплатной версии доступно {settings.free_memories_limit} воспоминаний.\n"
            "Оформите подписку «Моя книга», чтобы продолжить. ⭐",
            reply_markup=main_menu_kb(),
        )
        return

    data = await state.get_data()
    source_question_id = data.get("answering_question_id")

    await _process_and_preview(
        message, raw_transcript,
        audio_file_id=message.voice.file_id,
        source_question_id=source_question_id,
        state=state,
    )


# ── Text-as-memory handler (explicit text mode) ──

@router.message(F.text, MemoryStates.waiting_text_memory)
async def handle_text_memory(message: Message, state: FSMContext) -> None:
    """User explicitly chose to write a memory as text."""
    text = message.text.strip()

    # Check pending clarification FIRST — short answers are valid
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        pending = await repo.get_pending_clarification_memory(user.id)
        is_over_limit = not user.is_premium and user.memories_count >= settings.free_memories_limit

    if pending:
        await state.clear()
        if len(text) < 2:
            await message.answer("Напишите хотя бы пару слов.")
            return
        await _handle_clarification_answer(message, state, text, pending)
        return

    if len(text) < 20:
        await message.answer("Расскажите чуть подробнее — хотя бы пару предложений.")
        return

    if is_over_limit:
        await message.answer(
            f"В бесплатной версии доступно {settings.free_memories_limit} воспоминаний.\n"
            "Оформите подписку «Моя книга», чтобы продолжить. ⭐",
            reply_markup=main_menu_kb(),
        )
        return

    data = await state.get_data()
    source_question_id = data.get("answering_question_id")
    await state.clear()

    await _process_and_preview(
        message, text,
        source_question_id=source_question_id,
    )


# ── Edit text flow ──

@router.message(F.text, MemoryStates.waiting_edit_text)
async def handle_edit_text(message: Message, state: FSMContext) -> None:
    """User sends corrected text for an existing memory."""
    data = await state.get_data()
    memory_id = data.get("editing_memory_id")
    await state.clear()

    if not memory_id:
        await message.answer("Не удалось определить, какое воспоминание редактируем.")
        return

    new_text = message.text.strip()
    if len(new_text) < 10:
        await message.answer("Текст слишком короткий.")
        return

    async with async_session() as session:
        repo = Repository(session)
        await repo.update_memory_text(memory_id, new_text)
        memory = await repo.get_memory(memory_id)
        already_saved = memory and memory.approved

    from bot.keyboards.inline_memory import saved_memory_kb
    preview = new_text[:800] + ("…" if len(new_text) > 800 else "")
    if already_saved:
        await message.answer(
            f"✅ Текст обновлён!\n\n{preview}",
            reply_markup=saved_memory_kb(memory_id),
        )
    else:
        await message.answer(
            f"✅ Текст обновлён! Сохранить в книгу?\n\n{preview}",
            reply_markup=memory_preview_kb(memory_id),
        )


# ── Button: record prompt ──

@router.message(F.text == "🎙 Записать воспоминание")
async def prompt_record(message: Message, state: FSMContext) -> None:
    await state.set_state(MemoryStates.waiting_text_memory)
    await message.answer(
        "Отправьте голосовое сообщение или напишите текстом — "
        "расскажите что-нибудь из жизни.\n\n"
        "Говорите как вам удобно, я отредактирую для книги.",
    )


# ── Helpers ──

async def _refresh_style_profile(user_id: int, memory_text: str) -> None:
    try:
        async with async_session() as session:
            repo = Repository(session)
            existing = await repo.get_style_notes(user_id)
            updated = await update_style_profile(existing, memory_text)
            if updated:
                await repo.update_style_notes(user_id, updated)
    except Exception as e:
        logger.error("Style profile update error: %s", e)


async def _refresh_characters(user_id: int, memory_text: str) -> None:
    try:
        async with async_session() as session:
            repo = Repository(session)
            existing = await repo.get_characters(user_id)
            existing_dicts = [
                {
                    "name": c.name,
                    "relationship": c.relation_to_author,
                    "description": c.description,
                }
                for c in existing
            ]
            extracted = await extract_characters(memory_text, existing_dicts)
            for char in extracted:
                name = char.get("name", "").strip()
                if name:
                    await repo.upsert_character(
                        user_id=user_id,
                        name=name,
                        relationship=char.get("relationship"),
                        description=char.get("description"),
                        aliases=char.get("aliases", []),
                    )
    except Exception as e:
        logger.error("Character extraction error: %s", e)


async def _refresh_thread_summary(chapter_id: int, chapter_title: str, memory_text: str) -> None:
    try:
        async with async_session() as session:
            repo = Repository(session)
            existing = await repo.get_thread_summary(chapter_id)
            updated = await refresh_thread_summary(chapter_title, existing, memory_text)
            if updated:
                await repo.update_thread_summary(chapter_id, updated)
    except Exception as e:
        logger.error("Thread summary update error: %s", e)


# ── Inline callbacks for memory actions ──

async def _do_save_memory(callback: CallbackQuery, memory_id: int, use_fantasy: bool = False) -> None:
    """Shared save logic for both strict and fantasy versions."""
    async with async_session() as session:
        repo = Repository(session)
        if use_fantasy:
            await repo.set_primary_text_to_fantasy(memory_id)
        memory = await repo.get_memory(memory_id)
        if not memory:
            await callback.answer("Воспоминание не найдено")
            return

        user = await repo.get_user(callback.from_user.id)
        chapters = await repo.get_chapters(user.id)
        suggestion = memory.chapter_suggestion

        # Find or create the suggested chapter
        target_chapter = None
        if suggestion:
            target_chapter = next((ch for ch in chapters if ch.title == suggestion), None)
            if not target_chapter:
                target_chapter = await repo.create_chapter(user.id, suggestion)

        if target_chapter:
            await repo.approve_memory(memory_id, target_chapter.id)
            new_count = await repo.increment_memories_count(user.id)
            await repo.update_topic_coverage(user.id, memory.tags or [])
            from bot.keyboards.inline_memory import saved_memory_kb
            await callback.message.edit_text(
                f"{callback.message.text}\n\n"
                f"✅ Сохранено в главу «{target_chapter.title}»\n"
                f"📊 Всего воспоминаний: {new_count}",
                reply_markup=saved_memory_kb(memory_id),
            )
            text = memory.edited_memoir_text or ""
            asyncio.create_task(_refresh_style_profile(user.id, text))
            asyncio.create_task(_refresh_characters(user.id, text))
            asyncio.create_task(_refresh_thread_summary(target_chapter.id, target_chapter.title, text))
        elif not chapters:
            chapter = await repo.create_chapter(user.id, "Разное")
            await repo.approve_memory(memory_id, chapter.id)
            new_count = await repo.increment_memories_count(user.id)
            await repo.update_topic_coverage(user.id, memory.tags or [])
            from bot.keyboards.inline_memory import saved_memory_kb
            await callback.message.edit_text(
                f"{callback.message.text}\n\n"
                f"✅ Сохранено в главу «{chapter.title}»\n"
                f"📊 Всего воспоминаний: {new_count}",
                reply_markup=saved_memory_kb(memory_id),
            )
            text = memory.edited_memoir_text or ""
            asyncio.create_task(_refresh_style_profile(user.id, text))
            asyncio.create_task(_refresh_characters(user.id, text))
            asyncio.create_task(_refresh_thread_summary(chapter.id, chapter.title, text))
        else:
            chapters_dicts = [{"id": ch.id, "title": ch.title} for ch in chapters]
            await callback.message.edit_reply_markup(
                reply_markup=chapter_select_kb(chapters_dicts, memory_id),
            )

    await callback.answer()


@router.callback_query(F.data.startswith("mem_save:"))
async def cb_save_memory(callback: CallbackQuery) -> None:
    memory_id = int(callback.data.split(":")[1])
    await _do_save_memory(callback, memory_id, use_fantasy=False)


@router.callback_query(F.data.startswith("mem_save_fantasy:"))
async def cb_save_fantasy_memory(callback: CallbackQuery) -> None:
    memory_id = int(callback.data.split(":")[1])
    await _do_save_memory(callback, memory_id, use_fantasy=True)


@router.callback_query(F.data.startswith("mem_to_ch:"))
async def cb_move_to_chapter(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    memory_id = int(parts[1])
    chapter_id = int(parts[2])

    async with async_session() as session:
        repo = Repository(session)
        await repo.approve_memory(memory_id, chapter_id)
        user = await repo.get_user(callback.from_user.id)
        new_count = await repo.increment_memories_count(user.id)
        memory = await repo.get_memory(memory_id)
        chapter = await repo.get_chapter(chapter_id)
        await repo.update_topic_coverage(user.id, memory.tags or [])

    text = memory.edited_memoir_text or ""
    asyncio.create_task(_refresh_style_profile(user.id, text))
    asyncio.create_task(_refresh_characters(user.id, text))
    asyncio.create_task(_refresh_thread_summary(chapter_id, chapter.title, text))

    from bot.keyboards.inline_memory import saved_memory_kb
    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"✅ Сохранено в главу «{chapter.title}»\n"
        f"📊 Всего воспоминаний: {new_count}",
        reply_markup=saved_memory_kb(memory_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_new_ch:"))
async def cb_new_chapter_for_memory(callback: CallbackQuery, state: FSMContext) -> None:
    memory_id = int(callback.data.split(":")[1])
    await state.set_state(MemoryStates.waiting_new_chapter)
    await state.update_data(
        new_chapter_memory_id=memory_id,
        preview_message_id=callback.message.message_id,
        preview_chat_id=callback.message.chat.id,
    )
    await callback.message.answer("Напишите название новой главы:")
    await callback.answer()


@router.callback_query(F.data.startswith("mem_redo:"))
async def cb_redo_memory(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Отправьте новое голосовое сообщение — я заменю предыдущее. 🎙"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_edit:"))
async def cb_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    memory_id = int(callback.data.split(":")[1])
    await state.update_data(editing_memory_id=memory_id)
    await state.set_state(MemoryStates.waiting_edit_text)
    await callback.message.answer(
        "Отправьте исправленный текст — я заменю текущую версию.\n"
        "Текущий текст можно скопировать из сообщения выше."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_move:"))
async def cb_move_memory(callback: CallbackQuery) -> None:
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(callback.from_user.id)
        chapters = await repo.get_chapters(user.id)
        chapters_dicts = [{"id": ch.id, "title": ch.title} for ch in chapters]

    await callback.message.edit_reply_markup(
        reply_markup=chapter_select_kb(chapters_dicts, memory_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_split:"))
async def cb_split_memory(callback: CallbackQuery) -> None:
    await callback.answer("Разбиение на истории — скоро будет доступно!", show_alert=True)


@router.callback_query(F.data.startswith("skip_clarif:"))
async def cb_skip_clarification(callback: CallbackQuery, state: FSMContext) -> None:
    """User chose 'without clarification' — run editor immediately on original transcript."""
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory:
            await callback.answer("Воспоминание не найдено", show_alert=True)
            return
        await repo.clear_clarification_state(memory_id)
        user = await repo.get_user(callback.from_user.id)
        user_id = user.id

    await callback.message.edit_text("⏳ Редактирую для книги…")
    await callback.answer()

    ctx = await _fetch_user_context(user_id)
    await _run_editor_and_preview(
        callback.message,
        callback.message,
        memory_id,
        memory.cleaned_transcript or "",
        [],
        memory.source_question_id,
        state,
        ctx,
        user_telegram_id=callback.from_user.id,
    )


@router.callback_query(F.data.startswith("other_clarif:"))
async def cb_other_clarification(callback: CallbackQuery, state: FSMContext) -> None:
    """User wants a different clarification question — mark current as skipped and ask again."""
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory:
            await callback.answer("Воспоминание не найдено", show_alert=True)
            return
        user = await repo.get_user(callback.from_user.id)
        user_id = user.id

    thread = json.loads(memory.clarification_thread or "[]")
    cleaned = memory.cleaned_transcript or ""

    # Mark the last question as skipped so clarifier won't repeat it
    if thread and thread[-1]["role"] == "question":
        thread[-1]["role"] = "skipped"

    await callback.answer()
    processing_msg = await callback.message.edit_text("⏳ Думаю…")

    clarification = await ask_clarification(cleaned, thread)

    if not clarification.get("is_complete"):
        question = clarification["question"]
        thread.append({"role": "question", "text": question})
        async with async_session() as session:
            repo = Repository(session)
            await repo.set_clarification_state(memory_id, thread, memory.clarification_round)
        await processing_msg.edit_text(f"💬 {question}", reply_markup=_clarification_kb(memory_id))
    else:
        # No more questions — go to editor
        await processing_msg.edit_text("⏳ Редактирую для книги…")
        ctx = await _fetch_user_context(user_id)
        qa_answers = [e for e in thread if e["role"] == "answer"]
        await _run_editor_and_preview(
            callback.message, processing_msg, memory_id, cleaned,
            qa_answers, memory.source_question_id, state, ctx,
            user_telegram_id=callback.from_user.id,
        )


# ── Fantasy / strict version toggle ──

@router.callback_query(F.data.startswith("show_strict:"))
async def cb_show_strict_version(callback: CallbackQuery) -> None:
    """Switch the preview to the strict (accurate) version."""
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)

    if not memory or not memory.edited_memoir_text:
        await callback.answer("Точная версия недоступна", show_alert=True)
        return

    title = memory.title or "Воспоминание"
    chapter_line = f"\n📁 Предлагаю главу: <b>{memory.chapter_suggestion}</b>" if memory.chapter_suggestion else ""
    strict_text = memory.edited_memoir_text
    preview = strict_text[:1500] + ("…" if len(strict_text) > 1500 else "")

    await callback.message.edit_text(
        f"<b>{title}</b>{chapter_line}\n\n{preview}",
        reply_markup=memory_preview_kb(memory_id, has_fantasy=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("show_fantasy:"))
async def cb_show_fantasy_version(callback: CallbackQuery) -> None:
    """Switch the preview to the fantasy (creative) version."""
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)

    if not memory or not memory.fantasy_memoir_text:
        await callback.answer("Творческая версия недоступна", show_alert=True)
        return

    title = memory.title or "Воспоминание"
    chapter_line = f"\n📁 Предлагаю главу: <b>{memory.chapter_suggestion}</b>" if memory.chapter_suggestion else ""
    fantasy_text = memory.fantasy_memoir_text
    preview = fantasy_text[:1200] + ("…" if len(fantasy_text) > 1200 else "")
    hint = "\n\n✨ <i>Это творческая версия — редактор добавил детали от себя.</i>\n<i>Если вдохновила — можете перезаписать воспоминание 🎙</i>"

    await callback.message.edit_text(
        f"<b>{title}</b>{chapter_line}\n\n{preview}{hint}",
        reply_markup=memory_fantasy_kb(memory_id),
    )
    await callback.answer()


# ── New chapter name input ──

@router.message(F.text, MemoryStates.waiting_new_chapter)
async def handle_new_chapter_name(message: Message, state: FSMContext) -> None:
    """User typed a new chapter title — create chapter and save the memory."""
    data = await state.get_data()
    memory_id = data.get("new_chapter_memory_id")
    await state.clear()

    if not memory_id:
        await message.answer("Не удалось определить воспоминание. Попробуйте снова.")
        return

    chapter_title = message.text.strip()
    if len(chapter_title) < 2:
        await message.answer("Название главы слишком короткое.")
        return

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        if not user:
            await message.answer("Пользователь не найден.")
            return
        chapter = await repo.create_chapter(user.id, chapter_title)
        await repo.approve_memory(memory_id, chapter.id)
        new_count = await repo.increment_memories_count(user.id)
        memory = await repo.get_memory(memory_id)
        if memory:
            await repo.update_topic_coverage(user.id, memory.tags or [])
            mem_text = memory.edited_memoir_text or ""
        else:
            mem_text = ""

    asyncio.create_task(_refresh_style_profile(user.id, mem_text))
    asyncio.create_task(_refresh_characters(user.id, mem_text))
    asyncio.create_task(_refresh_thread_summary(chapter.id, chapter_title, mem_text))

    # Switch the original preview message to saved state (remove action buttons)
    preview_message_id = data.get("preview_message_id")
    preview_chat_id = data.get("preview_chat_id")
    if preview_message_id and preview_chat_id:
        from bot.keyboards.inline_memory import saved_memory_kb
        try:
            await bot.edit_message_reply_markup(
                chat_id=preview_chat_id,
                message_id=preview_message_id,
                reply_markup=saved_memory_kb(memory_id),
            )
        except Exception:
            pass  # Message too old or already edited

    await message.answer(
        f"✅ Создана глава «{chapter_title}» и воспоминание сохранено!\n"
        f"📊 Всего воспоминаний: {new_count}"
    )


# ── Back button from chapter select ──

@router.callback_query(F.data.startswith("mem_back:"))
async def cb_mem_back(callback: CallbackQuery) -> None:
    """Restore the original memory keyboard (saved or unsaved)."""
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)

    if not memory:
        await callback.answer("Воспоминание не найдено")
        return

    from bot.keyboards.inline_memory import saved_memory_kb
    if memory.approved:
        await callback.message.edit_reply_markup(reply_markup=saved_memory_kb(memory_id))
    else:
        await callback.message.edit_reply_markup(
            reply_markup=memory_preview_kb(memory_id, has_fantasy=bool(memory.fantasy_memoir_text))
        )
    await callback.answer()


# ── Catch-all: plain text treated as a memory or clarification answer ──

@router.message(F.text)
async def catch_all_text(message: Message, state: FSMContext) -> None:
    """Any unrecognized text: first check for pending clarification, then process as new memory."""
    text = message.text.strip()

    # Check pending clarification FIRST — short answers are valid for clarification
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        pending = await repo.get_pending_clarification_memory(user.id)
        is_over_limit = not user.is_premium and user.memories_count >= settings.free_memories_limit

    if pending:
        if len(text) < 2:
            await message.answer("Напишите хотя бы пару слов.")
            return
        await _handle_clarification_answer(message, state, text, pending)
        return

    # For new memories — require at least a couple of sentences
    if len(text) < 20:
        await message.answer(
            "Расскажите чуть подробнее — хотя бы пару предложений. "
            "Или нажмите «🎙 Записать воспоминание» в меню."
        )
        return

    if is_over_limit:
        await message.answer(
            f"В бесплатной версии доступно {settings.free_memories_limit} воспоминаний.\n"
            "Оформите подписку «Моя книга», чтобы продолжить. ⭐",
            reply_markup=main_menu_kb(),
        )
        return

    data = await state.get_data()
    source_question_id = data.get("answering_question_id")

    await _process_and_preview(
        message, text,
        source_question_id=source_question_id,
        state=state,
    )
