import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base, Question, User, Chapter, Memory


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite session for tests (no PostgreSQL needed)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def sample_questions() -> list[Question]:
    """Create a set of Question model instances for testing."""
    return [
        Question(
            id="childhood_001", pack="childhood",
            text="Каким был дом в детстве?",
            difficulty="easy", emotional_intensity="low",
            tags=["home", "childhood"],
            followups=["Кто жил вместе с вами?", "Тепло было?"],
        ),
        Question(
            id="childhood_002", pack="childhood",
            text="Во что играли в детстве?",
            difficulty="easy", emotional_intensity="low",
            tags=["games", "childhood"],
            followups=["С кем играли?"],
        ),
        Question(
            id="school_001", pack="school",
            text="Любимый учитель?",
            difficulty="easy", emotional_intensity="low",
            tags=["school", "teacher"],
            followups=["Какой предмет?"],
        ),
        Question(
            id="hardships_001", pack="hardships",
            text="Трудный момент в жизни?",
            difficulty="medium", emotional_intensity="medium",
            tags=["hardships", "resilience"],
            followups=["Кто помогал?"],
        ),
        Question(
            id="work_001", pack="work",
            text="Первая работа?",
            difficulty="easy", emotional_intensity="low",
            tags=["work", "career"],
            followups=["Сколько проработали?"],
        ),
    ]


@pytest.fixture
def questions_json_data() -> list[dict]:
    """Raw JSON data matching questions.json format."""
    path = Path(__file__).parent.parent / "bot" / "data" / "questions.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
