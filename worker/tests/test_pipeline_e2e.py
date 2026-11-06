"""Полный разбор синтетической песни с настоящими моделями. Долго: pytest -m slow."""

import json
from pathlib import Path

import pytest
import soundfile as sf
from synth_song import SR, make_song

from arranger.theory import parse_chord
from fretlines_worker.pipeline import run_analysis


def majmin(name: str) -> str:
    """Сравнение по стандарту MIREX «majmin»: корень и мажор/минор, септимы не важны."""
    return parse_chord(name).simplified().name()


@pytest.mark.slow
def test_full_pipeline_finds_the_progression(tmp_path: Path) -> None:
    audio, labels = make_song()
    sf.write(tmp_path / "source.wav", audio.T, SR)
    stages: list[str] = []
    meta: dict[str, object] = {}

    analysis = run_analysis(
        tmp_path,
        source_url=None,
        device="cpu",
        report=lambda stage, _: stages.append(stage),
        on_meta=meta.update,
        models_dir=Path.cwd() / ".models",
    )

    assert {"decode", "stems", "rhythm", "harmony", "melody", "bass", "save"} <= set(stages)
    assert (tmp_path / "analysis.json").exists()
    assert (tmp_path / "stems" / "mix.mp3").exists()
    tx = analysis["transcription"]
    assert tx["beats_per_bar"] == 4
    assert abs(tx["tempo"] - 100) < 3
    assert analysis["key"] in ("Am", "C")

    # Точность аккордов по времени (SPEC §1.9: ≥ 80 %), сравниваем по долям, «majmin».
    expected = {}
    for bar, name in enumerate(labels):
        for beat in range(4):
            expected[bar * 4 + beat] = name
    found = {}
    for span in tx["chords"]:
        for beat in range(int(span["start"]), int(span["end"])):
            found[beat] = majmin(span["chord"])
    offsets = [0, 4, -4]  # анализ может поставить первый такт на такт раньше или позже
    best = max(
        sum(found.get(b + off) == name for b, name in expected.items()) / len(expected)
        for off in offsets
    )
    assert best >= 0.8, json.dumps(tx["chords"][:12], ensure_ascii=False)
    assert meta.get("duration")
