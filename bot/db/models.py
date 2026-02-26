from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    memories_count = Column(Integer, default=0)
    questions_asked_count = Column(Integer, default=0)
    style_notes = Column(Text, nullable=True)  # cumulative author style profile

    chapters = relationship("Chapter", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    question_logs = relationship("QuestionLog", back_populates="user", cascade="all, delete-orphan")
    topic_coverages = relationship("TopicCoverage", back_populates="user", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="user", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    period_hint = Column(String(255), nullable=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    thread_summary = Column(Text, nullable=True)  # running digest of chapter content

    user = relationship("User", back_populates="chapters")
    memories = relationship("Memory", back_populates="chapter")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)

    audio_file_id = Column(String(500), nullable=True)
    raw_transcript = Column(Text, nullable=True)
    cleaned_transcript = Column(Text, nullable=True)
    edited_memoir_text = Column(Text, nullable=True)
    title = Column(String(500), nullable=True)

    time_hint_type = Column(String(50), nullable=True)
    time_hint_value = Column(String(255), nullable=True)
    time_confidence = Column(Float, nullable=True)

    tags = Column(JSON, default=list)
    people = Column(JSON, default=list)
    places = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    approved = Column(Boolean, default=False)
    source_question_id = Column(String(100), nullable=True)

    # Clarification loop state (stored in DB so it survives bot restarts)
    clarification_thread = Column(Text, nullable=True)   # JSON list of {role, text}
    clarification_round = Column(Integer, default=0)     # 0 = no pending, 1-3 = waiting

    user = relationship("User", back_populates="memories")
    chapter = relationship("Chapter", back_populates="memories")


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)       # canonical name, e.g. "Мария"
    aliases = Column(JSON, default=list)             # ["Маша", "жена", "мама Маша"]
    relation_to_author = Column("relationship", String(255), nullable=True)  # "жена", "дядя", "сосед"
    description = Column(Text, nullable=True)        # brief context snippet
    mention_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="characters")


class Question(Base):
    __tablename__ = "questions"

    id = Column(String(100), primary_key=True)
    pack = Column(String(100), nullable=False, index=True)
    text = Column(Text, nullable=False)
    difficulty = Column(String(20), default="easy")
    emotional_intensity = Column(String(20), default="low")
    tags = Column(JSON, default=list)
    followups = Column(JSON, default=list)


class QuestionLog(Base):
    __tablename__ = "question_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(String(100), ForeignKey("questions.id"), nullable=False)
    asked_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="asked")
    answered_memory_id = Column(Integer, ForeignKey("memories.id"), nullable=True)

    user = relationship("User", back_populates="question_logs")
    question = relationship("Question")


class TopicCoverage(Base):
    __tablename__ = "topic_coverage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tag = Column(String(100), nullable=False)
    count = Column(Integer, default=0)
    last_used_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="topic_coverages")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    premium_days = Column(Integer, default=90)
    max_uses = Column(Integer, default=1)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    redeemed_at = Column(DateTime, default=datetime.utcnow)


class PaymentLog(Base):
    __tablename__ = "payment_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, nullable=False)
    provider = Column(String(50), default="tribute")
    product = Column(String(100), nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
