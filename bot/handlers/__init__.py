from aiogram import Dispatcher

from bot.handlers.start import router as start_router
from bot.handlers.questions import router as questions_router
from bot.handlers.structure import router as structure_router
from bot.handlers.voice import router as voice_router
from bot.handlers.book import router as book_router
from bot.handlers.subscription import router as subscription_router


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start_router)
    dp.include_router(questions_router)
    dp.include_router(structure_router)
    dp.include_router(book_router)
    dp.include_router(subscription_router)
    dp.include_router(voice_router)  # last: contains catch-all text handler
