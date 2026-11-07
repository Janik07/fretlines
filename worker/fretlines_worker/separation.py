"""Разделение на дорожки: вокал, бас, барабаны, гитара, клавиши, остальное — и инструментал.

Два уровня качества:
- standard — один проход Demucs htdemucs_6s по всей записи (быстрее);
- max — сначала вокал отделяется сильнейшей моделью, что по силам компьютеру (на видеокарте
  BS-RoFormer, на процессоре MDX-Net Inst HQ4, через audio-separator), а потом Demucs
  раскладывает уже чистый инструментал по инструментам. Вокал не мешает Demucs — гитара и
  клавиши чище, а инструментал без «призраков» голоса.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np

from fretlines_worker.audio import SAMPLE_RATE, Audio

log = logging.getLogger("fretlines.separation")

MODEL = "htdemucs_6s"
STEMS = ("vocals", "bass", "drums", "guitar", "piano", "other")
Quality = Literal["standard", "max"]

# Отделение вокала: на видеокарте — лучшая из открытых моделей, на процессоре — быстрая и сильная.
VOCAL_MODELS = {
    "cuda": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",  # BS-RoFormer (ViperX), ~640 МБ
    "cpu": "UVR-MDX-NET-Inst_HQ_4.onnx",  # MDX-Net Inst HQ4, ~60 МБ
}
# Сколько секунд работы на секунду звука — для полоски прогресса (модели свой прогресс не отдают).
_SECONDS_PER_SECOND = {"cuda": 0.12, "cpu": 1.25}


def vocal_model(device: str) -> str:
    return VOCAL_MODELS["cuda" if device.startswith("cuda") else "cpu"]


def _demucs(audio: Audio, device: str, on_progress: Callable[[float], None]) -> dict[str, Audio]:
    import torch
    from demucs.api import Separator

    total = audio.shape[1]

    def callback(info: dict[str, object]) -> None:
        if info.get("state") != "end":
            return
        offset = info.get("segment_offset", 0)
        length = info.get("audio_length", total)
        if isinstance(offset, int | float) and isinstance(length, int | float) and length:
            on_progress(min(0.99, float(offset) / float(length)))

    def run(on: str) -> dict[str, Audio]:
        separator = Separator(model=MODEL, device=on, shifts=1, overlap=0.25, callback=callback)
        with torch.inference_mode():
            _, stems = separator.separate_tensor(
                torch.from_numpy(np.ascontiguousarray(audio)), SAMPLE_RATE
            )
        return {name: stems[name].float().cpu().numpy() for name in stems}

    try:
        return run(device)
    except torch.cuda.OutOfMemoryError:
        log.warning("видеокарте не хватило памяти — разделяю на процессоре")
        torch.cuda.empty_cache()
        return run("cpu")


def _fit(audio: Audio, length: int) -> Audio:
    """Модели иногда добавляют пару сотен отсчётов — подрезаем под исходную длину."""
    if audio.shape[1] >= length:
        return np.ascontiguousarray(audio[:, :length], dtype=np.float32)
    return np.pad(audio, ((0, 0), (0, length - audio.shape[1]))).astype(np.float32)


def split_vocals(
    audio: Audio,
    device: str,
    workdir: Path,
    models_dir: Path,
    on_progress: Callable[[float], None],
) -> tuple[Audio, Audio]:
    """(вокал, инструментал) лучшей моделью для этого компьютера."""
    import soundfile as sf
    from audio_separator.separator import Separator

    from fretlines_worker.audio import ffmpeg_on_path

    ffmpeg_on_path()
    kind = "cuda" if device.startswith("cuda") else "cpu"
    workdir.mkdir(parents=True, exist_ok=True)
    source = workdir / "mix.wav"
    sf.write(source, audio.T, SAMPLE_RATE, subtype="FLOAT")

    expected = max(5.0, audio.shape[1] / SAMPLE_RATE * _SECONDS_PER_SECOND[kind])
    started = time.monotonic()
    done = threading.Event()

    def tick() -> None:  # прогресс по времени: модель не сообщает, сколько осталось
        while not done.wait(1.0):
            on_progress(min(0.95, (time.monotonic() - started) / expected))

    ticker = threading.Thread(target=tick, daemon=True)
    ticker.start()
    try:
        separator = Separator(
            log_level=logging.WARNING,
            model_file_dir=str(models_dir),
            output_dir=str(workdir),
            output_format="WAV",
            sample_rate=SAMPLE_RATE,
            use_autocast=kind == "cuda",
        )
        separator.load_model(model_filename=vocal_model(device))
        names = separator.separate(str(source))
    finally:
        done.set()
    files = [workdir / Path(name).name for name in names]
    vocals_file = next(f for f in files if "(Vocals)" in f.name)
    instrumental_file = next(f for f in files if "(Instrumental)" in f.name)
    vocals = sf.read(vocals_file, dtype="float32", always_2d=True)[0].T
    instrumental = sf.read(instrumental_file, dtype="float32", always_2d=True)[0].T
    shutil.rmtree(workdir, ignore_errors=True)
    length = audio.shape[1]
    return _fit(vocals, length), _fit(instrumental, length)


def separate(
    audio: Audio,
    device: str,
    on_progress: Callable[[float], None],
    *,
    quality: Quality = "standard",
    workdir: Path | None = None,
    models_dir: Path | None = None,
) -> tuple[dict[str, Audio], Audio, list[str]]:
    """Дорожки (vocals, bass, drums, guitar, piano, other), инструментал и какие модели работали."""
    if quality == "max" and workdir is not None and models_dir is not None:
        try:
            vocals, instrumental = split_vocals(
                audio, device, workdir, models_dir, lambda f: on_progress(0.45 * f)
            )
        except Exception:  # модель не скачалась или не запустилась — обычное качество
            log.exception("отделение вокала не удалось — разделяю обычным способом")
        else:
            parts = _demucs(instrumental, device, lambda f: on_progress(0.45 + 0.55 * f))
            # Остатки голоса в инструментале (бэк-вокал, эффекты) не теряем — они в «остальном».
            parts["other"] = parts["other"] + parts.pop("vocals")
            parts["vocals"] = vocals
            on_progress(1.0)
            return {name: parts[name] for name in STEMS}, instrumental, [vocal_model(device), MODEL]
    stems = _demucs(audio, device, on_progress)
    on_progress(1.0)
    instrumental = sum((stems[name] for name in STEMS if name != "vocals"), np.zeros_like(audio))
    return stems, instrumental.astype(np.float32), [MODEL]
