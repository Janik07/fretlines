"""Аккордовые аппликатуры для любого строя и каподастра.

Перебираем окна по 3–4 лада, на каждой струне — лады, где звучит тон аккорда. Играются
соседние струны подряд (глушить можно только крайние). Аппликатура годится, если в ней есть
все важные тоны, хватает четырёх пальцев (с учётом баррэ) и растяжка в пределах окна.
Стоимость — насколько аккорд неудобен: позиция, баррэ, число пальцев, заглушённые струны.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from arranger.instruments import Instrument
from arranger.model import ChordSpan, Difficulty
from arranger.theory import Chord

SPAN: dict[Difficulty, int] = {"easy": 3, "medium": 4, "full": 4}
_MIN_STRINGS: dict[Difficulty, int] = {"easy": 3, "medium": 4, "full": 4}
_POSITION_W: dict[Difficulty, float] = {"easy": 0.45, "medium": 0.25, "full": 0.15}
_BARRE_W: dict[Difficulty, float] = {"easy": 4.0, "medium": 1.4, "full": 0.9}
_MUTED_W: dict[Difficulty, float] = {"easy": 0.25, "medium": 0.45, "full": 0.9}
_TOP_WINDOW = 12


@dataclass(frozen=True, slots=True)
class Voicing:
    frets: tuple[int | None, ...]  # по струнам, первая — тонкая; None — не играется
    cost: float
    barre: int | None

    @property
    def played(self) -> list[int]:
        return [i + 1 for i, fret in enumerate(self.frets) if fret is not None]

    @property
    def bass_string(self) -> int:
        return max(self.played)

    @property
    def position(self) -> int:
        fretted = [f for f in self.frets if f]
        return min(fretted) if fretted else 0

    def notes(self, instrument: Instrument) -> list[tuple[int, int, int]]:
        """(струна, лад, высота) от тонкой струны к толстой."""
        return [
            (string, fret, instrument.pitch_at(string, fret))
            for string, fret in ((i + 1, f) for i, f in enumerate(self.frets))
            if fret is not None
        ]


def _fingers(frets: tuple[int | None, ...]) -> tuple[int, int | None] | None:
    """Сколько пальцев нужно и на каком ладу баррэ; None — не сыграть."""
    fretted = [(i, f) for i, f in enumerate(frets) if f]
    if len(fretted) <= 4:
        return len(fretted), None
    lowest = min(f for _, f in fretted)
    at_lowest = [i for i, f in fretted if f == lowest]
    first, last = min(at_lowest), max(at_lowest)
    # Под баррэ не должно быть открытых струн: палец лежит поперёк всего промежутка.
    if any(frets[i] == 0 for i in range(first, last + 1)):
        return None
    fingers = len(fretted) - len(at_lowest) + 1
    return (fingers, lowest) if fingers <= 4 else None


def _cost(
    frets: tuple[int | None, ...],
    barre: int | None,
    fingers: int,
    chord: Chord,
    instrument: Instrument,
    level: Difficulty,
) -> float:
    fretted = [f for f in frets if f]
    played = [i for i, f in enumerate(frets) if f is not None]
    cost = 0.3 * fingers
    if fretted:
        cost += _POSITION_W[level] * max(0, min(fretted) - 1)
        cost += 0.35 * (max(fretted) - min(fretted))
    if barre is not None:
        covered = [i for i, f in enumerate(frets) if f == barre]
        width = max(covered) - min(covered) + 1
        cost += _BARRE_W[level] * (1 + 0.25 * (width - 2))
    cost += _MUTED_W[level] * (instrument.strings - len(played))
    if min(played) > 0 and chord.quality != "5":
        cost += 1.0  # заглушена первая струна: при бое её придётся глушить пальцем
    cost -= 0.12 * sum(1 for f in frets if f == 0)
    bass_string = max(played) + 1
    if instrument.pitch_at(bass_string, frets[max(played)] or 0) % 12 != chord.bass_pc:
        cost += 1.2  # в басу не основной тон — обращение
    return cost


@lru_cache(maxsize=8192)
def chord_voicings(
    chord: Chord, instrument: Instrument, level: Difficulty, limit: int = 6
) -> tuple[Voicing, ...]:
    """Лучшие аппликатуры аккорда — от самой удобной."""
    n = instrument.strings
    pcs = chord.pitch_classes
    span = SPAN[level]
    power = chord.quality == "5"
    min_strings = 2 if power else min(_MIN_STRINGS[level], n)
    top_window = min(_TOP_WINDOW, instrument.frets - span + 1)
    # Пауэр-аккорд без основного тона внизу — уже не пауэр-аккорд (квинта «висит»).
    allow_inversion = level != "full" and not power
    found: dict[tuple[int | None, ...], Voicing] = {}

    for low in range(n, 0, -1):  # самая толстая играемая струна
        for high in range(1, low + 1):  # самая тонкая
            count = low - high + 1
            if count < min_strings or (power and count > 3) or (not power and high > 2):
                continue
            if power and low < n - 2:  # пауэр-аккорды берут на трёх толстых струнах
                continue
            for window in range(1, max(1, top_window) + 1):
                frets_range = [0, *range(window, window + span)]
                options: list[list[int]] = []
                for string in range(high, low + 1):
                    open_pitch = instrument.open_pitch(string)
                    usable = [
                        f
                        for f in frets_range
                        if f <= instrument.frets and (open_pitch + f) % 12 in pcs
                    ]
                    if string == low:
                        bass = [f for f in usable if (open_pitch + f) % 12 == chord.bass_pc]
                        usable = bass if bass or not allow_inversion else usable
                    if not usable:
                        break
                    options.append(usable)
                else:
                    for combo in product(*options):
                        frets: tuple[int | None, ...] = tuple(
                            combo[s - high] if high <= s <= low else None for s in range(1, n + 1)
                        )
                        if frets in found:
                            continue
                        fretted = [f for f in combo if f]
                        if fretted and max(fretted) - min(fretted) >= span:
                            continue
                        sounding = {
                            (instrument.open_pitch(s) + f) % 12
                            for s, f in enumerate(frets, start=1)
                            if f is not None
                        }
                        if not chord.essential <= sounding:
                            continue
                        hand = _fingers(frets)
                        if hand is None:
                            continue
                        fingers, barre = hand
                        cost = _cost(frets, barre, fingers, chord, instrument, level)
                        found[frets] = Voicing(frets, round(cost, 4), barre)

    return tuple(sorted(found.values(), key=lambda v: (v.cost, v.frets.count(None)))[:limit])


def playable_voicings(
    chord: Chord, instrument: Instrument, level: Difficulty
) -> tuple[Voicing, ...]:
    """Аппликатуры с запасными вариантами: упрощённый аккорд, затем квинта."""
    for candidate in (chord, chord.simplified(), Chord(chord.root, "5")):
        voicings = chord_voicings(candidate, instrument, level)
        if voicings:
            return voicings
    return ()


@lru_cache(maxsize=4096)
def neck_voicings(
    chord: Chord, instrument: Instrument, level: Difficulty, max_fret: int
) -> tuple[Voicing, ...]:
    """По две лучших аппликатуры в каждой позиции грифа — чтобы взять ту, где играет запись.

    Открытые струны — только в первой позиции: открытая струна под аккордом на седьмом ладу
    звучит и выглядит в табах странно, так почти не играют.
    """
    for candidate in (chord, chord.simplified(), Chord(chord.root, "5")):
        every = tuple(
            v
            for v in chord_voicings(candidate, instrument, level, limit=100_000)
            if (top := max(f for f in v.frets if f is not None)) <= max_fret
            and (top <= 4 or 0 not in v.frets)
        )
        if every:
            break
    best: dict[int, list[Voicing]] = {}
    for voicing in every:  # уже по возрастанию стоимости
        bucket = best.setdefault(voicing.position, [])
        if len(bucket) < 2:
            bucket.append(voicing)
    return tuple(v for position in sorted(best) for v in best[position])


def best_path(
    options: Sequence[Sequence[Voicing]], costs: Sequence[Sequence[float]]
) -> list[Voicing | None]:
    """Витерби: у каждого аккорда своя цена аппликатуры, плюс переезды руки между ними.

    Аккорд без аппликатур рвёт цепочку — участки до и после него выбираются отдельно.
    """
    chosen: list[Voicing | None] = [None] * len(options)
    start = 0
    while start < len(options):
        if not options[start]:
            start += 1
            continue
        end = start
        while end < len(options) and options[end]:
            end += 1
        total = list(costs[start])
        backs: list[list[int]] = []
        for i in range(start + 1, end):
            prev = options[i - 1]
            step_costs: list[float] = []
            step_backs: list[int] = []
            for voicing, own in zip(options[i], costs[i], strict=True):
                cost, back = min(
                    (total[p] + 0.25 * abs(voicing.position - prev[p].position), p)
                    for p in range(len(prev))
                )
                step_costs.append(cost + own)
                step_backs.append(back)
            total = step_costs
            backs.append(step_backs)
        pick = min(range(len(total)), key=total.__getitem__)
        for i in range(end - 1, start - 1, -1):
            chosen[i] = options[i][pick]
            if i > start:
                pick = backs[i - start - 1][pick]
        start = end
    return chosen


def choose_voicings(
    chords: Sequence[Chord], instrument: Instrument, level: Difficulty
) -> list[Voicing | None]:
    """Аппликатуры для последовательности аккордов с минимумом переездов руки."""
    options = [playable_voicings(c, instrument, level) for c in chords]
    return best_path(options, [[v.cost for v in o] for o in options])


@dataclass(frozen=True, slots=True)
class CapoOption:
    capo: int
    score: float
    barre_chords: int


def suggest_capo(
    spans: Sequence[ChordSpan], instrument: Instrument, level: Difficulty, max_capo: int = 7
) -> list[CapoOption]:
    """Каподастры от лучшего: меньше баррэ и неудобных аккордов, ниже по грифу."""
    weight: dict[Chord, float] = {}
    for span in spans:
        chord = span.chord.simplified() if level == "easy" else span.chord
        weight[chord] = weight.get(chord, 0.0) + max(span.end - span.start, 0.25)
    if not weight:
        return [CapoOption(instrument.capo, 0.0, 0)]
    total = sum(weight.values())

    options = []
    for capo in range(0, max_capo + 1):
        shifted = Instrument(instrument.kind, instrument.tuning, capo)
        score = 0.15 * capo
        barres = 0
        for chord, w in weight.items():
            voicings = playable_voicings(chord, shifted, level)
            best = voicings[0] if voicings else None
            score += (best.cost if best else 12.0) * w / total
            barres += int(best is None or best.barre is not None)
        options.append(CapoOption(capo, round(score, 3), barres))
    return sorted(options, key=lambda o: (o.score, o.capo))
