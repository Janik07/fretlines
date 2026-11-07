from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки из переменных окружения FRETLINES_* или файла .env (см. .env.example)."""

    model_config = SettingsConfigDict(env_prefix="FRETLINES_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080
    storage_dir: Path = Path("storage")
    # Пусто — SQLite в storage_dir. Для PostgreSQL: postgresql+psycopg://user:pass@host/db
    database_url: str | None = None
    frontend_dir: Path = Path("frontend/dist")
    device: Literal["auto", "cpu", "cuda"] = "auto"
    max_upload_mb: int = 50
    max_video_upload_mb: int = 200
    # Текст песни: online — ищем готовый текст на lrclib.net (уходят только название и
    # исполнитель) и сверяем с Whisper; local — только Whisper, без сети; off — без текста.
    lyrics: Literal["online", "local", "off"] = "online"
    # Модель Whisper: small (~460 МБ) — быстро на процессоре; medium, large-v3 — точнее.
    lyrics_model: str = "small"
    # Разделение на дорожки: max — сначала вокал сильной моделью (MDX-Net, на видеокарте —
    # BS-RoFormer), потом Demucs по инструменталу; standard — один Demucs, примерно вдвое быстрее.
    separation: Literal["standard", "max"] = "max"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.storage_dir / "fretlines.db").resolve()
        return f"sqlite:///{db_path.as_posix()}"

    def song_dir(self, song_id: str) -> Path:
        return self.storage_dir / "songs" / song_id


@lru_cache
def load_settings() -> Settings:
    return Settings()
