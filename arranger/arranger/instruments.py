"""Строи, инструменты и позиции на грифе."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InstrumentKind = Literal["acoustic", "electric", "bass"]


@dataclass(frozen=True, slots=True)
class Tuning:
    id: str
    label: str
    strings: tuple[int, ...]  # MIDI-высоты открытых струн, первая — самая тонкая

    @property
    def is_bass(self) -> bool:
        return len(self.strings) <= 5


TUNINGS: dict[str, Tuning] = {
    t.id: t
    for t in (
        Tuning("standard", "Стандарт (E)", (64, 59, 55, 50, 45, 40)),
        Tuning("drop-d", "Drop D", (64, 59, 55, 50, 45, 38)),
        Tuning("half-down", "Полтона вниз (E♭)", (63, 58, 54, 49, 44, 39)),
        Tuning("full-down", "Тон вниз (D)", (62, 57, 53, 48, 43, 38)),
        Tuning("drop-c", "Drop C", (62, 57, 53, 48, 43, 36)),
        Tuning("open-g", "Open G", (62, 59, 55, 50, 43, 38)),
        Tuning("open-d", "Open D", (62, 57, 54, 50, 45, 38)),
        Tuning("dadgad", "DADGAD", (62, 57, 55, 50, 45, 38)),
        Tuning("bass-standard", "Бас: стандарт (E)", (43, 38, 33, 28)),
        Tuning("bass-drop-d", "Бас: Drop D", (43, 38, 33, 26)),
        Tuning("bass-half-down", "Бас: полтона вниз", (42, 37, 32, 27)),
    )
}

GUITAR_TUNINGS = tuple(t for t in TUNINGS.values() if not t.is_bass)
BASS_TUNINGS = tuple(t for t in TUNINGS.values() if t.is_bass)

# General MIDI: 25 — акустика со стальными струнами, 27 — чистая электро, 33 — бас пальцами.
_PROGRAMS: dict[InstrumentKind, int] = {"acoustic": 25, "electric": 27, "bass": 33}
_FRETS: dict[InstrumentKind, int] = {"acoustic": 19, "electric": 22, "bass": 20}

INSTRUMENT_LABELS: dict[InstrumentKind, str] = {
    "acoustic": "Акустика",
    "electric": "Электро",
    "bass": "Бас-гитара",
}

# Звук гитары. «auto» — как в записи: перегруз, если разбор услышал его в оригинале.
# Электро-тембры названы как пресеты смарт-гитар (Enya Inspire: Clean, Crunch, Overdrive, Lead),
# чтобы было понятно, что включить на своей гитаре.
Tone = Literal[
    "auto",
    "steel",
    "nylon",
    "clean",
    "funk",
    "chorus",
    "ambient",
    "jazz",
    "blues",
    "crunch",
    "drive",
    "fuzz",
    "lead",
    "metal",
    "finger",
    "pick",
]
TONES: dict[InstrumentKind, tuple[Tone, ...]] = {
    "acoustic": ("steel", "nylon"),
    # От чистого к самому злому перегрузу — так их и показываем в списке.
    "electric": (
        "clean",
        "funk",
        "chorus",
        "ambient",
        "jazz",
        "blues",
        "crunch",
        "drive",
        "fuzz",
        "lead",
        "metal",
    ),
    "bass": ("finger", "pick"),
}
TONE_LABELS: dict[Tone, str] = {
    "auto": "Как в записи",
    "steel": "Стальные струны",
    "nylon": "Нейлон",
    "clean": "Чистый (Clean)",
    "funk": "Фанк (чистый, компрессор)",
    "chorus": "Хорус (Chorus)",
    "ambient": "Эмбиент (дилей и ревер)",
    "jazz": "Джаз",
    "blues": "Блюз (лёгкий перегруз)",
    "crunch": "Кранч (Crunch)",
    "drive": "Перегруз (Overdrive)",
    "fuzz": "Фузз (Fuzz)",
    "lead": "Соло (Lead)",
    "metal": "Метал (Hi-Gain)",
    "finger": "Пальцами",
    "pick": "Медиатором",
}
# Программа General MIDI для встроенного синтезатора. Студийный звук (усилитель, кабинет,
# эффекты) интерфейс собирает сам из чистой гитары — см. frontend/src/pages/studio/tone.ts.
TONE_PROGRAMS: dict[Tone, int] = {
    "steel": 25,
    "nylon": 24,
    "clean": 27,
    "funk": 27,
    "chorus": 27,
    "ambient": 27,
    "jazz": 26,
    "blues": 29,
    "crunch": 29,
    "drive": 29,
    "fuzz": 30,
    "lead": 30,
    "metal": 30,
    "finger": 33,
    "pick": 34,
}
# С перегрузом аккорды берут пауэр-аккордами (основной тон + квинта): терции «грязнят».
DISTORTED: frozenset[Tone] = frozenset({"drive", "fuzz", "lead", "metal"})


def resolve_tone(kind: InstrumentKind, tone: str, heard: str = "", sound: str = "") -> Tone:
    """Звук игрока. heard — какая гитара в записи (acoustic, clean, distorted); sound — какой
    именно электро-тембр подобрал разбор (funk, metal…), пусто — старый разбор."""
    for known in TONES[kind]:
        if tone == known:
            return known
    if kind == "acoustic":
        return "nylon" if heard == "nylon" else "steel"
    if kind == "bass":
        return "finger"
    for known in TONES["electric"]:
        if sound == known:
            return known
    return "drive" if heard == "distorted" else "clean"


@dataclass(frozen=True, slots=True)
class Instrument:
    kind: InstrumentKind
    tuning: Tuning
    capo: int = 0

    @property
    def strings(self) -> int:
        return len(self.tuning.strings)

    @property
    def frets(self) -> int:
        """Ладов до верхнего края грифа, считая от каподастра."""
        return _FRETS[self.kind] - self.capo

    @property
    def midi_program(self) -> int:
        return _PROGRAMS[self.kind]

    def open_pitch(self, string: int) -> int:
        return self.tuning.strings[string - 1] + self.capo

    def pitch_at(self, string: int, fret: int) -> int:
        return self.open_pitch(string) + fret

    @property
    def lowest(self) -> int:
        return self.open_pitch(self.strings)

    @property
    def highest(self) -> int:
        return self.open_pitch(1) + self.frets

    def positions(self, pitch: int, max_fret: int | None = None) -> list[tuple[int, int]]:
        """Все (струна, лад), где звучит эта высота."""
        top = self.frets if max_fret is None else min(max_fret, self.frets)
        found = []
        for string in range(1, self.strings + 1):
            fret = pitch - self.open_pitch(string)
            if 0 <= fret <= top:
                found.append((string, fret))
        return found


def make_instrument(kind: InstrumentKind, tuning_id: str, capo: int = 0) -> Instrument:
    tuning = TUNINGS.get(tuning_id)
    if tuning is None:
        raise ValueError(f"Неизвестный строй: {tuning_id}")
    if (kind == "bass") != tuning.is_bass:
        tuning = TUNINGS["bass-standard" if kind == "bass" else "standard"]
    return Instrument(kind, tuning, max(0, min(capo, 12)))
