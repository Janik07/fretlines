import tempfile
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from fretlines_api import __version__
from fretlines_api.deps import get_engine, get_runner, get_settings
from fretlines_api.jobs import JobRunner
from fretlines_api.settings import Settings

router = APIRouter(tags=["system"])


class ComponentHealth(BaseModel):
    ok: bool
    detail: str | None = None


class HealthChecks(BaseModel):
    database: ComponentHealth
    storage: ComponentHealth
    ffmpeg: ComponentHealth
    jobs: ComponentHealth


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    device: str  # что указано в настройках: auto / cpu / cuda
    torch_build: str  # cpu или cuda — какая сборка PyTorch установлена
    busy_with: str | None
    checks: HealthChecks


def _check_database(engine: Engine) -> ComponentHealth:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return ComponentHealth(ok=False, detail=type(exc).__name__)
    return ComponentHealth(ok=True)


def _check_storage(storage_dir: Path) -> ComponentHealth:
    # Пробная запись честнее, чем os.access: на сетевых и облачных папках тот иногда врёт.
    try:
        with tempfile.TemporaryFile(dir=storage_dir):
            pass
    except OSError as exc:
        return ComponentHealth(ok=False, detail=exc.strerror or type(exc).__name__)
    return ComponentHealth(ok=True)


@cache
def _ffmpeg() -> ComponentHealth:
    try:
        import imageio_ffmpeg

        Path(imageio_ffmpeg.get_ffmpeg_exe()).stat()
    except (ImportError, OSError, RuntimeError) as exc:
        return ComponentHealth(ok=False, detail=type(exc).__name__)
    return ComponentHealth(ok=True)


@cache
def _torch_build() -> str:
    try:
        return "cuda" if "+cu" in version("torch") else "cpu"
    except PackageNotFoundError:
        return "missing"


@router.get("/health")
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    engine: Annotated[Engine, Depends(get_engine)],
    runner: Annotated[JobRunner, Depends(get_runner)],
) -> HealthResponse:
    """Состояние приложения. Всегда 200, пока жив сам процесс; детали — в checks."""
    checks = HealthChecks(
        database=_check_database(engine),
        storage=_check_storage(settings.storage_dir),
        ffmpeg=_ffmpeg(),
        jobs=ComponentHealth(ok=runner.alive, detail=None if runner.alive else "stopped"),
    )
    ok = all(c.ok for c in (checks.database, checks.storage, checks.ffmpeg, checks.jobs))
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=__version__,
        device=settings.device,
        torch_build=_torch_build(),
        busy_with=runner.busy_with,
        checks=checks,
    )
