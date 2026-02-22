import json
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.main_menu import main_menu_kb, onboarding_kb

router = Router()
logger = logging.getLogger(__name__)

ONBOARDING_TEXT = (
    "Здравствуйте! Я помогу вам сохранить воспоминания и собрать их в книгу.\n\n"
    "Как это работает: вы рассказываете — голосом или текстом — а я записываю, "
    "редактирую и раскладываю по главам.\n\n"
    "Например, расскажите: каким был двор, где вы играли в детстве? "
    "А я покажу, как это будет выглядеть в книге."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        questions_json = Path(__file__).parent.parent / "data" / "questions.json"
        if questions_json.exists():
            with open(questions_json, "r", encoding="utf-8") as f:
                questions_data = json.load(f)
            await repo.load_questions(questions_data)

    await message.answer(ONBOARDING_TEXT, reply_markup=onboarding_kb())


@router.message(F.text == "🎙 Начать говорить")
async def onboarding_speak(message: Message) -> None:
    await message.answer(
        "Отлично! Отправьте голосовое сообщение — расскажите что-нибудь из жизни. "
        "Я запишу, отредактирую и покажу результат.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "🧩 Сначала настрою главы")
async def onboarding_chapters(message: Message) -> None:
    await message.answer(
        "Хорошо! Напишите название первой главы. Например:\n\n"
        "• Детство\n"
        "• Школьные годы\n"
        "• Молодость\n"
        "• Работа и карьера\n\n"
        "Или просто отправьте голосовое — я сам подберу главу.",
        reply_markup=main_menu_kb(),
    )
