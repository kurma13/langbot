"""
Скрипт для загрузки уроков из JSON-файлов в базу данных.
Запуск: python -m utils.seed_lessons
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal, create_tables
from db.models import Lesson, LessonItem, Language, CEFRLevel, LessonType, TaskType
from sqlalchemy import select
from loguru import logger


LESSONS_DIR = Path(__file__).parent.parent / "data" / "lessons"


async def load_lesson_from_json(session: AsyncSession, data: dict) -> bool:
    """Загружает один урок из словаря. Пропускает если уже существует."""
    existing = await session.execute(
        select(Lesson).where(Lesson.slug == data["slug"])
    )
    if existing.scalar_one_or_none():
        logger.info(f"Lesson '{data['slug']}' already exists, skipping")
        return False

    lesson = Lesson(
        slug=data["slug"],
        title=data["title"],
        description=data.get("description"),
        language=Language(data["language"]),
        level=CEFRLevel(data["level"]),
        lesson_type=LessonType(data["lesson_type"]),
        scenario_context=data.get("scenario_context"),
        estimated_minutes=data.get("estimated_minutes", 15),
        xp_reward=data.get("xp_reward", 10),
        order_index=data.get("order_index", 0),
    )
    session.add(lesson)
    await session.flush()

    for item_data in data.get("items", []):
        item = LessonItem(
            lesson_id=lesson.id,
            task_type=TaskType(item_data["task_type"]),
            content=item_data["content"],
            order_index=item_data.get("order_index", 0),
            is_reviewable=item_data.get("is_reviewable", False),
            front_text=item_data.get("front_text"),
            back_text=item_data.get("back_text"),
        )
        session.add(item)

    await session.commit()
    logger.success(f"Loaded lesson: {data['slug']} ({len(data.get('items', []))} items)")
    return True


async def seed_placement_tests(session: AsyncSession):
    """Создаём минимальные placement test уроки."""
    placement_lessons = [
        {
            "slug": "placement-kz-a0",
            "title": "Тест: казахский A0",
            "language": "kz",
            "level": "A0",
            "lesson_type": "vocabulary",
            "order_index": 0,
            "xp_reward": 0,
            "items": [
                {
                    "order_index": 1,
                    "task_type": "multiple_choice",
                    "is_reviewable": False,
                    "content": {
                        "question": "Как будет 'Привет'?",
                        "options": ["Сәлем", "Рақмет", "Жоқ", "Иә"],
                        "correct_index": 0,
                        "explanation": ""
                    }
                }
            ]
        },
        {
            "slug": "placement-en-a0",
            "title": "Test: English A0",
            "language": "en",
            "level": "A0",
            "lesson_type": "vocabulary",
            "order_index": 0,
            "xp_reward": 0,
            "items": [
                {
                    "order_index": 1,
                    "task_type": "multiple_choice",
                    "is_reviewable": False,
                    "content": {
                        "question": "What does 'Hello' mean?",
                        "options": ["Привет", "Пока", "Спасибо", "Пожалуйста"],
                        "correct_index": 0,
                        "explanation": ""
                    }
                }
            ]
        }
    ]

    for lesson_data in placement_lessons:
        await load_lesson_from_json(session, lesson_data)


async def main():
    logger.info("Starting seed...")
    await create_tables()

    async with AsyncSessionLocal() as session:
        # Placement tests
        await seed_placement_tests(session)

        # Уроки из JSON файлов
        json_files = list(LESSONS_DIR.glob("*.json"))
        logger.info(f"Found {len(json_files)} lesson files")

        for filepath in sorted(json_files):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                await load_lesson_from_json(session, data)
            except Exception as e:
                logger.error(f"Error loading {filepath.name}: {e}")

    logger.success("Seed completed!")


if __name__ == "__main__":
    asyncio.run(main())
