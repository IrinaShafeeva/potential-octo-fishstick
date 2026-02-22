import pytest
import pytest_asyncio

from bot.db.models import Base
from bot.db.repository import Repository
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield Repository(session)

    await engine.dispose()


@pytest.mark.asyncio
class TestUserRepo:
    async def test_create_user(self, repo):
        user = await repo.get_or_create_user(123456, "testuser", "Тест")
        assert user.telegram_id == 123456
        assert user.username == "testuser"
        assert user.first_name == "Тест"
        assert user.is_premium is False
        assert user.memories_count == 0

    async def test_get_existing_user(self, repo):
        u1 = await repo.get_or_create_user(111, "a", "A")
        u2 = await repo.get_or_create_user(111, "a", "A")
        assert u1.id == u2.id

    async def test_increment_memories(self, repo):
        user = await repo.get_or_create_user(222)
        count = await repo.increment_memories_count(user.id)
        assert count == 1
        count = await repo.increment_memories_count(user.id)
        assert count == 2

    async def test_premium_check(self, repo):
        user = await repo.get_or_create_user(333)
        assert await repo.is_premium(333) is False


@pytest.mark.asyncio
class TestChapterRepo:
    async def test_create_chapter(self, repo):
        user = await repo.get_or_create_user(100)
        ch = await repo.create_chapter(user.id, "Детство", "1950-1960")
        assert ch.title == "Детство"
        assert ch.period_hint == "1950-1960"
        assert ch.order_index == 1

    async def test_auto_increment_order(self, repo):
        user = await repo.get_or_create_user(101)
        ch1 = await repo.create_chapter(user.id, "Первая")
        ch2 = await repo.create_chapter(user.id, "Вторая")
        assert ch2.order_index == ch1.order_index + 1

    async def test_get_chapters_ordered(self, repo):
        user = await repo.get_or_create_user(102)
        await repo.create_chapter(user.id, "Б")
        await repo.create_chapter(user.id, "А")
        chapters = await repo.get_chapters(user.id)
        assert len(chapters) == 2
        assert chapters[0].title == "Б"
        assert chapters[1].title == "А"

    async def test_rename_chapter(self, repo):
        user = await repo.get_or_create_user(103)
        ch = await repo.create_chapter(user.id, "Старое")
        await repo.rename_chapter(ch.id, "Новое")
        updated = await repo.get_chapter(ch.id)
        assert updated.title == "Новое"

    async def test_delete_chapter(self, repo):
        user = await repo.get_or_create_user(104)
        ch = await repo.create_chapter(user.id, "Удалить")
        await repo.delete_chapter(ch.id)
        assert await repo.get_chapter(ch.id) is None

    async def test_count_chapters(self, repo):
        user = await repo.get_or_create_user(105)
        assert await repo.count_chapters(user.id) == 0
        await repo.create_chapter(user.id, "X")
        assert await repo.count_chapters(user.id) == 1


@pytest.mark.asyncio
class TestMemoryRepo:
    async def test_create_memory(self, repo):
        user = await repo.get_or_create_user(200)
        mem = await repo.create_memory(
            user_id=user.id,
            raw_transcript="сырой текст",
            cleaned_transcript="чистый текст",
            edited_memoir_text="литературный текст",
            title="Тест",
            tags=["childhood"],
        )
        assert mem.id is not None
        assert mem.raw_transcript == "сырой текст"
        assert mem.approved is False

    async def test_approve_and_assign_chapter(self, repo):
        user = await repo.get_or_create_user(201)
        ch = await repo.create_chapter(user.id, "Глава")
        mem = await repo.create_memory(user_id=user.id, title="M")
        await repo.approve_memory(mem.id, ch.id)
        updated = await repo.get_memory(mem.id)
        assert updated.approved is True
        assert updated.chapter_id == ch.id

    async def test_get_memories_by_chapter(self, repo):
        user = await repo.get_or_create_user(202)
        ch = await repo.create_chapter(user.id, "Г")
        m1 = await repo.create_memory(user_id=user.id, title="A")
        m2 = await repo.create_memory(user_id=user.id, title="B")
        await repo.approve_memory(m1.id, ch.id)
        await repo.approve_memory(m2.id, ch.id)
        mems = await repo.get_memories_by_chapter(ch.id)
        assert len(mems) == 2

    async def test_unassigned_memories(self, repo):
        user = await repo.get_or_create_user(203)
        mem = await repo.create_memory(user_id=user.id, title="X")
        await repo.approve_memory(mem.id)
        unassigned = await repo.get_unassigned_memories(user.id)
        assert len(unassigned) == 1

    async def test_move_memory(self, repo):
        user = await repo.get_or_create_user(204)
        ch1 = await repo.create_chapter(user.id, "A")
        ch2 = await repo.create_chapter(user.id, "B")
        mem = await repo.create_memory(user_id=user.id, title="M")
        await repo.approve_memory(mem.id, ch1.id)
        await repo.move_memory(mem.id, ch2.id)
        updated = await repo.get_memory(mem.id)
        assert updated.chapter_id == ch2.id

    async def test_count_only_approved(self, repo):
        user = await repo.get_or_create_user(205)
        await repo.create_memory(user_id=user.id, title="Draft")
        assert await repo.count_memories(user.id) == 0
        m = await repo.create_memory(user_id=user.id, title="Done")
        await repo.approve_memory(m.id)
        assert await repo.count_memories(user.id) == 1


@pytest.mark.asyncio
class TestQuestionRepo:
    async def test_load_questions(self, repo, questions_json_data):
        await repo.load_questions(questions_json_data)
        all_q = await repo.get_all_questions()
        assert len(all_q) == len(questions_json_data)

    async def test_load_idempotent(self, repo, questions_json_data):
        await repo.load_questions(questions_json_data)
        await repo.load_questions(questions_json_data)
        all_q = await repo.get_all_questions()
        assert len(all_q) == len(questions_json_data)

    async def test_get_by_pack(self, repo, questions_json_data):
        await repo.load_questions(questions_json_data)
        childhood = await repo.get_questions_by_pack("childhood")
        assert all(q.pack == "childhood" for q in childhood)
        assert len(childhood) > 0

    async def test_log_question(self, repo, questions_json_data):
        await repo.load_questions(questions_json_data)
        user = await repo.get_or_create_user(300)
        first_q = (await repo.get_all_questions())[0]
        log = await repo.log_question(user.id, first_q.id)
        assert log.status == "asked"
        asked_ids = await repo.get_asked_question_ids(user.id)
        assert first_q.id in asked_ids

    async def test_mark_skipped(self, repo, questions_json_data):
        await repo.load_questions(questions_json_data)
        user = await repo.get_or_create_user(301)
        first_q = (await repo.get_all_questions())[0]
        log = await repo.log_question(user.id, first_q.id)
        await repo.mark_question_skipped(log.id)


@pytest.mark.asyncio
class TestTopicCoverage:
    async def test_update_coverage(self, repo):
        user = await repo.get_or_create_user(400)
        await repo.update_topic_coverage(user.id, ["childhood", "home"])
        cov = await repo.get_topic_coverage(user.id)
        assert cov["childhood"] == 1
        assert cov["home"] == 1

    async def test_increments(self, repo):
        user = await repo.get_or_create_user(401)
        await repo.update_topic_coverage(user.id, ["school"])
        await repo.update_topic_coverage(user.id, ["school"])
        cov = await repo.get_topic_coverage(user.id)
        assert cov["school"] == 2


@pytest.mark.asyncio
class TestBookProgress:
    async def test_empty_progress(self, repo):
        user = await repo.get_or_create_user(500)
        progress = await repo.get_book_progress(user.id)
        assert progress["memories_count"] == 0
        assert progress["chapters_total"] == 0

    async def test_progress_with_data(self, repo):
        user = await repo.get_or_create_user(501)
        ch = await repo.create_chapter(user.id, "Test")
        m = await repo.create_memory(user_id=user.id, title="M")
        await repo.approve_memory(m.id, ch.id)
        progress = await repo.get_book_progress(user.id)
        assert progress["memories_count"] == 1
        assert progress["chapters_filled"] == 1
