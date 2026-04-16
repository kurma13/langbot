from db.models import LessonItem, Lesson, TaskType, Language
from bot.keyboards.keyboards import (
    kb_multiple_choice, kb_phrase_build, kb_translation_check,
    kb_voice_or_text,
)
from typing import Optional


# ─── Placement Test Questions ─────────────────────────────────────────────────

PLACEMENT_QUESTIONS = {
    "kz": [
        {
            "question": "Как будет 'Привет' на казахском?",
            "options": ["Сәлем", "Рақмет", "Иә", "Жоқ"],
            "correct": 0,
        },
        {
            "question": "Что значит 'мен'?",
            "options": ["ты", "он", "я", "мы"],
            "correct": 2,
        },
        {
            "question": "Как сказать 'Я иду домой'?",
            "options": [
                "Мен үйге барамын",
                "Мен мектепте оқимын",
                "Мен жұмыс істеймін",
                "Сіз кімсіз?",
            ],
            "correct": 0,
        },
    ],
    "en": [
        {
            "question": "What does 'apple' mean?",
            "options": ["апельсин", "яблоко", "банан", "виноград"],
            "correct": 1,
        },
        {
            "question": "How do you say 'Я хочу воды'?",
            "options": [
                "I want water",
                "I have water",
                "Give me water",
                "Where is water?",
            ],
            "correct": 0,
        },
        {
            "question": "Choose the correct sentence:",
            "options": [
                "She go to school",
                "She goes to school",
                "She going to school",
                "She goed to school",
            ],
            "correct": 1,
        },
    ],
}


# ─── Task formatting ──────────────────────────────────────────────────────────

def format_task(item: LessonItem, progress_text: str = "") -> tuple[str, any]:
    """
    Форматирует задание в текст и возвращает соответствующую клавиатуру.
    """
    content = item.content
    header = f"{progress_text}\n\n" if progress_text else ""

    if item.task_type == TaskType.MULTIPLE_CHOICE:
        question = content.get("question", "")
        options = content.get("options", [])
        text = (
            f"{header}"
            f"❓ <b>Выбери правильный ответ:</b>\n\n"
            f"{question}"
        )
        return text, kb_multiple_choice(options)

    elif item.task_type == TaskType.TRANSLATION:
        source_text = content.get("source_text", "")
        source_lang = content.get("source_lang", "ru")
        target_lang = content.get("target_lang", "kz")
        hint = content.get("hint")

        lang_display = {
            "ru": "🇷🇺 Русский",
            "kz": "🇰🇿 Казахский",
            "en": "🇬🇧 Английский",
        }
        target_display = lang_display.get(target_lang, target_lang)

        text = (
            f"{header}"
            f"✍️ <b>Переведи на {target_display}:</b>\n\n"
            f"<i>{source_text}</i>\n\n"
            "Напиши перевод 👇"
        )
        return text, kb_translation_check(hint)

    elif item.task_type == TaskType.PHRASE_BUILD:
        instruction = content.get("instruction", "Составь фразу:")
        words = content.get("words", [])
        text = (
            f"{header}"
            f"🧩 <b>Собери фразу:</b>\n\n"
            f"{instruction}\n\n"
            "Нажимай слова по порядку 👇"
        )
        return text, kb_phrase_build(words)

    elif item.task_type == TaskType.FILL_BLANK:
        template = content.get("template", "")
        options = content.get("options", [])
        text = (
            f"{header}"
            f"📝 <b>Заполни пропуск:</b>\n\n"
            f"<code>{template}</code>"
        )
        return text, kb_multiple_choice(options)

    elif item.task_type == TaskType.VOICE:
        prompt = content.get("prompt", "")
        phonetic = content.get("phonetic_hint", "")
        text = (
            f"{header}"
            f"🎤 <b>Голосовое задание:</b>\n\n"
            f"{prompt}"
        )
        if phonetic:
            text += f"\n\n🗣 Произношение: <i>{phonetic}</i>"
        return text, kb_voice_or_text()

    return f"{header}❓ Задание", None


def format_lesson_intro(lesson: Lesson) -> str:
    """Превью урока перед началом."""
    level = lesson.level.value if lesson.level else "A0"
    type_emoji = {
        "vocabulary": "📖",
        "dialogue": "💬",
        "grammar": "📐",
        "endings": "🔤",
        "chunks": "🧱",
        "scenario": "🎭",
    }
    emoji = type_emoji.get(lesson.lesson_type.value if lesson.lesson_type else "", "📚")

    text = (
        f"{emoji} <b>{lesson.title}</b>\n"
        f"Уровень: {level} • ~{lesson.estimated_minutes} мин • +{lesson.xp_reward} XP\n"
    )
    if lesson.scenario_context:
        text += f"\n📍 Ситуация: <i>{lesson.scenario_context}</i>\n"
    if lesson.description:
        text += f"\n{lesson.description}\n"

    text += "\nНачинаем! 🚀"
    return text


def get_text(key: str, lang: str = "ru") -> str:
    """Заглушка для i18n."""
    return key
