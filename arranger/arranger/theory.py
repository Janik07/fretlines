"""Высоты, аккорды и тональности."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Quality = Literal["maj", "min", "7", "maj7", "min7", "dim", "aug", "sus2", "sus4", "5"]
Mode = Literal["major", "minor"]

SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

INTERVALS: dict[Quality, tuple[int, ...]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "5": (0, 7),
}

SUFFIXES: dict[Quality, str] = {
    "maj": "",
    "min": "m",
    "7": "7",
    "maj7": "maj7",
    "min7": "m7",
    "dim": "dim",
    "aug": "aug",
    "sus2": "sus2",
    "sus4": "sus4",
    "5": "5",
}

# «Упрощённо» (SPEC §1.4): всё сводится к мажору или минору.
_TRIAD: dict[Quality, Quality] = {
    "maj": "maj",
    "min": "min",
    "7": "maj",
    "maj7": "maj",
    "min7": "min",
    "dim": "min",
    "aug": "maj",
    "sus2": "maj",
    "sus4": "maj",
    "5": "maj",
}

_QUALITY_BY_SUFFIX: dict[str, Quality] = {suffix: q for q, suffix in SUFFIXES.items()}
_CHORD_RE = re.compile(r"^([A-G])([#b]?)(maj7|m7|m|7|dim|aug|sus2|sus4|5)?(?:/([A-G])([#b]?))?$")
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pc_name(pc: int, *, flats: bool = False) -> str:
    return (FLAT_NAMES if flats else SHARP_NAMES)[pc % 12]


def midi_name(pitch: int, *, flats: bool = False) -> str:
    """MIDI → «E4» (C4 = 60)."""
    return f"{pc_name(pitch, flats=flats)}{pitch // 12 - 1}"


def parse_pc(letter: str, accidental: str = "") -> int:
    shift = {"": 0, "#": 1, "b": -1}[accidental]
    return (_LETTER_PC[letter] + shift) % 12


@dataclass(frozen=True, slots=True)
class Chord:
    root: int
    quality: Quality
    bass: int | None = None

    @property
    def intervals(self) -> tuple[int, ...]:
        return INTERVALS[self.quality]

    @property
    def pitch_classes(self) -> frozenset[int]:
        pcs = {(self.root + i) % 12 for i in self.intervals}
        if self.bass is not None:
            pcs.add(self.bass)
        return frozenset(pcs)

    @property
    def essential(self) -> frozenset[int]:
        """Тоны, без которых аккорд не узнать: квинту можно опустить, если есть терция."""
        if self.quality == "5":
            keep: tuple[int, ...] = self.intervals
        else:
            keep = tuple(i for i in self.intervals if i != 7)
        return frozenset((self.root + i) % 12 for i in keep)

    @property
    def bass_pc(self) -> int:
        return self.root if self.bass is None else self.bass

    def transposed(self, semitones: int) -> Chord:
        bass = None if self.bass is None else (self.bass + semitones) % 12
        return Chord((self.root + semitones) % 12, self.quality, bass)

    def simplified(self) -> Chord:
        return Chord(self.root, _TRIAD[self.quality])

    def name(self, *, flats: bool = False) -> str:
        text = pc_name(self.root, flats=flats) + SUFFIXES[self.quality]
        if self.bass is not None and self.bass != self.root:
            text += "/" + pc_name(self.bass, flats=flats)
        return text


def parse_chord(text: str) -> Chord:
    match = _CHORD_RE.match(text.strip())
    if match is None:
        raise ValueError(f"Не похоже на аккорд: {text!r}")
    letter, acc, suffix, bass_letter, bass_acc = match.groups()
    quality = _QUALITY_BY_SUFFIX[suffix or ""]
    bass = parse_pc(bass_letter, bass_acc or "") if bass_letter else None
    return Chord(parse_pc(letter, acc), quality, bass)


@dataclass(frozen=True, slots=True)
class Key:
    tonic: int
    mode: Mode

    def transposed(self, semitones: int) -> Key:
        return Key((self.tonic + semitones) % 12, self.mode)

    @property
    def relative_major(self) -> int:
        return self.tonic if self.mode == "major" else (self.tonic + 3) % 12

    @property
    def flats(self) -> bool:
        # Тональности с бемолями: F, B♭, E♭, A♭, D♭ (и их параллельные миноры).
        return self.relative_major in {1, 3, 5, 8, 10}

    @property
    def name(self) -> str:
        return pc_name(self.tonic, flats=self.flats) + ("m" if self.mode == "minor" else "")
