"""Гитара из записи: какая дорожка её несёт и какие ноты на ней звучат (Basic Pitch)."""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

from arranger.model import Note
from fretlines_worker.audio import SAMPLE_RATE, Audio, to_mono
from fretlines_worker.grid import BeatGrid
from fretlines_worker.notes import SR as NOTES_SR
from fretlines_worker.notes import NoteEvent, extract_notes, posteriors

log = logging.getLogger("fretlines.guitar")

# Дорожка должна быть заметной частью микса, иначе на ней только просочившийся мусор.
_GUITAR_SHARE = 0.1
_KEYS_SHARE = 0.12
# Пороги (начало ноты, звучание): на отделённой дорожке модель уверена слабее, чем на чистой
# гитаре, поэтому порог опускаем, пока нот слишком мало. Ниже 0.3/0.2 — уже шум (проверено
# на записях: доля нот, попадающих в аккорд, держится ~0.8 и падает ниже этих порогов).
_THRESHOLDS = ((0.5, 0.3), (0.4, 0.25), (0.35, 0.22), (0.3, 0.2))
_ENOUGH_PER_SECOND = 4.0
_MIN_AMPLITUDE = 0.18


def _rms(audio: NDArray[np.float32]) -> float:
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def pick_source(stems: dict[str, Audio]) -> tuple[str, NDArray[np.float32]] | None:
    """("guitar" | "keys", моно) — откуда брать партию «как в записи», или None."""
    total = _rms(to_mono(sum(stems.values())))  # type: ignore[arg-type]
    if total <= 1e-6:
        return None
    guitar = to_mono(stems["guitar"])
    share = _rms(guitar) / total
    log.info("доля гитары в миксе: %.2f", share)
    if share >= _GUITAR_SHARE:
        return "guitar", guitar
    keys = to_mono(stems["piano"])
    if _rms(keys) / total >= _KEYS_SHARE:
        return "keys", keys
    return None


def clean(events: list[NoteEvent]) -> list[NoteEvent]:
    """Убираем сомнительные ноты и октавные призраки громкой ноты в тот же момент."""
    if not events:
        return []
    loud = float(np.percentile([e.amplitude for e in events], 90))
    kept = [e for e in events if e.amplitude >= max(_MIN_AMPLITUDE, 0.5 * loud)]
    kept.sort(key=lambda e: e.start)
    starts = [e.start for e in kept]
    out: list[NoteEvent] = []
    for i, event in enumerate(kept):
        lo = int(np.searchsorted(starts, event.start - 0.04))
        hi = int(np.searchsorted(starts, event.start + 0.04))
        ghost = any(
            (event.pitch - other.pitch) in (12, 19, 24) and other.amplitude > event.amplitude * 1.6
            for other in kept[lo:hi]
            if other is not kept[i]
        )
        if not ghost:
            out.append(event)
    return out


def listen(audio: NDArray[np.float32]) -> list[NoteEvent]:
    """Ноты дорожки (22.05 кГц): порог опускается, пока нот не станет достаточно."""
    p = posteriors(audio)
    seconds = max(audio.size / NOTES_SR, 1.0)
    events: list[NoteEvent] = []
    for onset, frame in _THRESHOLDS:
        events = extract_notes(p, onset_threshold=onset, frame_threshold=frame, low=36, high=96)
        if len(events) / seconds >= _ENOUGH_PER_SECOND:
            break
    return clean(events)


def transcribe(mono: NDArray[np.float32], grid: BeatGrid) -> tuple[Note, ...]:
    """Ноты дорожки в долях сетки; громкость — из уверенности модели."""
    import librosa

    audio = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=NOTES_SR).astype(np.float32)
    events = listen(audio)
    if not events:
        return ()
    starts = grid.to_beats([e.start for e in events])
    ends = grid.to_beats([e.end for e in events])
    notes = []
    for event, a, b in zip(events, starts, ends, strict=True):
        if a < 0 or b <= a:
            continue
        velocity = int(np.clip(40 + 87 * event.amplitude, 1, 127))
        notes.append(Note(round(float(a), 4), round(float(b - a), 4), event.pitch, velocity))
    return tuple(notes)
