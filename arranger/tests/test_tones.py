"""Звук гитары: тембры, пауэр-аккорды с перегрузом, акценты боя в alphaTex."""

import re
from dataclasses import replace

from arranger import arrange, to_alphatex
from arranger.arrange import PlayerSetup
from arranger.instruments import make_instrument, resolve_tone
from arranger.model import Transcription
from arranger.theory import Chord
from arranger.voicings import chord_voicings


def test_tone_follows_the_recording_unless_chosen() -> None:
    assert resolve_tone("electric", "auto", "distorted") == "drive"
    assert resolve_tone("electric", "auto", "") == "clean"
    assert resolve_tone("electric", "lead", "clean") == "lead"
    assert resolve_tone("acoustic", "drive", "distorted") == "steel"  # перегруз не для акустики
    assert resolve_tone("bass", "auto") == "finger"


def test_overdrive_rhythm_uses_power_chords(song: Transcription) -> None:
    player = PlayerSetup(id="p1", name="", kind="electric", roles=("rhythm",), tone="drive")
    part = arrange(song, [player]).parts[0]
    assert part.tone == "drive"
    assert {s.name for s in part.shapes} == {"C5", "G5", "A5", "F5"}
    for beat in part.beats:
        assert {n.pitch % 12 for n in beat.notes} <= {0, 7, 9, 4, 5, 2}
        assert len(beat.notes) <= 3


def test_clean_rhythm_keeps_full_chords(song: Transcription) -> None:
    player = PlayerSetup(id="p1", name="", kind="electric", roles=("rhythm",), tone="clean")
    part = arrange(song, [player]).parts[0]
    assert "Am" in {s.name for s in part.shapes}


def test_power_chords_have_the_root_in_the_bass() -> None:
    guitar = make_instrument("electric", "standard", 0)
    for root in range(12):
        for voicing in chord_voicings(Chord(root, "5"), guitar, "medium"):
            notes = voicing.notes(guitar)
            lowest = max(notes, key=lambda n: n[0])  # самая толстая струна
            assert lowest[2] % 12 == root
            assert lowest[0] >= guitar.strings - 2


def test_alphatex_accents_strums_and_picks_the_program(song: Transcription) -> None:
    tx = replace(song, guitar_tone="distorted")
    player = PlayerSetup(id="p1", name="", kind="electric", roles=("rhythm",), difficulty="medium")
    text = to_alphatex(arrange(tx, [player]), title="t")
    assert "{ instrument 29 }" in text  # перегруз для встроенного синтезатора
    dynamics = re.findall(r"dy (\w+)", text)
    assert "f" in dynamics
    assert "mp" in dynamics  # удары вверх тише
