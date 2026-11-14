"""Точность распознавания нот гитары на наборе GuitarSet.

Запускает на записях GuitarSet (микрофон, моно) то же распознавание нот, что и разбор песни
(Basic Pitch + чистка), и сверяет с разметкой: нота найдена, если высота та же, а начало
отличается не больше чем на 50 мс. Считает точность (сколько найденных нот настоящие), полноту
(сколько настоящих найдено) и F1.

Данные скрипт ищет в .bench/guitarset: annotation/*.jams и audio_mono-mic/*.wav
(https://zenodo.org/records/3371780, CC BY 4.0).

Запуск: python scripts/guitarset_notes_bench.py [--limit 60] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np

from fretlines_worker.guitar import listen
from fretlines_worker.notes import SR

ROOT = Path(__file__).resolve().parent.parent / ".bench" / "guitarset"
TOLERANCE = 0.05  # секунды


def reference(path: Path) -> list[tuple[float, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    notes = [
        (float(n["time"]), round(n["value"]))
        for a in data["annotations"]
        if a["namespace"] == "note_midi"
        for n in a["data"]
    ]
    return sorted(notes)


def match(found: list[tuple[float, int]], truth: list[tuple[float, int]]) -> int:
    """Сколько настоящих нот нашлось: каждая найденная нота засчитывается один раз."""
    used = [False] * len(found)
    hits = 0
    for time, pitch in truth:
        best = None
        for i, (t, p) in enumerate(found):
            if used[i] or p != pitch or abs(t - time) > TOLERANCE:
                continue
            if best is None or abs(t - time) < abs(found[best][0] - time):
                best = i
        if best is not None:
            used[best] = True
            hits += 1
    return hits


def score(hits: int, found: int, truth: int) -> dict[str, float]:
    precision = hits / found if found else 0.0
    recall = hits / truth if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="сколько записей взять (0 — все)")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    files = sorted((ROOT / "audio_mono-mic").glob("*.wav"))
    if args.limit:
        step = max(1, len(files) // args.limit)
        files = files[::step][: args.limit]
    if not files:
        raise SystemExit(f"Нет записей GuitarSet в {ROOT / 'audio_mono-mic'}")

    totals = {"comp": [0, 0, 0], "solo": [0, 0, 0]}  # найдено верно, найдено всего, настоящих
    for index, wav in enumerate(files, start=1):
        kind = "solo" if "_solo" in wav.stem else "comp"
        truth = reference(ROOT / "annotation" / (wav.stem.removesuffix("_mic") + ".jams"))
        audio, _ = librosa.load(wav, sr=SR, mono=True)
        found = sorted((e.start, e.pitch) for e in listen(audio.astype(np.float32)))
        hits = match(found, truth)
        for i, value in enumerate((hits, len(found), len(truth))):
            totals[kind][i] += value
        if index % 20 == 0:
            print(f"{index}/{len(files)}", flush=True)

    both = [a + b for a, b in zip(totals["comp"], totals["solo"], strict=True)]
    result = {
        "files": len(files),
        "tolerance_ms": int(TOLERANCE * 1000),
        "accompaniment": score(*totals["comp"]),
        "solo": score(*totals["solo"]),
        "all": score(*both),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
