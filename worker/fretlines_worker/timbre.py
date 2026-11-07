"""Какая гитара звучит в записи: акустика, чистая электро или с перегрузом — и каким пресетом.

Модель — PANNs Cnn10 (Kong et al., 2020; код MIT, веса CC BY 4.0), обучена на AudioSet:
527 классов звуков, среди них «Электрогитара», «Акустическая гитара», «Дисторшн», «Хэви-метал».
Слушаем гитарную дорожку в самых громких местах — по ответу выбираем тембр «как в записи».
"""

from __future__ import annotations

import logging
import urllib.request
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from fretlines_worker.audio import SAMPLE_RATE

log = logging.getLogger("fretlines.timbre")

WEIGHTS_URL = "https://zenodo.org/record/3987831/files/Cnn10_mAP%3D0.380.pth?download=1"
WEIGHTS_BYTES = 25_237_595
SR = 32_000
WINDOW = 10  # секунд на кусок — как при обучении модели

# Номера классов AudioSet (metadata/class_labels_indices.csv в репозитории PANNs).
CLASSES: dict[str, int] = {
    "guitar": 140,
    "electric": 141,
    "acoustic": 143,
    "pop": 216,
    "rock": 219,
    "metal": 220,
    "punk": 221,
    "grunge": 222,
    "psychedelic": 225,
    "rnb": 226,
    "soul": 227,
    "funk": 232,
    "jazz": 235,
    "disco": 236,
    "ambient": 246,
    "blues": 251,
    "new_age": 253,
    "indie": 265,
    "chorus": 464,  # «Chorus effect» — эффект, а не хор
    "reverb": 511,
    "echo": 512,
    "distortion": 517,
}


def _weights(models_dir: Path) -> Path:
    path = models_dir / "panns" / "Cnn10_mAP=0.380.pth"
    if path.exists() and path.stat().st_size == WEIGHTS_BYTES:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("скачиваю PANNs Cnn10 (25 МБ)")
    tmp = path.with_suffix(".part")
    request = urllib.request.Request(WEIGHTS_URL, headers={"User-Agent": "Fretlines/0.4"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    if tmp.stat().st_size != WEIGHTS_BYTES:
        tmp.unlink(missing_ok=True)
        raise OSError("веса PANNs скачались не целиком")
    tmp.replace(path)
    return path


@cache
def _model(weights: str) -> Any:  # noqa: ANN401 — модуль PyTorch
    import librosa
    import torch
    from torch import nn
    from torch.nn import functional

    class ConvBlock(nn.Module):
        def __init__(self, cin: int, cout: int) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(cin, cout, 3, padding=1, bias=False)
            self.conv2 = nn.Conv2d(cout, cout, 3, padding=1, bias=False)
            self.bn1 = nn.BatchNorm2d(cout)
            self.bn2 = nn.BatchNorm2d(cout)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = functional.relu_(self.bn1(self.conv1(x)))
            x = functional.relu_(self.bn2(self.conv2(x)))
            return functional.avg_pool2d(x, kernel_size=(2, 2))

    class Cnn10(nn.Module):
        """PANNs Cnn10. Спектр считаем сами, как torchlibrosa: окно Ханна 1024, шаг 320, 64 мела."""

        def __init__(self) -> None:
            super().__init__()
            self.bn0 = nn.BatchNorm2d(64)
            self.conv_block1 = ConvBlock(1, 64)
            self.conv_block2 = ConvBlock(64, 128)
            self.conv_block3 = ConvBlock(128, 256)
            self.conv_block4 = ConvBlock(256, 512)
            self.fc1 = nn.Linear(512, 512)
            self.fc_audioset = nn.Linear(512, 527)
            mel = librosa.filters.mel(sr=SR, n_fft=1024, n_mels=64, fmin=50, fmax=14000)
            # Модель работает только на процессоре — обычных тензоров-атрибутов достаточно.
            self.mel: torch.Tensor = torch.from_numpy(mel.T.astype(np.float32))
            self.window: torch.Tensor = torch.hann_window(1024, periodic=True)

        def forward(self, audio: torch.Tensor) -> torch.Tensor:
            spec = torch.stft(
                audio,
                n_fft=1024,
                hop_length=320,
                window=self.window,
                center=True,
                pad_mode="reflect",
                return_complex=True,
            )
            power = spec.real**2 + spec.imag**2  # (батч, частоты, кадры)
            x = 10 * torch.log10(torch.clamp(power.transpose(1, 2) @ self.mel, min=1e-10))
            x = x[:, None, :, :]  # (батч, 1, кадры, мелы)
            x = self.bn0(x.transpose(1, 3)).transpose(1, 3)
            for block in (self.conv_block1, self.conv_block2, self.conv_block3, self.conv_block4):
                x = block(x)
            x = torch.mean(x, dim=3)
            x = torch.max(x, dim=2).values + torch.mean(x, dim=2)
            x = functional.relu_(self.fc1(x))
            return torch.sigmoid(self.fc_audioset(x))

    model = Cnn10()
    state = torch.load(weights, map_location="cpu", weights_only=True)["model"]
    # Свой расчёт спектра: веса STFT и мел-фильтров из torchlibrosa не нужны.
    state = {k: v for k, v in state.items() if not k.startswith(("spectrogram", "logmel"))}
    model.load_state_dict(state, strict=False)
    model.eval()
    return model


def tag(mono: NDArray[np.float32], models_dir: Path, pieces: int = 6) -> dict[str, float]:
    """Вероятности классов по самым громким кускам дорожки (44.1 кГц моно)."""
    import librosa
    import torch

    audio = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=SR).astype(np.float32)
    size = SR * WINDOW
    if audio.size < size:
        audio = np.pad(audio, (0, size - audio.size))
    starts = list(range(0, audio.size - size + 1, size // 2))
    loudness = [float(np.sqrt(np.mean(audio[s : s + size] ** 2))) for s in starts]
    chosen = [starts[i] for i in np.argsort(loudness)[::-1][:pieces]]
    batch = torch.from_numpy(np.stack([audio[s : s + size] for s in chosen]))
    model = _model(str(_weights(models_dir)))
    with torch.inference_mode():
        probs = model(batch).mean(dim=0).numpy()
    return {name: round(float(probs[index]), 4) for name, index in CLASSES.items()}


def guitar_tone(scores: dict[str, float]) -> str:
    """acoustic / clean / distorted для тембра «как в записи»; пусто — не уверены.

    Пороги подобраны по гитарным дорожкам эталонных записей: на перегруженной «Distortion»
    ≈ 0.4, на чистой и акустике — не выше 0.02; акустика ≈ 0.24 против 0.07 у «электро».
    """
    if scores["distortion"] >= 0.12 or scores["metal"] >= 0.15:
        return "distorted"
    if scores["acoustic"] >= 0.05 and scores["acoustic"] > scores["electric"] * 1.2:
        return "acoustic"
    if scores["electric"] >= 0.02 or scores["guitar"] >= 0.05:
        return "clean"
    return ""


def guitar_sound(guitar: dict[str, float], mix: dict[str, float], single_share: float) -> str:
    """Какой пресет электро ближе к записи; пусто — гитара не электро.

    guitar — ответы модели на гитарную дорожку (перегруз и эффекты слышнее всего там), mix — на
    всю песню (жанр модель узнаёт по миксу целиком), single_share — доля ударов из одной ноты
    (соло и риффы). Жанр подсказывает, как обычно звучит гитара: фанк — чистый звук с
    компрессором, психоделика — фузз, эмбиент — дилей и большой ревер. Пороги — стартовые:
    у главного жанра песни модель обычно даёт 0.2–0.6, у остальных — меньше 0.1.
    """
    tone = guitar_tone(guitar)
    if tone == "distorted":
        if guitar.get("metal", 0) >= 0.2 or mix.get("metal", 0) >= 0.25:
            return "metal"
        if mix.get("psychedelic", 0) >= 0.1:
            return "fuzz"
        if single_share >= 0.8:
            return "lead"
        if guitar["distortion"] < 0.25:
            return "blues" if mix.get("blues", 0) >= 0.15 else "crunch"
        return "drive"
    if tone != "clean":
        return ""
    if mix.get("jazz", 0) >= 0.15:
        return "jazz"
    groove = mix.get("funk", 0) + mix.get("disco", 0) + mix.get("soul", 0) + mix.get("rnb", 0)
    if mix.get("funk", 0) >= 0.12 or groove >= 0.3:
        return "funk"
    if (
        mix.get("ambient", 0) + mix.get("new_age", 0) >= 0.12
        or guitar.get("echo", 0) >= 0.15
        or guitar.get("reverb", 0) >= 0.3
    ):
        return "ambient"
    if guitar.get("chorus", 0) >= 0.08:
        return "chorus"
    if mix.get("blues", 0) >= 0.25:
        return "blues"
    return "clean"
