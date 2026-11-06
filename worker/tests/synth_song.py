"""Синтетическая песня с известными аккордами, басом и барабанами — эталон для тестов анализа."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

SR = 44_100

# Am F C G по такту, 4/4. Голоса аккорда — как в открытых формах на гитаре.
PROGRESSION = [
    ("Am", [45, 52, 57, 60, 64]),
    ("F", [41, 48, 53, 57, 60, 65]),
    ("C", [48, 52, 55, 60, 64]),
    ("G", [43, 47, 50, 55, 59, 67]),
]
BASS_ROOTS = {"Am": 33, "F": 29, "C": 36, "G": 31}


def _pluck(
    freq: float, seconds: float, rng: np.random.Generator, decay: float = 0.996
) -> NDArray[np.float64]:
    """Карплус — Стронг: щипок струны."""
    n = int(seconds * SR)
    period = max(2, int(SR / freq))
    buffer = rng.uniform(-1, 1, period)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buffer[i % period]
        buffer[i % period] = decay * 0.5 * (buffer[i % period] + buffer[(i + 1) % period])
    return out


def _midi_hz(pitch: float) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def make_song(
    bpm: float = 100.0, bars: int = 16, seed: int = 7
) -> tuple[NDArray[np.float32], list[str]]:
    """Стерео-микс и аккорд каждого такта."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    total = int((bars * 4 + 2) * beat * SR)
    mix = np.zeros(total)
    labels: list[str] = []
    pluck_cache: dict[tuple[int, float], NDArray[np.float64]] = {}

    def add(signal: NDArray[np.float64], at: float, gain: float) -> None:
        start = int(at * SR)
        end = min(total, start + signal.size)
        if start < total:
            mix[start:end] += gain * signal[: end - start]

    for bar in range(bars):
        name, voicing = PROGRESSION[bar % len(PROGRESSION)]
        labels.append(name)
        for b in range(4):
            t0 = (bar * 4 + b) * beat
            # Бой: каждая доля — аккорд с лёгким разбросом струн.
            for k, pitch in enumerate(voicing):
                key = (pitch, beat)
                if key not in pluck_cache:
                    pluck_cache[key] = _pluck(_midi_hz(pitch), beat * 0.95, rng)
                add(pluck_cache[key], t0 + k * 0.008, 0.16)
            # Бас: корень на каждую долю.
            root = BASS_ROOTS[name]
            n = int(beat * 0.9 * SR)
            tt = np.arange(n) / SR
            bass = np.sin(2 * np.pi * _midi_hz(root) * tt) + 0.3 * np.sin(
                4 * np.pi * _midi_hz(root) * tt
            )
            add(bass * np.exp(-tt * 3.0), t0, 0.35)
            # Барабаны: бочка на 1 и 3, малый на 2 и 4, хэт восьмыми.
            if b in (0, 2):
                tk = np.arange(int(0.18 * SR)) / SR
                add(np.sin(2 * np.pi * (110 - 60 * tk / 0.18) * tk) * np.exp(-tk * 22), t0, 0.9)
            else:
                ts = int(0.12 * SR)
                add(rng.uniform(-1, 1, ts) * np.exp(-np.arange(ts) / SR * 30), t0, 0.35)
            for half in (0.0, 0.5):
                th = int(0.03 * SR)
                hat = np.diff(rng.uniform(-1, 1, th + 1)) * np.exp(-np.arange(th) / SR * 120)
                add(hat, t0 + half * beat, 0.12)

    mix /= max(1e-9, float(np.abs(mix).max())) * 1.1
    stereo = np.stack([mix, mix]).astype(np.float32)
    return stereo, labels
