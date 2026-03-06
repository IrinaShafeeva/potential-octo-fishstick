import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_question import pack_select_kb, question_actions_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.services.question_router import pick_next_question
from bot.handlers.voice import MemoryStates

router = Router()
logger = logging.getLogger(__name__)


async def _send_question(
    message_or_callback,
    telegram_id: int,
    state: FSMContext,
    selected_pack: str | None = None,
    should_edit: bool = False,
) -> None:
    """Pick a question and send it to the user.

    If should_edit=True and called from a CallbackQuery, edits the existing
    message in-place instead of sending a new one.
    """
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(telegram_id)

        if not user.is_premium and user.questions_asked_count >= settings.free_questions_limit:
            text = (
                f"В бесплатной версии доступно {settings.free_questions_limit} вопроса.\n"
                "Оформите подписку «Моя книга», чтобы открыть все вопросы."
            )
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.answer(text, reply_markup=main_menu_kb())
            else:
                await message_or_callback.answer(text, reply_markup=main_menu_kb())
            return

        all_questions = await repo.get_all_questions()
        asked_ids = await repo.get_asked_question_ids(user.id)
        topic_coverage = await repo.get_topic_coverage(user.id)

        last_log = await repo.get_last_question_log(user.id)
        last_tags = []
        if last_log:
            q = await repo.get_question(last_log.question_id)
            if q:
                last_tags = q.tags or []

        pack = selected_pack if selected_pack != "any" else None
        question = pick_next_question(
            all_questions, asked_ids, topic_coverage, pack, last_tags
        )

        if not question:
            text = "Вы ответили на все вопросы! Отличная работа 🎉"
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.answer(text)
            else:
                await message_or_callback.answer(text)
            return

        log = await repo.log_question(user.id, question.id)

        from sqlalchemy import update as sql_update
        from bot.db.models import User
        await session.execute(
            sql_update(User)
            .where(User.id == user.id)
            .values(questions_asked_count=User.questions_asked_count + 1)
        )
        await session.commit()

    await state.update_data(
        answering_question_log_id=log.id,
        answering_question_id=question.id,
    )

    text = f"💭 <b>{question.text}</b>"

    if isinstance(message_or_callback, CallbackQuery) and should_edit:
        try:
            await message_or_callback.message.edit_text(
                text, reply_markup=question_actions_kb(log.id)
            )
            return
        except Exception:
            pass  # fall through to answer() if edit fails (e.g. message too old)

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(
            text, reply_markup=question_actions_kb(log.id)
        )
    else:
        await message_or_callback.answer(
            text, reply_markup=question_actions_kb(log.id)
        )


@router.message(F.text == "🧠 Вспомнить вместе")
@router.message(F.text == "🧠 Помочь вопросами")
async def questions_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите тему, о которой хотите вспомнить:",
        reply_markup=pack_select_kb(),
    )


@router.callback_query(F.data.startswith("pack:"))
async def cb_select_pack(callback: CallbackQuery, state: FSMContext) -> None:
    pack = callback.data.split(":")[1]
    await state.update_data(current_pack=pack)
    await callback.answer()
    await _send_question(callback, callback.from_user.id, state, selected_pack=pack, should_edit=True)


@router.callback_query(F.data.startswith("q_next:"))
async def cb_next_question(callback: CallbackQuery, state: FSMContext) -> None:
    log_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        await repo.mark_question_skipped(log_id)

    data = await state.get_data()
    current_pack = data.get("current_pack")

    await callback.answer()
    await _send_question(callback, callback.from_user.id, state, selected_pack=current_pack, should_edit=True)


@router.callback_query(F.data.startswith("q_pause:"))
async def cb_pause_questions(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(
        "Хорошо, отдохните. Когда захотите продолжить — нажмите «Вспомнить вместе».",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("q_voice:"))
async def cb_answer_voice(callback: CallbackQuery, state: FSMContext) -> None:
    log_id = int(callback.data.split(":")[1])
    await state.update_data(answering_question_log_id=log_id)
    await callback.message.answer(
        "Отправьте голосовое сообщение — расскажите свою историю."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("q_text:"))
async def cb_answer_text(callback: CallbackQuery, state: FSMContext) -> None:
    log_id = int(callback.data.split(":")[1])
    await state.update_data(answering_question_log_id=log_id)
    await state.set_state(MemoryStates.waiting_text_memory)
    await callback.message.answer("Напишите свой ответ текстом. ✍️")
    await callback.answer()
