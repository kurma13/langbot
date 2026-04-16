from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal
from core.config import settings
from db.repositories import UserRepository, ReviewRepository
from db.models import UserStatus
from loguru import logger
import pytz
from datetime import datetime, timezone


scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)


async def send_daily_reminders(bot):
    """
    Рассылает ежедневные напоминания всем активным пользователям.
    Запускается каждый час, проверяет у кого сейчас нужное время.
    """
    current_hour = datetime.now(pytz.timezone(settings.TIMEZONE)).hour

    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        review_repo = ReviewRepository(session)

        users = await user_repo.get_all_active_with_notifications()

        for user in users:
            if user.notify_hour != current_hour:
                continue

            try:
                due_count = await review_repo.count_due_today(user.id)

                if due_count > 0:
                    text = (
                        f"👋 Привет! Время учиться!\n\n"
                        f"🔄 У тебя <b>{due_count}</b> слов для повторения.\n"
                        f"⏱ Займёт ~5 минут. Вперёд! 💪"
                    )
                else:
                    text = (
                        "📚 Время нового урока!\n\n"
                        "Всего 10–15 минут, и ты на шаг ближе к цели. 🚀"
                    )

                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
                logger.info(f"Reminder sent to user {user.telegram_id}")

            except Exception as e:
                logger.error(f"Failed to send reminder to {user.telegram_id}: {e}")


async def reset_streaks(bot):
    """
    Проверяет стрики ночью.
    Если пользователь не проходил урок 2+ дней — сбрасываем стрик.
    """
    from sqlalchemy import update, select
    from db.models import User
    from datetime import timedelta

    async with AsyncSessionLocal() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        result = await session.execute(
            select(User).where(
                User.last_lesson_at < cutoff,
                User.streak_days > 0,
            )
        )
        users = result.scalars().all()

        for user in users:
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(streak_days=0)
            )
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=(
                        "💔 Ой! Твой стрик сброшен — ты пропустил занятия.\n\n"
                        "Не расстраивайся — начни новую серию сегодня! 🔥"
                    ),
                )
            except Exception:
                pass

        await session.commit()
        logger.info(f"Reset streaks for {len(users)} users")


def setup_scheduler(bot):
    """Регистрируем все задачи планировщика."""

    # Напоминания каждый час в :00
    scheduler.add_job(
        send_daily_reminders,
        trigger=CronTrigger(minute=0),
        args=[bot],
        id="daily_reminders",
        replace_existing=True,
    )

    # Сброс стриков в 00:05
    scheduler.add_job(
        reset_streaks,
        trigger=CronTrigger(hour=0, minute=5),
        args=[bot],
        id="reset_streaks",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
