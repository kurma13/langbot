"""
Упрощённая реализация FSRS (Free Spaced Repetition Scheduler).
Оригинал: https://github.com/open-spaced-repetition/fsrs4anki

Рейтинги:
1 = Again  (забыл полностью)
2 = Hard   (вспомнил с трудом)
3 = Good   (вспомнил нормально)
4 = Easy   (легко вспомнил)
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
import math


@dataclass
class FSRSCard:
    stability: float = 1.0
    difficulty: float = 5.0
    retrievability: float = 1.0
    reps: int = 0
    lapses: int = 0
    interval_days: float = 1.0
    state: str = "new"  # new | learning | review | relearning


@dataclass
class FSRSResult:
    card: FSRSCard
    next_due: datetime
    interval_days: float


class FSRS:
    """
    Параметры FSRS по умолчанию (из исследований).
    Можно обучить под конкретных пользователей позже.
    """
    w = [
        0.4072, 1.1829, 3.1262, 15.4722,
        7.2102, 0.5316, 1.0651, 0.0589,
        1.4836, 0.0996, 1.0417, 1.9278,
        0.1100, 0.2900, 2.2700, 0.1600,
        2.9898, 0.5100, 0.3400,
    ]
    DECAY = -0.5
    FACTOR = 0.9 ** (1 / DECAY) - 1
    REQUEST_RETENTION = 0.9

    def stability_after_recall(self, d: float, s: float, r: float, rating: int) -> float:
        """Вычисляет новую стабильность после успешного вспоминания."""
        hard_penalty = self.w[15] if rating == 2 else 1
        easy_bonus = self.w[16] if rating == 4 else 1
        new_s = s * (
            math.exp(self.w[8])
            * (11 - d)
            * (s ** -self.w[9])
            * (math.exp((1 - r) * self.w[10]) - 1)
            * hard_penalty
            * easy_bonus
        )
        return max(new_s, 0.01)

    def stability_after_forgetting(self, d: float, s: float, r: float) -> float:
        """Вычисляет стабильность после провала (рейтинг 1 = Again)."""
        return (
            self.w[11]
            * (d ** -self.w[12])
            * ((s + 1) ** self.w[13] - 1)
            * math.exp((1 - r) * self.w[14])
        )

    def next_difficulty(self, d: float, rating: int) -> float:
        """Обновляет сложность карточки."""
        next_d = d - self.w[6] * (rating - 3)
        return max(1.0, min(10.0, self._mean_reversion(self.w[4], next_d)))

    def _mean_reversion(self, init: float, current: float) -> float:
        return self.w[7] * init + (1 - self.w[7]) * current

    def retrievability(self, elapsed_days: float, stability: float) -> float:
        """Вероятность вспомнить карточку через elapsed_days дней."""
        return (1 + self.FACTOR * elapsed_days / stability) ** self.DECAY

    def next_interval(self, stability: float) -> float:
        """Вычисляет следующий интервал повторения в днях."""
        interval = stability / self.FACTOR * (
            self.REQUEST_RETENTION ** (1 / self.DECAY) - 1
        )
        return max(1.0, round(interval, 1))

    def schedule(self, card: FSRSCard, rating: int) -> FSRSResult:
        """
        Основной метод: принимает карточку и рейтинг, возвращает обновлённую карточку.

        rating: 1=Again, 2=Hard, 3=Good, 4=Easy
        """
        now = datetime.now(timezone.utc)

        if card.state == "new":
            # Первое знакомство с карточкой
            card.stability = self._init_stability(rating)
            card.difficulty = self._init_difficulty(rating)
            card.reps = 1

            if rating == 1:
                card.state = "learning"
                interval = 0.003  # ~4 минуты
            elif rating == 2:
                card.state = "learning"
                interval = 0.007  # ~10 минут
            elif rating == 3:
                card.state = "review"
                interval = 1.0
            else:  # 4 Easy
                card.state = "review"
                interval = 4.0

        elif card.state in ("learning", "relearning"):
            if rating == 1:
                interval = 0.003
                card.state = "learning"
            elif rating == 2:
                interval = 0.007
            else:
                card.state = "review"
                card.stability = self._init_stability(rating)
                interval = self.next_interval(card.stability)

        else:  # review
            # Считаем retrievability на момент повторения
            elapsed = (now - (card.last_reviewed_at or now)).days or 1
            r = self.retrievability(elapsed, card.stability)

            if rating == 1:
                # Забыл — пересчитываем стабильность
                card.stability = self.stability_after_forgetting(card.difficulty, card.stability, r)
                card.lapses += 1
                card.state = "relearning"
                interval = 0.003
            else:
                card.stability = self.stability_after_recall(card.difficulty, card.stability, r, rating)
                interval = self.next_interval(card.stability)
                card.state = "review"

            card.difficulty = self.next_difficulty(card.difficulty, rating)
            card.reps += 1

        card.interval_days = interval
        card.last_reviewed_at = now
        card.retrievability = self.retrievability(interval, card.stability)

        next_due = now + timedelta(days=interval)
        return FSRSResult(card=card, next_due=next_due, interval_days=interval)

    def _init_stability(self, rating: int) -> float:
        return self.w[rating - 1]

    def _init_difficulty(self, rating: int) -> float:
        return self.w[4] - math.exp(self.w[5] * (rating - 1)) + 1


# Singleton
fsrs = FSRS()
