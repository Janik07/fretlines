"""Справочники для интерфейса: строи, инструменты, роли, пресеты состава."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from arranger import INSTRUMENT_LABELS, PRESET_LABELS, PRESETS, TUNINGS
from arranger.arrange import ROLE_LABELS
from arranger.instruments import TONE_LABELS, TONES
from arranger.theory import midi_name
from fretlines_api.deps import get_settings
from fretlines_api.settings import Settings

router = APIRouter(tags=["meta"])

DIFFICULTY_LABELS = {"easy": "Упрощённо", "medium": "Средне", "full": "Полностью"}


@router.get("/meta")
def meta(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    return {
        "tunings": [
            {
                "id": t.id,
                "label": t.label,
                "bass": t.is_bass,
                "notes": [midi_name(p, flats=True) for p in t.strings],
            }
            for t in TUNINGS.values()
        ],
        "instruments": [{"id": k, "label": v} for k, v in INSTRUMENT_LABELS.items()],
        "roles": [{"id": k, "label": v} for k, v in ROLE_LABELS.items()],
        "tones": {
            kind: [{"id": t, "label": TONE_LABELS[t]} for t in ("auto", *tones)]
            for kind, tones in TONES.items()
        },
        "difficulties": [{"id": k, "label": v} for k, v in DIFFICULTY_LABELS.items()],
        "presets": [
            {
                "id": key,
                "label": PRESET_LABELS[key],
                "players": [{"name": name, "roles": list(roles)} for name, roles in players],
            }
            for key, players in PRESETS.items()
        ],
        "limits": {
            "max_upload_mb": settings.max_upload_mb,
            "max_video_upload_mb": settings.max_video_upload_mb,
            "max_minutes": 15,
        },
    }
