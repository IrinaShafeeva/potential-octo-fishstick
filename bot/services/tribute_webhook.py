"""Tribute payment webhook handler.

Runs as an aiohttp web server alongside the bot.
Receives POST /webhook/tribute with payment confirmation,
verifies signature, and activates premium.
"""
import hashlib
import hmac
import json
import logging

from aiohttp import web

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository

logger = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Tribute webhook signature (HMAC-SHA256)."""
    if not secret:
        logger.warning("No webhook secret configured, skipping verification")
        return True
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def handle_tribute_webhook(request: web.Request) -> web.Response:
    """Handle incoming Tribute payment webhook."""
    try:
        body = await request.read()
        signature = request.headers.get("trbt-signature", "")

        if settings.tribute_webhook_secret and not verify_signature(
            body, signature, settings.tribute_webhook_secret
        ):
            logger.warning("Invalid webhook signature")
            return web.json_response({"error": "invalid signature"}, status=403)

        data = json.loads(body)
        logger.info("Tribute webhook received: %s", json.dumps(data, ensure_ascii=False)[:500])

        telegram_id = data.get("telegramID") or data.get("telegram_id") or data.get("telegramId")
        if not telegram_id:
            logger.error("No telegramID in webhook payload")
            return web.json_response({"error": "no telegram_id"}, status=400)

        telegram_id = int(telegram_id)

        async with async_session() as session:
            repo = Repository(session)
            await repo.log_payment(
                telegram_id=telegram_id,
                provider="tribute",
                product=data.get("productName", ""),
                amount=data.get("amount"),
                currency=data.get("currency", ""),
                raw_payload=data,
            )
            activated = await repo.activate_premium_by_telegram_id(
                telegram_id, days=settings.premium_days
            )

        if activated:
            logger.info("Premium activated for telegram_id=%d", telegram_id)
            from bot.loader import bot
            try:
                await bot.send_message(
                    telegram_id,
                    "🎉 <b>Подписка активирована!</b>\n\n"
                    "Теперь вам доступны все возможности:\n"
                    "• Безлимит воспоминаний\n"
                    "• Все главы\n"
                    "• Полный режим интервьюера\n"
                    "• Экспорт в PDF\n\n"
                    "Приятного использования!",
                )
            except Exception as e:
                logger.error("Failed to notify user %d: %s", telegram_id, e)
        else:
            logger.warning("User telegram_id=%d not found for premium activation", telegram_id)

        return web.json_response({"ok": True})

    except Exception as e:
        logger.exception("Webhook processing error: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/tribute", handle_tribute_webhook)
    app.router.add_get("/health", handle_health)
    return app
