"""Вход движка — транскрипция песни, выход — партии в виде табулатуры.

Время везде в долях (четвертях) от начала первого такта. В партиях время дискретное:
шаг сетки — шестнадцатая (STEPS_PER_BEAT шагов на долю).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from arranger.instruments import InstrumentKind
from arranger.theory import Chord, Key, Mode, parse_chord

STEPS_PER_BEAT = 4

Role = Literal["melody", "bass", "rhythm", "pad", "percussion"]
Difficulty = Literal["easy", "medium", "full"]
Stroke = Literal["down", "up"]

ROLES: tuple[Role, ...] = ("melody", "bass", "rhythm", "pad", "percussion")
DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium", "full")


@dataclass(frozen=True, slots=True)
class Note:
    start: float
    duration: float
    pitch: int
    velocity: int = 96

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True, slots=True)
class ChordSpan:
    start: float
    end: float
    chord: Chord


@dataclass(frozen=True)
class Transcription:
    """Что нашёл анализ, в долях. Сохраняется в analysis.json → поле "transcription"."""

    tempo: float
    beats_per_bar: int
    bars: int
    key: Key
    chords: tuple[ChordSpan, ...]
    melody: tuple[Note, ...] = ()
    bass: tuple[Note, ...] = ()
    # Сила ударов барабанов на каждой шестнадцатой такта, 0..1 (длина beats_per_bar * 4).
    accents: tuple[float, ...] = ()

    @property
    def total_beats(self) -> int:
        return self.bars * self.beats_per_bar

    def to_dict(self) -> dict[str, Any]:
        return {
            "tempo": self.tempo,
            "beats_per_bar": self.beats_per_bar,
            "bars": self.bars,
            "key": {"tonic": self.key.tonic, "mode": self.key.mode},
            "chords": [
                {"start": c.start, "end": c.end, "chord": c.chord.name()} for c in self.chords
            ],
            "melody": [_note_dict(n) for n in self.melody],
            "bass": [_note_dict(n) for n in self.bass],
            "accents": list(self.accents),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transcription:
        mode: Mode = "minor" if data["key"]["mode"] == "minor" else "major"
        return cls(
            tempo=float(data["tempo"]),
            beats_per_bar=int(data["beats_per_bar"]),
            bars=int(data["bars"]),
            key=Key(int(data["key"]["tonic"]) % 12, mode),
            chords=tuple(
                ChordSpan(float(c["start"]), float(c["end"]), parse_chord(c["chord"]))
                for c in data["chords"]
            ),
            melody=tuple(_note_from(n) for n in data.get("melody", [])),
            bass=tuple(_note_from(n) for n in data.get("bass", [])),
            accents=tuple(float(a) for a in data.get("accents", [])),
        )


def _note_dict(note: Note) -> dict[str, float | int]:
    return {
        "start": round(note.start, 4),
        "duration": round(note.duration, 4),
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _note_from(data: dict[str, Any]) -> Note:
    return Note(
        float(data["start"]),
        float(data["duration"]),
        int(data["pitch"]),
        int(data.get("velocity", 96)),
    )


@dataclass(frozen=True, slots=True)
class TabNote:
    string: int  # 1 — самая тонкая струна
    fret: int  # от каподастра: 0 — открытая (или струна у каподастра)
    pitch: int  # реально звучащая высота
    dead: bool = False  # глухая нота «x» (перкуссия)


@dataclass(frozen=True, slots=True)
class TabBeat:
    start: int  # в шагах сетки
    duration: int
    notes: tuple[TabNote, ...]  # пусто — пауза
    stroke: Stroke | None = None
    chord: str | None = None  # имя аккорда над долей — там, где он сменился


@dataclass(frozen=True, slots=True)
class ChordShape:
    """Аппликатура для диаграммы: лад на каждой струне, None — не играется."""

    name: str
    frets: tuple[int | None, ...]


@dataclass(frozen=True)
class Part:
    player_id: str
    title: str
    roles: tuple[Role, ...]
    difficulty: Difficulty
    instrument_kind: InstrumentKind
    tuning_id: str
    capo: int
    beats: tuple[TabBeat, ...]
    shapes: tuple[ChordShape, ...] = ()
    warnings: tuple[str, ...] = field(default=())
