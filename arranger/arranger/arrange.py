"""Аранжировка целиком: состав группы → партия для каждого игрока (SPEC §1.4, «Состав и роли»)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from arranger.instruments import DISTORTED, InstrumentKind, make_instrument, resolve_tone
from arranger.model import (
    STEPS_PER_BEAT,
    ChordShape,
    ChordSpan,
    Difficulty,
    Part,
    Role,
    TabBeat,
    Transcription,
)
from arranger.parts import (
    Context,
    bass_part,
    bass_strum_part,
    fingerstyle_part,
    harmony,
    melody_part,
    melody_with_pad,
    original_part,
    pad_part,
    percussion_part,
    playability_issues,
    rhythm_part,
)
from arranger.theory import Key
from arranger.voicings import SPAN, CapoOption, suggest_capo

# Если ролей у игрока больше, чем он может сыграть разом, остаётся главная по этому порядку.
PRIORITY: tuple[Role, ...] = ("original", "melody", "rhythm", "bass", "pad", "percussion")

ROLE_LABELS: dict[Role, str] = {
    "original": "Как в записи",
    "melody": "Мелодия",
    "bass": "Бас",
    "rhythm": "Ритм",
    "pad": "Фон",
    "percussion": "Перкуссия",
}


@dataclass(frozen=True)
class PlayerSetup:
    id: str
    name: str
    kind: InstrumentKind = "acoustic"
    tuning: str = "standard"
    capo: int = 0
    roles: tuple[Role, ...] = ("rhythm",)
    difficulty: Difficulty = "medium"
    tone: str = "auto"  # звук гитары: instruments.TONES или «auto» — как в записи


PRESETS: dict[str, tuple[tuple[str, tuple[Role, ...]], ...]] = {
    "record": (("Гитара", ("original",)), ("Мелодия", ("melody",)), ("Бас", ("bass",))),
    "solo": (("Гитара", ("melody", "bass", "rhythm")),),
    "duo": (("Лид", ("melody", "pad")), ("Ритм", ("rhythm", "bass"))),
    "trio": (("Мелодия", ("melody",)), ("Ритм", ("rhythm",)), ("Бас", ("bass",))),
    "quartet": (
        ("Мелодия", ("melody",)),
        ("Ритм", ("rhythm",)),
        ("Бас", ("bass",)),
        ("Фон", ("pad",)),
    ),
}

PRESET_LABELS: dict[str, str] = {
    "record": "Как в записи: гитара, мелодия, бас",
    "solo": "Соло фингерстайл",
    "duo": "Дуэт: лид + ритм",
    "trio": "Трио: мелодия + ритм + бас",
    "quartet": "Квартет",
}


def preset_players(preset: str) -> tuple[PlayerSetup, ...]:
    return tuple(
        PlayerSetup(id=f"p{i + 1}", name=name, roles=roles)
        for i, (name, roles) in enumerate(PRESETS[preset])
    )


@dataclass(frozen=True)
class ChartChord:
    offset: int  # шаг от начала такта
    name: str


@dataclass(frozen=True)
class Arrangement:
    tempo: float
    beats_per_bar: int
    bars: int
    key: Key
    transpose: int
    parts: tuple[Part, ...]
    chart: tuple[tuple[ChartChord, ...], ...]  # аккорды по тактам — для режима «Аккорды»
    capo_hints: dict[str, tuple[CapoOption, ...]] = field(default_factory=dict)
    bar_seconds: tuple[float, ...] = ()  # начала тактов в записи (+ конец последнего)


def _title(player: PlayerSetup, roles: Sequence[Role]) -> str:
    role_text = " + ".join(ROLE_LABELS[r].lower() for r in roles)
    return f"{player.name} · {role_text}" if player.name else role_text.capitalize()


def build_part(ctx: Context, player: PlayerSetup) -> Part:
    instrument = make_instrument(player.kind, player.tuning, player.capo)
    level = player.difficulty
    tone = resolve_tone(instrument.kind, player.tone, ctx.tx.guitar_tone)
    power = tone in DISTORTED
    wanted = [r for r in PRIORITY if r in player.roles] or ["rhythm"]
    warnings: list[str] = []
    if instrument.kind == "bass" and any(r not in ("bass", "melody") for r in wanted):
        warnings.append("На бас-гитаре только бас или мелодия — аккорды отданы другим.")
        wanted = [r for r in wanted if r in ("bass", "melody")] or ["bass"]

    roles = set(wanted)
    beats: list[TabBeat]
    played: list[Role]
    h = (
        harmony(ctx, instrument, level, power)
        if roles & {"rhythm", "pad", "original"} or len(roles) > 1
        else None
    )
    if "original" in roles and h is not None and not ctx.tx.guitar:
        # Нот из записи нет (старый разбор или в песне нет гитары) — играем ритм по аккордам.
        beats, played = rhythm_part(ctx, instrument, level, h), ["rhythm"]
        roles.add("rhythm")
        warnings.append(
            "Нот гитары из записи нет — вместо партии «как в записи» ритм по аккордам. "
            "Если разбор старый, нажми «Обновить разбор»."
        )
    elif "original" in roles and h is not None:
        # Партия из записи самодостаточна: остальные роли этого игрока она и так покрывает.
        # Аппликатуры в ней свои — в той позиции грифа, где играет запись.
        beats, h = original_part(ctx, instrument, level, h)
        played = ["original"]
        if ctx.tx.guitar_source == "keys":
            warnings.append("Гитары в записи почти не слышно — партия собрана по клавишным.")
    elif "melody" in roles and roles & {"bass", "rhythm"} and h is not None:
        beats, played = fingerstyle_part(ctx, instrument, level, h), ["melody", "bass", "rhythm"]
        played = [r for r in played if r in roles]
    elif {"rhythm", "bass"} <= roles and h is not None:
        beats, played = bass_strum_part(ctx, instrument, level, h), ["rhythm", "bass"]
    elif {"melody", "pad"} <= roles and h is not None:
        beats, played = melody_with_pad(ctx, instrument, level, h), ["melody", "pad"]
    else:
        main = wanted[0]
        played = [main]
        if main == "melody":
            beats = melody_part(ctx, instrument, level)
        elif main == "bass":
            beats = bass_part(ctx, instrument, level)
        elif main == "percussion":
            beats = percussion_part(ctx, instrument, level)
        else:
            h = h or harmony(ctx, instrument, level, power)
            beats = (rhythm_part if main == "rhythm" else pad_part)(ctx, instrument, level, h)
    # «Как в записи» либо сыграна, либо заменена ритмом (о чём уже предупредили).
    skipped = [ROLE_LABELS[r].lower() for r in wanted if r not in played and r != "original"]
    if skipped and "original" not in played:
        warnings.append(
            "Одному игроку столько не сыграть — без партии: " + ", ".join(skipped) + "."
        )
    if not beats:
        if "original" in played:
            pass  # причина уже в предупреждениях выше
        elif "melody" in played:
            warnings.append("Мелодию разобрать не удалось — попробуй файл с более чистым вокалом.")
        else:
            warnings.append("Для этой партии не нашлось нот.")

    issues = playability_issues(beats, instrument, SPAN[level])
    warnings.extend(f"Неудобное место: {issue}" for issue in issues[:3])
    shapes: tuple[ChordShape, ...] = ()
    if h is not None and "original" in played:
        # Ноты партии взяты из аппликатур — показываем все, по которым она играется.
        shown = {beat.chord for beat in beats if beat.chord}
        shapes = tuple(s for s in h.shapes() if s.name in shown)
    elif h is not None and roles & {"rhythm", "pad"}:
        shapes = h.shapes()
    return Part(
        player_id=player.id,
        title=_title(player, played),
        roles=tuple(played),
        difficulty=level,
        instrument_kind=instrument.kind,
        tuning_id=instrument.tuning.id,
        tone=tone,
        capo=instrument.capo,
        beats=tuple(beats),
        shapes=shapes,
        warnings=tuple(warnings),
    )


def chord_chart(ctx: Context) -> tuple[tuple[ChartChord, ...], ...]:
    bars: list[list[ChartChord]] = [[] for _ in range(ctx.tx.bars)]
    flats = ctx.key.flats
    for item in ctx.timeline("medium"):
        bar = item.start // ctx.bar_steps
        if bar < len(bars):
            bars[bar].append(ChartChord(item.start % ctx.bar_steps, item.chord.name(flats=flats)))
    return tuple(tuple(b) for b in bars)


def arrange(tx: Transcription, players: Sequence[PlayerSetup], transpose: int = 0) -> Arrangement:
    transpose = max(-12, min(12, transpose))
    ctx = Context(tx, transpose)
    parts = tuple(build_part(ctx, p) for p in players)
    hints: dict[str, tuple[CapoOption, ...]] = {}
    spans = tuple(ChordSpan(s.start, s.end, s.chord.transposed(transpose)) for s in tx.chords)
    for player in players:
        if player.kind != "bass" and set(player.roles) & {"rhythm", "pad", "original"}:
            bare = make_instrument(player.kind, player.tuning, 0)
            hints[player.id] = tuple(suggest_capo(spans, bare, player.difficulty)[:3])
    return Arrangement(
        tempo=tx.tempo,
        beats_per_bar=tx.beats_per_bar,
        bars=tx.bars,
        key=ctx.key,
        transpose=transpose,
        parts=parts,
        chart=chord_chart(ctx),
        capo_hints=hints,
        bar_seconds=tx.bar_seconds,
    )


def arrangement_to_dict(arr: Arrangement) -> dict[str, Any]:
    """Всё, что нужно интерфейсу, кроме самой нотной записи (она — в alphaTex)."""
    return {
        "tempo": round(arr.tempo, 2),
        "beats_per_bar": arr.beats_per_bar,
        "steps_per_beat": STEPS_PER_BEAT,
        "bars": arr.bars,
        "key": arr.key.name,
        "transpose": arr.transpose,
        "parts": [
            {
                "player_id": p.player_id,
                "title": p.title,
                "roles": list(p.roles),
                "difficulty": p.difficulty,
                "instrument": p.instrument_kind,
                "tuning": p.tuning_id,
                "capo": p.capo,
                "tone": p.tone,
                "notes": sum(len(b.notes) > 0 for b in p.beats),
                "shapes": [{"name": s.name, "frets": list(s.frets)} for s in p.shapes],
                "warnings": list(p.warnings),
            }
            for p in arr.parts
        ],
        "chart": [[{"offset": c.offset, "name": c.name} for c in bar] for bar in arr.chart],
        "bar_seconds": [round(t, 4) for t in arr.bar_seconds],
        "capo_hints": {
            pid: [{"capo": o.capo, "score": o.score, "barre_chords": o.barre_chords} for o in opts]
            for pid, opts in arr.capo_hints.items()
        },
    }
