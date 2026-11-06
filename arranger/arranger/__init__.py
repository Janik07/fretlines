"""Движок аранжировки Fretlines.

Чистый Python без ML-зависимостей: им пользуются и API (быстрый пересчёт партий
по сохранённой транскрипции), и воркер (первая сборка партий после анализа).
"""

from importlib.metadata import version

from arranger.alphatex import to_alphatex
from arranger.arrange import (
    PRESET_LABELS,
    PRESETS,
    Arrangement,
    PlayerSetup,
    arrange,
    arrangement_to_dict,
    preset_players,
)
from arranger.instruments import INSTRUMENT_LABELS, TUNINGS, make_instrument
from arranger.model import Note, Transcription

__version__ = version("fretlines-arranger")

__all__ = [
    "INSTRUMENT_LABELS",
    "PRESETS",
    "PRESET_LABELS",
    "TUNINGS",
    "Arrangement",
    "Note",
    "PlayerSetup",
    "Transcription",
    "arrange",
    "arrangement_to_dict",
    "make_instrument",
    "preset_players",
    "to_alphatex",
]
