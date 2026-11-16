from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


DEMO_LEARNER_ID = "demo"


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'sensei')", name="ck_app_users_role"),
    )

    auth_user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="student")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


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


class TranslationCache(Base):
    __tablename__ = "translation_cache"
    __table_args__ = (
        UniqueConstraint(
            "source_text",
            "source_language",
            "target_language",
            name="uq_translation_cache_language_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_text: Mapped[str] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(String(5), default="en")
    target_language: Mapped[str] = mapped_column(String(5))
    translated_text: Mapped[str] = mapped_column(Text)


class Bunpou(Base):
    __tablename__ = "bunpou"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(2), index=True)
    title: Mapped[str] = mapped_column(String(255), unique=True)
    explanation: Mapped[str] = mapped_column(Text)
    examples: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)


class LearningCategory(Base):
    __tablename__ = "learning_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class LearningMaterial(Base):
    __tablename__ = "learning_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_categories.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("app_users.auth_user_id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(String(1000), default="")
    content: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_categories.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("app_users.auth_user_id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1000), default="")
    published: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('multiple_choice', 'written')",
            name="ck_quiz_questions_type",
        ),
        CheckConstraint("points > 0", name="ck_quiz_questions_points"),
        UniqueConstraint("quiz_id", "position", name="uq_quiz_question_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20))
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer_key: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=1)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('needs_review', 'graded')", name="ck_quiz_attempt_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="RESTRICT"), index=True
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.auth_user_id", ondelete="RESTRICT"), index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default="graded")
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="RESTRICT")
    )
    response: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserItemProgress(Base):
    __tablename__ = "user_item_progress"
    __table_args__ = (
        UniqueConstraint("learner_id", "item_type", "item_id", name="uq_learner_item_progress"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(100), default=DEMO_LEARNER_ID, index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(255))
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
