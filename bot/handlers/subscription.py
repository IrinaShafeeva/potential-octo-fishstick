import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()
logger = logging.getLogger(__name__)

PRICING_TEXT = (
    "⭐ <b>Подписка «Моя книга»</b>\n\n"
    "Бесплатно:\n"
    "• 5 воспоминаний\n"
    "• 1 глава\n"
    "• 3 вопроса из интервьюера\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "📖 <b>«Моя книга» — 3 990 ₽ / 3 месяца</b>\n"
    "• Безлимит голосовых\n"
    "• Все главы\n"
    "• Полный режим интервьюера\n"
    "• Экспорт в PDF\n"
    "• Прогресс книги\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "👨‍👩‍👧 <b>«Семейная история» — 6 990 ₽ / 3 месяца</b>\n"
    "• Всё из «Моя книга»\n"
    "• До 3 авторов\n"
    "• Общая или раздельные книги\n\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "🎁 Хотите подарить? Спросите про подарочный сертификат!"
)


def subscription_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Моя книга — 3 990 ₽",
                    callback_data="sub:my_book",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍👩‍👧 Семейная — 6 990 ₽",
                    callback_data="sub:family",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎁 Подарочный сертификат",
                    callback_data="sub:gift",
                )
            ],
        ]
    )


@router.message(F.text == "⭐ Подписка")
async def show_subscription(message: Message) -> None:
    await message.answer(PRICING_TEXT, reply_markup=subscription_kb())


@router.callback_query(F.data == "sub:my_book")
async def cb_sub_my_book(callback: CallbackQuery) -> None:
    # TODO: integrate with payment provider (YooKassa / Telegram Payments)
    await callback.message.answer(
        "Для оплаты подписки «Моя книга» (3 990 ₽ / 3 месяца) "
        "свяжитесь с нами: @memoir_support\n\n"
        "После оплаты подписка активируется автоматически."
    )
    await callback.answer()


@router.callback_query(F.data == "sub:family")
async def cb_sub_family(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Для оплаты подписки «Семейная история» (6 990 ₽ / 3 месяца) "
        "свяжитесь с нами: @memoir_support\n\n"
        "После оплаты подписка активируется автоматически."
    )
    await callback.answer()


@router.callback_query(F.data == "sub:gift")
async def cb_sub_gift(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "🎁 <b>Подарочный сертификат</b>\n\n"
        "Подарите близкому человеку возможность сохранить свои воспоминания.\n\n"
        "Как это работает:\n"
        "1. Вы оплачиваете подписку\n"
        "2. Мы присылаем красивый сертификат\n"
        "3. Получатель активирует его в боте\n\n"
        "Для заказа напишите: @memoir_support"
    )
    await callback.answer()
