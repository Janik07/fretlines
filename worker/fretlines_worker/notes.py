"""Полифонические ноты по звуку: Basic Pitch (Spotify, Apache-2.0) через onnxruntime.

На каждом кадре (≈11.6 мс) модель даёт вероятность того, что звучит каждая из 88 нот
фортепиано, и отдельно — что нота только началась. Отсюда берутся чистая хрома для аккордов
(обертоны модель гасит сама) и ноты гитарной партии «как в записи».
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger("fretlines.notes")

SR = 22_050
HOP = 256
WINDOW = 2 * SR - HOP  # 43 844 отсчёта — окно, на котором училась модель
OVERLAP_FRAMES = 30
OVERLAP = OVERLAP_FRAMES * HOP
STEP = WINDOW - OVERLAP
FRAMES_PER_WINDOW = 172
KEPT_FRAMES = FRAMES_PER_WINDOW - OVERLAP_FRAMES  # края окон отрезаются — там модель хуже
LOWEST = 21  # A0 — нижняя клавиша фортепиано
N_PITCHES = 88

MODEL_URL = (
    "https://github.com/spotify/basic-pitch/raw/v0.4.0/"
    "basic_pitch/saved_models/icassp_2022/nmp.onnx"
)
MODEL_SHA256 = "2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec"


@dataclass(frozen=True)
class Posteriors:
    times: NDArray[np.float64]  # секунды каждого кадра
    note: NDArray[np.float32]  # (кадры, 88): нота звучит
    onset: NDArray[np.float32]  # (кадры, 88): нота началась


@dataclass(frozen=True, slots=True)
class NoteEvent:
    start: float  # секунды
    end: float
    pitch: int  # MIDI
    amplitude: float  # 0…1 — уверенность модели, она же примерно громкость


def models_root() -> Path:
    return Path(os.environ.get("FRETLINES_MODELS_DIR", Path.cwd() / ".models"))


def model_path() -> Path:
    """Файл модели (230 КБ) скачивается один раз в .models/basic-pitch/."""
    path = models_root() / "basic-pitch" / "nmp.onnx"
    if path.exists() and _sha256(path) == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("скачиваю Basic Pitch: %s", MODEL_URL)
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise RuntimeError("Basic Pitch скачался повреждённым — попробуй ещё раз")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@cache
def _session() -> Any:  # noqa: ANN401 — onnxruntime без типов
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    return ort.InferenceSession(
        str(model_path()), sess_options=options, providers=["CPUExecutionProvider"]
    )


def posteriors(mono: NDArray[np.float32], batch: int = 16) -> Posteriors:
    """Звук 22.05 кГц моно → вероятности нот по кадрам."""
    length = mono.size
    padded = np.concatenate([np.zeros(OVERLAP // 2, dtype=np.float32), mono.astype(np.float32)])
    starts = list(range(0, padded.size, STEP)) or [0]
    windows = np.zeros((len(starts), WINDOW, 1), dtype=np.float32)
    for i, start in enumerate(starts):
        chunk = padded[start : start + WINDOW]
        windows[i, : chunk.size, 0] = chunk

    session = _session()
    notes: list[NDArray[np.float32]] = []
    onsets: list[NDArray[np.float32]] = []
    for i in range(0, len(starts), batch):
        note, onset = session.run(
            ["StatefulPartitionedCall:1", "StatefulPartitionedCall:2"],
            {"serving_default_input_2:0": windows[i : i + batch]},
        )
        notes.append(note)
        onsets.append(onset)

    half = OVERLAP_FRAMES // 2
    note_all = np.concatenate(notes)[:, half:-half, :].reshape(-1, N_PITCHES)
    onset_all = np.concatenate(onsets)[:, half:-half, :].reshape(-1, N_PITCHES)
    # Окно сдвигается на STEP отсчётов, а кадров после обрезки краёв в нём KEPT_FRAMES:
    # время каждого кадра считаем от начала его окна, иначе к концу песни набегает секунда.
    index = np.arange(note_all.shape[0])
    times = ((index // KEPT_FRAMES) * STEP + (index % KEPT_FRAMES) * HOP) / SR
    keep = times < length / SR
    return Posteriors(times[keep], note_all[keep], onset_all[keep])


def pitch_class_profile(
    p: Posteriors, low: int = 28, high: int = 96, floor: float = 0.0
) -> NDArray[np.float64]:
    """Хрома из вероятностей нот: (12, кадры). Обертонов в ней почти нет.

    Вероятности ниже floor — шум модели: если их сложить по 88 нотам, хрома «расплывается».
    """
    lo, hi = low - LOWEST, high - LOWEST
    active = np.clip(p.note[:, lo:hi].astype(np.float64) - floor, 0.0, None)
    out = np.zeros((12, p.note.shape[0]))
    for k in range(hi - lo):
        out[(k + low) % 12] += active[:, k]
    return out


def extract_notes(
    p: Posteriors,
    *,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_seconds: float = 0.07,
    tolerance_frames: int = 8,
    low: int = 28,
    high: int = 100,
) -> list[NoteEvent]:
    """Начала нот — пики «онсетов», конец — пока нота держится выше порога.

    Начала обходятся с конца песни: поздняя нота забирает свои кадры, и ранняя нота той же
    высоты заканчивается там, где началась следующая (повторы не сливаются в одну).
    """
    note, onset = p.note, p.onset
    frames = note.shape[0]
    if frames < 3:
        return []
    # Онсеты, которые модель «проспала», видны по резкому росту вероятности звучания.
    rise = np.clip(note[2:] - np.maximum(note[1:-1], note[:-2]), 0, None)
    inferred = np.zeros_like(onset)
    inferred[2:] = rise
    strength = np.maximum(onset, inferred * (onset.max() / max(float(rise.max()), 1e-6)))
    peaks = (
        (strength[1:-1] > strength[:-2])
        & (strength[1:-1] >= strength[2:])
        & (strength[1:-1] >= onset_threshold)
    )
    t_idx, p_idx = np.nonzero(peaks)
    t_idx = t_idx + 1
    order = np.argsort(-t_idx, kind="stable")

    remaining = note.copy()
    min_frames = max(2, round(min_seconds / max(_frame_seconds(p), 1e-6)))
    events: list[NoteEvent] = []
    for t0, k in zip(t_idx[order], p_idx[order], strict=True):
        pitch = int(k) + LOWEST
        if not low <= pitch <= high:
            continue
        if remaining[t0, k] < frame_threshold and onset[t0, k] < onset_threshold:
            continue
        t = int(t0)
        quiet = 0
        while t + 1 < frames and quiet < tolerance_frames:
            t += 1
            quiet = quiet + 1 if remaining[t, k] < frame_threshold else 0
        end = t - quiet
        if end - t0 < min_frames:
            continue
        amplitude = float(np.mean(note[t0:end, k]))
        remaining[t0:end, k] = 0.0
        if k > 0:
            remaining[t0:end, k - 1] *= 0.5
        if k + 1 < N_PITCHES:
            remaining[t0:end, k + 1] *= 0.5
        start_time = float(p.times[t0])
        end_time = float(p.times[min(end, frames - 1)])
        events.append(NoteEvent(start_time, max(end_time, start_time + 0.03), pitch, amplitude))
    events.sort(key=lambda e: (e.start, e.pitch))
    return events


def _frame_seconds(p: Posteriors) -> float:
    if p.times.size < 2:
        return HOP / SR
    return float(np.median(np.diff(p.times)))
