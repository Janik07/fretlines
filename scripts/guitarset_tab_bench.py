"""Табы «как в записи» против GuitarSet: те же ли струна и лад, что у гитариста.

В партию «как в записи» подаются ноты из разметки (как если бы распознавание было идеальным)
и аккорды из разметки. Для каждой ноты гитариста ищем ту же ноту в наших табах и смотрим,
на той же ли она струне и ладу; отдельно считаем ноты табов, которых гитарист не играл.
Так меряется сама раскладка по грифу, без ошибок слуха.

Данные (CC BY 4.0, в репозиторий не входят) — см. docs/benchmarks.md:
    .bench/guitarset/annotation/*.jams

Запуск:
    python scripts/guitarset_tab_bench.py --level full
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from guitarset_bench import ANNOTATIONS, OPEN, parse_label

from arranger import arrange
from arranger.arrange import PlayerSetup
from arranger.model import STEPS_PER_BEAT, ChordSpan, Note, Transcription
from arranger.theory import Key

TabNote = tuple[float, int, int, int]  # время в секундах, высота, струна (1 — тонкая), лад


def load(path: Path) -> tuple[Transcription, list[TabNote], float, float]:
    """Разметка записи → вход аранжировщика, ноты гитариста, длина доли и начало первой доли."""
    data = json.loads(path.read_text(encoding="utf-8"))
    tempo = float(path.stem.split("_")[1].split("-")[1])
    beat = 60.0 / tempo
    strings = [a["data"] for a in data["annotations"] if a["namespace"] == "note_midi"]
    truth = sorted(
        (float(n["time"]), round(n["value"]), 6 - s, round(n["value"]) - OPEN[s])
        for s, items in enumerate(strings)
        for n in items
        if round(n["value"]) >= OPEN[s]
    )
    beats = [a["data"] for a in data["annotations"] if a["namespace"] == "beat_position"]
    offset = float(beats[0][0]["time"]) if beats and beats[0] else 0.0
    bars = max(1, int((float(data["file_metadata"]["duration"]) - offset) / beat / 4) + 1)
    chords = []
    for span in next(a["data"] for a in data["annotations"] if a["namespace"] == "chord"):
        chord = parse_label(span["value"])
        start = round(max(0.0, (span["time"] - offset) / beat) * 2) / 2
        end = round(min(bars * 4.0, (span["time"] + span["duration"] - offset) / beat) * 2) / 2
        if chord is not None and end > start:
            chords.append(ChordSpan(start, end, chord))
    tx = Transcription(
        tempo=tempo,
        beats_per_bar=4,
        bars=bars,
        key=Key(0, "major"),
        chords=tuple(chords),
        guitar=tuple(Note((t - offset) / beat, 0.5, p) for t, p, _, _ in truth if t >= offset),
        guitar_source="guitar",
        guitar_tone="clean",
    )
    return tx, truth, beat, offset


def compare(found: list[TabNote], truth: list[TabNote], tolerance: float) -> tuple[int, int]:
    """Сколько нот гитариста есть в табах и сколько из них на той же струне и ладу."""
    used = [False] * len(found)
    hits = same = 0
    for time, pitch, string, fret in truth:
        best = None
        for i, (t, p, _, _) in enumerate(found):
            if used[i] or p != pitch or abs(t - time) > tolerance:
                continue
            if best is None or abs(t - time) < abs(found[best][0] - time):
                best = i
        if best is not None:
            used[best] = True
            hits += 1
            same += found[best][2:] == (string, fret)
    return hits, same


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="full", choices=["easy", "medium", "full"])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if not any(ANNOTATIONS.glob("*.jams")):
        raise SystemExit(f"Нет разметки GuitarSet в {ANNOTATIONS}")
    player = PlayerSetup(
        "p", "", kind="electric", roles=("original",), difficulty=args.level, tone="clean"
    )
    report = {}
    for kind, title in (("solo", "Соло"), ("comp", "Аккомпанемент")):
        notes = hits = same = ours = 0
        for path in sorted(ANNOTATIONS.glob(f"*_{kind}.jams")):
            tx, truth, beat, offset = load(path)
            part = arrange(tx, [player]).parts[0]
            found = sorted(
                (offset + b.start / STEPS_PER_BEAT * beat, n.pitch, n.string, n.fret)
                for b in part.beats
                for n in b.notes
            )
            # Ноты встают на сетку шестнадцатых: допуск — полшага сетки и немного сверху.
            found_hits, found_same = compare(found, truth, max(0.06, beat / 8 + 0.035))
            notes += len(truth)
            ours += len(found)
            hits += found_hits
            same += found_same
        report[kind] = {
            "notes": notes,
            "kept": round(hits / max(notes, 1), 3),
            "extra": round(1 - hits / max(ours, 1), 3),
            "same_position": round(same / max(hits, 1), 3),
        }
        print(
            f"{title}: нот гитариста {notes}, дошло до табов {hits / max(notes, 1):.1%}, "
            f"из них на той же струне и ладу {same / max(hits, 1):.1%}; "
            f"нот в табах, которых гитарист не играл, {1 - hits / max(ours, 1):.1%}"
        )
    if args.json:
        args.json.write_text(json.dumps({"level": args.level, **report}, indent=2))


if __name__ == "__main__":
    main()
