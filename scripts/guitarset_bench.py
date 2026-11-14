"""Сверка аппликатур с живыми гитаристами на наборе GuitarSet.

GuitarSet (Xi et al., ISMIR 2018, лицензия CC BY 4.0) — 360 записей, где для каждой ноты
размечены струна и лад. Берём аккомпанементы (comp): для каждого аккорда смотрим, где на грифе
его взял гитарист, и сравниваем с тем, что выбирает Fretlines для той же последовательности.

Разметку (39 МБ) скрипт ищет в .bench/guitarset/annotation; скачать:
https://zenodo.org/records/3371780/files/annotation.zip

Запуск: python scripts/guitarset_bench.py [--level full] [--json out.json]
"""

from __future__ import annotations

import argparse
import inspect
import json
import statistics
from collections import Counter
from pathlib import Path

from arranger.instruments import make_instrument
from arranger.theory import Chord, parse_pc
from arranger.voicings import choose_voicings

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / ".bench" / "guitarset" / "annotation"
OPEN = (40, 45, 50, 55, 59, 64)  # струны GuitarSet: от шестой (0) к первой (5)
QUALITIES = {"maj": "maj", "min": "min", "7": "7", "maj7": "maj7", "min7": "min7", "dim": "dim"}


def parse_label(label: str) -> Chord | None:
    """«D#:maj» → аккорд; чего нет в словаре Fretlines (hdim7 и т. п.), пропускаем."""
    root, _, quality = label.partition(":")
    quality = quality.split("/")[0].split("(")[0]
    if not root or root == "N" or quality not in QUALITIES:
        return None
    return Chord(parse_pc(root[0], root[1:]), QUALITIES[quality])  # type: ignore[arg-type]


def human_shape(notes: list[list[dict[str, float]]], start: float, end: float) -> dict[int, int]:
    """Лад на каждой струне, который гитарист чаще всего брал за время аккорда."""
    shape: dict[int, int] = {}
    for string, items in enumerate(notes):
        frets = Counter(round(n["value"]) - OPEN[string] for n in items if start <= n["time"] < end)
        frets = Counter({f: c for f, c in frets.items() if f >= 0})
        if frets:
            shape[6 - string] = frets.most_common(1)[0][0]  # как в Fretlines: 1 — тонкая
    return shape


def position(frets: list[int]) -> int | None:
    fretted = [f for f in frets if f > 0]
    return min(fretted) if fretted else (1 if frets else None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="full", choices=["easy", "medium", "full"])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    files = sorted(ANNOTATIONS.glob("*_comp.jams"))
    if not files:
        raise SystemExit(f"Нет разметки GuitarSet в {ANNOTATIONS}")
    guitar = make_instrument("acoustic", "standard")
    timed = "seconds" in inspect.signature(choose_voicings).parameters

    distance: list[int] = []  # насколько наша позиция далека от позиции гитариста, в ладах
    agree: list[float] = []  # доля струн гитариста, где наш лад тот же
    ours_shift: list[int] = []
    human_shift: list[int] = []
    high_open = barre_open = total = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        notes = [a["data"] for a in data["annotations"] if a["namespace"] == "note_midi"]
        spans = next(a["data"] for a in data["annotations"] if a["namespace"] == "chord")
        chords, humans, seconds = [], [], []
        for span in spans:
            chord = parse_label(span["value"])
            shape = human_shape(notes, span["time"], span["time"] + span["duration"])
            if chord is None or len(shape) < 2:
                continue
            chords.append(chord)
            humans.append(shape)
            seconds.append(span["duration"])
        if not chords:
            continue
        if timed:
            chosen = choose_voicings(chords, guitar, args.level, seconds=seconds)
        else:
            chosen = choose_voicings(chords, guitar, args.level)
        previous: tuple[int | None, int | None] = (None, None)
        for voicing, human in zip(chosen, humans, strict=True):
            if voicing is None:
                continue
            total += 1
            frets = [f for f in voicing.frets if f is not None]
            ours, theirs = position(frets), position(list(human.values()))
            assert ours is not None
            assert theirs is not None
            distance.append(abs(ours - theirs))
            same = sum(voicing.frets[s - 1] == f for s, f in human.items())
            agree.append(same / len(human))
            high_open += 0 in frets and max(frets) > 4
            lowest = min((f for f in frets if f > 0), default=0)
            at_lowest = [i for i, f in enumerate(voicing.frets) if f == lowest and f]
            if len([f for f in frets if f > 0]) > 4 and at_lowest:
                barre_open += any(f == 0 for f in voicing.frets[: max(at_lowest)])
            if previous[0] is not None and previous[1] is not None:
                ours_shift.append(abs(ours - previous[0]))
                human_shift.append(abs(theirs - previous[1]))
            previous = (ours, theirs)

    result = {
        "level": args.level,
        "files": len(files),
        "chords": total,
        "position_distance_mean": round(statistics.mean(distance), 2),
        "position_within_2_frets": round(sum(d <= 2 for d in distance) / total, 3),
        "string_agreement_mean": round(statistics.mean(agree), 3),
        "shift_per_change_ours": round(statistics.mean(ours_shift), 2),
        "shift_per_change_human": round(statistics.mean(human_shift), 2),
        "open_string_above_fret_4": high_open,
        "barre_over_open_string": barre_open,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
