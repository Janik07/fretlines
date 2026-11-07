"""Очередь разборов без Redis: по одному, каждый — в своём процессе.

Тяжёлый анализ (PyTorch, Demucs) живёт в отдельном процессе: API остаётся отзывчивым,
память освобождается после каждой песни, а падение модели не роняет сервер.
Прогресс процесс пишет прямо в базу — вкладку можно закрыть и вернуться (SPEC §1.4).
"""

from __future__ import annotations

import logging
import multiprocessing
import queue
import threading
import time
from multiprocessing.process import BaseProcess
from pathlib import Path

from sqlalchemy import Engine, select

from fretlines_api.db import Song, create_db_engine, session_scope, utcnow

log = logging.getLogger("fretlines.jobs")


class JobRunner:
    def __init__(
        self,
        engine: Engine,
        storage_dir: Path,
        database_url: str,
        device: str,
        lyrics: tuple[str, str] = ("off", "small"),
        separation: str = "standard",
    ) -> None:
        self._engine = engine
        self._storage_dir = storage_dir
        self._database_url = database_url
        self._device = device
        self._lyrics = lyrics  # (режим, модель Whisper) — см. Settings.lyrics
        self._separation = separation  # качество дорожек — см. Settings.separation
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._current: tuple[str, BaseProcess] | None = None
        self._thread = threading.Thread(target=self._loop, name="fretlines-jobs", daemon=True)
        self._context = multiprocessing.get_context("spawn")

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def busy_with(self) -> str | None:
        with self._lock:
            return self._current[0] if self._current else None

    def start(self) -> None:
        self._thread.start()
        with session_scope(self._engine) as session:
            stale = session.scalars(
                select(Song).where(Song.status.in_(("queued", "running"))).order_by(Song.created_at)
            ).all()
            for song in stale:
                song.status, song.stage, song.progress = "queued", None, 0.0
            session.commit()
            for song in stale:
                self.submit(song.id)

    def submit(self, song_id: str) -> None:
        self._queue.put(song_id)

    def cancel(self, song_id: str) -> None:
        with self._lock:
            current = self._current
        if current and current[0] == song_id and current[1].is_alive():
            current[1].terminate()

    def stop(self) -> None:
        self._queue.put(None)
        with self._lock:
            current = self._current
        if current and current[1].is_alive():
            current[1].terminate()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while True:
            song_id = self._queue.get()
            if song_id is None:
                return
            with session_scope(self._engine) as session:
                song = session.get(Song, song_id)
                if song is None or song.status != "queued":
                    continue
            process = self._context.Process(
                target=run_job,
                args=(
                    song_id,
                    str(self._storage_dir),
                    self._database_url,
                    self._device,
                    self._lyrics,
                    self._separation,
                ),
                name=f"fretlines-analysis-{song_id[:8]}",
                daemon=True,
            )
            with self._lock:
                self._current = (song_id, process)
            started = time.perf_counter()
            process.start()
            process.join()
            with self._lock:
                self._current = None
            log.info(
                "job %s finished in %.1fs (exit %s)",
                song_id,
                time.perf_counter() - started,
                process.exitcode,
            )
            if process.exitcode != 0:
                _mark_crashed(self._engine, song_id)


def _mark_crashed(engine: Engine, song_id: str) -> None:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is not None and song.status in ("queued", "running"):
            song.status = "failed"
            song.error_code = "crashed"
            song.error_message = (
                "Разбор неожиданно прервался — возможно, не хватило памяти. Попробуй ещё раз."
            )
            session.commit()


class _Reporter:
    """Пишет прогресс в базу не чаще раза в полсекунды — SQLite не любит частых записей."""

    def __init__(self, engine: Engine, song_id: str, weights: dict[str, float]) -> None:
        self.engine = engine
        self.song_id = song_id
        self.weights = weights
        self.last_write = 0.0
        self.last_stage: str | None = None

    def overall(self, stage: str, fraction: float) -> float:
        done = 0.0
        for name, weight in self.weights.items():
            if name == stage:
                return min(0.99, done + weight * max(0.0, min(1.0, fraction)))
            done += weight
        return min(0.99, done)

    def __call__(self, stage: str, fraction: float) -> None:
        now = time.monotonic()
        if stage == self.last_stage and now - self.last_write < 0.5:
            return
        self.last_stage, self.last_write = stage, now
        with session_scope(self.engine) as session:
            song = session.get(Song, self.song_id)
            if song is None:
                raise SystemExit(0)  # песню удалили — разбирать больше нечего
            song.stage = stage
            song.progress = round(self.overall(stage, fraction), 4)
            session.commit()


def run_job(
    song_id: str,
    storage_dir: str,
    database_url: str,
    device: str,
    lyrics: tuple[str, str] = ("off", "small"),
    separation: str = "standard",
) -> None:
    """Выполняется в отдельном процессе (spawn): разбор одной песни от и до."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from fretlines_worker.errors import AnalysisError
    from fretlines_worker.pipeline import LyricsOptions, run_analysis, stage_weights

    engine = create_db_engine(database_url)
    folder = Path(storage_dir) / "songs" / song_id
    mode, model = lyrics
    options = LyricsOptions(mode=mode if mode in ("online", "local") else "off", model=model)  # type: ignore[arg-type]
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is None:
            return
        url = song.source_url if song.source_kind == "url" else None
        title, artist = song.title, song.artist
        song.status, song.stage, song.progress = "running", None, 0.0
        song.error_code = song.error_message = None
        session.commit()

    def on_meta(meta: dict[str, object]) -> None:
        with session_scope(engine) as session:
            song = session.get(Song, song_id)
            if song is None:
                return
            for field in ("title", "artist", "duration", "tempo", "key", "device"):
                value = meta.get(field)
                if value is not None:
                    setattr(song, field, value)
            session.commit()

    report = _Reporter(engine, song_id, stage_weights(url is not None, options.mode != "off"))
    try:
        run_analysis(
            folder,
            source_url=url,
            device=device,
            report=report,
            on_meta=on_meta,
            title=title,
            artist=artist,
            lyrics=options,
            separation="max" if separation == "max" else "standard",
        )
    except AnalysisError as error:
        _finish(engine, song_id, "failed", error.code, error.message)
        return
    except Exception:
        log.exception("analysis of %s failed", song_id)
        _finish(
            engine,
            song_id,
            "failed",
            "internal",
            "Что-то пошло не так при разборе. Попробуй ещё раз или возьми другой файл.",
        )
        return
    _finish(engine, song_id, "done", None, None)


def _finish(
    engine: Engine, song_id: str, status: str, code: str | None, message: str | None
) -> None:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is None:
            return
        song.status = status
        song.error_code, song.error_message = code, message
        song.progress = 1.0 if status == "done" else song.progress
        song.stage = None if status == "done" else song.stage
        song.finished_at = utcnow()
        session.commit()
