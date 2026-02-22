from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PACKS_DISPLAY = {
    "childhood": "👶 Детство",
    "parents_home": "🏠 Родители и дом",
    "school": "📚 Школа и друзья",
    "youth": "🌅 Молодость",
    "work": "💼 Работа и профессия",
    "love": "💕 Любовь и брак",
    "children_family": "👨‍👩‍👧 Дети и семья",
    "places": "🗺 Переезды и города",
    "hardships": "🌧 Трудные времена",
    "achievements": "🏆 Радости и достижения",
    "traditions": "🎄 Быт и традиции",
    "favorites": "⭐ Любимые вещи и места",
    "later_years": "🕰 Поздние годы",
}


def pack_select_kb() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for pack_id, label in PACKS_DISPLAY.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"pack:{pack_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🎲 Любая тема", callback_data="pack:any")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def question_actions_kb(question_log_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎙 Ответить голосом", callback_data=f"q_voice:{question_log_id}"),
                InlineKeyboardButton(text="📝 Написать текстом", callback_data=f"q_text:{question_log_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Другой вопрос", callback_data=f"q_next:{question_log_id}"),
                InlineKeyboardButton(text="⏸ Не сейчас", callback_data=f"q_pause:{question_log_id}"),
            ],
        ]
    )


def followup_kb(question_log_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎙 Дополнить голосом", callback_data=f"q_voice:{question_log_id}"),
                InlineKeyboardButton(text="📝 Дополнить текстом", callback_data=f"q_text:{question_log_id}"),
            ],
            [
                InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data=f"q_next:{question_log_id}"),
                InlineKeyboardButton(text="⏸ Хватит на сегодня", callback_data=f"q_pause:{question_log_id}"),
            ],
        ]
    )
