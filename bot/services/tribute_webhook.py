"""Tribute payment webhook handler + REST API for mobile app + Mini App.

Runs as an aiohttp web server alongside the bot.
- POST /webhook/tribute — payment confirmation
- /api/v1/* — REST API (auth, user, chapters, memories, book, subscription)
- /miniapp — Telegram Mini App
"""
import hashlib
import hmac
import json
import logging
from pathlib import Path

from aiohttp import web

from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository

from api.middleware import cors_middleware
from api.auth import auth_google, auth_apple, auth_register, auth_login, auth_telegram
from api.routes_user import get_me, patch_me
from api.routes_chapters import (
    get_chapters,
    create_chapter,
    patch_chapter,
    delete_chapter,
    reorder_chapters,
)
from api.routes_memories import (
    post_memories_text,
    post_memories_audio,
    patch_memory_transcript,
    post_correct_transcript,
    post_confirm_transcript,
    get_clarification,
    post_clarification,
    post_skip_clarification,
    get_memory,
    post_edit,
    post_save,
    post_move,
    delete_memory,
    post_fantasy,
)
from api.routes_book import get_book, get_book_pdf, get_book_progress
from api.routes_subscription import get_subscription, post_promo

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
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/webhook/tribute", handle_tribute_webhook)
    app.router.add_get("/health", handle_health)

    # API v1 for mobile app
    app.router.add_post("/api/v1/auth/google", auth_google)
    app.router.add_post("/api/v1/auth/apple", auth_apple)
    app.router.add_post("/api/v1/auth/register", auth_register)
    app.router.add_post("/api/v1/auth/login", auth_login)
    app.router.add_post("/api/v1/auth/telegram", auth_telegram)
    app.router.add_get("/api/v1/me", get_me)
    app.router.add_patch("/api/v1/me", patch_me)
    app.router.add_get("/api/v1/chapters", get_chapters)
    app.router.add_post("/api/v1/chapters", create_chapter)
    app.router.add_patch("/api/v1/chapters/{id}", patch_chapter)
    app.router.add_delete("/api/v1/chapters/{id}", delete_chapter)
    app.router.add_post("/api/v1/chapters/reorder", reorder_chapters)
    app.router.add_post("/api/v1/memories/text", post_memories_text)
    app.router.add_post("/api/v1/memories/audio", post_memories_audio)
    app.router.add_patch("/api/v1/memories/{id}", patch_memory_transcript)
    app.router.add_post("/api/v1/memories/{id}/correct-transcript", post_correct_transcript)
    app.router.add_post("/api/v1/memories/{id}/confirm-transcript", post_confirm_transcript)
    app.router.add_get("/api/v1/memories/{id}/clarification", get_clarification)
    app.router.add_post("/api/v1/memories/{id}/clarification", post_clarification)
    app.router.add_post("/api/v1/memories/{id}/skip-clarification", post_skip_clarification)
    app.router.add_get("/api/v1/memories/{id}", get_memory)
    app.router.add_post("/api/v1/memories/{id}/edit", post_edit)
    app.router.add_post("/api/v1/memories/{id}/save", post_save)
    app.router.add_post("/api/v1/memories/{id}/move", post_move)
    app.router.add_delete("/api/v1/memories/{id}", delete_memory)
    app.router.add_post("/api/v1/memories/{id}/fantasy", post_fantasy)
    app.router.add_get("/api/v1/book", get_book)
    app.router.add_get("/api/v1/book/pdf", get_book_pdf)
    app.router.add_get("/api/v1/book/progress", get_book_progress)
    app.router.add_get("/api/v1/subscription", get_subscription)
    app.router.add_post("/api/v1/subscription/promo", post_promo)

    # Mini App — explicit routes first (before add_static to avoid 403)
    miniapp_dir = Path(__file__).resolve().parent.parent.parent / "miniapp"
    if miniapp_dir.exists():
        index_path = miniapp_dir / "index.html"

        async def serve_miniapp_index(request):
            if index_path.exists():
                return web.FileResponse(index_path)
            raise web.HTTPNotFound()

        app.router.add_get("/miniapp", serve_miniapp_index)
        app.router.add_get("/miniapp/", serve_miniapp_index)
        app.router.add_static("/miniapp", miniapp_dir, name="miniapp")
        logger.info("Mini App served from %s", miniapp_dir)
    else:
        logger.warning("Mini App dir not found: %s", miniapp_dir)

    return app
