from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from db.models import Lesson, LessonItem, UserProgress, Language, CEFRLevel
from typing import Optional


class LessonRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, lesson_id: int) -> Optional[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .options(selectinload(Lesson.items))
            .where(Lesson.id == lesson_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .options(selectinload(Lesson.items))
            .where(Lesson.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_lessons_for_level(
        self,
        language: Language,
        level: CEFRLevel,
    ) -> list[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .where(
                and_(
                    Lesson.language == language,
                    Lesson.level == level,
                    Lesson.is_published == True,
                )
            )
            .order_by(Lesson.order_index)
        )
        return result.scalars().all()

    async def get_next_lesson(
        self,
        user_id: int,
        language: Language,
        level: CEFRLevel,
    ) -> Optional[Lesson]:
        """Получить следующий непройденный урок."""
        # Урок считается пройденным если есть запись с completed=True
        completed_subq = (
            select(UserProgress.lesson_id)
            .where(
                and_(
                    UserProgress.user_id == user_id,
                    UserProgress.completed == True,
                )
            )
            .scalar_subquery()
        )

        result = await self.session.execute(
            select(Lesson)
            .options(selectinload(Lesson.items))
            .where(
                and_(
                    Lesson.language == language,
                    Lesson.level == level,
                    Lesson.is_published == True,
                    Lesson.id.notin_(completed_subq),
                )
            )
            .order_by(Lesson.order_index)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Lesson:
        lesson = Lesson(**kwargs)
        self.session.add(lesson)
        await self.session.flush()
        await self.session.refresh(lesson)
        return lesson

    async def add_item(self, lesson_id: int, **kwargs) -> LessonItem:
        item = LessonItem(lesson_id=lesson_id, **kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def count_completed(self, user_id: int, language: Language) -> int:
        result = await self.session.execute(
            select(func.count(UserProgress.id))
            .join(Lesson, Lesson.id == UserProgress.lesson_id)
            .where(
                and_(
                    UserProgress.user_id == user_id,
                    UserProgress.completed == True,
                    Lesson.language == language,
                )
            )
        )
        return result.scalar() or 0
