import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class Settings:
    # ─── СЮДА ВСТАВЬ СВОИ ДАННЫЕ ───────────────────────────
    BOT_TOKEN: str = "8390317097:AAH46xNP9JR62GbSQqFeQ4hJ42Fkv6W0wMk"
    ADMIN_IDS: str = "8390317097"
    API_SECRET: str = "mysecret123"
    # ────────────────────────────────────────────────────────

    # Railway сам подставляет DATABASE_URL и REDIS_URL
    # через переменные своих сервисов — не трогай
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql+asyncpg://localhost/langbot")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    GOOGLE_STT_KEY: Optional[str] = os.environ.get("GOOGLE_STT_KEY")

    DEBUG: bool = False
    TIMEZONE: str = "Asia/Almaty"

    DAILY_NEW_CARDS: int = 10
    DAILY_REVIEW_LIMIT: int = 50
    LESSON_TIMEOUT_MINUTES: int = 30

    def __post_init__(self):
        # Railway даёт postgres:// — конвертируем в asyncpg
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            self.DATABASE_URL = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            self.DATABASE_URL = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def admin_id_list(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
