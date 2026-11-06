"""Разделение на стемы: Demucs htdemucs_6s — вокал, бас, барабаны, гитара, пианино, остальное."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from fretlines_worker.audio import SAMPLE_RATE, Audio

log = logging.getLogger("fretlines.separation")

MODEL = "htdemucs_6s"
STEMS = ("vocals", "bass", "drums", "guitar", "piano", "other")


def separate(audio: Audio, device: str, on_progress: Callable[[float], None]) -> dict[str, Audio]:
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
        stems = run(device)
    except torch.cuda.OutOfMemoryError:
        log.warning("видеокарте не хватило памяти — разделяю на процессоре")
        torch.cuda.empty_cache()
        stems = run("cpu")
    on_progress(1.0)
    return stems
