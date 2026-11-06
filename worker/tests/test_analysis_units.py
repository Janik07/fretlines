import numpy as np
import pytest

from arranger.theory import Key, parse_chord
from fretlines_worker.errors import AnalysisError
from fretlines_worker.grid import BeatGrid
from fretlines_worker.harmony import estimate_key, recognize_chords, to_spans
from fretlines_worker.pitch import MELODY, segment


def test_grid_adds_pickup_beats_before_the_first_bar() -> None:
    beats = [0.5 + 0.6 * i for i in range(40)]
    downbeats = beats[1::4]  # первая сильная доля — вторая по счёту: затакт на одну долю
    grid = BeatGrid.build(beats, downbeats, duration=25.0)
    assert grid.beats_per_bar == 4
    # Первая реальная доля стоит на позиции 3 (последняя доля «нулевого» такта).
    assert grid.to_beats([0.5])[0] == pytest.approx(3.0)
    assert grid.to_beats([beats[1]])[0] == pytest.approx(4.0)
    assert grid.times.size % 4 == 0
    assert grid.times[-1] >= 25.0 - 0.6
    assert grid.tempo == pytest.approx(100.0, rel=0.01)


def test_grid_round_trip_and_waltz_meter() -> None:
    beats = [0.6 * i for i in range(30)]
    grid = BeatGrid.build(beats, beats[::3], duration=18.0)
    assert grid.beats_per_bar == 3
    seconds = [1.0, 5.55, 12.3]
    assert grid.to_seconds(grid.to_beats(seconds)) == pytest.approx(seconds)


def test_grid_without_rhythm_is_a_human_error() -> None:
    with pytest.raises(AnalysisError) as info:
        BeatGrid.build([0.1, 0.2], [], duration=10)
    assert info.value.code == "no_rhythm"


def _chroma(names: list[str]) -> np.ndarray:
    columns = []
    for name in names:
        vector = np.full(12, 0.05)
        for pc in parse_chord(name).pitch_classes:
            vector[pc] = 1.0
        columns.append(vector)
    return np.array(columns).T


def test_chords_are_recognized_per_beat() -> None:
    names = ["Am"] * 8 + ["F"] * 8 + ["C"] * 8 + ["G"] * 8
    chroma = _chroma(names)
    bass = np.zeros_like(chroma)
    for i, name in enumerate(names):
        bass[parse_chord(name).root, i] = 1.0
    result = recognize_chords(chroma, bass, chroma.sum(axis=0), Key(9, "minor"))
    assert [c.name() if c else None for c in result] == names
    spans = to_spans(result)
    assert [(s.start, s.end, s.chord.name()) for s in spans] == [
        (0.0, 8.0, "Am"),
        (8.0, 16.0, "F"),
        (16.0, 24.0, "C"),
        (24.0, 32.0, "G"),
    ]


def test_short_blips_are_smoothed_out() -> None:
    names = ["C"] * 6 + ["Am"] + ["C"] * 5
    chroma = _chroma(names)
    result = recognize_chords(chroma, np.zeros_like(chroma), chroma.sum(axis=0), Key(0, "major"))
    assert {c.name() for c in result if c} == {"C"}


def test_silence_is_no_chord() -> None:
    chroma = _chroma(["G"] * 4)
    chroma = np.concatenate([np.zeros((12, 4)), chroma], axis=1)
    result = recognize_chords(chroma, np.zeros_like(chroma), chroma.sum(axis=0), Key(7, "major"))
    assert result[:4] == [None] * 4
    assert result[4] == parse_chord("G")


def test_key_of_a_major_scale_profile() -> None:
    profile = np.zeros(12)
    for pc, weight in zip([7, 9, 11, 0, 2, 4, 6], [5, 2, 3, 2, 4, 2, 1], strict=True):
        profile[pc] = weight
    key, confidence = estimate_key(profile)
    assert key == Key(7, "major")
    assert confidence > 0


def test_vibrato_becomes_one_note_and_glides_split() -> None:
    frames = 300
    t = np.arange(frames) * MELODY.hop_seconds
    midi = np.full(frames, np.nan)
    midi[0:100] = 69 + 0.35 * np.sin(2 * np.pi * 5.5 * t[0:100])  # A4 с вибрато
    midi[100:110] = np.nan  # вдох
    midi[110:200] = 72.0  # C5
    midi[200:290] = 74.1  # D5 сразу после C5
    notes = segment(t, midi, MELODY)
    assert [pitch for _, _, pitch in notes] == [69, 72, 74]
    assert notes[0][1] - notes[0][0] == pytest.approx(1.0, abs=0.02)
