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


# ─── Несколько нот разом (партия «как в записи») ───────────────────────────

Assignment = tuple[tuple[int, int], ...]  # (струна, лад) для каждой высоты события


def chord_options(
    pitches: Sequence[int], instrument: Instrument, span: int, top: int
) -> list[Assignment]:
    """Все способы взять ноты разом: каждая на своей струне, лады в пределах растяжки."""
    positions = [instrument.positions(p, top) for p in pitches]
    if any(not p for p in positions):
        return []
    options: list[Assignment] = []

    def walk(index: int, used: frozenset[int], chosen: tuple[tuple[int, int], ...]) -> None:
        if index == len(pitches):
            options.append(chosen)
            return
        for string, fret in positions[index]:
            if string in used:
                continue
            frets = [f for _, f in chosen if f > 0] + ([fret] if fret > 0 else [])
            if frets and max(frets) - min(frets) >= span:
                continue
            walk(index + 1, used | {string}, (*chosen, (string, fret)))

    walk(0, frozenset(), ())
    return options


_STATES = 32  # столько лучших состояний (вариант, рука) держим на событие
_State = tuple[int, int]  # (номер варианта, лад указательного пальца; 0 — рука не поставлена)


def _hands(option: Assignment, span: int) -> tuple[int, ...]:
    """Где может стоять рука, чтобы взять вариант; пусто — одни открытые струны, рука любая."""
    frets = [f for _, f in option if f > 0]
    if not frets:
        return ()
    low, high = min(frets), max(frets)
    return tuple(range(max(1, high - span + 1), low + 1)) or (low,)


# Открытая струна, когда рука ушла от порожка: звучит иначе, чем соседние ноты, и её не
# заглушить. В соло гитаристы почти не берут её (GuitarSet: 3 % нот), у порожка она бесплатна.
_OPEN_NEAR = 3
_OPEN_W = 0.6


def _open_cost(option: Assignment, hand: int) -> float:
    if hand <= _OPEN_NEAR:
        return 0.0
    return _OPEN_W * sum(fret == 0 for _, fret in option)


def _option_cost(option: Assignment, fret_weight: float, home: int = 0) -> float:
    """home — лад, вокруг которого удобнее всего играть (0 — чем ближе к порожку, тем лучше)."""
    frets = [f for _, f in option if f > 0]
    if not frets:
        return 0.0
    stretch = max(frets) - min(frets)
    height = sum(abs(f - home) for f in frets) / len(frets)
    return fret_weight * height + 0.25 * stretch + 0.05 * len(frets)


def finger_events(
    events: Sequence[tuple[float, Sequence[int], Assignment | None]],
    instrument: Instrument,
    *,
    span: int = 4,
    max_fret: int | None = None,
    fret_weight: float = 0.04,
    home: int = 0,
) -> list[Assignment | None]:
    """Раскладка последовательности созвучий: (время в долях, высоты, готовая аппликатура).

    home — лад, к которому тянется рука на свободных нотах: 0 — к порожку (так проще),
    7 — в середину грифа, где гитаристы играют риффы и соло.

    Готовая аппликатура (аккорд из библиотеки) не меняется — по ней только двигается рука.
    Если созвучие не взять ни одним способом, вместо него None: его отбросит вызывающий.
    """
    top = instrument.frets if max_fret is None else min(max_fret, instrument.frets)
    choices: list[list[Assignment]] = []
    for _, pitches, fixed in events:
        if fixed is not None:
            choices.append([fixed])
            continue
        options = chord_options(pitches, instrument, span, top)
        options.sort(key=lambda o: _option_cost(o, fret_weight, home))
        choices.append(options[:_BEAM])

    # Состояние — (вариант, где рука): указательный палец на ладу hand, пальцы достают до
    # hand + span - 1, так что ноты под рукой играются без сдвига. Открытые струны руку не
    # двигают: она остаётся там, где была, — иначе через открытую струну рука «бесплатно»
    # перелетала бы на другой конец грифа.
    layers: list[dict[_State, tuple[float, _State | None]]] = []
    alive: list[int] = []  # номера событий, которые удалось взять
    previous_time = 0.0
    for index, ((time, _, _), options) in enumerate(zip(events, choices, strict=True)):
        if not options:
            continue
        layer: dict[_State, tuple[float, _State | None]] = {}
        gap = time - previous_time
        for o, option in enumerate(options):
            own = _option_cost(option, fret_weight, home)
            reach = _hands(option, span)
            if not layers:
                for hand in reach or (0,):
                    layer[(o, hand)] = (own + _open_cost(option, hand), None)
                continue
            for before, (cost, _) in layers[-1].items():
                for hand in reach or (before[1],):
                    shift = abs(hand - before[1]) if hand and before[1] else 0
                    total = cost + own + _shift_cost(shift, gap) + _open_cost(option, hand)
                    best = layer.get((o, hand))
                    if best is None or total < best[0]:
                        layer[(o, hand)] = (total, before)
        if len(layer) > _STATES:
            layer = dict(sorted(layer.items(), key=lambda item: item[1][0])[:_STATES])
        layers.append(layer)
        alive.append(index)
        previous_time = time

    result: list[Assignment | None] = [None] * len(events)
    if not layers:
        return result
    pick: _State | None = min(layers[-1].items(), key=lambda item: item[1][0])[0]
    for layer, index in zip(reversed(layers), reversed(alive), strict=True):
        assert pick is not None
        result[index] = choices[index][pick[0]]
        pick = layer[pick][1]
    return result
