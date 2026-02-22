import asyncio
import logging

from bot.loader import bot, dp
from bot.handlers import register_all_handlers
from bot.db.engine import init_db


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    await init_db()
    register_all_handlers(dp)
    logging.info("Bot starting…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
