from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from db.models import Language, TaskType
from typing import Optional


def kb_choose_language() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇰🇿 Казахский", callback_data="lang:kz")
    builder.button(text="🇬🇧 Английский", callback_data="lang:en")
    builder.adjust(2)
    return builder.as_markup()


def kb_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 Урок")
    builder.button(text="🔄 Повторение")
    builder.button(text="📊 Прогресс")
    builder.button(text="⚙️ Настройки")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def kb_remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def kb_multiple_choice(options: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора ответа."""
    builder = InlineKeyboardBuilder()
    for i, option in enumerate(options):
        builder.button(text=option, callback_data=f"ans:{i}")
    builder.adjust(2)
    return builder.as_markup()


def kb_phrase_build(words: list[str], selected_indices: list[int] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для сборки фразы.
    Слова можно нажимать по одному — они добавляются в фразу.
    """
    selected_indices = selected_indices or []
    builder = InlineKeyboardBuilder()
    for i, word in enumerate(words):
        prefix = "✅ " if i in selected_indices else ""
        builder.button(
            text=f"{prefix}{word}",
            callback_data=f"word:{i}"
        )
    builder.button(text="✔️ Готово", callback_data="phrase:submit")
    builder.button(text="↩️ Сброс", callback_data="phrase:reset")
    builder.adjust(3)
    return builder.as_markup()


def kb_translation_check(hint: Optional[str] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if hint:
        builder.button(text="💡 Подсказка", callback_data="hint:show")
    builder.button(text="⏭ Пропустить", callback_data="ans:skip")
    builder.adjust(2)
    return builder.as_markup()


def kb_voice_or_text() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎤 Отвечу голосом", callback_data="voice:use")
    builder.button(text="⌨️ Напишу текстом", callback_data="voice:text")
    builder.button(text="⏭ Пропустить", callback_data="ans:skip")
    builder.adjust(2)
    return builder.as_markup()


def kb_after_correct() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Дальше", callback_data="next:continue")
    return builder.as_markup()


def kb_after_incorrect(correct_answer: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Понял, дальше", callback_data="next:continue")
    return builder.as_markup()


def kb_lesson_complete() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Главное меню", callback_data="menu:main")
    builder.button(text="▶️ Следующий урок", callback_data="lesson:next")
    builder.adjust(2)
    return builder.as_markup()


def kb_review_rating() -> InlineKeyboardMarkup:
    """FSRS rating: 1=Again, 2=Hard, 3=Good, 4=Easy."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Не помню (1)", callback_data="rate:1")
    builder.button(text="😓 Сложно (2)", callback_data="rate:2")
    builder.button(text="👍 Хорошо (3)", callback_data="rate:3")
    builder.button(text="⭐ Легко (4)", callback_data="rate:4")
    builder.adjust(2)
    return builder.as_markup()


def kb_placement_test_options(options: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, option in enumerate(options):
        builder.button(text=option, callback_data=f"pt:{i}")
    builder.button(text="🚫 Не знаю", callback_data="pt:skip")
    builder.adjust(2)
    return builder.as_markup()


def kb_start_lesson() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Начать урок", callback_data="lesson:start")
    builder.button(text="🔄 Сначала повторить", callback_data="review:start")
    builder.adjust(2)
    return builder.as_markup()


def kb_settings() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 Время уведомлений", callback_data="settings:notify")
    builder.button(text="🌍 Сменить язык", callback_data="settings:language")
    builder.button(text="📊 Статистика", callback_data="settings:stats")
    builder.button(text="◀️ Назад", callback_data="menu:main")
    builder.adjust(2)
    return builder.as_markup()


def kb_confirm_language_change() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="lang_change:confirm")
    builder.button(text="❌ Отмена", callback_data="lang_change:cancel")
    builder.adjust(2)
    return builder.as_markup()
