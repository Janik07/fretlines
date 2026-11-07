"""Разборы песен: загрузка файла или ссылки, прогресс, результат, аранжировка, звук, текст."""

from __future__ import annotations

import bisect
import json
import re
import shutil
import subprocess
import threading
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import Engine, select

from arranger import PlayerSetup, Transcription, arrange, arrangement_to_dict, to_alphatex
from arranger.model import STEPS_PER_BEAT
from fretlines_api.db import Song, session_scope
from fretlines_api.deps import get_engine, get_runner, get_settings
from fretlines_api.jobs import JobRunner
from fretlines_api.schemas import ArrangementIn, ImportIn, LyricsIn, SongOut, SongPatch
from fretlines_api.settings import Settings

router = APIRouter(tags=["songs"])

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg", "opus", "aac", "wma", "aif", "aiff"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "mkv", "avi", "3gp"}
StemName = Literal["mix", "vocals", "bass", "drums", "guitar", "piano", "other", "instrumental"]
STEMS = ("vocals", "bass", "drums", "guitar", "piano", "other")
# Как дорожки называются в скачанных файлах.
TRACK_LABELS = {
    "instrumental": "Инструментал",
    "vocals": "Вокал",
    "guitar": "Гитара",
    "bass": "Бас",
    "drums": "Барабаны",
    "piano": "Клавиши",
    "other": "Остальное",
    "mix": "Оригинал",
}
CURRENT_ANALYSIS = 2  # разборы старее — без темпа по тактам, гитары из записи и текста

_mix_locks: dict[str, threading.Lock] = {}
_mix_guard = threading.Lock()

SettingsDep = Annotated[Settings, Depends(get_settings)]
EngineDep = Annotated[Engine, Depends(get_engine)]
RunnerDep = Annotated[JobRunner, Depends(get_runner)]


def _get(engine: Engine, song_id: str) -> Song:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
    if song is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Такого разбора нет — возможно, его удалили."
        )
    return song


def _clean_title(filename: str) -> str:
    stem = Path(filename).stem
    title = re.sub(r"[_]+", " ", stem).strip()
    return title[:300] or "Без названия"


@router.get("/songs")
def list_songs(engine: EngineDep) -> list[SongOut]:
    with session_scope(engine) as session:
        songs = session.scalars(select(Song).order_by(Song.created_at.desc())).all()
    return [SongOut.of(s) for s in songs]


@router.post("/songs", status_code=status.HTTP_201_CREATED)
async def upload_song(
    file: UploadFile, settings: SettingsDep, engine: EngineDep, runner: RunnerDep
) -> SongOut:
    name = file.filename or "track"
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Такой формат не подойдёт. Подойдут mp3, wav, m4a, flac — или видео mp4.",
        )
    limit_mb = settings.max_video_upload_mb if ext in VIDEO_EXTENSIONS else settings.max_upload_mb
    song_id = uuid4().hex
    folder = settings.song_dir(song_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"source.{ext}"
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > limit_mb * 1024 * 1024:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"Файл больше {limit_mb} МБ. Возьми запись покороче или сожми её в mp3.",
                    )
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл пустой.")

    with session_scope(engine) as session:
        song = Song(id=song_id, title=_clean_title(name), source_kind="file", filename=name[:300])
        session.add(song)
        session.commit()
    runner.submit(song_id)
    return SongOut.of(song)


@router.post("/songs/import", status_code=status.HTTP_201_CREATED)
def import_song(
    body: ImportIn, settings: SettingsDep, engine: EngineDep, runner: RunnerDep
) -> SongOut:
    url = body.url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Это не похоже на ссылку. Скопируй адрес видео целиком — с https://",
        )
    host = parsed.netloc.removeprefix("www.").removeprefix("m.")
    song_id = uuid4().hex
    settings.song_dir(song_id).mkdir(parents=True, exist_ok=True)
    with session_scope(engine) as session:
        song = Song(id=song_id, title=f"Трек с {host}", source_kind="url", source_url=url)
        session.add(song)
        session.commit()
    runner.submit(song_id)
    return SongOut.of(song)


@router.get("/songs/{song_id}")
def get_song(song_id: str, engine: EngineDep) -> SongOut:
    return SongOut.of(_get(engine, song_id))


@router.patch("/songs/{song_id}")
def update_song(song_id: str, body: SongPatch, engine: EngineDep) -> SongOut:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого разбора нет.")
        if body.title is not None:
            song.title = body.title.strip()
        if body.artist is not None:
            song.artist = body.artist.strip() or None
        if body.setup is not None:
            song.setup = json.dumps(body.setup, ensure_ascii=False)
        session.commit()
    return SongOut.of(song)


@router.delete("/songs/{song_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_song(
    song_id: str, settings: SettingsDep, engine: EngineDep, runner: RunnerDep
) -> Response:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого разбора нет.")
        session.delete(song)
        session.commit()
    runner.cancel(song_id)
    shutil.rmtree(settings.song_dir(song_id), ignore_errors=True)
    _transcription.cache_clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/songs/{song_id}/retry")
def retry_song(song_id: str, engine: EngineDep, runner: RunnerDep) -> SongOut:
    with session_scope(engine) as session:
        song = session.get(Song, song_id)
        if song is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого разбора нет.")
        if song.status in ("queued", "running"):
            return SongOut.of(song)
        song.status, song.stage, song.progress = "queued", None, 0.0
        song.error_code = song.error_message = None
        session.commit()
    runner.submit(song_id)
    _transcription.cache_clear()
    return SongOut.of(song)


@router.get("/songs/{song_id}/peaks")
def song_peaks(song_id: str, settings: SettingsDep, engine: EngineDep) -> dict[str, Any]:
    _get(engine, song_id)
    path = settings.song_dir(song_id) / "peaks.json"
    if not path.exists():
        return {"peaks": [], "duration": None}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _analysis_path(settings: Settings, engine: Engine, song_id: str) -> Path:
    song = _get(engine, song_id)
    path = settings.song_dir(song_id) / "analysis.json"
    if song.status != "done" or not path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Разбор ещё не готов.")
    return path


@lru_cache(maxsize=16)
def _load_analysis(path: str, mtime: float) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=16)
def _transcription(path: str, mtime: float) -> Transcription:
    return Transcription.from_dict(_load_analysis(path, mtime)["transcription"])


@lru_cache(maxsize=16)
def _load_lyrics(path: str, mtime: float) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def _lyrics(settings: Settings, song_id: str) -> dict[str, Any] | None:
    path = settings.song_dir(song_id) / "lyrics.json"
    if not path.exists():
        return None
    return _load_lyrics(str(path), path.stat().st_mtime)


@router.get("/songs/{song_id}/analysis")
def song_analysis(song_id: str, settings: SettingsDep, engine: EngineDep) -> dict[str, Any]:
    path = _analysis_path(settings, engine, song_id)
    data = _load_analysis(str(path), path.stat().st_mtime)
    tx = data["transcription"]
    lyrics = _lyrics(settings, song_id)
    version = int(data.get("version", 1))
    return {
        "version": version,
        "outdated": version < CURRENT_ANALYSIS,
        "duration": data["duration"],
        "tempo": tx["tempo"],
        "beats_per_bar": tx["beats_per_bar"],
        "bars": tx["bars"],
        "bar_times": data["bar_times"],
        "bar_seconds": tx.get("bar_seconds", []),
        "key": data["key"],
        "key_confidence": data.get("key_confidence"),
        "stems": data.get("stems", []),
        "warnings": data.get("warnings", []),
        "guitar_source": tx.get("guitar_source", ""),
        "guitar_tone": tx.get("guitar_tone", ""),
        "counts": {
            "chords": len(tx["chords"]),
            "melody": len(tx["melody"]),
            "bass": len(tx["bass"]),
            "guitar": len(tx.get("guitar", [])),
            "lyrics_lines": len(lyrics["lines"]) if lyrics else 0,
        },
        "device": data.get("device"),
        "separation": data.get("separation", {"quality": "standard", "models": ["htdemucs_6s"]}),
        "lossless": sorted(
            p.stem for p in (settings.song_dir(song_id) / "stems" / "flac").glob("*.flac")
        ),
        "timings": data.get("timings", {}),
    }


def _to_step(times: list[float], seconds: float) -> int | None:
    """Секунды записи → шаг сетки (шестнадцатая) по долям из разбора."""
    if len(times) < 2:
        return None
    i = bisect.bisect_right(times, seconds) - 1
    i = max(0, min(i, len(times) - 2))
    span = times[i + 1] - times[i]
    if span <= 0:
        return None
    beat = i + (seconds - times[i]) / span
    return round(beat * STEPS_PER_BEAT) if beat >= 0 else None


def _words(analysis: dict[str, Any], lyrics: dict[str, Any] | None) -> list[tuple[int, str]]:
    if not lyrics:
        return []
    times = [float(t) for t in analysis.get("beats", [])]
    out: list[tuple[int, str]] = []
    for line in lyrics.get("lines", []):
        for word in line.get("words", []):
            step = _to_step(times, float(word["start"]))
            if step is not None:
                out.append((step, str(word["text"])))
    return out


@router.get("/songs/{song_id}/lyrics")
def song_lyrics(song_id: str, settings: SettingsDep, engine: EngineDep) -> dict[str, Any]:
    """Слова с таймингом в секундах записи. Пусто — текста нет или разбор старый."""
    _get(engine, song_id)
    return _lyrics(settings, song_id) or {"version": 1, "source": None, "lines": []}


@router.put("/songs/{song_id}/lyrics")
def save_lyrics(
    song_id: str, body: LyricsIn, settings: SettingsDep, engine: EngineDep
) -> dict[str, Any]:
    """Свой вариант текста (правка вручную): строки и слова с таймингом."""
    _get(engine, song_id)
    folder = settings.song_dir(song_id)
    if not folder.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Папка разбора потерялась.")
    data = {"version": 1, "source": "edited", **body.model_dump(exclude={"source"})}
    tmp = folder / "lyrics.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / "lyrics.json")
    return data


@router.post("/songs/{song_id}/arrangement")
def song_arrangement(
    song_id: str, body: ArrangementIn, settings: SettingsDep, engine: EngineDep
) -> dict[str, Any]:
    """Партии под состав группы. Без повторного анализа — быстро (SPEC §1.5)."""
    path = _analysis_path(settings, engine, song_id)
    song = _get(engine, song_id)
    tx = _transcription(str(path), path.stat().st_mtime)
    players = [
        PlayerSetup(
            id=p.id,
            name=p.name.strip(),
            kind=p.instrument,
            tuning=p.tuning,
            capo=p.capo,
            roles=tuple(p.roles),
            difficulty=p.difficulty,
            tone=p.tone,
        )
        for p in body.players
    ]
    try:
        result = arrange(tx, players, transpose=body.transpose)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    data = arrangement_to_dict(result)
    analysis = _load_analysis(str(path), path.stat().st_mtime)
    words = _words(analysis, _lyrics(settings, song_id)) if body.lyrics_in_tabs else []
    data["alphatex"] = to_alphatex(result, title=song.title, artist=song.artist, words=words)
    data["title"] = song.title
    data["artist"] = song.artist
    return data


@router.get("/songs/{song_id}/audio/{name}")
def song_audio(
    song_id: str, name: StemName, settings: SettingsDep, engine: EngineDep
) -> FileResponse:
    _get(engine, song_id)
    path = settings.song_dir(song_id) / "stems" / f"{name}.mp3"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Этой дорожки нет.")
    return FileResponse(path, media_type="audio/mpeg")


def _mixdown(folder: Path, keep: list[str], out: Path) -> None:
    """Сумма выбранных дорожек → mp3 (ffmpeg amix без нормализации: громкость как в оригинале)."""
    from fretlines_worker.audio import ffmpeg

    inputs: list[str] = []
    for name in keep:
        inputs += ["-i", str(folder / f"{name}.mp3")]
    mixer = f"amix=inputs={len(keep)}:duration=longest:normalize=0"
    tmp = out.with_suffix(".tmp.mp3")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", mixer, "-c:a", "libmp3lame", "-b:a", "160k", str(tmp)],
        capture_output=True,
        check=False,
        creationflags=flags,
    )  # fmt: skip
    if result.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Не получилось свести дорожки.")
    tmp.replace(out)


@router.get("/songs/{song_id}/mix")
def song_mix(
    song_id: str,
    settings: SettingsDep,
    engine: EngineDep,
    without: Annotated[str, Query(max_length=80)] = "",
) -> FileResponse:
    """Запись без выбранных дорожек: «без гитары» — играть поверх, «без вокала» — караоке.

    Сведение делается один раз и кэшируется рядом со стемами.
    """
    _get(engine, song_id)
    folder = settings.song_dir(song_id) / "stems"
    muted = sorted({name for name in without.split(",") if name in STEMS})
    if not muted:
        path = folder / "mix.mp3"
    elif muted == ["vocals"] and (folder / "instrumental.mp3").exists():
        # Инструментал отдельной моделью чище, чем сумма дорожек без вокала.
        path = folder / "instrumental.mp3"
    else:
        keep = [name for name in STEMS if name not in muted]
        if not keep or any(not (folder / f"{name}.mp3").exists() for name in keep):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Дорожек для сведения нет.")
        path = folder / f"mix-without-{'+'.join(muted)}.mp3"
        with _mix_guard:
            lock = _mix_locks.setdefault(song_id, threading.Lock())
        with lock:
            if not path.exists():
                _mixdown(folder, keep, path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Этой дорожки нет.")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "max-age=3600"})


def _download_name(song: Song, track: str, extension: str) -> str:
    title = re.sub(r'[\/:*?"<>|]+', " ", song.title).strip()[:80] or "Fretlines"
    return f"{title} — {TRACK_LABELS[track]}.{extension}"


@router.get("/songs/{song_id}/download/{track}")
def download_track(
    song_id: str,
    track: StemName,
    settings: SettingsDep,
    engine: EngineDep,
    format: Literal["flac", "mp3"] = "flac",
) -> FileResponse:
    """Дорожка или инструментал файлом: FLAC 24 бита без потерь или mp3 192 кбит/с."""
    song = _get(engine, song_id)
    stems = settings.song_dir(song_id) / "stems"
    path = stems / "flac" / f"{track}.flac" if format == "flac" else stems / f"{track}.mp3"
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Этой дорожки нет. Обнови разбор — дорожки сохранятся заново.",
        )
    return FileResponse(
        path,
        media_type="audio/flac" if format == "flac" else "audio/mpeg",
        filename=_download_name(song, track, format),
    )


@router.get("/songs/{song_id}/download-all")
def download_all(song_id: str, settings: SettingsDep, engine: EngineDep) -> FileResponse:
    """Все дорожки и инструментал одним архивом (FLAC без потерь)."""
    song = _get(engine, song_id)
    lossless = settings.song_dir(song_id) / "stems" / "flac"
    files = sorted(lossless.glob("*.flac")) if lossless.exists() else []
    if not files:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Дорожек без потерь нет — обнови разбор.")
    archive = lossless.parent / "all-flac.zip"
    newest = max(f.stat().st_mtime for f in files)
    with _mix_guard:
        lock = _mix_locks.setdefault(song_id, threading.Lock())
    with lock:
        if not archive.exists() or archive.stat().st_mtime < newest:
            tmp = archive.with_suffix(".tmp")
            # FLAC уже сжат — архив без сжатия собирается мгновенно.
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as bundle:
                for file in files:
                    if file.stem in TRACK_LABELS:
                        bundle.write(file, _download_name(song, file.stem, "flac"))
            tmp.replace(archive)
    title = re.sub(r'[\/:*?"<>|]+', " ", song.title).strip()[:80] or "Fretlines"
    return FileResponse(
        archive, media_type="application/zip", filename=f"{title} — дорожки (FLAC).zip"
    )
