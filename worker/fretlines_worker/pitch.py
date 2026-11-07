"""Одноголосные партии (вокал, бас): высота torchcrepe → ноты на сетке долей.

Вибрато и подъезды сглаживаются медианой: нота — это участок, где высота держится
в пределах ~0.6 полутона; её высота — медиана участка (SPEC §1.4, п. 5).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from arranger.model import Note
from fretlines_worker.audio import SAMPLE_RATE
from fretlines_worker.grid import BeatGrid

CREPE_SR = 16_000  # CREPE слышит от C1 (32.7 Гц) до B7 — fmin не может быть ниже


@dataclass(frozen=True)
class LineSettings:
    fmin: float
    fmax: float
    hop_seconds: float
    min_note: float  # секунды
    periodicity: float
    loudness_db: float


MELODY = LineSettings(
    fmin=70.0, fmax=1100.0, hop_seconds=0.01, min_note=0.09, periodicity=0.5, loudness_db=-38.0
)
BASS = LineSettings(
    fmin=35.0, fmax=330.0, hop_seconds=0.02, min_note=0.1, periodicity=0.45, loudness_db=-40.0
)


def track(
    mono: NDArray[np.float32], settings: LineSettings, device: str
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Времена кадров и высота в MIDI (NaN — тишина или шум)."""
    import librosa
    import torch
    import torchcrepe

    audio = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=CREPE_SR)
    hop = int(CREPE_SR * settings.hop_seconds)
    tensor = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))[None, :]
    model = "full" if device.startswith("cuda") else "tiny"
    with torch.inference_mode():
        frequency, periodicity = torchcrepe.predict(
            tensor,
            CREPE_SR,
            hop,
            settings.fmin,
            settings.fmax,
            model,
            batch_size=2048,
            device=device,
            return_periodicity=True,
            decoder=torchcrepe.decode.viterbi,
        )
        periodicity = torchcrepe.filter.median(periodicity, 3)
    freq = frequency[0].cpu().numpy().astype(np.float64)
    # NaN бывает на тишине и при границах ниже диапазона CREPE (32.7 Гц) — считаем как «нет ноты».
    conf = np.nan_to_num(periodicity[0].cpu().numpy().astype(np.float64), nan=0.0)

    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=hop, center=True)[0]
    rms = rms[: freq.size] if rms.size >= freq.size else np.pad(rms, (0, freq.size - rms.size))
    loud = 20 * np.log10(np.maximum(rms, 1e-9) / max(float(rms.max()), 1e-9)) > settings.loudness_db

    midi = 69 + 12 * np.log2(np.maximum(freq, 1e-6) / 440.0)
    midi[(conf < settings.periodicity) | ~loud] = np.nan
    times = np.arange(freq.size) * settings.hop_seconds
    return times, midi


def onsets(mono: NDArray[np.float32], settings: LineSettings) -> NDArray[np.float64]:
    """Атаки звука (секунды): по ним режутся повторы одной высоты — бас восьмыми, слоги."""
    import librosa

    audio = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=CREPE_SR)
    hop = int(CREPE_SR * settings.hop_seconds)
    found = librosa.onset.onset_detect(
        y=audio, sr=CREPE_SR, hop_length=hop, units="time", backtrack=False, delta=0.12
    )
    return np.asarray(found, dtype=np.float64)


def segment(
    times: NDArray[np.float64],
    midi: NDArray[np.float64],
    settings: LineSettings,
    attacks: NDArray[np.float64] | None = None,
) -> list[tuple[float, float, int]]:
    """Кадры → ноты (начало, конец в секундах, высота).

    attacks — атаки звука: если на ровной высоте случилась атака, это новая нота той же высоты.
    """
    notes: list[tuple[float, float, int]] = []
    hop = settings.hop_seconds
    max_wobble_frames = max(3, int(0.06 / hop))
    start: int | None = None
    values: list[float] = []
    drift = 0
    cuts: set[int] = set()
    if attacks is not None and attacks.size:
        cuts = {round(t / hop) for t in attacks}

    def close(begin: int | None, end_index: int, pitches: list[float]) -> None:
        if begin is None or not pitches or (end_index - begin) * hop < settings.min_note:
            return
        end_time = float(times[end_index - 1] + hop)
        notes.append((float(times[begin]), end_time, round(float(np.median(pitches)))))

    for i, value in enumerate(midi):
        if np.isnan(value):
            close(start, i, values)
            start, values, drift = None, [], 0
            continue
        if start is None:
            start, values, drift = i, [float(value)], 0
            continue
        if i in cuts and (i - start) * hop >= settings.min_note and drift == 0:
            close(start, i, values)
            start, values = i, [float(value)]
            continue
        center = float(np.median(values[-25:]))
        if abs(value - center) > 0.6:
            drift += 1
            if drift >= max_wobble_frames:
                cut = i - drift + 1
                close(start, cut, values)
                start, values, drift = cut, [float(v) for v in midi[cut : i + 1]], 0
            continue
        drift = 0
        values.append(float(value))
    close(start, len(midi), values)
    return notes


def to_notes(segments: list[tuple[float, float, int]], grid: BeatGrid) -> tuple[Note, ...]:
    if not segments:
        return ()
    starts = grid.to_beats([s for s, _, _ in segments])
    ends = grid.to_beats([e for _, e, _ in segments])
    return tuple(
        Note(round(float(a), 4), round(float(b - a), 4), pitch)
        for a, b, (_, _, pitch) in zip(starts, ends, segments, strict=True)
        if b > a and a >= 0
    )


def transcribe(
    mono: NDArray[np.float32], grid: BeatGrid, settings: LineSettings, device: str
) -> tuple[Note, ...]:
    times, midi = track(mono, settings, device)
    return to_notes(segment(times, midi, settings, onsets(mono, settings)), grid)
