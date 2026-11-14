"""Ручная правка аккордов: замена на отрезке и переименование по всей песне.

Время — в долях от начала песни. Функции чистые: входы не меняются, результат — новый кортеж,
отсортированный по началу и нормализованный (см. _normalize).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arranger.model import ChordSpan
from arranger.theory import Chord, parse_chord

# Участки короче этого выбрасываются, а одинаковые соседи с таким зазором склеиваются.
_EPS = 1e-6
# Запас на погрешность float: 1.000001 - 1.0 чуть меньше 1e-6, а 2.000001 - 2.0 — чуть больше.
_SLACK = 1e-9


@dataclass(frozen=True, slots=True)
class ChordEdit:
    """Правка: на [start, end) звучит chord; None — на отрезке нет аккорда."""

    start: float  # в долях от начала песни
    end: float
    chord: str | None  # имя аккорда («G#m», «F#7», «C/G»); None — убрать аккорд


@dataclass(frozen=True, slots=True)
class ChordRename:
    """Правка: аккорд old по всей песне становится new; None — убрать его."""

    old: str
    new: str | None


def apply_fixes(
    spans: Sequence[ChordSpan], fixes: Sequence[ChordEdit | ChordRename], total_beats: float
) -> tuple[ChordSpan, ...]:
    """Правки музыканта по порядку, как он их вносил: каждая видит результат предыдущих.

    Поэтому «C → Em везде», а потом «Em → E везде» делает E и из бывших C. Имена
    проверяются до любых изменений: мусор → ValueError.
    """
    for fix in fixes:
        names = (fix.chord,) if isinstance(fix, ChordEdit) else (fix.old, fix.new)
        for name in names:
            if name is not None:
                parse_chord(name)
    result = tuple(spans)
    for fix in fixes:
        if isinstance(fix, ChordEdit):
            result = apply_chord_edits(result, [fix], total_beats)
        else:
            result = rename_chords(result, {fix.old: fix.new})
    return result


def untransposed(name: str, semitones: int) -> str:
    """Имя аккорда, набранное в транспонированной тональности, — в тональности записи."""
    return parse_chord(name).transposed(-semitones).name()


def apply_chord_edits(
    spans: Sequence[ChordSpan], edits: Sequence[ChordEdit], total_beats: float
) -> tuple[ChordSpan, ...]:
    """Применяет правки по порядку: поздняя перекрывает раннюю. Мусор в именах → ValueError."""
    # Сначала разбираем все имена, чтобы ошибка не оставила полупримененных правок.
    parsed = [None if e.chord is None else parse_chord(e.chord) for e in edits]

    result = list(spans)
    for edit, chord in zip(edits, parsed, strict=True):
        start = max(edit.start, 0.0)
        end = min(edit.end, total_beats)
        if not start < end:  # пусто после обрезки; заодно отсекает NaN
            continue
        result = _cut(result, start, end)
        if chord is not None:
            result.append(ChordSpan(start, end, chord))
    return _normalize(result)


def rename_chords(
    spans: Sequence[ChordSpan], mapping: Mapping[str, str | None]
) -> tuple[ChordSpan, ...]:
    """Переименовывает аккорды по всей песне: «старое → новое», None — убрать участки.

    Ключи сравниваются как аккорды («Abm7» действует на G#m7), замены не цепляются друг за друга.
    """
    table: dict[Chord, Chord | None] = {}
    for old, new in mapping.items():
        key = parse_chord(old)
        if key in table:
            raise ValueError(f"Аккорд {old!r} указан в замене дважды")
        table[key] = None if new is None else parse_chord(new)

    result: list[ChordSpan] = []
    for span in spans:
        if span.chord not in table:
            result.append(span)
            continue
        target = table[span.chord]
        if target is not None:
            result.append(ChordSpan(span.start, span.end, target))
    return _normalize(result)


def _cut(spans: list[ChordSpan], start: float, end: float) -> list[ChordSpan]:
    """Вырезает [start, end) из участков: задетые обрезаются или делятся на две части."""
    out: list[ChordSpan] = []
    for span in spans:
        if span.end <= start or span.start >= end:
            out.append(span)
            continue
        if span.start < start:
            out.append(ChordSpan(span.start, start, span.chord))
        if span.end > end:
            out.append(ChordSpan(end, span.end, span.chord))
    return out


def _normalize(spans: Sequence[ChordSpan]) -> tuple[ChordSpan, ...]:
    """Сортирует, выбрасывает короткие участки и склеивает касающиеся одинаковые."""
    kept = sorted(
        (s for s in spans if s.end - s.start >= _EPS - _SLACK), key=lambda s: (s.start, s.end)
    )
    merged: list[ChordSpan] = []
    for span in kept:
        if merged:
            last = merged[-1]
            if last.chord == span.chord and span.start - last.end <= _EPS + _SLACK:
                merged[-1] = ChordSpan(last.start, max(last.end, span.end), last.chord)
                continue
        merged.append(span)
    return tuple(merged)
