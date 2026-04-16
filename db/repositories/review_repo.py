from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm import selectinload
from db.models import Review, UserProgress, Attempt, AttemptResult
from typing import Optional
from datetime import datetime, timezone


class ReviewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_due_reviews(
        self,
        user_id: int,
        limit: int = 20,
    ) -> list[Review]:
        """Получить карточки, которые нужно повторить сегодня."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Review)
            .options(selectinload(Review.lesson_item))
            .where(
                and_(
                    Review.user_id == user_id,
                    Review.due_at <= now,
                )
            )
            .order_by(Review.due_at)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_or_create(
        self,
        user_id: int,
        lesson_item_id: int,
        due_at: datetime,
    ) -> tuple[Review, bool]:
        result = await self.session.execute(
            select(Review).where(
                and_(
                    Review.user_id == user_id,
                    Review.lesson_item_id == lesson_item_id,
                )
            )
        )
        review = result.scalar_one_or_none()
        if review:
            return review, False

        review = Review(
            user_id=user_id,
            lesson_item_id=lesson_item_id,
            due_at=due_at,
        )
        self.session.add(review)
        await self.session.flush()
        return review, True

    async def update_review(self, review_id: int, **kwargs):
        await self.session.execute(
            update(Review).where(Review.id == review_id).values(**kwargs)
        )
        await self.session.flush()

    async def count_due_today(self, user_id: int) -> int:
        from sqlalchemy import func
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(func.count(Review.id)).where(
                and_(
                    Review.user_id == user_id,
                    Review.due_at <= now,
                )
            )
        )
        return result.scalar() or 0


class ProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int, lesson_id: int) -> Optional[UserProgress]:
        result = await self.session.execute(
            select(UserProgress).where(
                and_(
                    UserProgress.user_id == user_id,
                    UserProgress.lesson_id == lesson_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def start_lesson(self, user_id: int, lesson_id: int) -> UserProgress:
        progress = await self.get(user_id, lesson_id)
        if not progress:
            progress = UserProgress(
                user_id=user_id,
                lesson_id=lesson_id,
                started_at=datetime.now(timezone.utc),
                attempts_count=1,
            )
            self.session.add(progress)
        else:
            progress.attempts_count += 1
            progress.started_at = datetime.now(timezone.utc)
        await self.session.flush()
        return progress

    async def complete_lesson(
        self,
        user_id: int,
        lesson_id: int,
        score: float,
    ) -> UserProgress:
        progress = await self.get(user_id, lesson_id)
        if not progress:
            progress = UserProgress(user_id=user_id, lesson_id=lesson_id)
            self.session.add(progress)

        progress.completed = True
        progress.score = score
        progress.best_score = max(progress.best_score, score)
        progress.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return progress

    async def get_user_stats(self, user_id: int) -> dict:
        from sqlalchemy import func
        result = await self.session.execute(
            select(
                func.count(UserProgress.id).label("total"),
                func.sum(
                    func.cast(UserProgress.completed, type_=None)
                ).label("completed"),
            ).where(UserProgress.user_id == user_id)
        )
        row = result.one()
        return {
            "total_started": row.total or 0,
            "total_completed": row.completed or 0,
        }


class AttemptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(
        self,
        user_id: int,
        lesson_item_id: int,
        result: AttemptResult,
        user_answer: Optional[str] = None,
        rating: Optional[int] = None,
        time_spent_ms: Optional[int] = None,
    ) -> Attempt:
        attempt = Attempt(
            user_id=user_id,
            lesson_item_id=lesson_item_id,
            result=result,
            user_answer=user_answer,
            rating=rating,
            time_spent_ms=time_spent_ms,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt
