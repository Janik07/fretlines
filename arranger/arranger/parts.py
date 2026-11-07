"""Партии по ролям и уровням сложности (SPEC §1.4).

Все партии строятся на сетке шестнадцатых (шаг = 1/4 доли). Уровни:
- easy — открытые аккорды и трезвучия, бой четвертями, мелодия восьмыми без украшений,
  бас по корням аккордов;
- medium — септаккорды, бой восьмыми, мелодия и бас восьмыми;
- full — как в транскрипции, шестнадцатые.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

from arranger.fingering import Assignment, finger_events, finger_line
from arranger.instruments import Instrument
from arranger.model import (
    STEPS_PER_BEAT,
    ChordShape,
    Difficulty,
    Note,
    Stroke,
    TabBeat,
    TabNote,
    Transcription,
)
from arranger.theory import Chord, Key
from arranger.voicings import SPAN, Voicing, choose_voicings

GRID: dict[Difficulty, int] = {"easy": 2, "medium": 2, "full": 1}
MAX_FRET: dict[Difficulty, int] = {"easy": 7, "medium": 12, "full": 99}
_CHORD_GRID: dict[Difficulty, int] = {"easy": 4, "medium": 4, "full": 2}


@dataclass(frozen=True, slots=True)
class QNote:
    start: int
    length: int
    pitch: int

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True, slots=True)
class StepChord:
    start: int
    end: int
    chord: Chord


@dataclass(frozen=True)
class Context:
    """Общие данные одной аранжировки: транскрипция, транспонирование, сетка тактов."""

    tx: Transcription
    transpose: int = 0

    @property
    def bar_steps(self) -> int:
        return self.tx.beats_per_bar * STEPS_PER_BEAT

    @property
    def total_steps(self) -> int:
        return self.tx.bars * self.bar_steps

    @property
    def key(self) -> Key:
        return self.tx.key.transposed(self.transpose)

    def timeline(self, level: Difficulty) -> list[StepChord]:
        """Аккорды, привязанные к сетке уровня; одинаковые соседние склеены."""
        grid = _CHORD_GRID[level]
        out: list[StepChord] = []
        for span in sorted(self.tx.chords, key=lambda s: s.start):
            chord = span.chord.transposed(self.transpose)
            if level == "easy":
                chord = chord.simplified()
            start = round(span.start * STEPS_PER_BEAT / grid) * grid
            end = min(round(span.end * STEPS_PER_BEAT / grid) * grid, self.total_steps)
            if end <= start:
                continue
            if out and out[-1].end > start:
                start = out[-1].end
                if end <= start:
                    continue
            if out and out[-1].chord == chord and out[-1].end == start:
                out[-1] = StepChord(out[-1].start, end, chord)
            else:
                out.append(StepChord(start, end, chord))
        if level == "easy":
            out = _absorb_short(out, min_steps=STEPS_PER_BEAT * 2)
        return out


def _absorb_short(chords: list[StepChord], min_steps: int) -> list[StepChord]:
    """Слишком короткие аккорды (проходящие) отдаём предыдущему — так проще играть."""
    out: list[StepChord] = []
    for item in chords:
        if out and item.end - item.start < min_steps and out[-1].end == item.start:
            out[-1] = StepChord(out[-1].start, item.end, out[-1].chord)
        elif out and out[-1].chord == item.chord and out[-1].end == item.start:
            out[-1] = StepChord(out[-1].start, item.end, item.chord)
        else:
            out.append(item)
    return out


# ─── Ноты: квантование, упрощение, диапазон ────────────────────────────────


def quantize(notes: Sequence[Note], grid: int, total_steps: int, transpose: int) -> list[QNote]:
    """Привязка к сетке и одноголосие: одна нота в момент времени, без наложений."""
    raw: list[QNote] = []
    for note in sorted(notes, key=lambda n: (n.start, -n.duration)):
        start = round(note.start * STEPS_PER_BEAT / grid) * grid
        end = round(note.end * STEPS_PER_BEAT / grid) * grid
        if end <= start:
            end = start + grid
        if start < 0 or start >= total_steps:
            continue
        raw.append(QNote(start, min(end, total_steps) - start, note.pitch + transpose))
    mono: list[QNote] = []
    for q in raw:
        if mono and q.start == mono[-1].start:
            if q.length > mono[-1].length:
                mono[-1] = q
            continue
        if mono and mono[-1].end > q.start:
            mono[-1] = QNote(mono[-1].start, q.start - mono[-1].start, mono[-1].pitch)
        mono.append(q)
    return [q for q in mono if q.length > 0]


def merge_repeats(notes: list[QNote], max_gap: int) -> list[QNote]:
    out: list[QNote] = []
    for q in notes:
        if out and out[-1].pitch == q.pitch and q.start - out[-1].end <= max_gap:
            out[-1] = QNote(out[-1].start, q.end - out[-1].start, q.pitch)
        else:
            out.append(q)
    return out


def drop_ornaments(notes: list[QNote], max_len: int) -> list[QNote]:
    """Убирает короткие вспомогательные ноты между соседними тонами (мелизмы, форшлаги)."""
    if len(notes) < 3:
        return notes
    out = [notes[0]]
    for i in range(1, len(notes) - 1):
        prev, cur, nxt = out[-1], notes[i], notes[i + 1]
        ornament = (
            cur.length <= max_len
            and cur.length < prev.length
            and abs(nxt.pitch - prev.pitch) <= 2
            and cur.pitch not in (prev.pitch, nxt.pitch)
            and cur.start - prev.end <= 0
        )
        if ornament:
            out[-1] = QNote(prev.start, cur.end - prev.start, prev.pitch)
        else:
            out.append(cur)
    out.append(notes[-1])
    return out


def fit_range(notes: list[QNote], low: int, high: int, phrase_gap: int) -> list[QNote]:
    """Сдвиг по октавам: целиком, потом по фразам, оставшиеся ноты — по одной (SPEC §1.4)."""
    if not notes:
        return notes

    def inside(pitch: int) -> bool:
        return low <= pitch <= high

    center = (low + high) / 2
    sorted_pitches = sorted(n.pitch for n in notes)
    median = sorted_pitches[len(sorted_pitches) // 2]
    shift = max(
        range(-36, 37, 12),
        key=lambda s: (sum(inside(n.pitch + s) for n in notes), -abs(median + s - center)),
    )
    shifted = [QNote(n.start, n.length, n.pitch + shift) for n in notes]

    phrases: list[list[QNote]] = [[shifted[0]]]
    for q in shifted[1:]:
        if q.start - phrases[-1][-1].end >= phrase_gap:
            phrases.append([q])
        else:
            phrases[-1].append(q)
    out: list[QNote] = []
    for phrase in phrases:
        if not all(inside(q.pitch) for q in phrase):
            best = max(
                (-12, 0, 12),
                key=lambda s: (sum(inside(q.pitch + s) for q in phrase), s == 0),
            )
            phrase = [QNote(q.start, q.length, q.pitch + best) for q in phrase]
        for q in phrase:
            pitch = q.pitch
            while pitch < low:
                pitch += 12
            while pitch > high:
                pitch -= 12
            out.append(QNote(q.start, q.length, pitch if inside(pitch) else q.pitch))
    return [q for q in out if inside(q.pitch)]


# ─── Помощники ────────────────────────────────────────────────────────────


def _segment_index(timeline: Sequence[StepChord]) -> Callable[[int], int | None]:
    starts = [c.start for c in timeline]

    def at(time: int) -> int | None:
        i = bisect.bisect_right(starts, time) - 1
        if i >= 0 and timeline[i].start <= time < timeline[i].end:
            return i
        return None

    return at


def _shape_name(chord: Chord, instrument: Instrument, key: Key) -> str:
    """Имя аккорда так, как его видит гитарист: относительно каподастра."""
    shape_key = key.transposed(-instrument.capo)
    return chord.transposed(-instrument.capo).name(flats=shape_key.flats)


def _note(instrument: Instrument, string: int, fret: int, dead: bool = False) -> TabNote:
    return TabNote(string, fret, instrument.pitch_at(string, fret), dead)


def _durations(times: list[int], limit: Callable[[int], int]) -> list[int]:
    """Длительность события — до следующего события, но не дальше границы (такта/песни)."""
    out = []
    for i, t in enumerate(times):
        nxt = times[i + 1] if i + 1 < len(times) else limit(t)
        out.append(max(1, min(nxt, limit(t)) - t))
    return out


def _line(
    notes: list[QNote],
    instrument: Instrument,
    level: Difficulty,
    string_cost: Callable[[int], float],
) -> list[TabBeat]:
    fingered = finger_line(
        [(q.start / STEPS_PER_BEAT, q.pitch) for q in notes],
        instrument,
        span=SPAN[level],
        max_fret=MAX_FRET[level],
        string_cost=string_cost,
    )
    return [
        TabBeat(q.start, q.length, (TabNote(f.string, f.fret, q.pitch),))
        for q, f in zip(notes, fingered, strict=True)
    ]


def _melody_strings(string: int) -> float:
    return 0.25 * max(0, string - 3)


def melody_range(instrument: Instrument, level: Difficulty) -> tuple[int, int]:
    top = instrument.open_pitch(1) + min(MAX_FRET[level], instrument.frets)
    low = (
        instrument.open_pitch(min(4, instrument.strings)) if level != "full" else instrument.lowest
    )
    return low, top


def bass_range(instrument: Instrument) -> tuple[int, int]:
    if instrument.kind == "bass":
        return instrument.lowest, instrument.lowest + 22
    # На гитаре бас живёт на трёх толстых струнах: от открытой шестой до ~4 лада четвёртой.
    return instrument.lowest, instrument.lowest + 14


# ─── Мелодия ──────────────────────────────────────────────────────────────


def melody_notes(ctx: Context, instrument: Instrument, level: Difficulty) -> list[QNote]:
    notes = quantize(ctx.tx.melody, GRID[level], ctx.total_steps, ctx.transpose)
    if level == "easy":
        notes = drop_ornaments(merge_repeats(notes, max_gap=0), max_len=2)
    elif level == "medium":
        notes = drop_ornaments(notes, max_len=1)
    low, high = melody_range(instrument, level)
    return fit_range(notes, low, high, phrase_gap=STEPS_PER_BEAT * 2)


def melody_part(ctx: Context, instrument: Instrument, level: Difficulty) -> list[TabBeat]:
    return _line(melody_notes(ctx, instrument, level), instrument, level, _melody_strings)


# ─── Бас ──────────────────────────────────────────────────────────────────


def _root_notes(ctx: Context, level: Difficulty, low: int) -> list[QNote]:
    """Бас по корням аккордов: основной тон на такт (на «средне» — полтакта, чередуя с квинтой)."""
    notes: list[QNote] = []
    chunk = ctx.bar_steps if level == "easy" else ctx.bar_steps // 2
    for item in ctx.timeline(level):
        root = low + (item.chord.bass_pc - low) % 12
        fifth = root + 7 if root + 7 - low < 12 else root - 5
        t = item.start
        alternate = False
        while t < item.end:
            end = min(item.end, (t // chunk + 1) * chunk)
            pitch = fifth if (alternate and level != "easy") else root
            notes.append(QNote(t, end - t, pitch))
            alternate = not alternate
            t = end
    return notes


def bass_notes(ctx: Context, instrument: Instrument, level: Difficulty) -> list[QNote]:
    low, high = bass_range(instrument)
    transcribed = [n for n in ctx.tx.bass if n.duration > 0]
    if level == "easy" or len(transcribed) < 8:
        notes = _root_notes(ctx, level, low)
    else:
        notes = quantize(transcribed, GRID[level], ctx.total_steps, ctx.transpose)
        if level == "medium":
            notes = drop_ornaments(merge_repeats(notes, max_gap=0), max_len=1)
    return fit_range(notes, low, high, phrase_gap=STEPS_PER_BEAT * 4)


def bass_part(ctx: Context, instrument: Instrument, level: Difficulty) -> list[TabBeat]:
    def strings(string: int) -> float:
        if instrument.kind == "bass":
            return 0.0
        return 0.6 * max(0, instrument.strings - 2 - string)

    return _line(bass_notes(ctx, instrument, level), instrument, level, strings)


# ─── Ритм: аккорды и бой ──────────────────────────────────────────────────


def _pick_slots(
    accents: Sequence[float], bar: int, step: int, min_hits: int, max_hits: int
) -> list[int] | None:
    if len(accents) != bar:
        return None
    slots = list(range(0, bar, step))
    peak = max(accents[s] for s in slots)
    if peak < 0.05:
        return None
    strength = {s: accents[s] for s in slots}
    chosen = {s for s in slots if strength[s] >= 0.45 * peak} | {0}
    by_strength = sorted(slots, key=lambda s: -strength[s])
    for s in by_strength:
        if len(chosen) >= min_hits:
            break
        chosen.add(s)
    if len(chosen) > max_hits:
        chosen = {0, *[s for s in by_strength if s != 0][: max_hits - 1]}
    return sorted(chosen)


def strum_slots(
    level: Difficulty, beats_per_bar: int, accents: Sequence[float]
) -> list[tuple[int, Stroke]]:
    """Схема боя на один такт: (шаг от начала такта, направление удара)."""
    bar = beats_per_bar * STEPS_PER_BEAT
    if level == "easy":
        return [(b * STEPS_PER_BEAT, "down") for b in range(beats_per_bar)]
    defaults: dict[int, list[int]] = {4: [0, 4, 6, 10, 12, 14], 3: [0, 4, 6, 8, 10]}
    if level == "medium":
        picked = _pick_slots(accents, bar, 2, beats_per_bar, bar // 2 - 1)
        slots = picked or defaults.get(beats_per_bar, list(range(0, bar, STEPS_PER_BEAT)))
        return [(s, "down" if s % STEPS_PER_BEAT == 0 else "up") for s in slots]
    picked = _pick_slots(accents, bar, 1, beats_per_bar * 2, bar - 4)
    slots = picked or defaults.get(beats_per_bar, list(range(0, bar, 2)))
    return [(s, "down" if s % 2 == 0 else "up") for s in slots]


@dataclass(frozen=True)
class Harmony:
    """Аккорды партии: участки времени и выбранная аппликатура для каждого."""

    timeline: list[StepChord]
    voicings: list[Voicing | None]
    names: list[str]

    def shapes(self) -> tuple[ChordShape, ...]:
        seen: dict[str, ChordShape] = {}
        for name, voicing in zip(self.names, self.voicings, strict=True):
            if voicing is not None and name not in seen:
                seen[name] = ChordShape(name, voicing.frets)
        return tuple(seen.values())


def harmony(ctx: Context, instrument: Instrument, level: Difficulty) -> Harmony:
    timeline = ctx.timeline(level)
    voicings = choose_voicings([c.chord for c in timeline], instrument, level)
    names = [_shape_name(c.chord, instrument, ctx.key) for c in timeline]
    return Harmony(timeline, voicings, names)


def _event_times(ctx: Context, slots: Sequence[int], timeline: Sequence[StepChord]) -> list[int]:
    """Удары по схеме в каждом такте плюс удар в момент смены аккорда."""
    changes = sorted({c.start for c in timeline})
    times: set[int] = set()
    for bar in range(ctx.tx.bars):
        base = bar * ctx.bar_steps
        times.update(base + s for s in slots)
    times.update(t for t in changes if t < ctx.total_steps)
    return sorted(times)


def _bar_end(ctx: Context) -> Callable[[int], int]:
    return lambda t: min(ctx.total_steps, (t // ctx.bar_steps + 1) * ctx.bar_steps)


def rhythm_part(
    ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony
) -> list[TabBeat]:
    slots = strum_slots(level, ctx.tx.beats_per_bar, ctx.tx.accents)
    direction = dict(slots)
    at = _segment_index(h.timeline)
    times = _event_times(ctx, [s for s, _ in slots], h.timeline)
    beats: list[TabBeat] = []
    last_segment: int | None = None
    for t, length in zip(times, _durations(times, _bar_end(ctx)), strict=True):
        segment = at(t)
        voicing = h.voicings[segment] if segment is not None else None
        if segment is None or voicing is None:
            last_segment = None
            continue
        offset = t % ctx.bar_steps
        stroke = direction.get(offset, "down" if offset % STEPS_PER_BEAT == 0 else "up")
        notes = tuple(_note(instrument, s, f) for s, f, _ in voicing.notes(instrument))
        label = h.names[segment] if segment != last_segment else None
        beats.append(TabBeat(t, length, notes, stroke, label))
        last_segment = segment
    return beats


# ─── Перебор (роль «фон») ──────────────────────────────────────────────────


def _arpeggio_order(voicing: Voicing, level: Difficulty, beats_per_bar: int) -> list[int]:
    played = sorted(voicing.played)
    bass = played[-1]
    trebles = [s for s in played if s != bass][:3] or [bass]
    t1, t2, t3 = (trebles + trebles[-1:] * 3)[:3]  # t1 — самая тонкая
    alt = played[-2] if len(played) > 1 else bass
    if beats_per_bar == 3:
        return [bass, t3, t2] if level == "easy" else [bass, t3, t2, t1, t2, t3]
    if level == "easy":
        return [bass, t3, t2, t1]
    second_bass = alt if level == "full" else bass
    return [bass, t3, t2, t1, second_bass, t3, t2, t1]


def pad_part(ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony) -> list[TabBeat]:
    step = STEPS_PER_BEAT if level == "easy" else STEPS_PER_BEAT // 2
    at = _segment_index(h.timeline)
    beats: list[TabBeat] = []
    for t in range(0, ctx.total_steps, step):
        segment = at(t)
        if segment is None or h.voicings[segment] is None:
            continue
        voicing = h.voicings[segment]
        assert voicing is not None
        order = _arpeggio_order(voicing, level, ctx.tx.beats_per_bar)
        string = order[(t % ctx.bar_steps) // step % len(order)]
        fret = voicing.frets[string - 1]
        assert fret is not None
        label = h.names[segment] if h.timeline[segment].start == t else None
        beats.append(TabBeat(t, step, (_note(instrument, string, fret),), None, label))
    return beats


# ─── Перкуссия: глухие удары по струнам ────────────────────────────────────


def percussion_part(ctx: Context, instrument: Instrument, level: Difficulty) -> list[TabBeat]:
    n = instrument.strings
    low_strings = tuple(range(max(1, n - 2), n + 1))  # «бочка» — толстые струны
    high_strings = tuple(range(1, min(n, 4) + 1))  # «малый» — тонкие
    bar = ctx.bar_steps
    accents = ctx.tx.accents if len(ctx.tx.accents) == bar else ()
    if level == "easy":
        pattern = [(b * STEPS_PER_BEAT, b % 2 == 1) for b in range(ctx.tx.beats_per_bar)]
    else:
        step = 2 if level == "medium" else 1
        picked = (
            _pick_slots(accents, bar, step, ctx.tx.beats_per_bar, bar // step) if accents else None
        )
        slots = picked or list(range(0, bar, 2))
        pattern = [(s, (s // STEPS_PER_BEAT) % 2 == 1 and s % STEPS_PER_BEAT == 0) for s in slots]
    times = sorted(bar_index * bar + s for bar_index in range(ctx.tx.bars) for s, _ in pattern)
    snare = dict(pattern)
    beats = []
    for t, length in zip(times, _durations(times, _bar_end(ctx)), strict=True):
        hit_snare = snare[t % bar]
        strings = high_strings if hit_snare else low_strings
        notes = tuple(_note(instrument, s, 0, dead=True) for s in strings)
        stroke: Stroke = "down" if (t % bar) % 2 == 0 else "up"
        beats.append(TabBeat(t, length, notes, stroke))
    return beats


# ─── Как в записи: ноты гитары из оригинала ───────────────────────────────

# Сколько нот разом оставлять там, где в записи не бой, а перебор или рифф.
_ORIGINAL_VOICES: dict[Difficulty, int] = {"easy": 1, "medium": 2, "full": 6}
_STRUM_NOTES = 3  # столько нот на одной доле — это удар по аккорду
# Ноты одного удара по струнам расходятся на 20–40 мс: всё, что ближе этого (в долях), — один удар.
_STRUM_SPREAD = 0.1
# Такт считается «боем», если в нём столько ударов (созвучий от двух нот) от всех событий.
_STRUM_BAR_SHARE = 0.6


@dataclass(frozen=True, slots=True)
class _Group:
    start: int
    end: int
    pitches: tuple[int, ...]  # снизу вверх
    loudness: tuple[int, ...]


def original_groups(ctx: Context, instrument: Instrument, level: Difficulty) -> list[_Group]:
    """Ноты записи → созвучия на сетке уровня, перенесённые в диапазон инструмента."""
    grid = GRID[level]
    low = instrument.lowest
    high = instrument.open_pitch(1) + min(MAX_FRET[level], instrument.frets)
    # Сначала собираем ноты одного удара (они расходятся на десятки мс), потом — на сетку:
    # иначе удар разваливается на два соседних шага с половиной нот в каждом.
    clusters: list[list[Note]] = []
    for note in sorted(ctx.tx.guitar, key=lambda n: n.start):
        if clusters and note.start - clusters[-1][0].start <= _STRUM_SPREAD:
            clusters[-1].append(note)
        else:
            clusters.append([note])

    slots: dict[int, dict[int, int]] = {}  # шаг → высота → громкость
    ends: dict[int, int] = {}
    for cluster in clusters:
        start = round(cluster[0].start * STEPS_PER_BEAT / grid) * grid
        if not 0 <= start < ctx.total_steps:
            continue
        for note in cluster:
            end = round(note.end * STEPS_PER_BEAT / grid) * grid
            end = min(max(start + grid, end), ctx.total_steps)
            pitch = note.pitch + ctx.transpose
            while pitch < low:
                pitch += 12
            while pitch > high:
                pitch -= 12
            if pitch < low:
                continue
            slot = slots.setdefault(start, {})
            slot[pitch] = max(slot.get(pitch, 0), note.velocity)
            ends[start] = max(ends.get(start, start + grid), end)

    starts = sorted(slots)
    groups: list[_Group] = []
    for i, start in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else ctx.total_steps
        end = min(nxt, ends[start])
        # Короткие паузы внутри фразы на простых уровнях не пишем: нота тянется до следующей.
        if level != "full" and nxt - end <= STEPS_PER_BEAT:
            end = nxt
        pitches = tuple(sorted(slots[start]))
        groups.append(
            _Group(start, max(end, start + 1), pitches, tuple(slots[start][p] for p in pitches))
        )
    return groups


def _thin(group: _Group, voices: int) -> tuple[int, ...]:
    """Оставляем верх (мелодию), низ (бас) и самые громкие ноты между ними."""
    pitches = list(group.pitches)
    if len(pitches) <= voices:
        return tuple(pitches)
    if voices == 1:
        return (pitches[-1],)
    keep = {pitches[0], pitches[-1]}
    middle = sorted(
        (p for p in pitches[1:-1]),
        key=lambda p: -group.loudness[group.pitches.index(p)],
    )
    keep.update(middle[: voices - 2])
    return tuple(sorted(keep))


def original_part(
    ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony
) -> list[TabBeat]:
    """Партия «как в записи»: ритм и ноты гитары оригинала.

    Там, где в записи бьют по аккорду (три ноты и больше разом), берётся удобная аппликатура
    этого аккорда — так табы чище, а звучит так же. Рифы и переборы раскладываются по грифу
    нота в ноту.
    """
    groups = original_groups(ctx, instrument, level)
    if not groups:
        return []
    # Бой или перебор решаем по такту целиком: в бое число нот на удар скачет (часть струн
    # модель не слышит), и по одному удару табы превращаются в мешанину аккордов и двузвучий.
    per_bar: dict[int, list[_Group]] = {}
    for group in groups:
        per_bar.setdefault(group.start // ctx.bar_steps, []).append(group)
    strummed_bars = {
        bar
        for bar, items in per_bar.items()
        if len(items) >= 2
        and sum(len(g.pitches) >= 2 for g in items) >= _STRUM_BAR_SHARE * len(items)
        and sum(len(g.pitches) >= _STRUM_NOTES for g in items) >= 1
    }
    if level == "easy":  # на «легко» в бое — только удары на доли
        groups = [
            g
            for g in groups
            if g.start // ctx.bar_steps not in strummed_bars or g.start % STEPS_PER_BEAT == 0
        ]
    at = _segment_index(h.timeline)
    events: list[tuple[float, tuple[int, ...], Assignment | None]] = []
    strums: list[bool] = []
    for group in groups:
        segment = at(group.start)
        voicing = h.voicings[segment] if segment is not None else None
        in_strum = group.start // ctx.bar_steps in strummed_bars
        if voicing is not None and (in_strum or len(group.pitches) >= _STRUM_NOTES):
            fixed = tuple((s, f) for s, f, _ in voicing.notes(instrument))
            pitches = tuple(p for _, _, p in voicing.notes(instrument))
            events.append((group.start / STEPS_PER_BEAT, pitches, fixed))
            strums.append(True)
        else:
            pitches = _thin(group, _ORIGINAL_VOICES[level])
            events.append((group.start / STEPS_PER_BEAT, pitches, None))
            strums.append(False)

    fingered = finger_events(events, instrument, span=SPAN[level], max_fret=MAX_FRET[level])
    beats: list[TabBeat] = []
    last_segment: int | None = None
    for group, strum, option in zip(groups, strums, fingered, strict=True):
        if option is None:
            continue
        notes = tuple(
            TabNote(string, fret, instrument.pitch_at(string, fret)) for string, fret in option
        )
        stroke: Stroke | None = None
        if strum:
            # Рука ходит вверх-вниз по сетке уровня: вниз — на долю (или восьмую), вверх — между.
            on_beat = group.start % (2 * GRID[level]) == 0
            stroke = "down" if on_beat else "up"
        segment = at(group.start)
        label = h.names[segment] if segment is not None and segment != last_segment else None
        if segment is not None:
            last_segment = segment
        beats.append(TabBeat(group.start, group.end - group.start, notes, stroke, label))
    return beats


# ─── Сочетания ролей ──────────────────────────────────────────────────────


def bass_strum_part(
    ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony
) -> list[TabBeat]:
    """«Бас-аккорд»: басовая нота на сильные доли, между ними — удары по остальным струнам."""
    if ctx.tx.beats_per_bar == 3:
        pattern: list[tuple[int, str]] = [(0, "bass"), (4, "down"), (8, "down")]
    elif level == "easy":
        pattern = [(0, "bass"), (4, "down"), (8, "bass"), (12, "down")]
    else:
        pattern = [(0, "bass"), (4, "down"), (6, "up"), (8, "alt"), (12, "down"), (14, "up")]
    kinds = dict(pattern)
    at = _segment_index(h.timeline)
    times = _event_times(ctx, [s for s, _ in pattern], h.timeline)
    beats: list[TabBeat] = []
    last_segment: int | None = None
    for t, length in zip(times, _durations(times, _bar_end(ctx)), strict=True):
        segment = at(t)
        voicing = h.voicings[segment] if segment is not None else None
        if segment is None or voicing is None:
            last_segment = None
            continue
        kind = kinds.get(t % ctx.bar_steps, "bass" if segment != last_segment else "down")
        notes_all = voicing.notes(instrument)
        played = sorted(voicing.played)
        label = h.names[segment] if segment != last_segment else None
        if kind in ("bass", "alt"):
            string = played[-1] if kind == "bass" or len(played) < 2 else played[-2]
            fret = voicing.frets[string - 1]
            assert fret is not None
            beats.append(TabBeat(t, length, (_note(instrument, string, fret),), None, label))
        else:
            notes = tuple(_note(instrument, s, f) for s, f, _ in notes_all if s != played[-1])
            stroke: Stroke = "down" if kind == "down" else "up"
            beats.append(TabBeat(t, length, notes, stroke, label))
        last_segment = segment
    return beats


def melody_with_pad(
    ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony
) -> list[TabBeat]:
    """Мелодия, а в тактах без неё — перебор по аккордам."""
    melody = melody_part(ctx, instrument, level)
    busy: set[int] = set()
    for beat in melody:
        first = beat.start // ctx.bar_steps
        last = (beat.start + beat.duration - 1) // ctx.bar_steps
        busy.update(range(first, last + 1))
    fill = [b for b in pad_part(ctx, instrument, level, h) if b.start // ctx.bar_steps not in busy]
    return sorted([*melody, *fill], key=lambda b: b.start)


def _fingerstyle_cost(option: tuple[tuple[int, int], ...], hand: int) -> float:
    """Ниже по грифу, ближе к руке, мелодия — на тонких струнах."""
    fretted = [f for _, f in option if f]
    center = sum(fretted) / len(fretted) if fretted else hand
    melody_string = option[0][0] if option else 1
    return 0.05 * sum(fretted) + 0.4 * abs(center - hand) + 0.25 * max(0, melody_string - 3)


def fingerstyle_part(
    ctx: Context, instrument: Instrument, level: Difficulty, h: Harmony
) -> list[TabBeat]:
    """Фингерстайл: мелодия на тонких струнах и бас по корням на сильные доли (SPEC §1.4)."""
    span = SPAN[level]
    max_fret = MAX_FRET[level]
    low, high = melody_range(instrument, level)
    melody = fit_range(
        melody_notes(ctx, instrument, level),
        max(low, instrument.open_pitch(3)),
        high,
        phrase_gap=STEPS_PER_BEAT * 2,
    )
    bass_every = ctx.bar_steps if level == "easy" else ctx.bar_steps // 2
    bass_low = instrument.lowest
    roots: dict[int, int] = {}
    for item in h.timeline:
        t = item.start
        while t < item.end:
            roots[t] = bass_low + (item.chord.bass_pc - bass_low) % 12
            t = (t // bass_every + 1) * bass_every

    events: dict[int, tuple[int | None, int | None]] = {q.start: (q.pitch, None) for q in melody}
    for t, pitch in roots.items():
        tone, _ = events.get(t, (None, None))
        events[t] = (tone, pitch)
    times = sorted(events)

    def combos(tone: int | None, bass: int | None) -> list[tuple[tuple[int, int], ...]]:
        tones = instrument.positions(tone, max_fret) if tone is not None else [None]
        basses = instrument.positions(bass, max_fret) if bass is not None else [None]
        found = []
        for tp in tones:
            for bp in basses:
                picked = tuple(p for p in (tp, bp) if p is not None)
                if tp and bp and bp[0] <= tp[0]:
                    continue  # бас — на струне толще мелодии
                fretted = [f for _, f in picked if f]
                if fretted and max(fretted) - min(fretted) >= span:
                    continue
                found.append(picked)
        return found

    beats: list[TabBeat] = []
    hand = 0
    segment_at = _segment_index(h.timeline)
    for t, length in zip(times, _durations(times, lambda _: ctx.total_steps), strict=True):
        tone, bass = events[t]
        options = combos(tone, bass) or (combos(tone, None) if tone is not None else [])
        if not options:
            continue
        best = min(options, key=partial(_fingerstyle_cost, hand=hand))
        fretted = [f for _, f in best if f]
        if fretted:
            hand = round(sum(fretted) / len(fretted))
        notes = tuple(_note(instrument, s, f) for s, f in best)
        segment = segment_at(t)
        label = h.names[segment] if segment is not None and h.timeline[segment].start == t else None
        beats.append(TabBeat(t, length, notes, None, label))
    return beats


# ─── Проверка играбельности ────────────────────────────────────────────────


def playability_issues(beats: Sequence[TabBeat], instrument: Instrument, span: int) -> list[str]:
    """Нарушения SPEC §1.9: две ноты на одной струне, растяжка больше span ладов, лады вне грифа."""
    issues = []
    for beat in beats:
        strings = [n.string for n in beat.notes]
        if len(strings) != len(set(strings)):
            issues.append(f"шаг {beat.start}: две ноты на одной струне")
        fretted = [n.fret for n in beat.notes if n.fret > 0 and not n.dead]
        if fretted and max(fretted) - min(fretted) >= span:
            issues.append(f"шаг {beat.start}: растяжка {max(fretted) - min(fretted) + 1} лада")
        if any(not 0 <= n.fret <= instrument.frets for n in beat.notes):
            issues.append(f"шаг {beat.start}: лад вне грифа")
    return issues
