import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_memory import memory_preview_kb, chapter_select_kb, confirm_save_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.loader import bot
from bot.services.stt import transcribe_voice
from bot.services.ai_editor import clean_transcript, edit_memoir
from bot.services.timeline import extract_timeline
from bot.services.classifier import classify_chapter

router = Router()
logger = logging.getLogger(__name__)

MIN_VOICE_DURATION = 3
STT_CONFIDENCE_THRESHOLD = 0.3


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
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

    processing_msg = await message.answer("⏳ Обрабатываю запись…")

    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    audio_bytes = file_bytes.read()

    stt_result = await transcribe_voice(audio_bytes)
    raw_transcript = stt_result["text"]
    confidence = stt_result["confidence"]

    if not raw_transcript or confidence < STT_CONFIDENCE_THRESHOLD:
        await processing_msg.edit_text(
            "Не удалось разобрать запись. Попробуйте записать ещё раз в тихом месте."
        )
        return

    await processing_msg.edit_text("⏳ Очищаю текст…")
    cleaned = await clean_transcript(raw_transcript)

    await processing_msg.edit_text("⏳ Редактирую для книги…")

    async with async_session() as session:
        repo = Repository(session)
        known_people = await repo.get_known_people(
            (await repo.get_user(message.from_user.id)).id
        )
        known_places = await repo.get_known_places(
            (await repo.get_user(message.from_user.id)).id
        )

    edited = await edit_memoir(cleaned, known_people, known_places)
    time_hint = await extract_timeline(edited.get("edited_memoir_text", cleaned))

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        chapters = await repo.get_chapters(user.id)

        chapter_suggestion = None
        if chapters:
            chapters_dicts = [
                {"title": ch.title, "period_hint": ch.period_hint or ""}
                for ch in chapters
            ]
            classification = await classify_chapter(
                edited.get("edited_memoir_text", cleaned),
                {"type": time_hint.get("type", "unknown"), "value": time_hint.get("value", "")},
                chapters_dicts,
            )
            chapter_suggestion = classification.get("chapter_suggestion")

        memory = await repo.create_memory(
            user_id=user.id,
            audio_file_id=message.voice.file_id,
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
        )

    title = edited.get("title", "Воспоминание")
    memoir_text = edited.get("edited_memoir_text", cleaned)
    preview = memoir_text[:1500] + ("…" if len(memoir_text) > 1500 else "")

    chapter_line = ""
    if chapter_suggestion:
        chapter_line = f"\n📁 Предлагаю главу: <b>{chapter_suggestion}</b>"

    clarification = ""
    if edited.get("needs_clarification") and edited.get("clarification_question"):
        clarification = f"\n\n💬 {edited['clarification_question']}"

    await processing_msg.edit_text(
        f"<b>{title}</b>{chapter_line}\n\n{preview}{clarification}",
        reply_markup=memory_preview_kb(memory.id),
    )


@router.message(F.text == "🎙 Записать воспоминание")
async def prompt_record(message: Message) -> None:
    await message.answer(
        "Отправьте голосовое сообщение — расскажите что-нибудь из жизни.\n\n"
        "Говорите как вам удобно, я отредактирую для книги.",
    )


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

    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"✅ Сохранено в главу «{chapter.title}»\n"
        f"📊 Всего воспоминаний: {new_count}",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_new_ch:"))
async def cb_new_chapter_for_memory(callback: CallbackQuery) -> None:
    memory_id = callback.data.split(":")[1]
    await callback.message.answer(
        "Напишите название новой главы:",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mem_redo:"))
async def cb_redo_memory(callback: CallbackQuery) -> None:
    await callback.message.answer("Отправьте новое голосовое сообщение — я заменю предыдущее.")
    await callback.answer()


@router.callback_query(F.data.startswith("mem_edit:"))
async def cb_edit_text(callback: CallbackQuery) -> None:
    memory_id = int(callback.data.split(":")[1])
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
    memory_id = int(callback.data.split(":")[1])
    await callback.answer("Разбиение на истории — скоро будет доступно!", show_alert=True)
