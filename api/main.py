from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.database import get_db, create_tables
from db.models import (
    User, Lesson, LessonItem, UserProgress,
    Language, CEFRLevel, LessonType, TaskType
)
from loguru import logger

app = FastAPI(title="LangBot Admin API", version="1.0.0")

api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


@app.on_event("startup")
async def startup():
    await create_tables()
    logger.info("API started")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LessonItemCreate(BaseModel):
    task_type: str
    content: dict
    order_index: int = 0
    is_reviewable: bool = False
    front_text: Optional[str] = None
    back_text: Optional[str] = None


class LessonCreate(BaseModel):
    slug: str
    title: str
    description: Optional[str] = None
    language: str  # "kz" or "en"
    level: str     # "A0", "A1", "A2", "B1"
    lesson_type: str
    scenario_context: Optional[str] = None
    estimated_minutes: int = 15
    xp_reward: int = 10
    order_index: int = 0
    items: list[LessonItemCreate] = []


class UserProgressResponse(BaseModel):
    telegram_id: int
    username: Optional[str]
    full_name: Optional[str]
    target_language: Optional[str]
    current_level: Optional[str]
    streak_days: int
    total_xp: int
    completed_lessons: int
    total_lessons: int

    class Config:
        from_attributes = True


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/users", dependencies=[Depends(verify_api_key)])
async def get_users(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    users = result.scalars().all()

    response = []
    for user in users:
        # Считаем пройденные уроки
        comp_result = await session.execute(
            select(func.count(UserProgress.id)).where(
                UserProgress.user_id == user.id,
                UserProgress.completed == True,
            )
        )
        completed = comp_result.scalar() or 0

        total_result = await session.execute(
            select(func.count(UserProgress.id)).where(UserProgress.user_id == user.id)
        )
        total = total_result.scalar() or 0

        response.append({
            "telegram_id": user.telegram_id,
            "username": user.username,
            "full_name": user.full_name,
            "target_language": user.target_language.value if user.target_language else None,
            "current_level": user.current_level.value if user.current_level else None,
            "streak_days": user.streak_days,
            "total_xp": user.total_xp,
            "completed_lessons": completed,
            "onboarding_done": user.onboarding_done,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        })

    return {"users": response, "total": len(response)}


@app.get("/users/{telegram_id}/progress", dependencies=[Depends(verify_api_key)])
async def get_user_progress(telegram_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    progress_result = await session.execute(
        select(UserProgress, Lesson)
        .join(Lesson, Lesson.id == UserProgress.lesson_id)
        .where(UserProgress.user_id == user.id)
        .order_by(UserProgress.completed_at.desc())
    )
    rows = progress_result.all()

    progress_list = []
    for prog, lesson in rows:
        progress_list.append({
            "lesson_slug": lesson.slug,
            "lesson_title": lesson.title,
            "completed": prog.completed,
            "score": prog.score,
            "completed_at": prog.completed_at.isoformat() if prog.completed_at else None,
        })

    return {
        "user": {
            "telegram_id": user.telegram_id,
            "current_level": user.current_level.value if user.current_level else None,
            "streak_days": user.streak_days,
            "total_xp": user.total_xp,
        },
        "progress": progress_list,
    }


@app.post("/lessons", dependencies=[Depends(verify_api_key)])
async def create_lesson(
    data: LessonCreate,
    session: AsyncSession = Depends(get_db),
):
    # Проверяем, нет ли уже урока с таким slug
    existing = await session.execute(
        select(Lesson).where(Lesson.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Lesson with slug '{data.slug}' already exists")

    # Конвертируем строки в enum
    try:
        language = Language(data.language)
        level = CEFRLevel(data.level)
        lesson_type = LessonType(data.lesson_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    lesson = Lesson(
        slug=data.slug,
        title=data.title,
        description=data.description,
        language=language,
        level=level,
        lesson_type=lesson_type,
        scenario_context=data.scenario_context,
        estimated_minutes=data.estimated_minutes,
        xp_reward=data.xp_reward,
        order_index=data.order_index,
    )
    session.add(lesson)
    await session.flush()

    for item_data in data.items:
        try:
            task_type = TaskType(item_data.task_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid task_type: {item_data.task_type}")

        item = LessonItem(
            lesson_id=lesson.id,
            task_type=task_type,
            content=item_data.content,
            order_index=item_data.order_index,
            is_reviewable=item_data.is_reviewable,
            front_text=item_data.front_text,
            back_text=item_data.back_text,
        )
        session.add(item)

    await session.commit()
    await session.refresh(lesson)

    return {"id": lesson.id, "slug": lesson.slug, "message": "Lesson created"}


@app.get("/lessons", dependencies=[Depends(verify_api_key)])
async def get_lessons(
    language: Optional[str] = None,
    level: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):
    query = select(Lesson)
    if language:
        query = query.where(Lesson.language == Language(language))
    if level:
        query = query.where(Lesson.level == CEFRLevel(level))
    query = query.order_by(Lesson.language, Lesson.level, Lesson.order_index)

    result = await session.execute(query)
    lessons = result.scalars().all()

    return {
        "lessons": [
            {
                "id": l.id,
                "slug": l.slug,
                "title": l.title,
                "language": l.language.value,
                "level": l.level.value,
                "lesson_type": l.lesson_type.value,
                "is_published": l.is_published,
                "order_index": l.order_index,
            }
            for l in lessons
        ]
    }


@app.get("/stats", dependencies=[Depends(verify_api_key)])
async def get_stats(session: AsyncSession = Depends(get_db)):
    user_count = (await session.execute(select(func.count(User.id)))).scalar()
    active_count = (await session.execute(
        select(func.count(User.id)).where(User.onboarding_done == True)
    )).scalar()
    lesson_count = (await session.execute(select(func.count(Lesson.id)))).scalar()
    completed_count = (await session.execute(
        select(func.count(UserProgress.id)).where(UserProgress.completed == True)
    )).scalar()

    return {
        "total_users": user_count,
        "active_users": active_count,
        "total_lessons": lesson_count,
        "total_completions": completed_count,
    }
