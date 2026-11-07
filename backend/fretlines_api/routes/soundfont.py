"""Большой банк звуков для плеера: MuseScore General (MIT, ~40 МБ) — гитары записаны вживую.

Скачивается сервером один раз в .models/soundfont/ при первом запросе (в фоне). Пока его нет,
плеер играет маленьким встроенным банком alphaTab — интерфейс об этом не беспокоится.
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

log = logging.getLogger("fretlines.soundfont")

router = APIRouter(tags=["soundfont"])

SOUNDFONT_URL = (
    "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3"
)
SOUNDFONT_BYTES = 39_900_972
_lock = threading.Lock()
_downloading = False


def soundfont_path() -> Path:
    return Path.cwd() / ".models" / "soundfont" / "MuseScore_General.sf3"


def _download(path: Path) -> None:
    global _downloading
    tmp = path.with_suffix(".part")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(SOUNDFONT_URL, headers={"User-Agent": "Fretlines/0.3"})
        with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        if tmp.stat().st_size != SOUNDFONT_BYTES:
            raise OSError(f"неполный файл: {tmp.stat().st_size} байт")
        tmp.replace(path)
        log.info("банк звуков скачан: %s", path)
    except OSError as error:
        log.warning("банк звуков не скачался: %s", error)
        tmp.unlink(missing_ok=True)
    finally:
        with _lock:
            _downloading = False


def ensure_soundfont() -> bool:
    """True — файл уже есть. Иначе запускает фоновую загрузку (если она ещё не идёт)."""
    global _downloading
    path = soundfont_path()
    if path.exists():
        return True
    with _lock:
        if not _downloading:
            _downloading = True
            threading.Thread(target=_download, args=(path,), daemon=True).start()
    return False


@router.get("/soundfont")
def soundfont() -> FileResponse:
    if not ensure_soundfont():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Банк звуков ещё скачивается.")
    return FileResponse(
        soundfont_path(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
