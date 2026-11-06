"""Сетка долей: секунды ↔ доли от начала первого такта."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from fretlines_worker.errors import AnalysisError


@dataclass(frozen=True)
class BeatGrid:
    """Доли песни в секундах. Индекс доли — её позиция в долях; доля 0 — начало первого такта.

    Если до первой сильной доли есть затакт, спереди добавляются «виртуальные» доли,
    чтобы первый такт начинался с доли 0. Сзади сетка продлевается до конца записи.
    """

    times: NDArray[np.float64]
    beats_per_bar: int

    @classmethod
    def build(cls, beats: Sequence[float], downbeats: Sequence[float], duration: float) -> BeatGrid:
        times = np.unique(np.asarray(beats, dtype=np.float64))
        if times.size < 8:
            raise AnalysisError(
                "no_rhythm",
                "Не удалось уловить ритм. Попробуй запись, где хорошо слышны барабаны или бой.",
            )
        meter = _meter(times, downbeats)
        first = _first_downbeat(times, downbeats, meter)
        step = float(np.median(np.diff(times[: min(9, times.size)])))
        lead = (meter - first % meter) % meter
        before = times[0] - step * np.arange(lead, 0, -1)
        grid = np.concatenate([before, times])

        tail = float(np.median(np.diff(times[-9:])))
        extra: list[float] = []
        last = grid[-1]
        while last + tail < duration + tail * 0.5:
            last += tail
            extra.append(last)
        grid = np.concatenate([grid, extra])
        pad = (-grid.size) % meter
        if pad:
            grid = np.concatenate([grid, grid[-1] + tail * np.arange(1, pad + 1)])
        return cls(grid, meter)

    @property
    def bars(self) -> int:
        return math.ceil(self.times.size / self.beats_per_bar)

    @property
    def tempo(self) -> float:
        return float(60.0 / np.median(np.diff(self.times)))

    def to_beats(self, seconds: ArrayLike) -> NDArray[np.float64]:
        t = np.asarray(seconds, dtype=np.float64)
        index = np.arange(self.times.size, dtype=np.float64)
        out = np.interp(t, self.times, index)
        first_step = self.times[1] - self.times[0]
        last_step = self.times[-1] - self.times[-2]
        out = np.where(t < self.times[0], (t - self.times[0]) / first_step, out)
        return np.where(t > self.times[-1], index[-1] + (t - self.times[-1]) / last_step, out)

    def to_seconds(self, beats: ArrayLike) -> NDArray[np.float64]:
        b = np.asarray(beats, dtype=np.float64)
        index = np.arange(self.times.size, dtype=np.float64)
        out = np.interp(b, index, self.times)
        last_step = self.times[-1] - self.times[-2]
        return np.where(b > index[-1], self.times[-1] + (b - index[-1]) * last_step, out)

    def bar_times(self) -> list[float]:
        return [round(float(t), 4) for t in self.times[:: self.beats_per_bar]]


def _meter(times: NDArray[np.float64], downbeats: Sequence[float]) -> int:
    """Долей в такте по расстояниям между сильными долями: обычно 4, бывает 3."""
    if len(downbeats) < 3:
        return 4
    positions = np.searchsorted(times, np.asarray(downbeats) - 0.07)
    counts = Counter(int(c) for c in np.diff(positions) if 2 <= c <= 7)
    if not counts:
        return 4
    meter = counts.most_common(1)[0][0]
    return meter if meter in (3, 4) else 4


def _first_downbeat(times: NDArray[np.float64], downbeats: Sequence[float], meter: int) -> int:
    """Индекс доли, с которой начинается первый полный такт."""
    if not len(downbeats):
        return 0
    nearest = [int(np.argmin(np.abs(times - d))) for d in downbeats]
    phases = Counter(i % meter for i in nearest)
    return phases.most_common(1)[0][0]
