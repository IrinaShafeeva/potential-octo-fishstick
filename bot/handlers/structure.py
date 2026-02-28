import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.main_menu import main_menu_kb, MENU_BUTTONS

router = Router()
logger = logging.getLogger(__name__)


class ChapterStates(StatesGroup):
    waiting_title = State()
    waiting_rename = State()


@router.message(F.text == "🧩 Структура глав")
async def show_structure(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        if not user:
            await message.answer("Сначала нажмите /start")
            return

        chapters = await repo.get_chapters(user.id)

    if not chapters:
        text = (
            "У вас пока нет глав.\n\n"
            "Я могу создать их автоматически, когда вы начнёте рассказывать. "
            "Или создайте сами — напишите название первой главы.\n\n"
            "Примеры:\n"
            "• Детство\n"
            "• Школьные годы\n"
            "• Молодость и свадьба\n"
            "• Работа\n"
            "• Семья"
        )
    else:
        text = "📁 <b>Ваши главы:</b>\n\n"
        for i, ch in enumerate(chapters, 1):
            text += f"  {i}. <b>{ch.title}</b>"
            if ch.period_hint:
                text += f" — {ch.period_hint}"
            text += "\n"
        text += (
            "\nЧтобы добавить главу — просто напишите её название.\n"
            "Чтобы переименовать — отправьте: /rename Номер Новое название"
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text="➕ Добавить главу", callback_data="ch_add")]]
    if chapters:
        for ch in chapters:
            buttons.append([
                InlineKeyboardButton(text=f"✏️ {ch.title}", callback_data=f"ch_rename:{ch.id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"ch_del:{ch.id}"),
            ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "ch_add")
async def cb_add_chapter(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(callback.from_user.id)
        ch_count = await repo.count_chapters(user.id)

    if not (await _is_premium(callback.from_user.id)) and ch_count >= settings.free_chapters_limit:
        await callback.message.answer(
            f"В бесплатной версии доступна {settings.free_chapters_limit} глава.\n"
            "Оформите подписку, чтобы добавить больше. ⭐"
        )
        await callback.answer()
        return

    await callback.message.answer("Напишите название новой главы:")
    await state.set_state(ChapterStates.waiting_title)
    await callback.answer()


@router.message(ChapterStates.waiting_title, F.text.func(lambda t: t not in MENU_BUTTONS))
async def receive_chapter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 200:
        await message.answer("Пожалуйста, введите название главы (до 200 символов).")
        return

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)
        chapter = await repo.create_chapter(user.id, title)

    await state.clear()
    await message.answer(
        f"✅ Глава «{chapter.title}» создана!",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data.startswith("ch_rename:"))
async def cb_rename_chapter(callback: CallbackQuery, state: FSMContext) -> None:
    chapter_id = int(callback.data.split(":")[1])
    await state.update_data(rename_chapter_id=chapter_id)
    await state.set_state(ChapterStates.waiting_rename)
    await callback.message.answer("Введите новое название главы:")
    await callback.answer()


@router.message(ChapterStates.waiting_rename, F.text.func(lambda t: t not in MENU_BUTTONS))
async def receive_rename(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chapter_id = data.get("rename_chapter_id")
    title = message.text.strip()

    if not title or len(title) > 200:
        await message.answer("Пожалуйста, введите название (до 200 символов).")
        return

    async with async_session() as session:
        repo = Repository(session)
        await repo.rename_chapter(chapter_id, title)

    await state.clear()
    await message.answer(f"✅ Глава переименована в «{title}»", reply_markup=main_menu_kb())


@router.callback_query(F.data.startswith("ch_del:"))
async def cb_delete_chapter(callback: CallbackQuery) -> None:
    chapter_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        chapter = await repo.get_chapter(chapter_id)
        title = chapter.title if chapter else "?"
        await repo.delete_chapter(chapter_id)

    await callback.message.answer(
        f"🗑 Глава «{title}» удалена. Воспоминания из неё остались без главы.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


async def _is_premium(telegram_id: int) -> bool:
    async with async_session() as session:
        repo = Repository(session)
        return await repo.is_premium(telegram_id)
