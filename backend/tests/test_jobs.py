from pathlib import Path
from typing import Any

import pytest

from fretlines_api import jobs
from fretlines_api.db import Song, create_db_engine, init_db, session_scope
from fretlines_worker import pipeline
from fretlines_worker.errors import AnalysisError


@pytest.fixture
def database(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = create_db_engine(url)
    init_db(engine)
    with session_scope(engine) as session:
        session.add(Song(id="s1", title="Песня", source_kind="file"))
        session.commit()
    return url


def _song(url: str) -> Song:
    with session_scope(create_db_engine(url)) as session:
        song = session.get(Song, "s1")
        assert song is not None
        return song


def test_job_reports_progress_and_finishes(
    tmp_path: Path, database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[float] = []

    def fake(folder: Path, **kwargs: Any) -> dict[str, Any]:
        kwargs["on_meta"]({"key": "Am", "tempo": 96.0, "device": "cpu"})
        kwargs["report"]("stems", 0.5)
        seen.append(_song(database).progress)
        return {}

    monkeypatch.setattr(pipeline, "run_analysis", fake)
    jobs.run_job("s1", str(tmp_path), database, "auto")

    song = _song(database)
    assert song.status == "done"
    assert song.progress == 1.0
    assert (song.key, song.tempo, song.device) == ("Am", 96.0, "cpu")
    assert 0 < seen[0] < 1


def test_job_failure_keeps_a_human_message(
    tmp_path: Path, database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(folder: Path, **kwargs: Any) -> dict[str, Any]:
        raise AnalysisError("decode_failed", "Файл не читается как аудио.")

    monkeypatch.setattr(pipeline, "run_analysis", fake)
    jobs.run_job("s1", str(tmp_path), database, "auto")

    song = _song(database)
    assert song.status == "failed"
    assert song.error_code == "decode_failed"
    assert song.error_message == "Файл не читается как аудио."


def test_unexpected_crash_is_reported_politely(
    tmp_path: Path, database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(folder: Path, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "run_analysis", fake)
    jobs.run_job("s1", str(tmp_path), database, "auto")
    song = _song(database)
    assert song.status == "failed"
    assert song.error_code == "internal"
    assert "boom" not in (song.error_message or "")


def test_stage_weights_cover_all_stages() -> None:
    assert pytest.approx(sum(pipeline.stage_weights(True).values())) == 1.0
    assert "download" not in pipeline.stage_weights(False)
