"""Скачать все модели заранее (Codespaces, Docker): иначе они качаются при первом разборе.

Demucs и Beat This! (~130 МБ), Basic Pitch (230 КБ), PANNs Cnn10 (25 МБ), MDX-Net (60 МБ),
Whisper (small — ~460 МБ) и банк звуков для плеера (~40 МБ). Всё ложится в .models/.

Запуск из корня проекта: python scripts/fetch_models.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / ".models"


def main() -> None:
    os.chdir(ROOT)
    os.environ.setdefault("FRETLINES_MODELS_DIR", str(MODELS))
    os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
    os.environ.setdefault("TORCH_HOME", str(MODELS / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    print("== Demucs htdemucs_6s", flush=True)
    from demucs.pretrained import get_model

    get_model("htdemucs_6s")

    print("== Beat This!", flush=True)
    from beat_this.inference import load_checkpoint

    load_checkpoint("final0")

    print("== Basic Pitch", flush=True)
    from fretlines_worker.notes import model_path

    model_path()

    print("== PANNs Cnn10 (тембр гитары)", flush=True)
    from fretlines_worker.timbre import _weights

    _weights(MODELS)

    print("== MDX-Net Inst HQ4 (вокал и инструментал)", flush=True)
    from audio_separator.separator import Separator

    from fretlines_worker.audio import ffmpeg_on_path
    from fretlines_worker.separation import VOCAL_MODELS

    ffmpeg_on_path()  # audio-separator ищет ffmpeg по имени
    separator = Separator(model_file_dir=str(MODELS / "separator"), info_only=False)
    separator.download_model_and_data(VOCAL_MODELS["cpu"])

    model = os.environ.get("FRETLINES_LYRICS_MODEL", "small")
    print(f"== Whisper {model}", flush=True)
    from faster_whisper import WhisperModel

    WhisperModel(model, device="cpu", compute_type="int8", download_root=str(MODELS / "whisper"))

    print("== Банк звуков MuseScore General", flush=True)
    from fretlines_api.routes.soundfont import _download, soundfont_path

    path = soundfont_path()
    if not path.exists():
        _download(path)
    if not path.exists():
        print("   не скачался — плеер будет играть встроенным банком", file=sys.stderr)

    print("== Модели на месте", flush=True)


if __name__ == "__main__":
    main()
