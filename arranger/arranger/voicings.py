"""Аккордовые аппликатуры для любого строя и каподастра.

Сначала — библиотека форм, которыми аккорды берут гитаристы: открытые аккорды, баррэ от форм
E и A, формы на тонких струнах. Форма годится, если на этом инструменте (строй, каподастр) она
даёт тоны аккорда, — поэтому библиотека работает и «на полтона ниже», и с каподастром.
Чего в библиотеке нет (редкий строй, аккорд с басом), собирает перебор, но со строгой моделью
руки: баррэ только указательным пальцем и без открытых струн под ним, открытые струны — только
пока рука у порожка.

Аппликатуры для песни выбираются вместе: у каждого аккорда одна форма на всю партию, и формы
подобраны так, чтобы между ними было удобно переходить (assign_voicings).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from arranger.instruments import Instrument
from arranger.model import ChordSpan, Difficulty
from arranger.theory import Chord

Frets = tuple[int | None, ...]

SPAN: dict[Difficulty, int] = {"easy": 3, "medium": 4, "full": 4}
_MIN_STRINGS: dict[Difficulty, int] = {"easy": 3, "medium": 4, "full": 4}
_POSITION_W: dict[Difficulty, float] = {"easy": 0.45, "medium": 0.25, "full": 0.15}
_BARRE_W: dict[Difficulty, float] = {"easy": 4.0, "medium": 0.3, "full": 0.0}
# Формы на трёх-четырёх струнах звучат тоньше полного аккорда: новичку они в самый раз.
_SMALL_W: dict[Difficulty, float] = {"easy": 0.0, "medium": 0.6, "full": 0.9}
_MUTED_W: dict[Difficulty, float] = {"easy": 0.25, "medium": 0.45, "full": 0.9}
# Цена переезда руки на один лад при смене аккорда.
_SHIFT_W: dict[Difficulty, float] = {"easy": 0.6, "medium": 0.45, "full": 0.35}
_INVERSION = 1.2  # в басу не основной тон
_UNUSUAL = 1.0  # форма не из библиотеки: сыграть можно, но так аккорд обычно не берут
_TOP_WINDOW = 12
_OPEN_LIMIT = 4  # открытые струны звучат в аккорде, только пока рука у порожка
_CHANGE_SECONDS = 2.0  # смена аккорда раз в столько секунд — обычный темп, быстрее — труднее


@dataclass(frozen=True, slots=True)
class Voicing:
    frets: Frets  # по струнам, первая — тонкая; None — не играется
    cost: float
    barre: int | None
    fingers: Frets = ()  # палец на каждой струне: 1–4, 0 — открытая струна
    form: str = ""  # форма из библиотеки («E», «A», «C»…); пусто — собрана перебором

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


# ─── Библиотека форм ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Form:
    name: str
    frets: Frets  # у подвижной формы — от лада указательного пальца
    fingers: Frets
    base: float  # насколько форма трудна сама по себе
    movable: bool
    open_ok: bool  # подвижную форму можно взять у порожка: вместо баррэ — открытые струны


def _form(
    name: str, frets: str, fingers: str, base: float, movable: bool = True, open_ok: bool = True
) -> _Form:
    """Запись как в песенниках: от толстой струны к тонкой, «x» — струна не играется."""

    def parse(text: str) -> Frets:
        return tuple(None if ch == "x" else int(ch) for ch in reversed(text))

    return _Form(name, parse(frets), parse(fingers), base, movable, open_ok)


_FORMS: tuple[_Form, ...] = (
    # Открытые аккорды, которые не получаются из подвижных форм у порожка.
    _form("C", "x32010", "x32010", 1.3, movable=False),
    _form("C", "x32310", "x32410", 1.5, movable=False),  # C7
    _form("C", "x32000", "x32000", 1.2, movable=False),  # Cmaj7
    _form("G", "320003", "210003", 1.3, movable=False),
    _form("G", "320001", "320001", 1.4, movable=False),  # G7
    _form("G", "320002", "320001", 1.4, movable=False),  # Gmaj7
    _form("B7", "x21202", "x21304", 1.6, movable=False),
    _form("F", "xx3210", "xx3210", 1.4, movable=False),  # Fmaj7
    # Форма E: баррэ с основным тоном на шестой струне (у порожка — E, Em, E7…).
    _form("E", "022100", "134211", 2.0),
    _form("E", "022000", "134111", 2.0),  # минор
    _form("E", "020100", "131211", 2.1),  # 7
    _form("E", "020000", "131111", 2.1),  # m7
    _form("E", "021100", "142311", 2.3),  # maj7
    _form("E", "022200", "123411", 2.2),  # sus4
    # Форма A: баррэ с основным тоном на пятой струне (у порожка — A, Am, A7…).
    _form("A", "x02220", "x12341", 2.3),
    _form("A", "x02210", "x13421", 2.2),  # минор
    _form("A", "x02020", "x13141", 2.3),  # 7
    _form("A", "x02010", "x13121", 2.3),  # m7
    _form("A", "x02120", "x13241", 2.4),  # maj7
    _form("A", "x02200", "x13411", 2.3),  # sus2
    _form("A", "x02230", "x12341", 2.5),  # sus4
    _form("A", "x0121x", "x1243x", 2.8, open_ok=False),  # dim
    _form("A", "x2100x", "x3211x", 2.8, open_ok=False),  # aug
    # Форма D: четыре тонкие струны, основной тон на четвёртой (у порожка — D, Dm, D7…).
    _form("D", "xx0232", "xx1243", 3.0),
    _form("D", "xx0231", "xx1342", 3.0),  # минор
    _form("D", "xx0212", "xx1324", 3.0),  # 7
    _form("D", "xx0211", "xx1322", 3.0),  # m7
    _form("D", "xx0222", "xx1333", 3.0),  # maj7
    _form("D", "xx0230", "xx1341", 3.1),  # sus2
    _form("D", "xx0233", "xx1234", 3.1),  # sus4
    _form("D", "xx0131", "xx1243", 3.2, open_ok=False),  # dim
    _form("D", "xx2110", "xx4231", 3.0),  # aug
    # «Малое баррэ»: верх формы E на четырёх струнах — так новички берут F.
    _form("F", "xx2100", "xx3211", 2.2, open_ok=False),
    _form("F", "xx2000", "xx3111", 2.2, open_ok=False),  # минор
    # Верх формы A: в басу квинта — запасной вариант без большого баррэ (Bm как xx4432).
    _form("A4", "xx2220", "xx2341", 2.4, open_ok=False),
    _form("A4", "xx2210", "xx3421", 2.4, open_ok=False),  # минор
    # Пауэр-аккорды: основной тон и квинта на толстых струнах (с октавой — плотнее).
    _form("5", "022xxx", "134xxx", 1.0),
    _form("5", "x022xx", "x134xx", 1.0),
    _form("5", "xx023x", "xx134x", 1.1),
    _form("5", "02xxxx", "13xxxx", 1.2),
    _form("5", "x02xxx", "x13xxx", 1.2),
    _form("5", "xx02xx", "xx13xx", 1.3),
    _form("5", "000xxx", "111xxx", 0.9),  # в строях Drop — одним пальцем
)


def _open_fingers(form: _Form) -> Frets:
    """Пальцы формы у порожка: баррэ не нужно, остальные пальцы сдвигаются к указательному."""
    raw = [
        None if fret is None else (0 if fret == 0 else finger)
        for fret, finger in zip(form.frets, form.fingers, strict=True)
    ]
    used = [f for f in raw if f]
    shift = min(used) - 1 if used else 0
    return tuple(f - shift if f else f for f in raw)


def _barre(frets: Frets, fingers: Frets) -> int | None:
    """Лад баррэ: указательный палец лежит хотя бы на четырёх струнах.

    Прижать две-три тонкие струны одним пальцем (малое F, Dmaj7) — ещё не баррэ: это по силам
    и новичку.
    """
    index = [i for i, finger in enumerate(fingers) if finger == 1]
    if len(index) >= 2 and max(index) - min(index) >= 3:
        return frets[index[0]]
    return None


def _extend_down(frets: Frets, chord: Chord, instrument: Instrument) -> Frets:
    """Открытые толстые струны, если они удваивают бас аккорда (D в Drop D — все шесть струн)."""
    current = list(frets)
    best: Frets | None = None
    low = max(i for i, f in enumerate(frets) if f is not None)
    if (instrument.open_pitch(low + 1) + (frets[low] or 0)) % 12 != chord.bass_pc:
        return frets
    for i in range(low + 1, len(frets)):
        pc = instrument.open_pitch(i + 1) % 12
        if pc not in chord.pitch_classes:
            break
        current[i] = 0
        if pc == chord.bass_pc:
            best = tuple(current)
    return best or frets


def _library(chord: Chord, instrument: Instrument, level: Difficulty) -> dict[Frets, Voicing]:
    """Формы из библиотеки, которые на этом инструменте дают этот аккорд."""
    found: dict[Frets, Voicing] = {}
    if instrument.strings != 6:
        return found
    pcs = chord.pitch_classes
    power = chord.quality == "5"
    allow_inversion = level != "full" and not power
    for form in _FORMS:
        if (form.name == "5") != power:
            continue
        first = 0 if form.open_ok or not form.movable else 1
        for base in range(first, _TOP_WINDOW + 1 if form.movable else 1):
            frets: Frets = tuple(None if f is None else f + base for f in form.frets)
            fretted = [f for f in frets if f]
            if fretted and max(fretted) > instrument.frets:
                break
            if fretted and max(fretted) - min(fretted) >= SPAN[level]:
                continue
            fingers = form.fingers if base or not form.movable else _open_fingers(form)
            if not fretted or max(fretted) <= _OPEN_LIMIT:
                extended = _extend_down(frets, chord, instrument)
                fingers = tuple(
                    0 if old is None and new == 0 else finger
                    for old, new, finger in zip(frets, extended, fingers, strict=True)
                )
                frets = extended
            sounding = {
                (instrument.open_pitch(s) + f) % 12
                for s, f in enumerate(frets, start=1)
                if f is not None
            }
            if not (sounding <= pcs and chord.essential <= sounding):
                continue
            played = [i for i, f in enumerate(frets) if f is not None]
            bass = (instrument.open_pitch(max(played) + 1) + (frets[max(played)] or 0)) % 12
            if bass != chord.bass_pc and not allow_inversion:
                continue
            barre = _barre(frets, fingers)
            at_nut = not form.movable or base == 0
            if at_nut:
                fixed = not form.movable or power
                cost = form.base if fixed else 1.0 + 0.1 * len(fretted)
            else:
                cost = form.base + _POSITION_W[level] * (base - 1)
                if len(played) <= 4 and not power:
                    cost += _SMALL_W[level]
            if barre is not None and not power:
                cost += _BARRE_W[level]
            if bass != chord.bass_pc:
                cost += _INVERSION
            voicing = Voicing(frets, round(cost, 4), barre, fingers, form.name)
            if frets not in found or voicing.cost < found[frets].cost:
                found[frets] = voicing
    return found


# ─── Перебор для редких строев и аккордов ──────────────────────────────────


def _hand(frets: Frets) -> tuple[Frets, int | None] | None:
    """Пальцы для аппликатуры и лад баррэ; None — рукой так не взять.

    Указательный палец стоит на самом низком ладу. Если там несколько струн, он кладётся
    баррэ — от самой толстой из них до первой струны, и под ним не бывает ни открытых, ни
    заглушённых струн. Остальным нотам — по пальцу, пальцев четыре.
    """
    fretted = [f for f in frets if f]
    fingers: list[int | None] = [None if f is None else 0 for f in frets]
    if not fretted:
        return tuple(fingers), None
    if 0 in frets and max(fretted) > _OPEN_LIMIT:
        return None
    lowest = min(fretted)
    at_lowest = [i for i, f in enumerate(frets) if f == lowest]
    # Пальцы идут по порядку: ниже лад — меньше номер, на одном ладу — от толстой струны.
    rest = sorted(((f, -i) for i, f in enumerate(frets) if f and f > lowest))
    barre: int | None = None
    under = frets[: max(at_lowest) + 1]
    if len(at_lowest) >= 2 and all(f is not None and f >= lowest for f in under):
        for i in at_lowest:
            fingers[i] = 1
        barre = lowest if max(at_lowest) >= 3 else None
        used = 1
    else:
        rest = sorted([*((lowest, -i) for i in at_lowest), *rest])
        used = 0
    if used + len(rest) > 4:
        return None
    for finger, (_, negative) in enumerate(rest, start=used + 1):
        fingers[-negative] = finger
    return tuple(fingers), barre


def _cost(
    frets: Frets,
    barre: int | None,
    fingers: int,
    chord: Chord,
    instrument: Instrument,
    level: Difficulty,
) -> float:
    fretted = [f for f in frets if f]
    played = [i for i, f in enumerate(frets) if f is not None]
    cost = _UNUSUAL + 0.3 * fingers
    if fretted:
        cost += _POSITION_W[level] * max(0, min(fretted) - 1)
        cost += 0.35 * (max(fretted) - min(fretted))
    if barre is not None:
        covered = [i for i, f in enumerate(frets) if f == barre]
        width = max(covered) - min(covered) + 1
        cost += max(_BARRE_W[level], 0.9) * (1 + 0.25 * (width - 2))
    cost += _MUTED_W[level] * (instrument.strings - len(played))
    if min(played) > 0 and chord.quality != "5":
        cost += 1.0  # заглушена первая струна: при бое её придётся глушить пальцем
    cost -= 0.12 * sum(1 for f in frets if f == 0)
    bass_string = max(played) + 1
    if instrument.pitch_at(bass_string, frets[max(played)] or 0) % 12 != chord.bass_pc:
        cost += _INVERSION
    return cost


def _generated(chord: Chord, instrument: Instrument, level: Difficulty) -> dict[Frets, Voicing]:
    """Перебор окон по 3–4 лада: соседние струны подряд, глушить можно только крайние."""
    n = instrument.strings
    pcs = chord.pitch_classes
    span = SPAN[level]
    power = chord.quality == "5"
    min_strings = 2 if power else min(_MIN_STRINGS[level], n)
    top_window = min(_TOP_WINDOW, instrument.frets - span + 1)
    # Пауэр-аккорд без основного тона внизу — уже не пауэр-аккорд (квинта «висит»).
    allow_inversion = level != "full" and not power
    found: dict[Frets, Voicing] = {}

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
                        frets: Frets = tuple(
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
                        hand = _hand(frets)
                        if hand is None:
                            continue
                        fingers, barre = hand
                        used = len({f for f in fingers if f})
                        cost = _cost(frets, barre, used, chord, instrument, level)
                        found[frets] = Voicing(frets, round(cost, 4), barre, fingers)
    return found


@lru_cache(maxsize=8192)
def chord_voicings(
    chord: Chord, instrument: Instrument, level: Difficulty, limit: int = 6
) -> tuple[Voicing, ...]:
    """Лучшие аппликатуры аккорда — от самой удобной."""
    found = _library(chord, instrument, level) or _generated(chord, instrument, level)
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

    Открытые струны — только у порожка: открытая струна под аккордом на седьмом ладу
    звучит и выглядит в табах странно, так почти не играют.
    """
    for candidate in (chord, chord.simplified(), Chord(chord.root, "5")):
        every = tuple(
            v
            for v in chord_voicings(candidate, instrument, level, limit=100_000)
            if (top := max(f for f in v.frets if f is not None)) <= max_fret
            and (top <= _OPEN_LIMIT or 0 not in v.frets)
        )
        if every:
            break
    best: dict[int, list[Voicing]] = {}
    for voicing in every:  # уже по возрастанию стоимости
        bucket = best.setdefault(voicing.position, [])
        if len(bucket) < 2:
            bucket.append(voicing)
    return tuple(v for position in sorted(best) for v in best[position])


# ─── Смены аккордов ────────────────────────────────────────────────────────


def _hand_fret(voicing: Voicing) -> int:
    """Где стоит указательный палец; открытые аккорды берутся в первой позиции."""
    return max(1, voicing.position)


def transition_cost(a: Voicing, b: Voicing, level: Difficulty) -> float:
    """Насколько трудно перейти с аппликатуры на аппликатуру.

    Дорого — ехать рукой по грифу и переставлять пальцы. Дёшево — когда пальцы остаются на
    своих местах (общие ноты: C → Am) или форма целиком сдвигается вдоль грифа (F → G баррэ).
    """
    if a.frets == b.frets:
        return 0.0
    shift = abs(_hand_fret(a) - _hand_fret(b))
    if a.form and a.form == b.form and a.fingers == b.fingers and a.barre and b.barre:
        return 0.5 * _SHIFT_W[level] * shift  # та же форма: рука едет, пальцы не перестраиваются
    kept = {
        finger
        for fa, fb, finger, other in zip(a.frets, b.frets, a.fingers, b.fingers, strict=False)
        if fa and fa == fb and finger and finger == other
    }
    placed = len({f for f in b.fingers if f} - kept)
    return max(0.05, _SHIFT_W[level] * shift + 0.15 * placed - 0.2 * len(kept))


def change_weight(seconds: float) -> float:
    """Вес смены аккорда: чем меньше времени на аккорд, тем важнее удобный переход."""
    return min(3.0, max(0.5, _CHANGE_SECONDS / max(seconds, 0.1)))


def assign_voicings(
    options: Mapping[Chord, Sequence[Voicing]],
    own: Mapping[Chord, Sequence[float]],
    changes: Mapping[tuple[Chord, Chord], float],
    level: Difficulty,
) -> dict[Chord, Voicing]:
    """Одна аппликатура на аккорд — так, чтобы всю песню было удобно играть.

    own — цена каждого варианта (уже за все появления аккорда), changes — вес каждой смены
    «аккорд → аккорд» (сколько раз и как быстро). Начинаем с самых удобных форм и меняем по
    одному аккорду, пока общая цена падает: аккордов в песне немного, сходится за пару кругов.
    """
    chords = [c for c in options if options[c]]
    pick = {c: own[c].index(min(own[c])) for c in chords}
    links: dict[Chord, list[tuple[Chord, float, bool]]] = {c: [] for c in chords}
    for (a, b), weight in changes.items():
        if a in links and b in links and a != b:
            links[a].append((b, weight, True))
            links[b].append((a, weight, False))

    def price(chord: Chord, i: int) -> float:
        mine = options[chord][i]
        total = own[chord][i]
        for other, weight, outgoing in links[chord]:
            theirs = options[other][pick[other]]
            pair = (mine, theirs) if outgoing else (theirs, mine)
            total += weight * transition_cost(*pair, level)
        return total

    for _ in range(12):
        changed = False
        for chord in chords:
            prices = [price(chord, i) for i in range(len(options[chord]))]
            best = prices.index(min(prices))
            if prices[best] < prices[pick[chord]] - 1e-9:
                pick[chord] = best
                changed = True
        if not changed:
            break
    return {c: options[c][pick[c]] for c in chords}


def chord_changes(
    chords: Sequence[Chord], seconds: Sequence[float] | None = None
) -> dict[tuple[Chord, Chord], float]:
    """Смены аккордов в последовательности с весами: частые и быстрые — тяжелее."""
    changes: dict[tuple[Chord, Chord], float] = {}
    for i in range(1, len(chords)):
        if chords[i] == chords[i - 1]:
            continue
        weight = 1.0 if seconds is None else change_weight(min(seconds[i - 1], seconds[i]))
        pair = (chords[i - 1], chords[i])
        changes[pair] = changes.get(pair, 0.0) + weight
    return changes


def choose_voicings(
    chords: Sequence[Chord],
    instrument: Instrument,
    level: Difficulty,
    seconds: Sequence[float] | None = None,
    smooth: bool = True,
    pins: Mapping[Chord, Frets] | None = None,
) -> list[Voicing | None]:
    """Аппликатуры для последовательности аккордов: одна форма на аккорд, удобные смены.

    seconds — сколько звучит каждый аккорд (в быстрых сменах переезды руки дороже).
    smooth=False — у каждого аккорда просто самая привычная форма, без оглядки на соседей.
    pins — аппликатуры, выбранные вручную: лады по струнам для аккорда.
    """
    count: dict[Chord, int] = {}
    for chord in chords:
        count[chord] = count.get(chord, 0) + 1
    options: dict[Chord, Sequence[Voicing]] = {}
    for chord in count:
        found = playable_voicings(chord, instrument, level)
        pinned = pinned_voicing(chord, instrument, level, (pins or {}).get(chord))
        options[chord] = (pinned,) if pinned else found
    own = {c: [v.cost * count[c] for v in options[c]] for c in options}
    changes = chord_changes(chords, seconds) if smooth else {}
    chosen = assign_voicings(options, own, changes, level)
    return [chosen.get(c) for c in chords]


def pinned_voicing(
    chord: Chord, instrument: Instrument, level: Difficulty, frets: Frets | None
) -> Voicing | None:
    """Аппликатура, выбранная вручную, если она действительно даёт этот аккорд."""
    if frets is None:
        return None
    for candidate in (chord, chord.simplified(), Chord(chord.root, "5")):
        for voicing in chord_voicings(candidate, instrument, level, limit=100_000):
            if voicing.frets == frets:
                return voicing
    return None


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
