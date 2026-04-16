from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from db.models import User, UserStatus
from typing import Optional
from datetime import datetime, timezone


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language_code=language_code,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Обновляем данные при каждом обращении
            user.username = username
            user.full_name = full_name
            user.last_active_at = datetime.now(timezone.utc)
            await self.session.flush()
            return user, False
        user = await self.create(telegram_id, username, full_name, language_code)
        return user, True

    async def update_field(self, user_id: int, **kwargs):
        await self.session.execute(
            update(User).where(User.id == user_id).values(**kwargs)
        )
        await self.session.flush()

    async def get_all_active_with_notifications(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(
                User.status == UserStatus.ACTIVE,
                User.notifications_enabled == True,
                User.onboarding_done == True,
            )
        )
        return result.scalars().all()

    async def increment_streak(self, user_id: int):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                streak_days=User.streak_days + 1,
                last_lesson_at=datetime.now(timezone.utc),
            )
        )
        await self.session.flush()

    async def add_xp(self, user_id: int, xp: int):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(total_xp=User.total_xp + xp)
        )
        await self.session.flush()
