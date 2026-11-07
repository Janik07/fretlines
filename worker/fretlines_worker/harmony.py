"""Тональность и аккорды по хромаграмме: шаблоны трезвучий и септаккордов + Витерби.

Хрома берётся из двух источников: CQT по гармоническим дорожкам и вероятности нот Basic Pitch
(в ней почти нет обертонов). Смена аккорда вероятнее на сильной доле, чем посреди такта.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from arranger.model import ChordSpan
from arranger.theory import INTERVALS, Chord, Key, Quality
from fretlines_worker.grid import BeatGrid

if TYPE_CHECKING:
    from fretlines_worker.notes import Posteriors

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
# Вероятность, что аккорд не сменится на этой доле: на первой доле такта смена частая,
# на середине такта — реже, на слабых долях — редко.
_STAY_DOWNBEAT = 0.7
_STAY_HALF_BAR = 0.8
_STAY_WEAK = 0.96
# Доля хромы из нот Basic Pitch в общей хроме (остальное — CQT). Подобрано на записях:
# одна CQT путает аккорды с общими нотами (Am ↔ F ↔ C), одни ноты теряют тихие голоса.
NOTE_CHROMA_WEIGHT = 0.4
_NOTE_FLOOR = 0.12  # слабые вероятности нот — шум, в хрому не идут


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


def stay_probabilities(beats: int, beats_per_bar: int) -> NDArray[np.float64]:
    """Для каждой доли — вероятность, что аккорд на ней не сменится (доля 0 — сильная)."""
    position = np.arange(beats) % max(beats_per_bar, 1)
    stay = np.full(beats, _STAY_WEAK)
    if beats_per_bar % 2 == 0:
        stay[position == beats_per_bar // 2] = _STAY_HALF_BAR
    stay[position == 0] = _STAY_DOWNBEAT
    return stay


def recognize_chords(
    harmonic: NDArray[np.float64],
    bass: NDArray[np.float64],
    energy: NDArray[np.float64],
    key: Key,
    beats_per_bar: int = 4,
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
    stay_p = stay_probabilities(all_scores.shape[1], beats_per_bar)
    log_stay = np.log(stay_p)
    log_move = np.log((1 - stay_p) / (n_states - 1))
    best = emit[:, 0].copy()
    back = np.zeros(all_scores.shape, dtype=np.int64)
    for t in range(1, all_scores.shape[1]):
        top = int(np.argmax(best))
        stay = best + log_stay[t]
        move = best[top] + log_move[t]
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


def _unit(features: NDArray[np.float64]) -> NDArray[np.float64]:
    unit: NDArray[np.float64] = features / np.maximum(np.linalg.norm(features, axis=0), 1e-9)
    return unit


def blend_chroma(
    cqt: NDArray[np.float64], notes: NDArray[np.float64] | None, weight: float = NOTE_CHROMA_WEIGHT
) -> NDArray[np.float64]:
    """Средневзвешенная хрома по долям; доли, где модель нот молчит, остаются на CQT."""
    if notes is None:
        return cqt
    note_unit = _unit(notes)
    has_notes = np.linalg.norm(notes, axis=0) > 1e-6
    mixed = (1 - weight) * _unit(cqt) + weight * note_unit
    return np.where(has_notes[None, :], mixed, _unit(cqt))


def analyze(
    harmonic_mono: NDArray[np.float32],
    bass_mono: NDArray[np.float32],
    grid: BeatGrid,
    notes: Posteriors | None = None,
) -> Harmony:
    c, times = chroma(harmonic_mono)
    b, b_times = bass_chroma(bass_mono)
    cqt = per_beat(c, times, grid)
    bass = per_beat(b, b_times, grid)
    energy = cqt.sum(axis=0)
    note_chroma = None
    if notes is not None:
        from fretlines_worker.notes import pitch_class_profile

        profile = pitch_class_profile(notes, floor=_NOTE_FLOOR)
        note_chroma = per_beat(profile, notes.times, grid)
    harmonic = blend_chroma(cqt, note_chroma)
    # Тональность — по громким долям: тихие вступления и паузы не должны её перекашивать.
    loudness = energy / max(float(energy.max()), 1e-9)
    key_profile = (harmonic * loudness).sum(axis=1)
    key_profile /= max(float(key_profile.sum()), 1e-9)
    bass_profile = bass.sum(axis=1) / max(float(bass.sum()), 1e-9)
    key, confidence = estimate_key(key_profile + 0.5 * bass_profile)
    chords = recognize_chords(harmonic, bass, energy, key, grid.beats_per_bar)
    return Harmony(key, confidence, to_spans(chords))
