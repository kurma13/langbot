from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.repositories import UserRepository
from db.models import UserProgress, Lesson, Language, Review
from bot.states.states import SettingsStates
from bot.keyboards.keyboards import kb_main_menu, kb_settings, kb_choose_language
from datetime import datetime, timezone
from loguru import logger

router = Router()


@router.message(F.text == "📊 Прогресс")
@router.message(Command("progress"))
async def cmd_progress(message: Message, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if not user:
        await message.answer("Сначала пройди /start.")
        return

    # Всего начато уроков
    total_result = await session.execute(
        select(func.count(UserProgress.id)).where(UserProgress.user_id == user.id)
    )
    total = total_result.scalar() or 0

    # Завершённых уроков
    completed_result = await session.execute(
        select(func.count(UserProgress.id)).where(
            UserProgress.user_id == user.id,
            UserProgress.completed == True,
        )
    )
    completed = completed_result.scalar() or 0

    # Повторения
    due_count_result = await session.execute(
        select(func.count(Review.id)).where(
            Review.user_id == user.id,
            Review.due_at <= datetime.now(timezone.utc),
        )
    )
    due_count = due_count_result.scalar() or 0

    total_reviews_result = await session.execute(
        select(func.count(Review.id)).where(Review.user_id == user.id)
    )
    total_reviews = total_reviews_result.scalar() or 0

    lang_emoji = "🇰🇿" if user.target_language == Language.KAZAKH else "🇬🇧"
    lang_name = "Казахский" if user.target_language == Language.KAZAKH else "Английский"

    level_display = {
        "A0": "A0 ▓░░░░ A1",
        "A1": "A1 ▓▓░░░ A2",
        "A2": "A2 ▓▓▓░░ B1",
        "B1": "B1 ▓▓▓▓▓ ✅",
    }
    level_bar = level_display.get(user.current_level.value if user.current_level else "A0", "")

    text = (
        f"📊 <b>Твой прогресс</b>\n\n"
        f"{lang_emoji} Язык: <b>{lang_name}</b>\n"
        f"📈 Уровень: <b>{user.current_level.value if user.current_level else 'A0'}</b>\n"
        f"    {level_bar}\n\n"
        f"📚 Уроков пройдено: <b>{completed}</b> / {total}\n"
        f"🔄 Слов для повторения: <b>{due_count}</b>\n"
        f"🃏 Всего карточек: <b>{total_reviews}</b>\n\n"
        f"🔥 Стрик: <b>{user.streak_days}</b> дней\n"
        f"⭐ Всего XP: <b>{user.total_xp}</b>\n"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb_main_menu())


@router.message(F.text == "⚙️ Настройки")
@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if not user:
        await message.answer("Сначала пройди /start.")
        return

    notif_status = "🔔 Включены" if user.notifications_enabled else "🔕 Выключены"
    lang_name = "Казахский 🇰🇿" if user.target_language == Language.KAZAKH else "Английский 🇬🇧"

    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"🌍 Язык обучения: <b>{lang_name}</b>\n"
        f"🔔 Уведомления: <b>{notif_status}</b>\n"
        f"⏰ Время напоминания: <b>{user.notify_hour:02d}:00</b>",
        parse_mode="HTML",
        reply_markup=kb_settings(),
    )
    await state.set_state(SettingsStates.main)


@router.callback_query(SettingsStates.main, F.data == "settings:notify")
async def on_settings_notify(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⏰ В какое время присылать напоминание?\n\n"
        "Напиши число от 0 до 23 (час)\n"
        "Например: <code>9</code> — напоминание в 09:00",
        parse_mode="HTML",
    )
    await state.set_state(SettingsStates.changing_notify_time)
    await callback.answer()


@router.message(SettingsStates.changing_notify_time)
async def on_notify_time_input(message: Message, state: FSMContext, session: AsyncSession):
    try:
        hour = int(message.text.strip())
        if not (0 <= hour <= 23):
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число от 0 до 23")
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    await user_repo.update_field(user.id, notify_hour=hour)

    await state.set_state(SettingsStates.main)
    await message.answer(
        f"✅ Напоминание установлено на <b>{hour:02d}:00</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


@router.callback_query(SettingsStates.main, F.data == "settings:language")
async def on_settings_language(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌍 Выбери язык для изучения.\n\n"
        "⚠️ Это сбросит твой текущий прогресс!",
        reply_markup=kb_choose_language(),
    )
    await state.set_state(SettingsStates.main)
    await callback.answer()


@router.callback_query(SettingsStates.main, F.data == "settings:stats")
async def on_settings_stats(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await callback.message.delete()
    await cmd_progress(callback.message, session)
    await callback.answer()
