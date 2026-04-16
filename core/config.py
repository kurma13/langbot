from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: str = ""

    # Database
    # Railway автоматически выставляет DATABASE_URL при подключении Postgres сервиса.
    # Формат Railway: postgresql://user:pass@host/db  →  нам нужен asyncpg
    DATABASE_URL: str = "postgresql+asyncpg://langbot:secret@localhost:5432/langbot"

    # Redis
    # Railway выставляет REDIS_URL автоматически при подключении Redis сервиса
    REDIS_URL: str = "redis://localhost:6379/0"

    # API
    API_SECRET: str = "supersecret"

    # Voice (Google STT)
    GOOGLE_STT_KEY: Optional[str] = None

    # App
    DEBUG: bool = False
    TIMEZONE: str = "Asia/Almaty"

    # Learning config
    DAILY_NEW_CARDS: int = 10
    DAILY_REVIEW_LIMIT: int = 50
    LESSON_TIMEOUT_MINUTES: int = 30

    @property
    def admin_id_list(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    def model_post_init(self, __context):
        """
        Railway даёт DATABASE_URL как postgres:// или postgresql://
        asyncpg требует postgresql+asyncpg://  — исправляем автоматически.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            object.__setattr__(self, "DATABASE_URL",
                url.replace("postgres://", "postgresql+asyncpg://", 1))
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            object.__setattr__(self, "DATABASE_URL",
                url.replace("postgresql://", "postgresql+asyncpg://", 1))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
