from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Kanji(Base):
    __tablename__ = "kanji"

    character: Mapped[str] = mapped_column(String(8), primary_key=True)
    level: Mapped[str] = mapped_column(String(2), index=True)
    meanings: Mapped[list[str]] = mapped_column(JSON, default=list)
    onyomi: Mapped[list[str]] = mapped_column(JSON, default=list)
    kunyomi: Mapped[list[str]] = mapped_column(JSON, default=list)
    stroke_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meanings: Mapped[list[str]] = mapped_column(JSON, default=list)
    jlpt_level: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="jisho")


class Bunpou(Base):
    __tablename__ = "bunpou"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(2), index=True)
    title: Mapped[str] = mapped_column(String(255), unique=True)
    explanation: Mapped[str] = mapped_column(Text)
    examples: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)


class UserItemProgress(Base):
    __tablename__ = "user_item_progress"
    __table_args__ = (
        UniqueConstraint("learner_id", "item_type", "item_id", name="uq_learner_item_progress"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(100), default="demo", index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(255))
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
