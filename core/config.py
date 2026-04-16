import os
from typing import Optional


def _fix_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings:
    # ─── ВСТАВЬ СВОИ ДАННЫЕ СЮДА ───────────────────────
    BOT_TOKEN: str = "СЮДА_ТОКЕН_ОТ_BOTFATHER"
    ADMIN_IDS: str = "СЮДА_ТВОЙ_TELEGRAM_ID"
    API_SECRET: str = "mysecret123"
    # ────────────────────────────────────────────────────

    # Railway сам передаёт эти переменные — читаем из среды
    DATABASE_URL: str = _fix_db_url(os.environ.get("DATABASE_URL", "postgresql+asyncpg://localhost/langbot"))
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    GOOGLE_STT_KEY: Optional[str] = os.environ.get("GOOGLE_STT_KEY")

    DEBUG: bool = False
    TIMEZONE: str = "Asia/Almaty"
    DAILY_NEW_CARDS: int = 10
    DAILY_REVIEW_LIMIT: int = 50
    LESSON_TIMEOUT_MINUTES: int = 30

    @property
    def admin_id_list(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
