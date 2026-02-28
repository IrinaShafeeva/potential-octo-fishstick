import logging
import secrets
import string

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.keyboards.main_menu import main_menu_kb, MENU_BUTTONS

router = Router()
logger = logging.getLogger(__name__)


class PromoStates(StatesGroup):
    waiting_promo_code = State()


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
    "Есть промокод? Нажмите «🎟 Ввести промокод»"
)


def subscription_kb() -> InlineKeyboardMarkup:
    buttons = []
    if settings.tribute_product_link:
        buttons.append([InlineKeyboardButton(
            text="📖 Оплатить «Моя книга» — 3 990 ₽",
            url=settings.tribute_product_link,
        )])
    if settings.tribute_family_product_link:
        buttons.append([InlineKeyboardButton(
            text="👨‍👩‍👧 Оплатить «Семейная» — 6 990 ₽",
            url=settings.tribute_family_product_link,
        )])
    buttons.append([InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="sub:promo")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Show subscription ──

@router.message(F.text == "⭐ Подписка")
async def show_subscription(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_user(message.from_user.id)

    if user and user.is_premium and user.premium_until:
        until = user.premium_until.strftime("%d.%m.%Y")
        await message.answer(
            f"✅ У вас активная подписка до <b>{until}</b>\n\n"
            "Все функции доступны без ограничений.",
            reply_markup=main_menu_kb(),
        )
        return

    await message.answer(PRICING_TEXT, reply_markup=subscription_kb())


# ── Promo code flow ──

@router.callback_query(F.data == "sub:promo")
async def cb_enter_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoStates.waiting_promo_code)
    await callback.message.answer("Введите промокод:")
    await callback.answer()


@router.message(PromoStates.waiting_promo_code, F.text.func(lambda t: t not in MENU_BUTTONS))
async def handle_promo_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    await state.clear()

    if not code or len(code) > 50:
        await message.answer("Неверный формат промокода.", reply_markup=main_menu_kb())
        return

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        result = await repo.redeem_promo_code(user.id, code)

    if result["ok"]:
        await message.answer(
            f"🎉 {result['msg']}\n\n"
            "Все функции теперь доступны без ограничений!",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(f"❌ {result['msg']}", reply_markup=main_menu_kb())


# ── Direct promo command: /promo CODE ──

@router.message(Command("promo"))
async def cmd_promo(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /promo КОД")
        return

    code = parts[1].strip()

    async with async_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        result = await repo.redeem_promo_code(user.id, code)

    if result["ok"]:
        await message.answer(
            f"🎉 {result['msg']}\n\nВсе функции теперь доступны!",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(f"❌ {result['msg']}")


# ── Admin commands ──

def _is_admin(telegram_id: int) -> bool:
    return settings.admin_telegram_id and telegram_id == settings.admin_telegram_id


@router.message(Command("create_promo"))
async def cmd_create_promo(message: Message) -> None:
    """Admin: /create_promo [DAYS] [MAX_USES] [CODE]
    Examples:
        /create_promo              → random code, 90 days, 1 use
        /create_promo 30           → random code, 30 days, 1 use
        /create_promo 90 10        → random code, 90 days, 10 uses
        /create_promo 90 5 BETA    → code BETA, 90 days, 5 uses
    """
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 else 90
    max_uses = int(parts[2]) if len(parts) > 2 else 1
    code = parts[3].upper() if len(parts) > 3 else _generate_code()

    async with async_session() as session:
        repo = Repository(session)
        existing = await repo.get_promo_code(code)
        if existing:
            await message.answer(f"❌ Код {code} уже существует.")
            return
        promo = await repo.create_promo_code(code, premium_days=days, max_uses=max_uses)

    await message.answer(
        f"✅ Промокод создан:\n\n"
        f"<code>{promo.code}</code>\n"
        f"Срок подписки: {days} дней\n"
        f"Макс. использований: {max_uses}\n\n"
        f"Пользователь вводит: /promo {promo.code}",
    )


@router.message(Command("grant_premium"))
async def cmd_grant_premium(message: Message) -> None:
    """Admin: /grant_premium TELEGRAM_ID [DAYS]"""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /grant_premium TELEGRAM_ID [DAYS]")
        return

    target_id = int(parts[1])
    days = int(parts[2]) if len(parts) > 2 else 90

    async with async_session() as session:
        repo = Repository(session)
        ok = await repo.activate_premium_by_telegram_id(target_id, days)

    if ok:
        await message.answer(f"✅ Премиум на {days} дней выдан пользователю {target_id}")
    else:
        await message.answer(f"❌ Пользователь {target_id} не найден. Он должен сначала запустить бота (/start).")


def _generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))
