"""Экспорт аранжировки в alphaTex (alphaTab 1.9): каждая партия — отдельный трек с табами.

Темп пишется на каждый такт по записи: так синтезатор играет «вживую», как оригинал, и время
плеера совпадает со временем записи. Слова песни подписываются под долями партий.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterator, Sequence
from itertools import pairwise

from arranger.arrange import Arrangement
from arranger.instruments import Instrument, make_instrument
from arranger.model import STEPS_PER_BEAT, Part, TabBeat, TabNote
from arranger.theory import midi_name

# Длительности в шагах (шестнадцатых) → (длительность alphaTex, с точкой). От длинных к коротким.
_VALUES: tuple[tuple[int, int, bool], ...] = (
    (16, 1, False),
    (12, 2, True),
    (8, 2, False),
    (6, 4, True),
    (4, 4, False),
    (3, 8, True),
    (2, 8, False),
    (1, 16, False),
)


def _text(value: str) -> str:
    """Строка alphaTex: кавычки и всё, что вне ASCII, — через экранирование."""
    out = []
    for ch in value:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            out.append(f"\\u{ord(ch):04x}")
    return '"' + "".join(out) + '"'


def _split(length: int, offset: int) -> Iterator[tuple[int, bool]]:
    """Длина в шагах → последовательность нотных длительностей (длинные лиги — через ties)."""
    remaining = length
    position = offset
    while remaining > 0:
        for steps, value, dotted in _VALUES:
            # Длинные ноты не начинаем посреди доли — так табы читаются легче.
            off_beat = position % STEPS_PER_BEAT != 0
            if steps <= remaining and not (off_beat and steps > STEPS_PER_BEAT // 2 and steps != 3):
                yield value, dotted
                remaining -= steps
                position += steps
                break
        else:  # pragma: no cover — 1 шаг подходит всегда
            raise AssertionError(length)


def _note_text(note: TabNote, tie: bool) -> str:
    fret = "-" if tie else str(note.fret)
    return f"{fret}.{note.string}" + ("{x}" if note.dead and not tie else "")


def _beat_text(
    beat: TabBeat | None, value: int, dotted: bool, tie: bool, first: bool, lyric: str | None = None
) -> str:
    props = []
    if dotted:
        props.append("d")
    if lyric:
        props.append("lyrics " + _text(lyric))
    if beat is None or not beat.notes:
        body = "r"
    else:
        notes = [_note_text(n, tie) for n in sorted(beat.notes, key=lambda n: n.string)]
        body = notes[0] if len(notes) == 1 else "(" + " ".join(notes) + ")"
        if first and not tie:
            if beat.stroke == "down":
                props.append("bd")
            elif beat.stroke == "up":
                props.append("bu")
            if beat.chord:
                props.append("ch " + _text(beat.chord))
    suffix = " {" + " ".join(props) + "}" if props else ""
    return f"{body}.{value}{suffix}"


def _lyrics_by_event(
    events: Sequence[tuple[int, int, TabBeat | None]], words: Sequence[tuple[int, str]]
) -> dict[int, str]:
    """Слово → событие, во время которого оно спето. Несколько слов на одну долю — через пробел."""
    starts = [start for start, _, _ in events]
    out: dict[int, list[str]] = {}
    for step, text in words:
        index = bisect.bisect_right(starts, step) - 1
        if index < 0 or not text.strip():
            continue
        beat = events[index][2]
        # Слово, попавшее в паузу прямо перед нотой, подписываем под этой нотой.
        if beat is None and index + 1 < len(events) and events[index + 1][0] - step <= 2:
            index += 1
        out.setdefault(index, []).append(text.strip())
    return {index: " ".join(texts) for index, texts in out.items()}


def _bars(
    part: Part, bars: int, bar_steps: int, words: Sequence[tuple[int, str]] = ()
) -> list[str]:
    """Такты партии: события в шагах → текст alphaTex, паузы и лиги через тактовую черту."""
    events: list[tuple[int, int, TabBeat | None]] = []  # (старт, длина, доля или пауза)
    cursor = 0
    total = bars * bar_steps
    for item in sorted(part.beats, key=lambda b: b.start):
        start = max(item.start, cursor)
        end = min(item.start + item.duration, total)
        if end <= start:
            continue
        if start > cursor:
            events.append((cursor, start - cursor, None))
        events.append((start, end - start, item))
        cursor = end
    if cursor < total:
        events.append((cursor, total - cursor, None))

    lyrics = _lyrics_by_event(events, words)
    out: list[list[str]] = [[] for _ in range(bars)]
    for index, (start, length, beat) in enumerate(events):
        t = start
        first = True
        while t < start + length:
            bar = t // bar_steps
            chunk = min(start + length, (bar + 1) * bar_steps) - t
            pieces = list(_split(chunk, t % bar_steps))
            for i, (value, dotted) in enumerate(pieces):
                is_first = first and i == 0
                lyric = lyrics.get(index) if is_first else None
                out[bar].append(_beat_text(beat, value, dotted, not is_first, is_first, lyric))
            first = False
            t += chunk
    return [" ".join(tokens) for tokens in out]


def bar_tempos(bar_seconds: Sequence[float], beats_per_bar: int, bars: int) -> list[float] | None:
    """Темп каждого такта (четвертей в минуту) по секундам начала тактов в записи."""
    if len(bar_seconds) < bars + 1:
        return None
    tempos: list[float] = []
    for begin, end in pairwise(bar_seconds[: bars + 1]):
        if end <= begin:
            return None
        tempos.append(round(min(max(60.0 * beats_per_bar / (end - begin), 20.0), 400.0), 2))
    return tempos


def _tuning(instrument: Instrument) -> str:
    names = " ".join(midi_name(p, flats=True) for p in instrument.tuning.strings)
    return f"\\tuning ({names}) {{ label {_text(instrument.tuning.label)} }}"


def _short(title: str) -> str:
    word = title.split("·")[-1].strip().split(" ")[0]
    return (word[:4] + ".") if len(word) > 5 else word


def part_to_alphatex(
    part: Part,
    bars: int,
    beats_per_bar: int,
    *,
    tempos: Sequence[float] | None = None,
    words: Sequence[tuple[int, str]] = (),
) -> str:
    instrument = make_instrument(part.instrument_kind, part.tuning_id, part.capo)
    lines = [
        f"\\track ({_text(part.title)} {_text(_short(part.title))}) "
        f"{{ instrument {instrument.midi_program} }}",
        "\\staff {tabs}",
        _tuning(instrument),
    ]
    if part.capo:
        lines.append(f"\\capo {part.capo}")
    for shape in part.shapes:
        frets = " ".join("x" if f is None else str(f) for f in shape.frets)
        lines.append(f"\\chord ({_text(shape.name)} {frets})")
    bar_steps = beats_per_bar * STEPS_PER_BEAT
    bar_texts = _bars(part, bars, bar_steps, words)
    previous = tempos[0] if tempos else None
    for index, text in enumerate(bar_texts):
        prefix = f"\\ts ({beats_per_bar} 4) " if index == 0 else ""
        # Темп — свойство такта для всей партитуры: достаточно записать его в первой партии.
        if tempos and index > 0 and abs(tempos[index] - (previous or 0.0)) >= 0.01:
            prefix += f"\\tempo {_number(tempos[index])} "
            previous = tempos[index]
        lines.append(f"{prefix}{text} |")
    return "\n".join(lines)


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def to_alphatex(
    arrangement: Arrangement,
    *,
    title: str,
    artist: str | None = None,
    words: Sequence[tuple[int, str]] = (),
) -> str:
    """Партитура целиком. words — слова песни: (шаг сетки, текст), подписываются под долями."""
    tempos = bar_tempos(arrangement.bar_seconds, arrangement.beats_per_bar, arrangement.bars)
    head = [f"\\title {_text(title)}"]
    if artist:
        head.append(f"\\artist {_text(artist)}")
    head.append(f"\\tempo {_number(tempos[0]) if tempos else round(arrangement.tempo)}")
    body = [
        part_to_alphatex(
            part,
            arrangement.bars,
            arrangement.beats_per_bar,
            tempos=tempos if index == 0 else None,
            words=words,
        )
        for index, part in enumerate(arrangement.parts)
    ]
    return "\n".join(head) + "\n" + "\n".join(body) + "\n"
