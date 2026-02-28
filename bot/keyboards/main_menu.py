from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BTN_RECORD = "🎙 Записать воспоминание"
BTN_QUESTIONS = "🧠 Вспомнить вместе"
BTN_BOOK = "📖 Моя книга"
BTN_CHAPTERS = "🧩 Структура глав"
BTN_SUB = "⭐ Подписка"

MENU_BUTTONS = frozenset({BTN_RECORD, BTN_QUESTIONS, BTN_BOOK, BTN_CHAPTERS, BTN_SUB})


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RECORD), KeyboardButton(text=BTN_QUESTIONS)],
            [KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_CHAPTERS)],
            [KeyboardButton(text=BTN_SUB)],
        ],
        resize_keyboard=True,
    )


def onboarding_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎙 Начать говорить")],
            [KeyboardButton(text="🧠 Помочь вопросами")],
            [KeyboardButton(text="🧩 Сначала настрою главы")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
