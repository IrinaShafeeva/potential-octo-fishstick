from datetime import datetime
from typing import Optional

from sqlalchemy import select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User, Chapter, Memory, Question, QuestionLog, TopicCoverage


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Users ──

    async def get_or_create_user(
        self, telegram_id: int, username: str | None = None, first_name: str | None = None
    ) -> User:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id, username=username, first_name=first_name
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        return user

    async def get_user(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def set_premium(self, user_id: int, until: datetime) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_premium=True, premium_until=until)
        )
        await self.session.commit()

    async def is_premium(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        if not user or not user.is_premium:
            return False
        if user.premium_until and user.premium_until < datetime.utcnow():
            await self.session.execute(
                update(User).where(User.id == user.id).values(is_premium=False)
            )
            await self.session.commit()
            return False
        return True

    async def increment_memories_count(self, user_id: int) -> int:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(memories_count=User.memories_count + 1)
        )
        await self.session.commit()
        result = await self.session.execute(
            select(User.memories_count).where(User.id == user_id)
        )
        return result.scalar_one()

    # ── Chapters ──

    async def create_chapter(
        self, user_id: int, title: str, period_hint: str | None = None
    ) -> Chapter:
        max_order = await self.session.execute(
            select(func.max(Chapter.order_index)).where(Chapter.user_id == user_id)
        )
        next_order = (max_order.scalar_one() or 0) + 1
        chapter = Chapter(
            user_id=user_id,
            title=title,
            period_hint=period_hint,
            order_index=next_order,
        )
        self.session.add(chapter)
        await self.session.commit()
        await self.session.refresh(chapter)
        return chapter

    async def get_chapters(self, user_id: int) -> list[Chapter]:
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.user_id == user_id)
            .order_by(Chapter.order_index)
        )
        return list(result.scalars().all())

    async def get_chapter(self, chapter_id: int) -> Optional[Chapter]:
        result = await self.session.execute(
            select(Chapter).where(Chapter.id == chapter_id)
        )
        return result.scalar_one_or_none()

    async def rename_chapter(self, chapter_id: int, title: str) -> None:
        await self.session.execute(
            update(Chapter).where(Chapter.id == chapter_id).values(title=title)
        )
        await self.session.commit()

    async def delete_chapter(self, chapter_id: int) -> None:
        await self.session.execute(
            update(Memory).where(Memory.chapter_id == chapter_id).values(chapter_id=None)
        )
        await self.session.execute(
            delete(Chapter).where(Chapter.id == chapter_id)
        )
        await self.session.commit()

    async def count_chapters(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Chapter.id)).where(Chapter.user_id == user_id)
        )
        return result.scalar_one()

    # ── Memories ──

    async def create_memory(self, user_id: int, **kwargs) -> Memory:
        memory = Memory(user_id=user_id, **kwargs)
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def get_memory(self, memory_id: int) -> Optional[Memory]:
        result = await self.session.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        return result.scalar_one_or_none()

    async def approve_memory(self, memory_id: int, chapter_id: int | None = None) -> None:
        values = {"approved": True}
        if chapter_id is not None:
            values["chapter_id"] = chapter_id
        await self.session.execute(
            update(Memory).where(Memory.id == memory_id).values(**values)
        )
        await self.session.commit()

    async def move_memory(self, memory_id: int, chapter_id: int) -> None:
        await self.session.execute(
            update(Memory).where(Memory.id == memory_id).values(chapter_id=chapter_id)
        )
        await self.session.commit()

    async def update_memory_text(self, memory_id: int, edited_text: str) -> None:
        await self.session.execute(
            update(Memory)
            .where(Memory.id == memory_id)
            .values(edited_memoir_text=edited_text)
        )
        await self.session.commit()

    async def get_memories_by_chapter(self, chapter_id: int) -> list[Memory]:
        result = await self.session.execute(
            select(Memory)
            .where(Memory.chapter_id == chapter_id, Memory.approved == True)
            .order_by(Memory.created_at)
        )
        return list(result.scalars().all())

    async def get_all_approved_memories(self, user_id: int) -> list[Memory]:
        result = await self.session.execute(
            select(Memory)
            .where(Memory.user_id == user_id, Memory.approved == True)
            .order_by(Memory.created_at)
        )
        return list(result.scalars().all())

    async def get_unassigned_memories(self, user_id: int) -> list[Memory]:
        result = await self.session.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.approved == True,
                Memory.chapter_id == None,
            )
            .order_by(Memory.created_at)
        )
        return list(result.scalars().all())

    async def count_memories(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Memory.id)).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        return result.scalar_one()

    # ── Questions ──

    async def load_questions(self, questions_data: list[dict]) -> None:
        existing = await self.session.execute(select(func.count(Question.id)))
        if existing.scalar_one() > 0:
            return
        for q in questions_data:
            self.session.add(
                Question(
                    id=q["id"],
                    pack=q["pack"],
                    text=q["text"],
                    difficulty=q.get("difficulty", "easy"),
                    emotional_intensity=q.get("emotional_intensity", "low"),
                    tags=q.get("tags", []),
                    followups=q.get("followups", []),
                )
            )
        await self.session.commit()

    async def get_questions_by_pack(self, pack: str) -> list[Question]:
        result = await self.session.execute(
            select(Question).where(Question.pack == pack)
        )
        return list(result.scalars().all())

    async def get_all_questions(self) -> list[Question]:
        result = await self.session.execute(select(Question))
        return list(result.scalars().all())

    async def get_question(self, question_id: str) -> Optional[Question]:
        result = await self.session.execute(
            select(Question).where(Question.id == question_id)
        )
        return result.scalar_one_or_none()

    # ── Question Log ──

    async def log_question(self, user_id: int, question_id: str) -> QuestionLog:
        log = QuestionLog(user_id=user_id, question_id=question_id, status="asked")
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def mark_question_answered(
        self, log_id: int, memory_id: int | None = None
    ) -> None:
        values = {"status": "answered"}
        if memory_id:
            values["answered_memory_id"] = memory_id
        await self.session.execute(
            update(QuestionLog).where(QuestionLog.id == log_id).values(**values)
        )
        await self.session.commit()

    async def mark_question_skipped(self, log_id: int) -> None:
        await self.session.execute(
            update(QuestionLog)
            .where(QuestionLog.id == log_id)
            .values(status="skipped")
        )
        await self.session.commit()

    async def get_asked_question_ids(self, user_id: int) -> list[str]:
        result = await self.session.execute(
            select(QuestionLog.question_id).where(QuestionLog.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_last_question_log(self, user_id: int) -> Optional[QuestionLog]:
        result = await self.session.execute(
            select(QuestionLog)
            .where(QuestionLog.user_id == user_id)
            .order_by(QuestionLog.asked_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Topic Coverage ──

    async def update_topic_coverage(self, user_id: int, tags: list[str]) -> None:
        for tag in tags:
            result = await self.session.execute(
                select(TopicCoverage).where(
                    TopicCoverage.user_id == user_id, TopicCoverage.tag == tag
                )
            )
            tc = result.scalar_one_or_none()
            if tc:
                tc.count += 1
                tc.last_used_at = datetime.utcnow()
            else:
                self.session.add(
                    TopicCoverage(user_id=user_id, tag=tag, count=1)
                )
        await self.session.commit()

    async def get_topic_coverage(self, user_id: int) -> dict[str, int]:
        result = await self.session.execute(
            select(TopicCoverage.tag, TopicCoverage.count).where(
                TopicCoverage.user_id == user_id
            )
        )
        return {row[0]: row[1] for row in result.all()}

    # ── Author Context (aggregated) ──

    async def get_known_people(self, user_id: int) -> list[str]:
        result = await self.session.execute(
            select(Memory.people).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        people = set()
        for row in result.scalars().all():
            if row:
                people.update(row)
        return sorted(people)

    async def get_known_places(self, user_id: int) -> list[str]:
        result = await self.session.execute(
            select(Memory.places).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        places = set()
        for row in result.scalars().all():
            if row:
                places.update(row)
        return sorted(places)

    # ── Progress ──

    async def get_book_progress(self, user_id: int) -> dict:
        memories_count = await self.count_memories(user_id)
        chapters_count = await self.count_chapters(user_id)
        chapters = await self.get_chapters(user_id)

        filled_chapters = 0
        for ch in chapters:
            mems = await self.get_memories_by_chapter(ch.id)
            if mems:
                filled_chapters += 1

        estimated_pages = round(memories_count * 0.75, 1)
        return {
            "memories_count": memories_count,
            "chapters_total": chapters_count,
            "chapters_filled": filled_chapters,
            "estimated_pages": estimated_pages,
        }
