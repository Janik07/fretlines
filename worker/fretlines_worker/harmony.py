"""Тональность и аккорды по хромаграмме: шаблоны трезвучий и септаккордов + Витерби."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from arranger.model import ChordSpan
from arranger.theory import INTERVALS, Chord, Key, Quality
from fretlines_worker.grid import BeatGrid

ANALYSIS_SR = 22_050
HOP = 2048

# Профили Крумхансла — Кесслер: насколько каждая ступень «своя» в мажоре и миноре.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

_QUALITIES: tuple[Quality, ...] = ("maj", "min", "7", "min7", "maj7")
_WEIGHTS = {0: 1.0, 3: 1.0, 4: 1.0, 7: 0.8, 10: 0.65, 11: 0.65}
# Обертоны струн подделывают септиму: третья гармоника терции — это большая септима (C → E → B),
# у минора — малая (Am → C → G). Поэтому септаккорды должны «доказать» себя заметнее трезвучий.
_SEVENTH_PENALTY: dict[str, float] = {"maj7": 0.09, "min7": 0.07, "7": 0.05}
_STAY = 0.9


@dataclass(frozen=True)
class Harmony:
    key: Key
    key_confidence: float
    chords: tuple[ChordSpan, ...]


def chroma(mono: NDArray[np.float32]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Хромаграмма CQT и времена кадров (секунды)."""
    import librosa

    c = librosa.feature.chroma_cqt(
        y=mono, sr=ANALYSIS_SR, hop_length=HOP, bins_per_octave=36, n_chroma=12
    )
    times = librosa.frames_to_time(np.arange(c.shape[1]), sr=ANALYSIS_SR, hop_length=HOP)
    return np.asarray(c, dtype=np.float64), np.asarray(times, dtype=np.float64)


def bass_chroma(mono: NDArray[np.float32]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Хрома низких частот (от C1 три октавы) — подсказка, какой тон в басу."""
    import librosa

    cqt = np.abs(
        librosa.cqt(
            y=mono,
            sr=ANALYSIS_SR,
            hop_length=HOP,
            fmin=librosa.note_to_hz("C1"),
            n_bins=36,
            bins_per_octave=12,
        )
    )
    c = cqt.reshape(3, 12, -1).sum(axis=0)
    times = librosa.frames_to_time(np.arange(c.shape[1]), sr=ANALYSIS_SR, hop_length=HOP)
    return np.asarray(c, dtype=np.float64), np.asarray(times, dtype=np.float64)


def per_beat(
    features: NDArray[np.float64], times: NDArray[np.float64], grid: BeatGrid
) -> NDArray[np.float64]:
    """Среднее по каждой доле: (12, число долей)."""
    beat_index = np.floor(grid.to_beats(times)).astype(np.int64)
    total = grid.times.size
    out = np.zeros((features.shape[0], total))
    counts = np.zeros(total)
    valid = (beat_index >= 0) & (beat_index < total)
    np.add.at(out.T, beat_index[valid], features[:, valid].T)
    np.add.at(counts, beat_index[valid], 1)
    return out / np.maximum(counts, 1)


def estimate_key(profile: NDArray[np.float64]) -> tuple[Key, float]:
    """Тональность — профиль, сильнее всего похожий на суммарную хрому."""
    if not np.any(profile):
        return Key(0, "major"), 0.0
    scores: list[tuple[float, Key]] = []
    for tonic in range(12):
        rolled = np.roll(profile, -tonic)
        scores.append((float(np.corrcoef(rolled, _MAJOR)[0, 1]), Key(tonic, "major")))
        scores.append((float(np.corrcoef(rolled, _MINOR)[0, 1]), Key(tonic, "minor")))
    scores.sort(key=lambda item: item[0], reverse=True)
    best, second = scores[0][0], scores[1][0]
    return scores[0][1], round(max(0.0, best - second) * 5 + max(0.0, best), 3)


def _templates() -> tuple[list[Chord], NDArray[np.float64]]:
    chords: list[Chord] = []
    rows = []
    for quality in _QUALITIES:
        for root in range(12):
            vector = np.zeros(12)
            for interval in INTERVALS[quality]:
                vector[(root + interval) % 12] = _WEIGHTS[interval]
            chords.append(Chord(root, quality))
            rows.append(vector / np.linalg.norm(vector))
    return chords, np.array(rows)


def _triad_kind(chord: Chord) -> str:
    return "min" if chord.quality in ("min", "min7") else "maj"


def _diatonic(key: Key) -> set[tuple[int, str]]:
    """Трезвучия ступеней тональности (для лёгкого предпочтения при сомнениях)."""
    major_tonic = key.relative_major
    scale = [(major_tonic + i) % 12 for i in (0, 2, 4, 5, 7, 9)]
    kinds = ["maj", "min", "min", "maj", "maj", "min"]
    out = set(zip(scale, kinds, strict=True))
    if key.mode == "minor":
        out.add(((key.tonic + 7) % 12, "maj"))  # гармонический минор: мажорная доминанта
    return out


def recognize_chords(
    harmonic: NDArray[np.float64], bass: NDArray[np.float64], energy: NDArray[np.float64], key: Key
) -> list[Chord | None]:
    """Аккорд на каждой доле; None — тишина или нет гармонии."""
    chords, templates = _templates()
    norms = np.linalg.norm(harmonic, axis=0)
    unit = harmonic / np.maximum(norms, 1e-9)
    scores = templates @ unit  # (аккорды, доли)

    bass_unit = bass / np.maximum(bass.max(axis=0), 1e-9)
    roots = np.array([c.root for c in chords])
    scores += 0.25 * bass_unit[roots, :]
    penalty = np.array([_SEVENTH_PENALTY.get(c.quality, 0.0) for c in chords])
    scores -= penalty[:, None]
    diatonic = _diatonic(key)
    bonus = np.array([(c.root, _triad_kind(c)) in diatonic for c in chords])
    scores += 0.04 * bonus[:, None]

    silent = energy < 0.04 * max(float(energy.max()), 1e-9)
    no_chord = np.where(silent, 2.0, 0.45)
    all_scores = np.vstack([scores, no_chord[None, :]])

    n_states = all_scores.shape[0]
    emit = all_scores * 14.0
    log_stay = np.log(_STAY)
    log_move = np.log((1 - _STAY) / (n_states - 1))
    best = emit[:, 0].copy()
    back = np.zeros(all_scores.shape, dtype=np.int64)
    for t in range(1, all_scores.shape[1]):
        top = int(np.argmax(best))
        stay = best + log_stay
        move = best[top] + log_move
        choose_move = move > stay
        back[:, t] = np.where(choose_move, top, np.arange(n_states))
        best = np.where(choose_move, move, stay) + emit[:, t]
    state = int(np.argmax(best))
    path = [state]
    for t in range(all_scores.shape[1] - 1, 0, -1):
        state = int(back[state, t])
        path.append(state)
    path.reverse()
    return [chords[s] if s < len(chords) else None for s in path]


def to_spans(per_beat_chords: list[Chord | None], min_beats: int = 2) -> tuple[ChordSpan, ...]:
    """Доли → отрезки аккордов; очень короткие отдаём соседу слева."""
    runs: list[tuple[int, int, Chord | None]] = []
    for beat, chord in enumerate(per_beat_chords):
        if runs and runs[-1][2] == chord:
            runs[-1] = (runs[-1][0], beat + 1, chord)
        else:
            runs.append((beat, beat + 1, chord))
    merged: list[tuple[int, int, Chord | None]] = []
    for start, end, chord in runs:
        if merged and (end - start < min_beats or merged[-1][2] == chord):
            merged[-1] = (merged[-1][0], end, merged[-1][2])
        else:
            merged.append((start, end, chord))
    return tuple(ChordSpan(float(s), float(e), c) for s, e, c in merged if c is not None)


def analyze(
    harmonic_mono: NDArray[np.float32], bass_mono: NDArray[np.float32], grid: BeatGrid
) -> Harmony:
    c, times = chroma(harmonic_mono)
    b, b_times = bass_chroma(bass_mono)
    harmonic = per_beat(c, times, grid)
    bass = per_beat(b, b_times, grid)
    energy = harmonic.sum(axis=0)
    key, confidence = estimate_key(harmonic.sum(axis=1) + 0.5 * bass.sum(axis=1))
    chords = recognize_chords(harmonic, bass, energy, key)
    return Harmony(key, confidence, to_spans(chords))
