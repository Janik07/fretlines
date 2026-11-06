"""Разборы песен: загрузка файла или ссылки, прогресс, результат, аранжировка, звук."""

from __future__ import annotations

import json
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import Engine, select

from arranger import PlayerSetup, Transcription, arrange, arrangement_to_dict, to_alphatex
from fretlines_api.db import Song, session_scope
from fretlines_api.deps import get_engine, get_runner, get_settings
from fretlines_api.jobs import JobRunner
from fretlines_api.schemas import ArrangementIn, ImportIn, SongOut, SongPatch
from fretlines_api.settings import Settings

router = APIRouter(tags=["songs"])

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg", "opus", "aac", "wma", "aif", "aiff"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "mkv", "avi", "3gp"}
StemName = Literal["mix", "vocals", "bass", "drums", "guitar", "piano", "other"]

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


@router.get("/songs/{song_id}/analysis")
def song_analysis(song_id: str, settings: SettingsDep, engine: EngineDep) -> dict[str, Any]:
    path = _analysis_path(settings, engine, song_id)
    data = _load_analysis(str(path), path.stat().st_mtime)
    tx = data["transcription"]
    return {
        "duration": data["duration"],
        "tempo": tx["tempo"],
        "beats_per_bar": tx["beats_per_bar"],
        "bars": tx["bars"],
        "bar_times": data["bar_times"],
        "key": data["key"],
        "key_confidence": data.get("key_confidence"),
        "stems": data.get("stems", []),
        "warnings": data.get("warnings", []),
        "counts": {
            "chords": len(tx["chords"]),
            "melody": len(tx["melody"]),
            "bass": len(tx["bass"]),
        },
        "device": data.get("device"),
        "timings": data.get("timings", {}),
    }


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
        )
        for p in body.players
    ]
    try:
        result = arrange(tx, players, transpose=body.transpose)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    data = arrangement_to_dict(result)
    data["alphatex"] = to_alphatex(result, title=song.title, artist=song.artist)
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
