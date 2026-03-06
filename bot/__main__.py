import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web

from aiogram.types import MenuButtonWebApp, WebAppInfo

from bot.loader import bot, dp
from bot.handlers import register_all_handlers
from bot.db.engine import init_db, async_session
from bot.db.repository import Repository
from bot.config import settings
from bot.services.tribute_webhook import create_webhook_app


async def seed_questions() -> None:
    """Load questions from JSON into DB on startup (idempotent)."""
    questions_json = Path(__file__).parent / "data" / "questions.json"
    if not questions_json.exists():
        logging.warning("questions.json not found at %s", questions_json)
        return
    with open(questions_json, "r", encoding="utf-8") as f:
        questions_data = json.load(f)
    async with async_session() as session:
        repo = Repository(session)
        await repo.load_questions(questions_data)
    logging.info("Questions seeded: %d total", len(questions_data))


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    await init_db()
    await seed_questions()
    register_all_handlers(dp)

    webhook_app = create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logging.info("Webhook server started on %s:%d", settings.webhook_host, settings.webhook_port)

    if not settings.mini_app_url:
        logging.warning("MINI_APP_URL not set — add it in Render Environment to enable Mini App button")

    if settings.mini_app_url:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Open",
                    web_app=WebAppInfo(url=settings.mini_app_url.rstrip("/") + "/miniapp"),
                )
            )
            logging.info("Mini App menu button set: %s", settings.mini_app_url)
        except Exception as e:
            logging.warning("Failed to set Mini App menu button: %s", e)

    logging.info("Bot starting…")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
