"""Разбор песни целиком: звук → стемы → доли → аккорды → гитара, мелодия, бас → текст.

Результат — analysis.json (транскрипция) и lyrics.json (слова с таймингом).
Этапы и их «вес» в общем прогрессе видны в интерфейсе (SPEC §2.5, «Обработка»).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from arranger import Transcription, arrange, preset_players
from fretlines_worker.audio import SAMPLE_RATE, decode, encode_flac, encode_mp3, peaks, to_mono
from fretlines_worker.errors import AnalysisError

log = logging.getLogger("fretlines.pipeline")

Report = Callable[[str, float], None]
OnMeta = Callable[[dict[str, object]], None]

ANALYSIS_VERSION = 2  # 2 — темп по тактам, гитара из записи, текст песни

_WEIGHTS = {
    "download": 0.1,
    "decode": 0.03,
    "stems": 0.45,
    "rhythm": 0.06,
    "harmony": 0.06,
    "guitar": 0.03,
    "melody": 0.08,
    "bass": 0.04,
    "lyrics": 0.1,
    "arrange": 0.02,
    "save": 0.03,
}


@dataclass(frozen=True)
class LyricsOptions:
    """online — LRCLIB + Whisper; local — только Whisper (в сеть ничего); off — без текста."""

    mode: Literal["online", "local", "off"] = "online"
    model: str = "small"


def stage_weights(has_url: bool, lyrics: bool = True) -> dict[str, float]:
    weights = {
        k: v
        for k, v in _WEIGHTS.items()
        if (has_url or k != "download") and (lyrics or k != "lyrics")
    }
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def configure_models(models_dir: Path | None = None) -> None:
    """Модели (Demucs, Beat This!, Whisper…) скачиваются один раз и живут в папке .models/."""
    root = (models_dir or Path.cwd() / ".models").resolve()
    os.environ.setdefault("FRETLINES_MODELS_DIR", str(root))
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


def _lyrics(
    vocals: Any,  # noqa: ANN401 — стерео-дорожка numpy
    *,
    title: str | None,
    artist: str | None,
    duration: float,
    options: LyricsOptions,
    device: str,
) -> dict[str, Any] | None:
    """Текст песни. Ошибки здесь не роняют разбор: без текста партии всё равно нужны."""
    import librosa

    from fretlines_worker import lyrics
    from fretlines_worker.notes import models_root

    found = None
    if options.mode == "online" and title:
        found = lyrics.fetch_lrclib(title, artist, duration)
    hint = str((found or {}).get("plainLyrics") or (found or {}).get("syncedLyrics") or title or "")
    language = "ru" if lyrics.has_cyrillic(hint) else None
    mono = librosa.resample(to_mono(vocals), orig_sr=SAMPLE_RATE, target_sr=lyrics.WHISPER_SR)
    heard, language = lyrics.hear_words(
        mono.astype(np.float32),
        model_name=options.model,
        device=device,
        language=language,
        download_root=models_root() / "whisper",
    )
    result = lyrics.build(found=found, heard=heard, language=language, duration=duration)
    return result.to_dict() if result.lines else None


def run_analysis(
    folder: Path,
    *,
    source_url: str | None,
    device: str,
    report: Report,
    on_meta: OnMeta,
    models_dir: Path | None = None,
    title: str | None = None,
    artist: str | None = None,
    lyrics: LyricsOptions | None = None,
    separation: Literal["standard", "max"] = "standard",
) -> dict[str, Any]:
    configure_models(models_dir)
    lyrics = lyrics or LyricsOptions(mode="off")
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
        title, artist = got.title or title, got.artist or artist
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

    from fretlines_worker.notes import models_root
    from fretlines_worker.separation import separate

    report("stems", 0.0)
    stems, instrumental, separated_by = separate(
        audio,
        used,
        lambda f: report("stems", f),
        quality=separation,
        workdir=folder / "_separation",
        models_dir=models_root() / "separator",
    )
    lap("stems")

    from fretlines_worker.grid import BeatGrid
    from fretlines_worker.rhythm import drum_accents, track_beats

    report("rhythm", 0.0)
    beats, downbeats = track_beats(to_mono(audio), used)
    grid = BeatGrid.build(beats, downbeats, duration)
    on_meta({"tempo": round(grid.tempo, 1)})
    lap("rhythm")

    import librosa

    from fretlines_worker.harmony import ANALYSIS_SR, analyze
    from fretlines_worker.notes import posteriors

    report("harmony", 0.0)
    harmonic = to_mono(stems["guitar"] + stems["piano"] + stems["other"])
    harmonic_22 = librosa.resample(harmonic, orig_sr=SAMPLE_RATE, target_sr=ANALYSIS_SR)
    bass_22 = librosa.resample(to_mono(stems["bass"]), orig_sr=SAMPLE_RATE, target_sr=ANALYSIS_SR)
    try:
        note_map = posteriors(harmonic_22.astype(np.float32))
    except Exception:  # без модели нот аккорды всё равно найдутся по CQT
        log.exception("Basic Pitch не сработал — аккорды только по CQT")
        note_map = None
    report("harmony", 0.5)
    harmony = analyze(harmonic_22.astype(np.float32), bass_22.astype(np.float32), grid, note_map)
    if not harmony.chords:
        raise AnalysisError(
            "no_music", "В записи не нашлось гармонии — проверь, что это песня, а не тишина."
        )
    on_meta({"key": harmony.key.name})
    lap("harmony")

    from fretlines_worker import guitar

    report("guitar", 0.0)
    source = guitar.pick_source(stems)
    guitar_notes: tuple[Any, ...] = ()
    if source is not None:
        try:
            guitar_notes = guitar.transcribe(source[1], grid)
        except Exception:
            log.exception("ноты гитары не распознались")
    # Какая гитара в записи (акустика, чистая, перегруз) — для звука «как в записи».
    heard_tone = ""
    if source is not None and source[0] == "guitar":
        try:
            from fretlines_worker import timbre

            heard_tone = timbre.guitar_tone(timbre.tag(source[1], models_root()))
        except Exception:
            log.exception("тембр гитары не определился")
    # Схема боя: по гитаре, если она есть в записи, иначе — по барабанам.
    accents: tuple[float, ...] = ()
    if source is not None and source[0] == "guitar":
        accents = drum_accents(source[1], grid, active_only=True)
    accents = accents or drum_accents(to_mono(stems["drums"]), grid)
    lap("guitar")

    from fretlines_worker.pitch import BASS, MELODY, transcribe

    report("melody", 0.0)
    melody = transcribe(to_mono(stems["vocals"]), grid, MELODY, used)
    lap("melody")
    report("bass", 0.0)
    bass = transcribe(to_mono(stems["bass"]), grid, BASS, used)
    lap("bass")

    words: dict[str, Any] | None = None
    if lyrics.mode != "off" and len(melody) >= 8:
        report("lyrics", 0.0)
        try:
            words = _lyrics(
                stems["vocals"],
                title=title,
                artist=artist,
                duration=duration,
                options=lyrics,
                device=used,
            )
        except Exception:
            log.exception("текст песни не распознался")
        lap("lyrics")

    transcription = Transcription(
        tempo=round(grid.tempo, 2),
        beats_per_bar=grid.beats_per_bar,
        bars=grid.bars,
        key=harmony.key,
        chords=harmony.chords,
        melody=melody,
        bass=bass,
        accents=accents,
        bar_seconds=grid.bar_seconds(),
        guitar=guitar_notes,
        guitar_source=source[0] if source is not None and guitar_notes else "",
        guitar_tone=heard_tone,
    )
    report("arrange", 0.0)
    arrange(transcription, preset_players("trio"))  # партии собираются — значит, разбор годный
    lap("arrange")

    report("save", 0.0)
    out = folder / "stems"
    out.mkdir(exist_ok=True)
    # mp3 — чтобы слушать в плеере, FLAC 24 бита — чтобы скачать дорожки без потерь.
    tracks: dict[str, Any] = {"mix": audio, **stems, "instrumental": instrumental}
    names = list(tracks)
    lossless = out / "flac"
    lossless.mkdir(exist_ok=True)
    for i, name in enumerate(names):
        encode_mp3(tracks[name], out / f"{name}.mp3", bitrate="192k")
        if name != "mix":  # оригинал и так лежит как есть (source.*)
            encode_flac(tracks[name], lossless / f"{name}.flac")
        report("save", (i + 1) / len(names))

    warnings: list[str] = []
    if len(melody) < 8:
        warnings.append(
            "Не удалось выделить вокал — мелодия почти пустая. Попробуй файл лучшего качества."
        )
    if len(bass) < 8:
        warnings.append("Бас еле слышно — басовая партия собрана по корням аккордов.")
    if words is not None:
        _write_json(folder / "lyrics.json", words)
    else:
        (folder / "lyrics.json").unlink(missing_ok=True)
    analysis: dict[str, Any] = {
        "version": ANALYSIS_VERSION,
        "duration": round(duration, 3),
        "sample_rate": SAMPLE_RATE,
        "beats": [round(float(t), 4) for t in grid.times],
        "bar_times": grid.bar_times(),
        "key": harmony.key.name,
        "key_confidence": harmony.key_confidence,
        "transcription": transcription.to_dict(),
        "stems": names,
        "device": used,
        "separation": {
            "quality": "max" if len(separated_by) > 1 else "standard",
            "models": separated_by,
        },
        "warnings": warnings,
        "timings": timings,
    }
    lap("save")
    _write_json(folder / "analysis.json", analysis)
    return analysis
