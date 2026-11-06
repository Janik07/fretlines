import pytest

from arranger.model import ChordSpan, Note, Transcription
from arranger.theory import Key, parse_chord


def _song() -> Transcription:
    """8 тактов 4/4: C–G–Am–F по два такта, простая мелодия и бас по корням."""
    progression = ["C", "G", "Am", "F"]
    chords = tuple(
        ChordSpan(i * 8.0, i * 8.0 + 8.0, parse_chord(name)) for i, name in enumerate(progression)
    )
    melody_pitches = [64, 65, 67, 67, 69, 67, 65, 64, 62, 64, 65, 67, 64, 62, 60, 60]
    melody = tuple(Note(i * 2.0, 1.5, p) for i, p in enumerate(melody_pitches))
    roots = {"C": 36, "G": 43, "Am": 45, "F": 41}
    bass = tuple(
        Note(bar * 4.0 + beat, 0.9, roots[progression[bar // 2]])
        for bar in range(8)
        for beat in (0.0, 1.0, 2.0, 3.0)
    )
    accents = (1.0, 0, 0.2, 0, 0.8, 0, 0.6, 0, 0.9, 0, 0.3, 0, 0.8, 0, 0.6, 0)
    return Transcription(
        tempo=96.0,
        beats_per_bar=4,
        bars=8,
        key=Key(0, "major"),
        chords=chords,
        melody=melody,
        bass=bass,
        accents=accents,
    )


@pytest.fixture
def song() -> Transcription:
    return _song()
