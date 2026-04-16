from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import UserRepository, LessonRepository
from db.models import Language, CEFRLevel
from bot.states.states import OnboardingStates, LessonStates
from bot.keyboards.keyboards import (
    kb_choose_language, kb_main_menu, kb_placement_test_options,
    kb_start_lesson, kb_remove,
)
from services.learning.service import LearningService
from utils.texts import get_text, PLACEMENT_QUESTIONS
from loguru import logger

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user, is_new = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        language_code=message.from_user.language_code,
    )

    await state.clear()

    if not is_new and user.onboarding_done:
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name}!\n\n"
            "Продолжаем учёбу?",
            reply_markup=kb_main_menu(),
        )
        return

    # Новый пользователь → onboarding
    await message.answer(
        "👋 Привет! Я <b>LangBot</b> — твой персональный тренер по языкам.\n\n"
        "Я помогу тебе выучить казахский или английский:\n"
        "• Короткие уроки по 10–15 минут\n"
        "• Умное повторение слов\n"
        "• Обучение через реальные ситуации\n\n"
        "Какой язык хочешь учить?",
        parse_mode="HTML",
        reply_markup=kb_choose_language(),
    )
    await state.set_state(OnboardingStates.choosing_language)


@router.callback_query(OnboardingStates.choosing_language, F.data.startswith("lang:"))
async def on_language_chosen(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    lang_code = callback.data.split(":")[1]
    language = Language.KAZAKH if lang_code == "kz" else Language.ENGLISH

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    await user_repo.update_field(user.id, target_language=language)

    lang_name = "казахский 🇰🇿" if language == Language.KAZAKH else "английский 🇬🇧"

    await callback.message.edit_text(
        f"Отлично! Ты выбрал <b>{lang_name}</b>.\n\n"
        "Сейчас пройдём короткий тест (3 вопроса), чтобы определить твой уровень.\n"
        "Не переживай — просто отвечай честно! 🎯",
        parse_mode="HTML",
    )

    await state.update_data(
        language=lang_code,
        pt_index=0,
        pt_scores=[],
    )
    await state.set_state(OnboardingStates.placement_test)
    await send_placement_question(callback.message, state, lang_code, 0)
    await callback.answer()


async def send_placement_question(message, state: FSMContext, lang: str, index: int):
    questions = PLACEMENT_QUESTIONS.get(lang, [])
    if index >= len(questions):
        await finish_placement(message, state)
        return

    q = questions[index]
    await message.answer(
        f"📝 Вопрос {index + 1}/{len(questions)}\n\n"
        f"<b>{q['question']}</b>",
        parse_mode="HTML",
        reply_markup=kb_placement_test_options(q["options"]),
    )


@router.callback_query(OnboardingStates.placement_test, F.data.startswith("pt:"))
async def on_placement_answer(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    lang = data["lang"] if "lang" in data else data.get("language", "kz")
    index = data["pt_index"]
    scores = data["pt_scores"]

    answer = callback.data.split(":")[1]
    questions = PLACEMENT_QUESTIONS.get(lang, [])

    if index < len(questions):
        q = questions[index]
        if answer != "skip":
            try:
                ans_idx = int(answer)
                is_correct = ans_idx == q.get("correct", 0)
                scores.append(1 if is_correct else 0)
            except ValueError:
                scores.append(0)
        else:
            scores.append(0)

    next_index = index + 1
    await state.update_data(pt_index=next_index, pt_scores=scores)

    await callback.message.delete()

    if next_index >= len(questions):
        await finish_placement(callback.message, state, session, callback.from_user.id, lang, scores)
    else:
        await send_placement_question(callback.message, state, lang, next_index)

    await callback.answer()


async def finish_placement(message, state, session=None, user_id=None, lang=None, scores=None):
    if scores is None:
        scores = []

    total = len(scores)
    correct = sum(scores)
    ratio = correct / total if total > 0 else 0

    # Определяем уровень
    if ratio >= 0.8:
        level = CEFRLevel.A2
        level_text = "A2 — у тебя есть база!"
    elif ratio >= 0.5:
        level = CEFRLevel.A1
        level_text = "A1 — хорошее начало!"
    else:
        level = CEFRLevel.A0
        level_text = "A0 — начинаем с нуля, это нормально!"

    if session and user_id:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        if user:
            await user_repo.update_field(
                user.id,
                current_level=level,
                placement_done=True,
                onboarding_done=True,
            )

    await state.clear()

    lang_name = "казахского" if lang == "kz" else "английского"
    await message.answer(
        f"🎯 Твой уровень: <b>{level_text}</b>\n\n"
        f"Правильных ответов: {correct}/{total}\n\n"
        f"Буду строить план изучения {lang_name} специально для тебя.\n"
        "Начинаем? 🚀",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Команды бота:</b>\n\n"
        "/start — перезапустить\n"
        "/lesson — начать урок\n"
        "/review — повторение слов\n"
        "/progress — твой прогресс\n"
        "/settings — настройки\n\n"
        "Или используй кнопки ниже 👇",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )

@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext, session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        return
    await user_repo.update_field(
        user.id,
        current_level=CEFRLevel.A0,
        onboarding_done=False,
        placement_done=False,
    )
    await state.clear()
    await message.answer("✅ Прогресс сброшен! Напиши /start")
