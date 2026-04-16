from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import UserRepository
from db.models import Language
from bot.states.states import ReviewStates
from bot.keyboards.keyboards import kb_review_rating, kb_main_menu
from services.learning.service import LearningService
from loguru import logger

router = Router()


@router.message(F.text == "🔄 Повторение")
@router.message(Command("review"))
async def cmd_review(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if not user or not user.onboarding_done:
        await message.answer("Сначала пройди /start.")
        return

    svc = LearningService(session)
    reviews = await svc.get_due_reviews(user.id)

    if not reviews:
        await message.answer(
            "✅ Нет карточек для повторения!\n\n"
            "Все слова в памяти. Пройди новый урок 📚",
            reply_markup=kb_main_menu(),
        )
        return

    await state.set_state(ReviewStates.in_review)
    await state.update_data(
        review_ids=[r.id for r in reviews],
        review_index=0,
        correct_count=0,
    )

    await message.answer(
        f"🔄 <b>Повторение</b>\n\n"
        f"Карточек для повторения: {len(reviews)}\n\n"
        "Я покажу слово или фразу, а ты вспомни перевод. Затем оцени насколько легко вспомнил.",
        parse_mode="HTML",
    )
    await send_review_card(message, state, session, user.id, reviews[0])


async def send_review_card(message_or_cb, state: FSMContext, session: AsyncSession, user_id: int, review):
    """Показываем карточку для повторения (лицевая сторона)."""
    item = review.lesson_item
    front = item.front_text or item.content.get("question", "?")

    target = message_or_cb
    if isinstance(message_or_cb, CallbackQuery):
        target = message_or_cb.message

    await target.answer(
        f"🃏 <b>Что значит:</b>\n\n"
        f"<b>{front}</b>\n\n"
        "Вспомни ответ, затем нажми чтобы увидеть:",
        parse_mode="HTML",
        reply_markup=_kb_show_answer(),
    )
    await state.update_data(current_review_id=review.id)


def _kb_show_answer():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Показать ответ", callback_data="review:show_answer")
    return builder.as_markup()


@router.callback_query(ReviewStates.in_review, F.data == "review:show_answer")
async def on_show_answer(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    review_ids = data.get("review_ids", [])
    index = data.get("review_index", 0)

    if index >= len(review_ids):
        await finish_review(callback.message, state)
        await callback.answer()
        return

    from sqlalchemy import select
    from db.models import Review
    result = await session.execute(
        select(Review).where(Review.id == review_ids[index])
    )
    review = result.scalar_one_or_none()
    if not review:
        await callback.answer()
        return

    item = review.lesson_item
    back = item.back_text or item.content.get("correct_answer", "?")

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ <b>Ответ:</b> {back}\n\n"
        "Насколько легко вспомнил?",
        parse_mode="HTML",
        reply_markup=kb_review_rating(),
    )
    await state.set_state(ReviewStates.rating_card)
    await callback.answer()


@router.callback_query(ReviewStates.rating_card, F.data.startswith("rate:"))
async def on_rate_card(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    rating = int(callback.data.split(":")[1])

    data = await state.get_data()
    review_ids = data.get("review_ids", [])
    index = data.get("review_index", 0)
    correct_count = data.get("correct_count", 0)

    # Обновляем FSRS
    from sqlalchemy import select, update
    from db.models import Review
    from services.spaced_repetition.fsrs import fsrs, FSRSCard
    from datetime import datetime, timezone

    result = await session.execute(
        select(Review).where(Review.id == review_ids[index])
    )
    review = result.scalar_one_or_none()

    if review:
        card = FSRSCard(
            stability=review.stability,
            difficulty=review.difficulty,
            retrievability=review.retrievability,
            reps=review.reps,
            lapses=review.lapses,
            interval_days=review.interval_days,
            state=review.state,
        )
        card.last_reviewed_at = review.last_reviewed_at

        fsrs_result = fsrs.schedule(card, rating)

        await session.execute(
            update(Review).where(Review.id == review.id).values(
                stability=fsrs_result.card.stability,
                difficulty=fsrs_result.card.difficulty,
                retrievability=fsrs_result.card.retrievability,
                reps=fsrs_result.card.reps,
                lapses=fsrs_result.card.lapses,
                interval_days=fsrs_result.interval_days,
                state=fsrs_result.card.state,
                due_at=fsrs_result.next_due,
                last_reviewed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    if rating >= 3:
        correct_count += 1

    next_index = index + 1
    await state.update_data(review_index=next_index, correct_count=correct_count)

    await callback.message.delete()

    if next_index >= len(review_ids):
        await finish_review(callback.message, state, len(review_ids), correct_count)
    else:
        # Следующая карточка
        result = await session.execute(
            select(Review).where(Review.id == review_ids[next_index])
        )
        next_review = result.scalar_one_or_none()
        if next_review:
            await state.set_state(ReviewStates.in_review)
            await send_review_card(callback.message, state, session, callback.from_user.id, next_review)

    await callback.answer()


async def finish_review(message, state: FSMContext, total: int = 0, correct: int = 0):
    await state.clear()
    pct = int(correct / total * 100) if total > 0 else 0
    await message.answer(
        f"🎉 <b>Повторение завершено!</b>\n\n"
        f"Карточек: {total}\n"
        f"Правильно: {correct} ({pct}%)\n\n"
        "Слова закреплены в памяти 🧠",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )
