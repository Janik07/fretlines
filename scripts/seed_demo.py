"""Демо-песня для пустой библиотеки: синтетический трек Am – F – C – G (для Codespaces и тестов).

Запуск, когда приложение уже работает: python scripts/seed_demo.py [адрес API]
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker" / "tests"))
from synth_song import SR, make_song

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/api"


def call(method: str, path: str, body: bytes | None = None, kind: str = "application/json") -> Any:  # noqa: ANN401 — ответы API разные
    request = urllib.request.Request(
        API + path, data=body, method=method, headers={"Content-Type": kind}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


def wait_for_server(seconds: int = 180) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            call("GET", "/health")
            return
        except OSError:
            time.sleep(2)
    raise SystemExit("Fretlines так и не ответил — посмотри /tmp/fretlines.log")


def main() -> None:
    wait_for_server()
    if call("GET", "/songs"):
        return
    audio, _ = make_song(bpm=96, bars=24, seed=11)
    wav = io.BytesIO()
    sf.write(wav, audio.T, SR, format="WAV")
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="demo.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode()
        + wav.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    song = call("POST", "/songs", body, f"multipart/form-data; boundary={boundary}")
    patch = {"title": "Демо: Am – F – C – G", "artist": "Синтетический трек Fretlines"}
    call("PATCH", f"/songs/{song['id']}", json.dumps(patch).encode())
    print("Демо-песня добавлена:", song["id"])


if __name__ == "__main__":
    main()
