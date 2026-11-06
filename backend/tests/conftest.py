import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arranger.model import ChordSpan, Note, Transcription
from arranger.theory import Key, parse_chord
from fretlines_api.db import Song, session_scope
from fretlines_api.main import create_app
from fretlines_api.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        frontend_dir=tmp_path / "no-frontend",
        max_upload_mb=1,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # Очередь не запускаем: тесты API не должны поднимать PyTorch.
    with TestClient(create_app(settings, run_jobs=False)) as test_client:
        yield test_client


def transcription() -> Transcription:
    chords = tuple(
        ChordSpan(i * 8.0, i * 8.0 + 8.0, parse_chord(n))
        for i, n in enumerate(["Am", "F", "C", "G"])
    )
    melody = tuple(
        Note(i * 1.0, 0.9, p) for i, p in enumerate([69, 72, 74, 76, 74, 72, 69, 67] * 4)
    )
    return Transcription(
        tempo=100.0, beats_per_bar=4, bars=8, key=Key(9, "minor"), chords=chords, melody=melody
    )


@pytest.fixture
def ready_song(client: TestClient, settings: Settings) -> str:
    """Разобранная песня: строка в базе и analysis.json, как после воркера."""
    song_id = "a" * 32
    folder = settings.song_dir(song_id)
    folder.mkdir(parents=True)
    analysis = {
        "version": 1,
        "duration": 19.2,
        "bar_times": [i * 2.4 for i in range(8)],
        "key": "Am",
        "key_confidence": 0.7,
        "transcription": transcription().to_dict(),
        "stems": ["mix"],
        "warnings": [],
    }
    (folder / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    engine = client.app.state.engine  # type: ignore[attr-defined]
    with session_scope(engine) as session:
        session.add(Song(id=song_id, title="Тестовая", source_kind="file", status="done", key="Am"))
        session.commit()
    return song_id
