import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_memory import saved_memory_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.services.export import export_book_pdf

router = Router()
logger = logging.getLogger(__name__)


def _progress_bar(filled: int, total: int, length: int = 10) -> str:
    if total == 0:
        return "░" * length
    ratio = min(filled / total, 1.0)
    filled_blocks = int(ratio * length)
    return "▓" * filled_blocks + "░" * (length - filled_blocks)


@router.message(F.text == "Моя книга")
async def show_book(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        if not user:
            await message.answer("Сначала нажмите /start")
            return

        progress = await repo.get_book_progress(user.id)
        chapters = await repo.get_chapters(user.id)

    mem_count = progress["memories_count"]
    ch_total = progress["chapters_total"]
    ch_filled = progress["chapters_filled"]
    pages = progress["estimated_pages"]

    bar = _progress_bar(mem_count, max(mem_count, 20))
    percent = min(100, int(mem_count / max(20, 1) * 100))

    text = (
        f"<b>Ваша книга</b>\n\n"
        f"📝 Воспоминаний: {mem_count}\n"
        f"📁 Глав: {ch_total} (заполнены: {ch_filled})\n"
        f"📄 Примерно страниц: {pages}\n\n"
        f"{bar} {percent}%\n"
    )

    if chapters:
        text += "\n<b>Главы:</b>\n"
        for i, ch in enumerate(chapters, 1):
            text += f"  {i}. {ch.title}"
            if ch.period_hint:
                text += f" <i>({ch.period_hint})</i>"
            text += "\n"
        text += "\nНажмите на номер главы, чтобы посмотреть содержимое."

    if not chapters:
        text += "\nУ вас пока нет глав. Нажмите «Структура глав», чтобы создать."

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for ch in chapters:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {ch.title}", callback_data=f"book_ch:{ch.id}")
        ])
    if mem_count > 0 and user.is_premium:
        buttons.append([
            InlineKeyboardButton(text="📥 Скачать PDF", callback_data="book_pdf")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("book_ch:"))
async def cb_show_chapter(callback: CallbackQuery) -> None:
    chapter_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        chapter = await repo.get_chapter(chapter_id)
        if not chapter:
            await callback.answer("Глава не найдена")
            return

        memories = await repo.get_memories_by_chapter(chapter_id)

    if not memories:
        await callback.message.answer(f"📁 <b>{chapter.title}</b>\n\nПока пусто.")
        await callback.answer()
        return

    await callback.message.answer(f"📁 <b>{chapter.title}</b> — {len(memories)} воспоминаний:")
    for i, mem in enumerate(memories, 1):
        title = mem.title or "Без названия"
        full_text = mem.edited_memoir_text or ""
        preview = full_text[:800] + ("…" if len(full_text) > 800 else "")
        msg = f"<b>{i}. {title}</b>\n\n{preview}"
        await callback.message.answer(msg, reply_markup=saved_memory_kb(mem.id))

    await callback.answer()


@router.callback_query(F.data == "book_pdf")
async def cb_export_pdf(callback: CallbackQuery) -> None:
    await callback.answer("Генерирую PDF…")

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(callback.from_user.id)
        if not user:
            return

        if not user.is_premium:
            await callback.message.answer(
                "Экспорт в PDF доступен только в подписке «Моя книга»."
            )
            return

        author_name = user.first_name or "Автор"
        user_db_id = user.id
        chapters = await repo.get_chapters(user_db_id)
        chapters_data = []
        for ch in chapters:
            memories = await repo.get_memories_by_chapter(ch.id)
            if memories:
                chapters_data.append({
                    "title": ch.title,
                    "period_hint": ch.period_hint or "",
                    "memories": [
                        {
                            "title": m.title or "",
                            "text": m.edited_memoir_text or m.cleaned_transcript or "",
                        }
                        for m in memories
                    ],
                })

    if not chapters_data:
        await callback.message.answer("В книге пока нет воспоминаний.")
        return

    processing_msg = await callback.message.answer("⏳ Генерирую PDF…")

    pdf_bytes = await export_book_pdf(
        chapters_data,
        author_name=author_name,
        user_id=user_db_id,
    )

    if pdf_bytes:
        try:
            await processing_msg.delete()
        except Exception:
            pass
        doc = BufferedInputFile(pdf_bytes, filename="Моя_книга_воспоминаний.pdf")
        await callback.message.answer_document(doc, caption="Ваша книга воспоминаний")
    else:
        await processing_msg.edit_text("Не удалось создать PDF. Попробуйте позже.")
