from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def memory_fantasy_kb(memory_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown when fantasy (creative) version is displayed."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить в книгу", callback_data=f"mem_save_fantasy:{memory_id}"),
                InlineKeyboardButton(text="📝 Точная версия", callback_data=f"show_strict:{memory_id}"),
            ],
            [
                InlineKeyboardButton(text="🧩 Разбить на истории", callback_data=f"mem_split:{memory_id}"),
                InlineKeyboardButton(text="🧷 В другую главу", callback_data=f"mem_move:{memory_id}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Исправить текст", callback_data=f"mem_edit:{memory_id}"),
                InlineKeyboardButton(text="🎙 Перезаписать", callback_data=f"mem_redo:{memory_id}"),
            ],
        ]
    )


def memory_preview_kb(memory_id: int, has_fantasy: bool = True) -> InlineKeyboardMarkup:
    """Keyboard for strict (accurate) version."""
    first_row = [InlineKeyboardButton(text="✅ Сохранить в книгу", callback_data=f"mem_save:{memory_id}")]
    if has_fantasy:
        first_row.append(InlineKeyboardButton(text="✨ Творческая версия", callback_data=f"show_fantasy:{memory_id}"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            first_row,
            [
                InlineKeyboardButton(text="🧩 Разбить на истории", callback_data=f"mem_split:{memory_id}"),
                InlineKeyboardButton(text="🧷 В другую главу", callback_data=f"mem_move:{memory_id}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Исправить текст", callback_data=f"mem_edit:{memory_id}"),
                InlineKeyboardButton(text="🎙 Перезаписать", callback_data=f"mem_redo:{memory_id}"),
            ],
        ]
    )


def chapter_select_kb(chapters: list[dict], memory_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for ch in chapters:
        buttons.append([
            InlineKeyboardButton(
                text=ch["title"],
                callback_data=f"mem_to_ch:{memory_id}:{ch['id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="📁 Новая глава", callback_data=f"mem_new_ch:{memory_id}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"mem_back:{memory_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def saved_memory_kb(memory_id: int) -> InlineKeyboardMarkup:
    """Actions for an already-saved memory (viewed from chapter)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Исправить текст", callback_data=f"mem_edit:{memory_id}"),
                InlineKeyboardButton(text="🧷 В другую главу", callback_data=f"mem_move:{memory_id}"),
            ],
        ]
    )


def confirm_save_kb(memory_id: int, chapter_title: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Да, в «{chapter_title}»",
                    callback_data=f"mem_confirm:{memory_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧷 Выбрать другую главу",
                    callback_data=f"mem_move:{memory_id}",
                ),
            ],
        ]
    )
