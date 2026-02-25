from datetime import datetime
from typing import Optional

from sqlalchemy import select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    User, Chapter, Memory, Question, QuestionLog, TopicCoverage,
    PromoCode, PromoRedemption, PaymentLog, Character,
)


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

    async def get_style_notes(self, user_id: int) -> str | None:
        result = await self.session.execute(
            select(User.style_notes).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_style_notes(self, user_id: int, notes: str) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(style_notes=notes)
        )
        await self.session.commit()

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

    async def get_thread_summary(self, chapter_id: int) -> str | None:
        result = await self.session.execute(
            select(Chapter.thread_summary).where(Chapter.id == chapter_id)
        )
        return result.scalar_one_or_none()

    async def update_thread_summary(self, chapter_id: int, summary: str) -> None:
        await self.session.execute(
            update(Chapter).where(Chapter.id == chapter_id).values(thread_summary=summary)
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
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            if row:
                for name in row:
                    counts[name] = counts.get(name, 0) + 1
        # Return sorted by frequency descending so most important people come first
        return [name for name, _ in sorted(counts.items(), key=lambda x: -x[1])]

    async def get_known_places(self, user_id: int) -> list[str]:
        result = await self.session.execute(
            select(Memory.places).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            if row:
                for place in row:
                    counts[place] = counts.get(place, 0) + 1
        # Return sorted by frequency descending
        return [place for place, _ in sorted(counts.items(), key=lambda x: -x[1])]

    async def get_people_with_counts(self, user_id: int) -> list[tuple[str, int]]:
        """Returns (name, mention_count) sorted by frequency — for rich editor context."""
        result = await self.session.execute(
            select(Memory.people).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            if row:
                for name in row:
                    counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])

    async def get_places_with_counts(self, user_id: int) -> list[tuple[str, int]]:
        """Returns (place, mention_count) sorted by frequency — for rich editor context."""
        result = await self.session.execute(
            select(Memory.places).where(
                Memory.user_id == user_id, Memory.approved == True
            )
        )
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            if row:
                for place in row:
                    counts[place] = counts.get(place, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])

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

    # ── Promo Codes ──

    async def create_promo_code(
        self, code: str, premium_days: int = 90, max_uses: int = 1
    ) -> PromoCode:
        promo = PromoCode(code=code.upper(), premium_days=premium_days, max_uses=max_uses)
        self.session.add(promo)
        await self.session.commit()
        await self.session.refresh(promo)
        return promo

    async def get_promo_code(self, code: str) -> Optional[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code.upper())
        )
        return result.scalar_one_or_none()

    async def redeem_promo_code(self, user_id: int, code: str) -> dict:
        """Try to redeem a promo code. Returns {"ok": bool, "msg": str, "days": int}."""
        promo = await self.get_promo_code(code)
        if not promo:
            return {"ok": False, "msg": "Промокод не найден", "days": 0}
        if not promo.is_active:
            return {"ok": False, "msg": "Промокод больше не активен", "days": 0}
        if promo.used_count >= promo.max_uses:
            return {"ok": False, "msg": "Промокод уже использован максимальное число раз", "days": 0}

        already = await self.session.execute(
            select(PromoRedemption).where(
                PromoRedemption.promo_code_id == promo.id,
                PromoRedemption.user_id == user_id,
            )
        )
        if already.scalar_one_or_none():
            return {"ok": False, "msg": "Вы уже использовали этот промокод", "days": 0}

        promo.used_count += 1
        self.session.add(PromoRedemption(promo_code_id=promo.id, user_id=user_id))

        user = await self.session.execute(select(User).where(User.id == user_id))
        user_obj = user.scalar_one()
        now = datetime.utcnow()
        base = user_obj.premium_until if (user_obj.premium_until and user_obj.premium_until > now) else now
        from datetime import timedelta
        new_until = base + timedelta(days=promo.premium_days)
        user_obj.is_premium = True
        user_obj.premium_until = new_until

        await self.session.commit()
        return {"ok": True, "msg": f"Подписка активирована до {new_until.strftime('%d.%m.%Y')}", "days": promo.premium_days}

    # ── Payment Logs ──

    async def log_payment(
        self, telegram_id: int, provider: str = "tribute", **kwargs
    ) -> PaymentLog:
        log = PaymentLog(telegram_id=telegram_id, provider=provider, **kwargs)
        self.session.add(log)
        await self.session.commit()
        return log

    async def activate_premium_by_telegram_id(self, telegram_id: int, days: int = 90) -> bool:
        """Activate premium for user by telegram_id. Returns True if user found."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return False

        now = datetime.utcnow()
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        from datetime import timedelta
        user.is_premium = True
        user.premium_until = base + timedelta(days=days)
        await self.session.commit()
        return True

    # ── Characters ──

    async def get_characters(self, user_id: int) -> list[Character]:
        result = await self.session.execute(
            select(Character)
            .where(Character.user_id == user_id)
            .order_by(Character.mention_count.desc())
        )
        return list(result.scalars().all())

    async def upsert_character(
        self,
        user_id: int,
        name: str,
        relationship: str | None = None,
        description: str | None = None,
        aliases: list[str] | None = None,
    ) -> Character:
        """Create or update a character by name (case-insensitive) or alias match."""
        # Try exact name match first (case-insensitive)
        result = await self.session.execute(
            select(Character).where(
                Character.user_id == user_id,
                func.lower(Character.name) == name.lower(),
            )
        )
        char = result.scalar_one_or_none()

        # Try alias match if not found by name
        if char is None:
            all_chars = await self.get_characters(user_id)
            for c in all_chars:
                if c.aliases and any(
                    a.lower() == name.lower() for a in c.aliases
                ):
                    char = c
                    break

        if char:
            char.mention_count += 1
            char.last_seen_at = datetime.utcnow()
            if relationship and not char.relationship:
                char.relationship = relationship
            if description and not char.description:
                char.description = description
            if aliases:
                existing = set(char.aliases or [])
                existing.update(aliases)
                char.aliases = list(existing)
        else:
            char = Character(
                user_id=user_id,
                name=name,
                relationship=relationship,
                description=description,
                aliases=aliases or [],
                mention_count=1,
            )
            self.session.add(char)

        await self.session.commit()
        await self.session.refresh(char)
        return char
