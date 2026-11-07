from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from fretlines_api.db import Song

Status = Literal["queued", "running", "done", "failed"]
RoleName = Literal["original", "melody", "bass", "rhythm", "pad", "percussion"]
Level = Literal["easy", "medium", "full"]
Kind = Literal["acoustic", "electric", "bass"]
ToneName = Literal[
    "auto", "steel", "nylon", "clean", "crunch", "drive", "lead", "jazz", "finger", "pick"
]


class ErrorOut(BaseModel):
    code: str
    message: str


class SongOut(BaseModel):
    id: str
    title: str
    artist: str | None
    source_kind: Literal["file", "url"]
    source_url: str | None
    status: Status
    stage: str | None
    progress: float
    error: ErrorOut | None
    duration: float | None
    tempo: float | None
    key: str | None
    device: str | None
    setup: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def of(cls, song: Song) -> SongOut:
        error = None
        if song.status == "failed":
            error = ErrorOut(
                code=song.error_code or "internal",
                message=song.error_message or "Разбор не удался.",
            )
        return cls(
            id=song.id,
            title=song.title,
            artist=song.artist,
            source_kind="url" if song.source_kind == "url" else "file",
            source_url=song.source_url,
            status=song.status,  # type: ignore[arg-type]
            stage=song.stage,
            progress=song.progress,
            error=error,
            duration=song.duration,
            tempo=song.tempo,
            key=song.key,
            device=song.device,
            setup=json.loads(song.setup) if song.setup else None,
            created_at=song.created_at,
        )


class ImportIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class SongPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    artist: str | None = Field(default=None, max_length=300)
    setup: dict[str, Any] | None = None


class PlayerIn(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=40)
    instrument: Kind = "acoustic"
    tuning: str = Field(default="standard", max_length=32)
    capo: int = Field(default=0, ge=0, le=12)
    roles: list[RoleName] = Field(min_length=1, max_length=5)
    difficulty: Level = "medium"
    tone: ToneName = "auto"


class ArrangementIn(BaseModel):
    players: list[PlayerIn] = Field(min_length=1, max_length=4)
    transpose: int = Field(default=0, ge=-12, le=12)
    lyrics_in_tabs: bool = True  # подписывать слова песни под долями партий


class WordIn(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class LineIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    words: list[WordIn] = Field(max_length=60)


class LyricsIn(BaseModel):
    source: str | None = None
    language: str | None = Field(default=None, max_length=12)
    lines: list[LineIn] = Field(max_length=600)
