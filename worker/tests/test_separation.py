"""Двухшаговое разделение (вокал моделью, инструменты — Demucs) и тембр гитары в записи."""

from pathlib import Path

import numpy as np
import pytest

from arranger.model import Note
from fretlines_worker import separation
from fretlines_worker.audio import Audio
from fretlines_worker.guitar import single_note_share
from fretlines_worker.timbre import guitar_sound, guitar_tone

N = 1000


def _fake_demucs(audio: Audio, device: str, on_progress: object) -> dict[str, Audio]:
    """Делит вход поровну на шесть дорожек — сумма совпадает с входом, как у Demucs."""
    return dict.fromkeys(separation.STEMS, audio / 6)


def test_max_quality_takes_vocals_from_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    audio = np.ones((2, N), dtype=np.float32)
    vocals = np.full((2, N), 0.25, dtype=np.float32)

    def split(*args: object, **kwargs: object) -> tuple[Audio, Audio]:
        return vocals, audio - vocals

    monkeypatch.setattr(separation, "split_vocals", split)
    monkeypatch.setattr(separation, "_demucs", _fake_demucs)
    stems, instrumental, models = separation.separate(
        audio, "cpu", lambda f: None, quality="max", workdir=tmp_path, models_dir=tmp_path
    )
    assert models == [separation.VOCAL_MODELS["cpu"], separation.MODEL]
    assert np.allclose(stems["vocals"], 0.25)
    assert np.allclose(instrumental, 0.75)
    # Остатки голоса в инструментале уходят в «остальное»: дорожки вместе = вся песня.
    total = sum(stems.values())
    assert np.allclose(total, audio)


def test_failed_vocal_model_falls_back_to_demucs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(*args: object, **kwargs: object) -> tuple[Audio, Audio]:
        raise OSError("модель не скачалась")

    monkeypatch.setattr(separation, "split_vocals", broken)
    monkeypatch.setattr(separation, "_demucs", _fake_demucs)
    audio = np.ones((2, N), dtype=np.float32)
    _, instrumental, models = separation.separate(
        audio, "cpu", lambda f: None, quality="max", workdir=tmp_path, models_dir=tmp_path
    )
    assert models == [separation.MODEL]
    assert np.allclose(instrumental, audio * 5 / 6)


def test_vocal_model_depends_on_the_device() -> None:
    assert "roformer" in separation.vocal_model("cuda:0")
    assert separation.vocal_model("cpu").endswith(".onnx")


def test_guitar_tone_thresholds_match_reference_recordings() -> None:
    # Значения — ответы модели на гитарные дорожки эталонных записей (см. timbre.guitar_tone).
    distorted = {
        "guitar": 0.75,
        "electric": 0.33,
        "acoustic": 0.03,
        "distortion": 0.39,
        "metal": 0.01,
    }
    acoustic = {
        "guitar": 0.47,
        "electric": 0.07,
        "acoustic": 0.24,
        "distortion": 0.02,
        "metal": 0.0,
    }
    clean = {"guitar": 0.2, "electric": 0.05, "acoustic": 0.01, "distortion": 0.01, "metal": 0.0}
    silent = {
        "guitar": 0.03,
        "electric": 0.006,
        "acoustic": 0.004,
        "distortion": 0.005,
        "metal": 0.0,
    }
    assert guitar_tone(distorted) == "distorted"
    assert guitar_tone(acoustic) == "acoustic"
    assert guitar_tone(clean) == "clean"
    assert guitar_tone(silent) == ""


def _scores(**values: float) -> dict[str, float]:
    """Ответ модели: всё по нулям, кроме названного."""
    base = {"guitar": 0.6, "electric": 0.3, "acoustic": 0.02, "distortion": 0.01, "metal": 0.0}
    return {**base, **values}


def test_clean_guitar_preset_follows_the_genre_and_effects() -> None:
    clean = _scores()
    assert guitar_sound(clean, {"jazz": 0.4}, 0.3) == "jazz"
    assert guitar_sound(clean, {"funk": 0.2}, 0.3) == "funk"
    assert guitar_sound(clean, {"disco": 0.15, "soul": 0.1, "rnb": 0.1}, 0.3) == "funk"
    assert guitar_sound(clean, {"ambient": 0.15}, 0.3) == "ambient"
    assert guitar_sound(_scores(echo=0.3), {"pop": 0.4}, 0.3) == "ambient"
    assert guitar_sound(_scores(chorus=0.12), {"pop": 0.4}, 0.3) == "chorus"
    assert guitar_sound(clean, {"pop": 0.5}, 0.3) == "clean"


def test_distorted_guitar_preset_follows_gain_genre_and_playing() -> None:
    heavy = _scores(distortion=0.45)
    assert guitar_sound(_scores(distortion=0.4, metal=0.3), {}, 0.2) == "metal"
    assert guitar_sound(heavy, {"metal": 0.4}, 0.2) == "metal"
    assert guitar_sound(heavy, {"psychedelic": 0.2}, 0.2) == "fuzz"
    assert guitar_sound(heavy, {"rock": 0.5}, 0.9) == "lead"  # одни одиночные ноты — соло
    assert guitar_sound(heavy, {"rock": 0.5}, 0.2) == "drive"
    assert guitar_sound(_scores(distortion=0.18), {"rock": 0.5}, 0.2) == "crunch"
    assert guitar_sound(_scores(distortion=0.18), {"blues": 0.3}, 0.2) == "blues"


def test_no_electric_preset_for_acoustic_or_silence() -> None:
    assert guitar_sound(_scores(acoustic=0.3, electric=0.05), {"funk": 0.5}, 0.2) == ""
    silent = {"guitar": 0.01, "electric": 0.0, "acoustic": 0.0, "distortion": 0.0, "metal": 0.0}
    assert guitar_sound(silent, {}, 0.0) == ""


def test_single_note_share_counts_strokes_not_notes() -> None:
    chord = [Note(0.0, 0.5, p) for p in (48, 52, 55)]  # один удар
    riff = [Note(1.0 + i * 0.5, 0.4, 60 + i) for i in range(3)]  # три одиночные ноты
    assert single_note_share([*chord, *riff]) == 0.75
    assert single_note_share([]) == 0.0
