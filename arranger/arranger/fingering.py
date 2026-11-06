"""Раскладка одноголосной линии по грифу — динамическое программирование (Витерби).

Состояние: позиция ноты (струна, лад) и положение руки h — указательный палец на ладу h,
пальцы покрывают лады h … h+span-1 (span = растяжка, 4 лада или 3 на «упрощённо»).
Открытая струна руку не двигает: h наследуется. Стоимость складывается из высоты на грифе,
неудобных струн, прыжков через струны и сдвигов руки — тем дороже, чем быстрее ноты.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from arranger.instruments import Instrument

_BEAM = 48

StateKey = tuple[int, int, int]  # (струна, лад, рука); рука 0 — ещё не поставлена


@dataclass(frozen=True, slots=True)
class Fingered:
    string: int
    fret: int
    hand: int


def _no_cost(_: int) -> float:
    return 0.0


def _offer(
    layer: dict[StateKey, tuple[float, StateKey | None]],
    key: StateKey,
    cost: float,
    back: StateKey | None,
) -> None:
    best = layer.get(key)
    if best is None or cost < best[0]:
        layer[key] = (cost, back)


def _shift_cost(distance: int, gap: float) -> float:
    if distance == 0:
        return 0.0
    return 0.6 + distance * (0.35 + 0.65 / max(gap, 0.25))


def finger_line(
    notes: Sequence[tuple[float, int]],
    instrument: Instrument,
    *,
    span: int = 4,
    max_fret: int | None = None,
    string_cost: Callable[[int], float] = _no_cost,
    fret_weight: float = 0.04,
) -> list[Fingered]:
    """notes — (начало в долях, высота MIDI). Возвращает позицию для каждой ноты.

    Высоты, которых нет на грифе, — ошибка вызывающего: диапазон подгоняется заранее.
    """
    if not notes:
        return []
    top = instrument.frets if max_fret is None else min(max_fret, instrument.frets)

    def hands(fret: int) -> range:
        return range(max(1, fret - span + 1), fret + 1)

    def node_cost(string: int, fret: int) -> float:
        return fret_weight * fret + string_cost(string)

    layers: list[dict[StateKey, tuple[float, StateKey | None]]] = []
    previous_time = notes[0][0]
    for index, (time, pitch) in enumerate(notes):
        candidates = instrument.positions(pitch, top)
        if not candidates:
            raise ValueError(f"Нота {pitch} не помещается на гриф до {top} лада")
        layer: dict[StateKey, tuple[float, StateKey | None]] = {}
        if index == 0:
            for string, fret in candidates:
                for hand in hands(fret) if fret else (0,):
                    _offer(layer, (string, fret, hand), node_cost(string, fret), None)
        else:
            gap = time - previous_time
            for prev_key, (prev_cost, _) in layers[-1].items():
                prev_string, _, prev_hand = prev_key
                for string, fret in candidates:
                    base = prev_cost + node_cost(string, fret) + 0.1 * abs(string - prev_string)
                    if fret == 0:
                        _offer(layer, (string, 0, prev_hand), base, prev_key)
                        continue
                    for hand in hands(fret):
                        shift = 0 if prev_hand == 0 else abs(hand - prev_hand)
                        cost = base + _shift_cost(shift, gap)
                        _offer(layer, (string, fret, hand), cost, prev_key)

        if len(layer) > _BEAM:
            kept = sorted(layer.items(), key=lambda item: item[1][0])[:_BEAM]
            layer = dict(kept)
        layers.append(layer)
        previous_time = time

    key: StateKey | None = min(layers[-1].items(), key=lambda item: item[1][0])[0]
    path: list[Fingered] = []
    for layer in reversed(layers):
        assert key is not None
        string, fret, hand = key
        path.append(Fingered(string, fret, hand))
        key = layer[key][1]
    path.reverse()
    return path
