"""Basic Pitch через onnxruntime: начала нот и время кадров не «уплывают» к концу записи."""

import numpy as np
import pytest

from fretlines_worker.notes import SR, extract_notes, model_path, pitch_class_profile, posteriors


@pytest.fixture(scope="module")
def ready() -> None:
    try:
        model_path()
    except OSError:
        pytest.skip("нет модели Basic Pitch и нет сети, чтобы её скачать")


def _tones(starts: list[float], pitch: int, seconds: float) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    out = np.zeros_like(t)
    freq = 440.0 * 2 ** ((pitch - 69) / 12)
    for start in starts:
        on = (t >= start) & (t < start + 0.5)
        out[on] += 0.5 * np.sin(2 * np.pi * freq * (t[on] - start)) * np.exp(-(t[on] - start) * 2)
    return out.astype(np.float32)


@pytest.mark.usefixtures("ready")
def test_onsets_land_on_time_even_late_in_the_song() -> None:
    starts = [0.5, 3.0, 20.0, 41.5]  # 41.5 с — после двух десятков окон модели
    events = extract_notes(posteriors(_tones(starts, 69, 43.0)))
    found = [e.start for e in events if e.pitch == 69]
    assert len(found) == len(starts)
    for got, expected in zip(found, starts, strict=True):
        assert abs(got - expected) < 0.04


@pytest.mark.usefixtures("ready")
def test_pitch_class_profile_points_at_the_note() -> None:
    p = posteriors(_tones([0.2, 1.0], 64, 2.0))
    profile = pitch_class_profile(p, floor=0.1).sum(axis=1)
    assert int(np.argmax(profile)) == 4  # E
