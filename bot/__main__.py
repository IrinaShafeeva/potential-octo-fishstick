import asyncio
import logging

from aiohttp import web

from bot.loader import bot, dp
from bot.handlers import register_all_handlers
from bot.db.engine import init_db
from bot.config import settings
from bot.services.tribute_webhook import create_webhook_app


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    await init_db()
    register_all_handlers(dp)

    webhook_app = create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    logging.info("Webhook server started on %s:%d", settings.webhook_host, settings.webhook_port)

    logging.info("Bot starting…")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
