from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.db.models import Base

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=5)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration: add style_notes column if it doesn't exist yet
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE users ADD COLUMN style_notes TEXT"
                )
            )
        except Exception:
            pass  # Column already exists — ignore


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
