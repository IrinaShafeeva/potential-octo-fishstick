import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_memory import memory_preview_kb, chapter_select_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.loader import bot
from bot.services.stt import transcribe_voice
from bot.services.ai_editor import clean_transcript, edit_memoir, merge_clarification
from bot.services.timeline import extract_timeline
from bot.services.classifier import classify_chapter
from bot.services.style_profiler import update_style_profile
from bot.services.character_extractor import extract_characters
from bot.services.thread_summarizer import refresh_thread_summary

router = Router()
logger = logging.getLogger(__name__)

MIN_VOICE_DURATION = 3
STT_CONFIDENCE_THRESHOLD = 0.3


class MemoryStates(StatesGroup):
    waiting_edit_text = State()
    waiting_text_memory = State()
    waiting_clarification = State()
    waiting_new_chapter = State()


async def _process_and_preview(
    message: Message,
    raw_transcript: str,
    audio_file_id: str | None = None,
    source_question_id: str | None = None,
    state: FSMContext | None = None,
) -> None:
    """Shared pipeline: clean → classify → edit (with thread_summary) → preview."""
    processing_msg = await message.answer("⏳ Обрабатываю текст…")

    cleaned = await clean_transcript(raw_transcript)
    await processing_msg.edit_text("⏳ Редактирую для книги…")

    # Fetch author context + chapters in one session
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        known_characters = await repo.get_characters(user.id)
        known_places = await repo.get_places_with_counts(user.id)
        style_notes = await repo.get_style_notes(user.id)
        chapters = await repo.get_chapters(user.id)

    # Classify on cleaned text first — needed to fetch chapter thread_summary for editing
    chapter_suggestion = None
    thread_summary = None
    if chapters:
        chapters_dicts = [
            {"title": ch.title, "period_hint": ch.period_hint or ""}
            for ch in chapters
        ]
        classification = await classify_chapter(
            cleaned,
            {"type": "unknown", "value": ""},
            chapters_dicts,
        )
        chapter_suggestion = classification.get("chapter_suggestion")
        if chapter_suggestion:
            for ch in chapters:
                if ch.title == chapter_suggestion:
                    thread_summary = ch.thread_summary
                    break

    edited = await edit_memoir(cleaned, known_characters, known_places, style_notes, thread_summary)
    time_hint = await extract_timeline(edited.get("edited_memoir_text", cleaned))

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)

        memory = await repo.create_memory(
            user_id=user.id,
            audio_file_id=audio_file_id,
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned,
            edited_memoir_text=edited.get("edited_memoir_text", cleaned),
            title=edited.get("title", ""),
            time_hint_type=time_hint.get("type"),
            time_hint_value=time_hint.get("value"),
            time_confidence=time_hint.get("confidence"),
            tags=edited.get("tags", []),
            people=edited.get("people", []),
            places=edited.get("places", []),
            source_question_id=source_question_id,
        )

    title = edited.get("title", "Воспоминание")
    memoir_text = edited.get("edited_memoir_text", cleaned)
    preview = memoir_text[:1500] + ("…" if len(memoir_text) > 1500 else "")

    chapter_line = ""
    if chapter_suggestion:
        chapter_line = f"\n📁 Предлагаю главу: <b>{chapter_suggestion}</b>"

    has_clarification = edited.get("needs_clarification") and edited.get("clarification_question")

    if has_clarification:
        # Show preview without save buttons, then ask the clarification question
        await processing_msg.edit_text(
            f"<b>{title}</b>{chapter_line}\n\n{preview}"
        )
        await message.answer(
            f"💬 {edited['clarification_question']}\n\n"
            "Ответьте — я дополню воспоминание и предложу сохранить."
        )
        if state:
            await state.set_state(MemoryStates.waiting_clarification)
            await state.update_data(clarification_memory_id=memory.id)
    else:
        await processing_msg.edit_text(
            f"<b>{title}</b>{chapter_line}\n\n{preview}",
            reply_markup=memory_preview_kb(memory.id),
        )
        if state:
            data = await state.get_data()
            question_log_id = data.get("answering_question_log_id")
            if question_log_id:
                async with async_session() as session:
                    repo = Repository(session)
                    await repo.mark_question_answered(question_log_id, memory.id)
            await state.clear()


# ── Voice handler ──

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext) -> None:
    if message.voice.duration < MIN_VOICE_DURATION:
        await message.answer("Запись слишком короткая. Расскажите подробнее!")
        return

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        if not user.is_premium and user.memories_count >= settings.free_memories_limit:
            await message.answer(
                f"В бесплатной версии доступно {settings.free_memories_limit} воспоминаний.\n"
                "Оформите подписку «Моя книга», чтобы продолжить. ⭐",
                reply_markup=main_menu_kb(),
            )
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

    data = await state.get_data()
    source_question_id = data.get("answering_question_id")

    await _process_and_preview(
        message, raw_transcript,
        audio_file_id=message.voice.file_id,
        source_question_id=source_question_id,
        state=state,
    )


# ── Text-as-memory handler (catch-all for free text, lowest priority) ──

@router.message(F.text, MemoryStates.waiting_text_memory)
async def handle_text_memory(message: Message, state: FSMContext) -> None:
    """User explicitly chose to write a memory as text."""
    text = message.text.strip()
    if len(text) < 20:
        await message.answer("Расскажите чуть подробнее — хотя бы пару предложений.")
        return

    data = await state.get_data()
    source_question_id = data.get("answering_question_id")
    await state.clear()

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        if not user.is_premium and user.memories_count >= settings.free_memories_limit:
            await message.answer(
                f"В бесплатной версии доступно {settings.free_memories_limit} воспоминаний.\n"
                "Оформите подписку «Моя книга», чтобы продолжить. ⭐",
                reply_markup=main_menu_kb(),
            )
            return

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
    """Update the author's style profile in the background after a memory is approved."""
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
    """Extract characters from a new approved memory and upsert into character library."""
    try:
        async with async_session() as session:
            repo = Repository(session)
            existing = await repo.get_characters(user_id)
            existing_dicts = [
                {
                    "name": c.name,
                    "relationship": c.relationship,
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
    """Update the chapter's running thread summary after a memory is approved."""
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

@router.callback_query(F.data.startswith("mem_save:"))
async def cb_save_memory(callback: CallbackQuery) -> None:
    memory_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory:
            await callback.answer("Воспоминание не найдено")
            return

        user = await repo.get_user(callback.from_user.id)
        chapters = await repo.get_chapters(user.id)

        if not chapters:
            chapter = await repo.create_chapter(user.id, "Разное")
            chapters = [chapter]

        if len(chapters) == 1:
            await repo.approve_memory(memory_id, chapters[0].id)
            new_count = await repo.increment_memories_count(user.id)
            await repo.update_topic_coverage(user.id, memory.tags or [])
            await callback.message.edit_text(
                f"{callback.message.text}\n\n"
                f"✅ Сохранено в главу «{chapters[0].title}»\n"
                f"📊 Всего воспоминаний: {new_count}",
            )
            text = memory.edited_memoir_text or ""
            asyncio.create_task(_refresh_style_profile(user.id, text))
            asyncio.create_task(_refresh_characters(user.id, text))
            asyncio.create_task(_refresh_thread_summary(chapters[0].id, chapters[0].title, text))
        else:
            chapters_dicts = [{"id": ch.id, "title": ch.title} for ch in chapters]
            await callback.message.edit_reply_markup(
                reply_markup=chapter_select_kb(chapters_dicts, memory_id),
            )

    await callback.answer()


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

    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"✅ Сохранено в главу «{chapter.title}»\n"
        f"📊 Всего воспоминаний: {new_count}",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_new_ch:"))
async def cb_new_chapter_for_memory(callback: CallbackQuery, state: FSMContext) -> None:
    memory_id = int(callback.data.split(":")[1])
    await state.set_state(MemoryStates.waiting_new_chapter)
    await state.update_data(new_chapter_memory_id=memory_id)
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


# ── Clarification answer ──

@router.message(F.text, MemoryStates.waiting_clarification)
async def handle_clarification(message: Message, state: FSMContext) -> None:
    """User answered the clarification question — append to memory and show save buttons."""
    data = await state.get_data()
    memory_id = data.get("clarification_memory_id")
    await state.clear()

    if not memory_id:
        await message.answer("Не удалось найти воспоминание. Попробуйте записать заново.")
        return

    addition = message.text.strip()
    if len(addition) < 5:
        await message.answer(
            "Слишком коротко. Расскажите чуть подробнее.",
            reply_markup=memory_preview_kb(memory_id),
        )
        return

    merging_msg = await message.answer("⏳ Встраиваю уточнение в текст…")

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory:
            await merging_msg.edit_text("Воспоминание не найдено.")
            return
        merged = await merge_clarification(
            memory.edited_memoir_text or "", addition
        )
        await repo.update_memory_text(memory_id, merged)

    preview = merged[:1500] + ("…" if len(merged) > 1500 else "")
    await merging_msg.edit_text(
        f"✅ Готово! Вот обновлённый текст:\n\n{preview}\n\nСохранить?",
        reply_markup=memory_preview_kb(memory_id),
    )


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
        await callback.message.edit_reply_markup(reply_markup=memory_preview_kb(memory_id))
    await callback.answer()


# ── Catch-all: plain text treated as a memory (lowest priority) ──

@router.message(F.text)
async def catch_all_text(message: Message, state: FSMContext) -> None:
    """Any unrecognized text ≥20 chars is processed as a memory entry."""
    text = message.text.strip()
    if len(text) < 20:
        await message.answer(
            "Расскажите чуть подробнее — хотя бы пару предложений. "
            "Или нажмите «🎙 Записать воспоминание» в меню."
        )
        return

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        if not user.is_premium and user.memories_count >= settings.free_memories_limit:
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
