"""Звук по ссылке (YouTube, TikTok и другие сайты, которые понимает yt-dlp)."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fretlines_worker.audio import MAX_SECONDS, ffmpeg
from fretlines_worker.errors import AnalysisError

MAX_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class Downloaded:
    path: Path
    title: str | None
    artist: str | None
    duration: float | None


def check_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AnalysisError("bad_url", "Это не похоже на ссылку. Скопируй адрес видео целиком.")
    return url.strip()


def _deno() -> str | None:
    """yt-dlp решает задачки YouTube на JavaScript — deno ставится вместе с зависимостями."""
    found = shutil.which("deno")
    if found:
        return found
    scripts = Path(sys.executable).parent
    for name in ("deno.exe", "deno"):
        candidate = scripts / name
        if candidate.exists():
            return str(candidate)
    return None


def _friendly(error: Exception) -> AnalysisError:
    text = str(error).lower()
    if "unsupported url" in text:
        return AnalysisError(
            "unsupported_url", "Эту ссылку не открыть. Подойдут YouTube, TikTok и похожие сайты."
        )
    if "private" in text or "sign in" in text or "login" in text or "age" in text:
        return AnalysisError(
            "private_media", "Видео закрыто или требует входа — скачать не выйдет."
        )
    if "unavailable" in text or "not available" in text or "removed" in text or "404" in text:
        return AnalysisError(
            "media_unavailable",
            "Видео недоступно: его удалили, закрыли или оно не открывается в твоей стране.",
        )
    if "too long" in text or "duration" in text:
        return AnalysisError("too_long", "Видео длиннее 15 минут — такие пока не разбираем.")
    return AnalysisError(
        "download_failed",
        "Не получилось скачать звук по ссылке. Проверь, что видео открывается без входа, "
        "или загрузи файл.",
    )


def download_audio(url: str, folder: Path, on_progress: Callable[[float], None]) -> Downloaded:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = check_url(url)
    folder.mkdir(parents=True, exist_ok=True)

    def hook(status: dict[str, Any]) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            if total:
                on_progress(min(0.99, float(status.get("downloaded_bytes", 0)) / float(total)))

    def too_long(info: dict[str, Any], *, incomplete: bool) -> str | None:
        duration = info.get("duration")
        if duration and duration > MAX_SECONDS:
            return "too long"
        return None

    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "max_filesize": MAX_BYTES,
        "match_filter": too_long,
        "progress_hooks": [hook],
        "ffmpeg_location": ffmpeg(),
        "socket_timeout": 30,
        "retries": 3,
    }
    deno = _deno()
    if deno:
        options["js_runtimes"] = {"deno": {"path": deno}}

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as error:
        raise _friendly(error) from error
    if info is None:
        raise AnalysisError("download_failed", "По ссылке не нашлось ни видео, ни звука.")
    if info.get("duration") and info["duration"] > MAX_SECONDS:
        raise AnalysisError("too_long", "Видео длиннее 15 минут — такие пока не разбираем.")

    files = sorted(folder.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not files:
        raise AnalysisError(
            "download_failed", "Звук скачался, но файл не нашёлся. Попробуй ещё раз."
        )
    on_progress(1.0)
    title = info.get("track") or info.get("title")
    artist = info.get("artist") or info.get("creator") or info.get("uploader")
    return Downloaded(files[0], title, artist, info.get("duration"))
