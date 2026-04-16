from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Voice
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.repositories import UserRepository
from db.models import User, LessonItem, TaskType, Language, UserLessonState
from bot.states.states import LessonStates
from bot.keyboards.keyboards import (
    kb_multiple_choice, kb_phrase_build, kb_translation_check,
    kb_voice_or_text, kb_after_correct, kb_after_incorrect,
    kb_lesson_complete, kb_main_menu,
)
from services.learning.service import LearningService
from services.voice.stt import process_voice_message
from utils.texts import format_task, format_lesson_intro
from loguru import logger

router = Router()


# ─── /lesson command & menu button ───────────────────────────────────────────

@router.message(F.text == "📚 Урок")
@router.message(Command("lesson"))
async def cmd_lesson(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)

    if not user or not user.onboarding_done:
        await message.answer("Сначала пройди /start для настройки бота.")
        return

    svc = LearningService(session)

    # Проверяем повторения
    due_reviews = await svc.get_due_reviews(user.id)
    if due_reviews:
        await message.answer(
            f"🔄 У тебя {len(due_reviews)} слов для повторения!\n"
            "Рекомендую сначала повторить, потом перейти к новому уроку.",
            reply_markup=kb_main_menu(),
        )

    lesson = await svc.get_next_lesson(user)
    if not lesson:
        await message.answer(
            "🎉 Все уроки пройдены!\nПовтори слова или подожди новых уроков.",
            reply_markup=kb_main_menu(),
        )
        return

    # Показываем превью урока
    intro_text = format_lesson_intro(lesson)
    await message.answer(intro_text, parse_mode="HTML", reply_markup=kb_main_menu())

    # Стартуем урок
    state_obj = await svc.start_lesson(user, lesson)
    await state.set_state(LessonStates.in_lesson)
    await state.update_data(user_id=user.id, lesson_id=lesson.id)

    # Отправляем первое задание
    await send_current_task(message, session, user, state)


async def send_current_task(message_or_callback, session: AsyncSession, user: User, state: FSMContext):
    """Отправляет текущее задание урока."""
    svc = LearningService(session)
    result = await svc.get_current_item(user.id)

    if not result:
        await _finish_lesson(message_or_callback, session, user, state)
        return

    state_obj, item = result

    # Прогресс
    progress_text = f"📍 {state_obj.current_item_index + 1}/{state_obj.total_count}"
    task_text, markup = format_task(item, progress_text)

    target = message_or_callback
    if isinstance(message_or_callback, CallbackQuery):
        target = message_or_callback.message

    if item.task_type == TaskType.VOICE:
        await state.set_state(LessonStates.waiting_voice_answer)
    elif item.task_type == TaskType.TRANSLATION:
        await state.set_state(LessonStates.waiting_text_answer)
    else:
        await state.set_state(LessonStates.in_lesson)

    await target.answer(task_text, parse_mode="HTML", reply_markup=markup)


# ─── Ответ на Multiple Choice / Fill Blank ───────────────────────────────────

@router.callback_query(LessonStates.in_lesson, F.data.startswith("ans:"))
async def on_choice_answer(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    svc = LearningService(session)

    result = await svc.get_current_item(user.id)
    if not result:
        await callback.answer()
        return

    _, item = result
    answer_data = callback.data.split(":")[1]

    if answer_data == "skip":
        is_correct, explanation, is_complete = await svc.submit_answer(user, item, "__skip__", rating=1)
    else:
        is_correct, explanation, is_complete = await svc.submit_answer(user, item, answer_data)

    await callback.message.delete()
    await _show_answer_result(callback.message, state, session, user, is_correct, explanation, is_complete, item)
    await callback.answer()


# ─── Ответ на перевод (текстовый) ────────────────────────────────────────────

@router.message(LessonStates.waiting_text_answer)
async def on_text_answer(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    svc = LearningService(session)

    result = await svc.get_current_item(user.id)
    if not result:
        return

    _, item = result
    is_correct, explanation, is_complete = await svc.submit_answer(user, item, message.text)
    await _show_answer_result(message, state, session, user, is_correct, explanation, is_complete, item)


# ─── Ответ голосом ────────────────────────────────────────────────────────────

@router.callback_query(LessonStates.waiting_voice_answer, F.data == "voice:text")
async def on_voice_prefer_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LessonStates.waiting_text_answer)
    await callback.message.edit_text(
        callback.message.text + "\n\n<i>Напиши текстом 👇</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer()


@router.message(LessonStates.waiting_voice_answer, F.voice)
async def on_voice_message(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    svc = LearningService(session)

    result = await svc.get_current_item(user.id)
    if not result:
        return

    _, item = result
    content = item.content
    expected_text = content.get("expected_text", "")

    # Определяем язык для STT
    lang_code = "kk-KZ" if user.target_language == Language.KAZAKH else "en-US"

    await message.answer("🎤 Обрабатываю твой голос...")
    is_correct, transcript = await process_voice_message(
        bot=message.bot,
        file_id=message.voice.file_id,
        expected_text=expected_text,
        language_code=lang_code,
        threshold=content.get("similarity_threshold", 0.75),
    )

    if transcript:
        await message.answer(f"🗣 Я услышал: <i>{transcript}</i>", parse_mode="HTML")

    is_correct_submit, explanation, is_complete = await svc.submit_answer(
        user, item, transcript or "", rating=3 if is_correct else 1
    )
    await _show_answer_result(message, state, session, user, is_correct, explanation, is_complete, item)


# ─── Сборка фразы ─────────────────────────────────────────────────────────────

@router.callback_query(LessonStates.in_lesson, F.data.startswith("word:"))
async def on_word_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    selected = data.get("phrase_selected", [])

    word_idx = int(callback.data.split(":")[1])
    if word_idx in selected:
        selected.remove(word_idx)
    else:
        selected.append(word_idx)

    await state.update_data(phrase_selected=selected)

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    svc = LearningService(session)

    result = await svc.get_current_item(user.id)
    if not result:
        await callback.answer()
        return

    _, item = result
    words = item.content.get("words", [])
    selected_text = " ".join(words[i] for i in selected if i < len(words))

    await callback.message.edit_reply_markup(
        reply_markup=kb_phrase_build(words, selected)
    )
    await callback.answer(f"Фраза: {selected_text}" if selected_text else "Выбери слова")


@router.callback_query(LessonStates.in_lesson, F.data == "phrase:reset")
async def on_phrase_reset(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.update_data(phrase_selected=[])
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    svc = LearningService(session)
    result = await svc.get_current_item(user.id)
    if result:
        _, item = result
        words = item.content.get("words", [])
        await callback.message.edit_reply_markup(reply_markup=kb_phrase_build(words, []))
    await callback.answer("Сброшено")


@router.callback_query(LessonStates.in_lesson, F.data == "phrase:submit")
async def on_phrase_submit(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    selected = data.get("phrase_selected", [])

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    svc = LearningService(session)

    result = await svc.get_current_item(user.id)
    if not result:
        await callback.answer()
        return

    _, item = result
    words = item.content.get("words", [])
    user_phrase = " ".join(words[i] for i in selected if i < len(words))

    is_correct, explanation, is_complete = await svc.submit_answer(user, item, user_phrase)
    await state.update_data(phrase_selected=[])
    await callback.message.delete()
    await _show_answer_result(callback.message, state, session, user, is_correct, explanation, is_complete, item)
    await callback.answer()


# ─── Continue button ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "next:continue")
async def on_next_continue(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)

    await callback.message.delete()
    await state.set_state(LessonStates.in_lesson)
    await send_current_task(callback, session, user, state)
    await callback.answer()


@router.callback_query(F.data == "lesson:next")
async def on_lesson_next(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.message.delete()
    await state.clear()
    # Перенаправляем на начало нового урока
    fake_msg = callback.message
    fake_msg.from_user = callback.from_user
    await cmd_lesson(callback.message, state, session)
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def on_menu_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 Главное меню")
    await callback.message.answer("Выбери действие:", reply_markup=kb_main_menu())
    await callback.answer()


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _show_answer_result(
    message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    is_correct: bool,
    explanation: str,
    is_complete: bool,
    item: LessonItem,
):
    if is_complete:
        await _finish_lesson(message, session, user, state)
        return

    if is_correct:
        text = "✅ <b>Правильно!</b>"
        if explanation:
            text += f"\n\n💡 {explanation}"
        await message.answer(text, parse_mode="HTML", reply_markup=kb_after_correct())
    else:
        correct_answer = _get_correct_answer(item)
        text = f"❌ <b>Неправильно.</b>"
        if correct_answer:
            text += f"\n\n✅ Правильный ответ: <code>{correct_answer}</code>"
        if explanation:
            text += f"\n\n💡 {explanation}"
        await message.answer(text, parse_mode="HTML", reply_markup=kb_after_incorrect(correct_answer))


async def _finish_lesson(message, session: AsyncSession, user: User, state: FSMContext):
    """Завершаем урок, показываем результат."""
    from db.repositories import ProgressRepository
    progress_repo = ProgressRepository(session)
    stats = await progress_repo.get_user_stats(user.id)

    await state.clear()
    await message.answer(
        f"🎉 <b>Урок завершён!</b>\n\n"
        f"🏆 Всего уроков пройдено: {stats['total_completed']}\n"
        f"🔥 Стрик: {user.streak_days} дней\n"
        f"⭐ XP: {user.total_xp}\n\n"
        "Молодец! Продолжай в том же духе 💪",
        parse_mode="HTML",
        reply_markup=kb_lesson_complete(),
    )


def _get_correct_answer(item: LessonItem) -> str:
    content = item.content
    if item.task_type == TaskType.MULTIPLE_CHOICE:
        idx = content.get("correct_index", 0)
        options = content.get("options", [])
        return options[idx] if idx < len(options) else ""
    elif item.task_type == TaskType.TRANSLATION:
        return content.get("correct_answer", "")
    elif item.task_type == TaskType.FILL_BLANK:
        idx = content.get("correct_index", 0)
        options = content.get("options", [])
        return options[idx] if idx < len(options) else ""
    elif item.task_type == TaskType.PHRASE_BUILD:
        return content.get("correct_phrase", "")
    elif item.task_type == TaskType.VOICE:
        return content.get("expected_text", "")
    return ""
