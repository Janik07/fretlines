"""Звук через ffmpeg из imageio-ffmpeg: читает любой формат, ставить ничего не нужно."""

from __future__ import annotations

import subprocess
from functools import cache
from itertools import pairwise
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from fretlines_worker.errors import AnalysisError

SAMPLE_RATE = 44_100
MAX_SECONDS = 15 * 60

Audio = NDArray[np.float32]  # (каналы, отсчёты)


@cache
def ffmpeg() -> str:
    import imageio_ffmpeg

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _run(args: list[str], data: bytes | None = None) -> bytes:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", *args],
        input=data,
        capture_output=True,
        check=False,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise AnalysisError(
            "decode_failed",
            "Файл не читается как аудио. Попробуй mp3, wav, m4a или flac.",
        )
    return result.stdout


def decode(path: Path) -> Audio:
    """Файл → стерео float32, 44.1 кГц. Длиннее 15 минут — отказ (SPEC §1.4)."""
    raw = _run(
        [
            "-i",
            str(path),
            "-t",
            str(MAX_SECONDS + 1),
            "-vn",
            "-f",
            "f32le",
            "-ac",
            "2",
            "-ar",
            str(SAMPLE_RATE),
            "pipe:1",
        ]
    )
    audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()
    seconds = audio.shape[1] / SAMPLE_RATE
    if seconds < 5:
        raise AnalysisError("too_short", "Запись слишком короткая — нужно хотя бы 5 секунд.")
    if seconds > MAX_SECONDS:
        raise AnalysisError("too_long", "Трек длиннее 15 минут — такие пока не разбираем.")
    return audio


def encode_mp3(audio: Audio, path: Path, bitrate: str = "160k") -> None:
    channels = audio.shape[0]
    interleaved = np.ascontiguousarray(audio.T, dtype=np.float32).tobytes()
    _run(
        [
            "-f",
            "f32le",
            "-ac",
            str(channels),
            "-ar",
            str(SAMPLE_RATE),
            "-i",
            "pipe:0",
            "-c:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-y",
            str(path),
        ],
        data=interleaved,
    )


def to_mono(audio: Audio) -> NDArray[np.float32]:
    return np.asarray(audio.mean(axis=0), dtype=np.float32)


def peaks(audio: Audio, buckets: int = 1600) -> list[float]:
    """Огибающая для волны в интерфейсе: максимум по модулю в каждом отрезке, 0…1."""
    mono = np.abs(to_mono(audio))
    if mono.size == 0:
        return []
    edges = np.linspace(0, mono.size, buckets + 1, dtype=np.int64)
    values = np.array([mono[a:b].max() if b > a else 0.0 for a, b in pairwise(edges)])
    top = float(values.max()) or 1.0
    return [round(float(v) / top, 3) for v in values]
