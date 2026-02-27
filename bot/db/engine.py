from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.db.models import Base

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=5)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    # Create all tables (idempotent — skips existing ones)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Each migration in its own transaction so a failure in one
    # doesn't abort or roll back the others
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE users ADD COLUMN style_notes TEXT",
        "ALTER TABLE chapters ADD COLUMN thread_summary TEXT",
        "ALTER TABLE memories ADD COLUMN clarification_thread TEXT",
        "ALTER TABLE memories ADD COLUMN clarification_round INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE memories ADD COLUMN chapter_suggestion VARCHAR(500)",
    ]
    for stmt in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception:
            pass  # Column already exists — ignore


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
