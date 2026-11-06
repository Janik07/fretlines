"""Разбор песни целиком: звук → стемы → доли → аккорды → мелодия и бас → analysis.json.

Этапы и их «вес» в общем прогрессе видны в интерфейсе (SPEC §2.5, «Обработка»).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from arranger import Transcription, arrange, preset_players
from fretlines_worker.audio import SAMPLE_RATE, decode, encode_mp3, peaks, to_mono
from fretlines_worker.errors import AnalysisError

log = logging.getLogger("fretlines.pipeline")

Report = Callable[[str, float], None]
OnMeta = Callable[[dict[str, object]], None]

_WEIGHTS = {
    "download": 0.12,
    "decode": 0.03,
    "stems": 0.5,
    "rhythm": 0.07,
    "harmony": 0.06,
    "melody": 0.1,
    "bass": 0.05,
    "arrange": 0.02,
    "save": 0.05,
}


def stage_weights(has_url: bool) -> dict[str, float]:
    weights = {k: v for k, v in _WEIGHTS.items() if has_url or k != "download"}
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def configure_models(models_dir: Path | None = None) -> None:
    """Модели (Demucs, Beat This!) скачиваются один раз и живут в папке проекта .models/."""
    root = (models_dir or Path.cwd() / ".models").resolve()
    os.environ.setdefault("HF_HOME", str(root / "hf"))
    os.environ.setdefault("TORCH_HOME", str(root / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def pick_device(preference: str) -> str:
    import torch

    if preference == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _source(folder: Path) -> Path:
    files = [p for p in folder.glob("source.*") if p.is_file() and p.stat().st_size > 0]
    if not files:
        raise AnalysisError("no_source", "Файл песни потерялся. Загрузи его ещё раз.")
    return max(files, key=lambda p: p.stat().st_size)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def run_analysis(
    folder: Path,
    *,
    source_url: str | None,
    device: str,
    report: Report,
    on_meta: OnMeta,
    models_dir: Path | None = None,
) -> dict[str, Any]:
    configure_models(models_dir)
    timings: dict[str, float] = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        timings[name] = round(now - clock, 2)
        clock = now

    if source_url:
        from fretlines_worker.download import download_audio

        report("download", 0.0)
        got = download_audio(source_url, folder, lambda f: report("download", f))
        on_meta({"title": got.title, "artist": got.artist})
        lap("download")

    report("decode", 0.0)
    audio = decode(_source(folder))
    duration = audio.shape[1] / SAMPLE_RATE
    _write_json(folder / "peaks.json", {"peaks": peaks(audio), "duration": round(duration, 2)})
    on_meta({"duration": round(duration, 2)})
    lap("decode")

    used = pick_device(device)
    on_meta({"device": used})
    log.info("разбор %s: %.0f с звука, устройство %s", folder.name, duration, used)

    from fretlines_worker.separation import separate

    report("stems", 0.0)
    stems = separate(audio, used, lambda f: report("stems", f))
    lap("stems")

    from fretlines_worker.grid import BeatGrid
    from fretlines_worker.rhythm import drum_accents, track_beats

    report("rhythm", 0.0)
    beats, downbeats = track_beats(to_mono(audio), used)
    grid = BeatGrid.build(beats, downbeats, duration)
    accents = drum_accents(to_mono(stems["drums"]), grid)
    on_meta({"tempo": round(grid.tempo, 1)})
    lap("rhythm")

    import librosa

    from fretlines_worker.harmony import ANALYSIS_SR, analyze

    report("harmony", 0.0)
    harmonic = to_mono(stems["guitar"] + stems["piano"] + stems["other"])
    harmonic_22 = librosa.resample(harmonic, orig_sr=SAMPLE_RATE, target_sr=ANALYSIS_SR)
    bass_22 = librosa.resample(to_mono(stems["bass"]), orig_sr=SAMPLE_RATE, target_sr=ANALYSIS_SR)
    harmony = analyze(harmonic_22.astype(np.float32), bass_22.astype(np.float32), grid)
    if not harmony.chords:
        raise AnalysisError(
            "no_music", "В записи не нашлось гармонии — проверь, что это песня, а не тишина."
        )
    on_meta({"key": harmony.key.name})
    lap("harmony")

    from fretlines_worker.pitch import BASS, MELODY, transcribe

    report("melody", 0.0)
    melody = transcribe(to_mono(stems["vocals"]), grid, MELODY, used)
    lap("melody")
    report("bass", 0.0)
    bass = transcribe(to_mono(stems["bass"]), grid, BASS, used)
    lap("bass")

    transcription = Transcription(
        tempo=round(grid.tempo, 2),
        beats_per_bar=grid.beats_per_bar,
        bars=grid.bars,
        key=harmony.key,
        chords=harmony.chords,
        melody=melody,
        bass=bass,
        accents=accents,
    )
    report("arrange", 0.0)
    arrange(transcription, preset_players("trio"))  # партии собираются — значит, разбор годный
    lap("arrange")

    report("save", 0.0)
    out = folder / "stems"
    out.mkdir(exist_ok=True)
    names = ["mix", *stems]
    for i, name in enumerate(names):
        encode_mp3(audio if name == "mix" else stems[name], out / f"{name}.mp3", bitrate="128k")
        report("save", (i + 1) / len(names))

    warnings: list[str] = []
    if len(melody) < 8:
        warnings.append(
            "Не удалось выделить вокал — мелодия почти пустая. Попробуй файл лучшего качества."
        )
    if len(bass) < 8:
        warnings.append("Бас еле слышно — басовая партия собрана по корням аккордов.")
    analysis: dict[str, Any] = {
        "version": 1,
        "duration": round(duration, 3),
        "sample_rate": SAMPLE_RATE,
        "beats": [round(float(t), 4) for t in grid.times],
        "bar_times": grid.bar_times(),
        "key": harmony.key.name,
        "key_confidence": harmony.key_confidence,
        "transcription": transcription.to_dict(),
        "stems": names,
        "device": used,
        "warnings": warnings,
        "timings": timings,
    }
    lap("save")
    _write_json(folder / "analysis.json", analysis)
    return analysis
