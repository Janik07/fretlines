"""Доли и сильные доли (Beat This!), акценты барабанов для схемы боя."""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

from fretlines_worker.audio import SAMPLE_RATE
from fretlines_worker.grid import BeatGrid

log = logging.getLogger("fretlines.rhythm")


def track_beats(mono: NDArray[np.float32], device: str) -> tuple[list[float], list[float]]:
    """Секунды долей и сильных долей. Если модель недоступна — доли librosa, такты угадаем."""
    try:
        from beat_this.inference import Audio2Beats

        model = Audio2Beats(checkpoint_path="final0", device=device, dbn=False)
        beats, downbeats = model(mono, SAMPLE_RATE)
        if len(beats) >= 8:
            return [float(b) for b in beats], [float(d) for d in downbeats]
        log.warning("Beat This! нашёл мало долей (%d) — пробую librosa", len(beats))
    except Exception:
        log.exception("Beat This! не сработал — пробую librosa")

    import librosa

    y = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=22_050)
    _, times = librosa.beat.beat_track(y=y, sr=22_050, units="time")
    return [float(t) for t in times], []


def drum_accents(
    drums: NDArray[np.float32], grid: BeatGrid, active_only: bool = False
) -> tuple[float, ...]:
    """Средняя сила ударов на каждой шестнадцатой такта, 0…1 — основа для схемы боя.

    active_only — считать только такты, где дорожка звучит (гитара молчит в куплетах — эти
    такты не должны «обнулять» схему боя).
    """
    import librosa

    sr = 22_050
    hop = 256
    y = librosa.resample(drums, orig_sr=SAMPLE_RATE, target_sr=sr)
    envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    if envelope.size == 0 or not np.any(envelope):
        return ()
    times = librosa.times_like(envelope, sr=sr, hop_length=hop)
    slots = grid.beats_per_bar * 4
    positions = np.arange(grid.bars * slots) / 4.0
    seconds = grid.to_seconds(positions)
    index = np.clip(np.searchsorted(times, seconds), 0, envelope.size - 1)
    padded = np.pad(envelope, 2, mode="edge")
    window = np.stack([padded[index + k] for k in range(5)]).max(axis=0)
    per_slot = window.reshape(grid.bars, slots)
    if active_only:
        loudness = per_slot.sum(axis=1)
        active = loudness >= 0.3 * float(np.percentile(loudness, 90))
        if active.sum() < 4:
            return ()
        per_slot = per_slot[active]
    # Берём медиану по тактам: так случайные сбивки не перекраивают схему.
    profile = np.median(per_slot, axis=0)
    top = float(profile.max())
    if top <= 0:
        return ()
    return tuple(round(float(v) / top, 3) for v in profile)
