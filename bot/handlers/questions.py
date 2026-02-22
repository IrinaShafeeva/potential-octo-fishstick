import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.inline_question import pack_select_kb, question_actions_kb, followup_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.services.question_router import pick_next_question, get_followup

router = Router()
logger = logging.getLogger(__name__)


async def _send_question(
    message_or_callback,
    user_id: int,
    telegram_id: int,
    selected_pack: str | None = None,
) -> None:
    """Shared logic: pick a question and send it."""
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(telegram_id)

        if not user.is_premium and user.questions_asked_count >= settings.free_questions_limit:
            text = (
                f"В бесплатной версии доступно {settings.free_questions_limit} вопроса.\n"
                "Оформите подписку «Моя книга», чтобы открыть все вопросы. ⭐"
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

    text = f"💭 <b>{question.text}</b>"

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
async def questions_start(message: Message) -> None:
    await message.answer(
        "Выберите тему, о которой хотите вспомнить:",
        reply_markup=pack_select_kb(),
    )


@router.callback_query(F.data.startswith("pack:"))
async def cb_select_pack(callback: CallbackQuery) -> None:
    pack = callback.data.split(":")[1]
    await callback.answer()
    await _send_question(callback, 0, callback.from_user.id, selected_pack=pack)


@router.callback_query(F.data.startswith("q_next:"))
async def cb_next_question(callback: CallbackQuery) -> None:
    log_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        repo = Repository(session)
        await repo.mark_question_skipped(log_id)

    await callback.answer()
    await _send_question(callback, 0, callback.from_user.id)


@router.callback_query(F.data.startswith("q_pause:"))
async def cb_pause_questions(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Хорошо, отдохните. Когда захотите продолжить — нажмите «🧠 Вспомнить вместе».",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("q_voice:"))
async def cb_answer_voice(callback: CallbackQuery) -> None:
    log_id = callback.data.split(":")[1]
    await callback.message.answer(
        "Отправьте голосовое сообщение — расскажите свою историю. 🎙"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("q_text:"))
async def cb_answer_text(callback: CallbackQuery) -> None:
    log_id = callback.data.split(":")[1]
    await callback.message.answer("Напишите свой ответ текстом. ✍️")
    await callback.answer()
