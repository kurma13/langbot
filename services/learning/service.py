from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories import UserRepository, LessonRepository, ReviewRepository, ProgressRepository, AttemptRepository
from db.models import User, Lesson, LessonItem, Review, UserLessonState, Language, CEFRLevel, TaskType, AttemptResult
from services.spaced_repetition.fsrs import fsrs, FSRSCard
from core.config import settings
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update
from loguru import logger
import json


class LearningService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.lesson_repo = LessonRepository(session)
        self.review_repo = ReviewRepository(session)
        self.progress_repo = ProgressRepository(session)
        self.attempt_repo = AttemptRepository(session)

    # ─── Placement Test ──────────────────────────────────────────────────────

    PLACEMENT_SLUGS = {
        Language.KAZAKH: [
            "placement-kz-a0",
            "placement-kz-a1",
            "placement-kz-a2",
        ],
        Language.ENGLISH: [
            "placement-en-a0",
            "placement-en-a1",
            "placement-en-a2",
        ],
    }

    def calculate_level_from_score(self, scores: list[tuple[str, float]]) -> CEFRLevel:
        """
        scores = [("placement-kz-a0", 0.9), ("placement-kz-a1", 0.4), ...]
        Определяем уровень по результатам placement test.
        """
        level_map = {
            "a0": (0, CEFRLevel.A0),
            "a1": (1, CEFRLevel.A1),
            "a2": (2, CEFRLevel.A2),
            "b1": (3, CEFRLevel.B1),
        }

        # Логика: если пройден уровень X с score >= 0.7, начинаем с X+1
        reached_level = CEFRLevel.A0
        for slug, score in scores:
            for key, (idx, level) in level_map.items():
                if key in slug and score >= 0.7:
                    # Переходим на следующий уровень
                    levels = [CEFRLevel.A0, CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1]
                    if idx + 1 < len(levels):
                        reached_level = levels[idx + 1]
                    break

        return reached_level

    # ─── Урок ────────────────────────────────────────────────────────────────

    async def get_next_lesson(self, user: User) -> Optional[Lesson]:
        """
        Алгоритм выбора следующего урока:
        1. Сначала смотрим — есть ли карточки для повторения (due reviews)
        2. Если нет — берём следующий новый урок по уровню
        """
        due_count = await self.review_repo.count_due_today(user.id)
        if due_count > 0:
            return None  # Сигнал: сначала повторение

        lesson = await self.lesson_repo.get_next_lesson(
            user_id=user.id,
            language=user.target_language,
            level=user.current_level,
        )

        if not lesson:
            # Все уроки пройдены — повышаем уровень
            await self._try_level_up(user)
            lesson = await self.lesson_repo.get_next_lesson(
                user_id=user.id,
                language=user.target_language,
                level=user.current_level,
            )

        return lesson

    async def _try_level_up(self, user: User):
        """Повышаем уровень, если все уроки текущего уровня пройдены."""
        level_order = [CEFRLevel.A0, CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1]
        current_idx = level_order.index(user.current_level)
        if current_idx < len(level_order) - 1:
            new_level = level_order[current_idx + 1]
            await self.user_repo.update_field(user.id, current_level=new_level)
            user.current_level = new_level
            logger.info(f"User {user.telegram_id} leveled up to {new_level}")

    # ─── Состояние урока ─────────────────────────────────────────────────────

    async def start_lesson(self, user: User, lesson: Lesson) -> UserLessonState:
        """Инициализируем состояние урока для пользователя."""
        await self.progress_repo.start_lesson(user.id, lesson.id)

        # Убираем старое состояние
        await self.session.execute(
            update(UserLessonState)
            .where(UserLessonState.user_id == user.id)
            .values(
                lesson_id=lesson.id,
                current_item_index=0,
                item_ids=[item.id for item in lesson.items],
                correct_count=0,
                total_count=len(lesson.items),
                started_at=datetime.now(timezone.utc),
            )
        )
        # Или создаём новое
        result = await self.session.execute(
            select(UserLessonState).where(UserLessonState.user_id == user.id)
        )
        state = result.scalar_one_or_none()
        if not state:
            state = UserLessonState(
                user_id=user.id,
                lesson_id=lesson.id,
                item_ids=[item.id for item in lesson.items],
                total_count=len(lesson.items),
            )
            self.session.add(state)
            await self.session.flush()
        else:
            await self.session.flush()
            await self.session.refresh(state)

        return state

    async def get_current_item(self, user_id: int) -> Optional[tuple[UserLessonState, LessonItem]]:
        """Получить текущее задание в уроке."""
        result = await self.session.execute(
            select(UserLessonState).where(UserLessonState.user_id == user_id)
        )
        state = result.scalar_one_or_none()
        if not state:
            return None

        item_ids = state.item_ids
        if state.current_item_index >= len(item_ids):
            return None  # Урок завершён

        item_id = item_ids[state.current_item_index]
        result = await self.session.execute(
            select(LessonItem).where(LessonItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        return (state, item) if item else None

    async def submit_answer(
        self,
        user: User,
        item: LessonItem,
        user_answer: str,
        rating: int = 3,  # 1-4 для FSRS
    ) -> tuple[bool, str, bool]:
        """
        Проверяет ответ, сохраняет попытку, обновляет spaced repetition.

        Возвращает: (is_correct, explanation, is_lesson_complete)
        """
        is_correct, explanation = self._check_answer(item, user_answer)
        result = AttemptResult.CORRECT if is_correct else AttemptResult.INCORRECT

        # Сохраняем попытку
        await self.attempt_repo.save(
            user_id=user.id,
            lesson_item_id=item.id,
            result=result,
            user_answer=user_answer,
            rating=rating if is_correct else 1,
        )

        # Обновляем spaced repetition для reviewable items
        if item.is_reviewable:
            await self._update_review(user.id, item.id, rating if is_correct else 1)

        # Переходим к следующему заданию
        is_lesson_complete = await self._advance_lesson(user.id, is_correct)

        return is_correct, explanation, is_lesson_complete

    def _check_answer(self, item: LessonItem, user_answer: str) -> tuple[bool, str]:
        """Проверяет ответ в зависимости от типа задания."""
        content = item.content
        user_answer = user_answer.strip().lower()

        if item.task_type == TaskType.MULTIPLE_CHOICE:
            correct_idx = content.get("correct_index", 0)
            options = content.get("options", [])
            # user_answer может быть индексом (0,1,2,3) или текстом
            try:
                idx = int(user_answer)
                is_correct = idx == correct_idx
            except ValueError:
                correct_text = options[correct_idx].lower() if options else ""
                is_correct = user_answer == correct_text
            explanation = content.get("explanation", "")
            return is_correct, explanation

        elif item.task_type == TaskType.TRANSLATION:
            correct = content.get("correct_answer", "").lower()
            acceptable = [a.lower() for a in content.get("acceptable_answers", [])]
            all_correct = [correct] + acceptable
            is_correct = any(
                self._similarity(user_answer, ans) >= 0.85
                for ans in all_correct
            )
            explanation = content.get("hint", "")
            return is_correct, explanation

        elif item.task_type == TaskType.FILL_BLANK:
            correct_idx = content.get("correct_index", 0)
            options = content.get("options", [])
            try:
                idx = int(user_answer)
                is_correct = idx == correct_idx
            except ValueError:
                correct_text = options[correct_idx].lower() if options else ""
                is_correct = user_answer == correct_text
            explanation = content.get("explanation", "")
            return is_correct, explanation

        elif item.task_type == TaskType.PHRASE_BUILD:
            correct_phrase = content.get("correct_phrase", "").lower()
            is_correct = self._similarity(user_answer, correct_phrase) >= 0.90
            return is_correct, ""

        elif item.task_type == TaskType.VOICE:
            expected = content.get("expected_text", "").lower()
            threshold = content.get("similarity_threshold", 0.75)
            is_correct = self._similarity(user_answer, expected) >= threshold
            return is_correct, content.get("phonetic_hint", "")

        return False, ""

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Расстояние Левенштейна → нормализованное сходство."""
        import Levenshtein
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        distance = Levenshtein.distance(a, b)
        max_len = max(len(a), len(b))
        return 1 - distance / max_len

    async def _update_review(self, user_id: int, item_id: int, rating: int):
        """Обновляем запись spaced repetition."""
        result = await self.session.execute(
            select(Review).where(
                Review.user_id == user_id,
                Review.lesson_item_id == item_id,
            )
        )
        review = result.scalar_one_or_none()

        card = FSRSCard(
            stability=review.stability if review else 1.0,
            difficulty=review.difficulty if review else 5.0,
            retrievability=review.retrievability if review else 1.0,
            reps=review.reps if review else 0,
            lapses=review.lapses if review else 0,
            interval_days=review.interval_days if review else 1.0,
            state=review.state if review else "new",
        )
        if review:
            card.last_reviewed_at = review.last_reviewed_at

        fsrs_result = fsrs.schedule(card, rating)

        if review:
            await self.session.execute(
                update(Review)
                .where(Review.id == review.id)
                .values(
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
        else:
            new_review = Review(
                user_id=user_id,
                lesson_item_id=item_id,
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
            self.session.add(new_review)

        await self.session.flush()

    async def _advance_lesson(self, user_id: int, is_correct: bool) -> bool:
        """Переходим к следующему заданию. Возвращает True если урок завершён."""
        result = await self.session.execute(
            select(UserLessonState).where(UserLessonState.user_id == user_id)
        )
        state = result.scalar_one_or_none()
        if not state:
            return True

        if is_correct:
            state.correct_count += 1
        state.current_item_index += 1

        is_complete = state.current_item_index >= len(state.item_ids)

        if is_complete:
            score = state.correct_count / state.total_count if state.total_count > 0 else 0
            await self.progress_repo.complete_lesson(user_id, state.lesson_id, score)
            await self.session.delete(state)

            # Начисляем XP
            lesson_result = await self.session.execute(
                select(Lesson).where(Lesson.id == state.lesson_id)
            )
            lesson = lesson_result.scalar_one_or_none()
            if lesson:
                xp = int(lesson.xp_reward * score)
                await self.user_repo.add_xp(user_id, xp)

        await self.session.flush()
        return is_complete

    # ─── Review session ──────────────────────────────────────────────────────

    async def get_due_reviews(self, user_id: int) -> list[Review]:
        return await self.review_repo.get_due_reviews(
            user_id=user_id,
            limit=settings.DAILY_REVIEW_LIMIT,
        )
