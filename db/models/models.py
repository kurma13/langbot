from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, JSON, BigInteger, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum
from datetime import datetime


# ─── Enums ────────────────────────────────────────────────────────────────────

class Language(str, enum.Enum):
    KAZAKH = "kz"
    ENGLISH = "en"


class CEFRLevel(str, enum.Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"


class LessonType(str, enum.Enum):
    VOCABULARY = "vocabulary"
    DIALOGUE = "dialogue"
    GRAMMAR = "grammar"
    ENDINGS = "endings"      # Казахские окончания
    CHUNKS = "chunks"        # Английские chunks
    SCENARIO = "scenario"    # Ситуационные уроки


class TaskType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"    # Выбор ответа
    PHRASE_BUILD = "phrase_build"          # Сборка фразы
    TRANSLATION = "translation"            # Перевод
    VOICE = "voice"                        # Голосовой ответ
    FILL_BLANK = "fill_blank"             # Вставить пропуск


class AttemptResult(str, enum.Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    SKIP = "skip"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    language_code = Column(String(10), nullable=True)  # telegram language

    # Learning settings
    target_language = Column(Enum(Language), nullable=True)
    current_level = Column(Enum(CEFRLevel), default=CEFRLevel.A0, nullable=False)
    streak_days = Column(Integer, default=0)
    total_xp = Column(Integer, default=0)

    # Onboarding
    placement_done = Column(Boolean, default=False)
    onboarding_done = Column(Boolean, default=False)

    # Notifications
    notifications_enabled = Column(Boolean, default=True)
    notify_hour = Column(Integer, default=9)   # 09:00 local time
    timezone = Column(String(50), default="Asia/Almaty")

    # Status
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    last_lesson_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    attempts = relationship("Attempt", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")
    current_lesson_state = relationship("UserLessonState", back_populates="user", uselist=False, cascade="all, delete-orphan")


# ─── Lesson ───────────────────────────────────────────────────────────────────

class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    language = Column(Enum(Language), nullable=False, index=True)
    level = Column(Enum(CEFRLevel), nullable=False, index=True)
    lesson_type = Column(Enum(LessonType), nullable=False)

    order_index = Column(Integer, default=0)  # порядок в учебном плане
    is_published = Column(Boolean, default=True)

    # Scenario context (for scenario-based lessons)
    scenario_context = Column(Text, nullable=True)  # "В кафе", "На работе"
    scenario_image_url = Column(String(500), nullable=True)

    # Metadata
    estimated_minutes = Column(Integer, default=15)
    xp_reward = Column(Integer, default=10)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("LessonItem", back_populates="lesson", cascade="all, delete-orphan", order_by="LessonItem.order_index")
    progress_records = relationship("UserProgress", back_populates="lesson")

    __table_args__ = (
        Index("ix_lessons_lang_level", "language", "level"),
    )


class LessonItem(Base):
    """
    Один элемент урока: слово, фраза, задание, диалог.
    content хранит всю логику в JSON — гибко и расширяемо.
    """
    __tablename__ = "lesson_items"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, default=0)

    task_type = Column(Enum(TaskType), nullable=False)
    content = Column(JSON, nullable=False)
    """
    Структура content по типу задания:

    MULTIPLE_CHOICE:
    {
        "question": "Как будет 'яблоко'?",
        "question_kz": "...",       # Если нужен перевод вопроса
        "options": ["алма", "нан", "су", "ет"],
        "correct_index": 0,
        "explanation": "Алма — это яблоко на казахском"
    }

    PHRASE_BUILD:
    {
        "instruction": "Составь фразу: Я иду домой",
        "words": ["Мен", "үйге", "бардым", "кеттім", "жүрмін"],
        "correct_order": [0, 1, 3],  # индексы слов в правильном порядке
        "correct_phrase": "Мен үйге кеттім"
    }

    TRANSLATION:
    {
        "source_text": "Я хочу воды",
        "source_lang": "ru",
        "target_lang": "kz",
        "correct_answer": "Мен су ішкім келеді",
        "acceptable_answers": ["Маған су керек"],
        "hint": "Используй конструкцию -кім келеді"
    }

    VOICE:
    {
        "prompt": "Скажи: 'Қалайсыз?'",
        "expected_text": "Қалайсыз",
        "phonetic_hint": "Кала-й-суз",
        "similarity_threshold": 0.75
    }

    FILL_BLANK:
    {
        "template": "Мен мектепке ___ бардым",
        "options": ["жаяу", "машинамен", "автобуспен"],
        "correct_index": 0,
        "explanation": "жаяу = пешком"
    }
    """

    # Карточка для spaced repetition
    is_reviewable = Column(Boolean, default=False)  # слова/фразы для повторения
    front_text = Column(String(500), nullable=True)  # что показываем
    back_text = Column(String(500), nullable=True)   # правильный ответ

    lesson = relationship("Lesson", back_populates="items")
    reviews = relationship("Review", back_populates="lesson_item")


# ─── UserProgress ─────────────────────────────────────────────────────────────

class UserProgress(Base):
    """Прогресс пользователя по конкретному уроку."""
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)

    completed = Column(Boolean, default=False)
    score = Column(Float, default=0.0)        # 0.0 – 1.0
    attempts_count = Column(Integer, default=0)
    best_score = Column(Float, default=0.0)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="progress")
    lesson = relationship("Lesson", back_populates="progress_records")

    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson"),
        Index("ix_user_progress_user", "user_id"),
    )


# ─── Review (Spaced Repetition) ───────────────────────────────────────────────

class Review(Base):
    """
    FSRS-подобная система повторений.
    Каждая запись — одна карточка для одного пользователя.
    """
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_item_id = Column(Integer, ForeignKey("lesson_items.id", ondelete="CASCADE"), nullable=False)

    # FSRS алгоритм параметры
    stability = Column(Float, default=1.0)    # S — стабильность памяти
    difficulty = Column(Float, default=5.0)   # D — сложность карточки (1–10)
    retrievability = Column(Float, default=1.0)  # R — вероятность вспомнить
    reps = Column(Integer, default=0)         # количество повторений
    lapses = Column(Integer, default=0)       # количество забываний

    # Планировщик
    due_at = Column(DateTime(timezone=True), nullable=False)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    interval_days = Column(Float, default=1.0)  # текущий интервал

    state = Column(String(20), default="new")  # new | learning | review | relearning

    user = relationship("User", back_populates="reviews")
    lesson_item = relationship("LessonItem", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("user_id", "lesson_item_id", name="uq_user_item_review"),
        Index("ix_reviews_due", "user_id", "due_at"),
    )


# ─── Attempt ──────────────────────────────────────────────────────────────────

class Attempt(Base):
    """Каждая попытка ответа на задание."""
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_item_id = Column(Integer, ForeignKey("lesson_items.id"), nullable=False)

    result = Column(Enum(AttemptResult), nullable=False)
    user_answer = Column(Text, nullable=True)   # что ответил пользователь
    time_spent_ms = Column(Integer, nullable=True)

    # Для spaced repetition — рейтинг 1-4 (Again, Hard, Good, Easy)
    rating = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="attempts")

    __table_args__ = (
        Index("ix_attempts_user_item", "user_id", "lesson_item_id"),
    )


# ─── UserLessonState ──────────────────────────────────────────────────────────

class UserLessonState(Base):
    """
    Текущее состояние активного урока пользователя.
    Хранит, на каком шаге урока находится пользователь.
    """
    __tablename__ = "user_lesson_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)

    current_item_index = Column(Integer, default=0)
    item_ids = Column(JSON, nullable=False)   # список ID заданий урока
    correct_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="current_lesson_state")
