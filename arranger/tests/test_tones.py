"""Звук гитары: тембры, пауэр-аккорды с перегрузом, акценты боя в alphaTex."""

import re
from dataclasses import replace

import pytest

from arranger import arrange, to_alphatex
from arranger.arrange import PlayerSetup
from arranger.instruments import TONE_LABELS, TONE_PROGRAMS, TONES, make_instrument, resolve_tone
from arranger.model import Transcription
from arranger.theory import Chord
from arranger.voicings import chord_voicings


def test_tone_follows_the_recording_unless_chosen() -> None:
    assert resolve_tone("electric", "auto", "distorted") == "drive"
    assert resolve_tone("electric", "auto", "") == "clean"
    assert resolve_tone("electric", "lead", "clean") == "lead"
    assert resolve_tone("acoustic", "drive", "distorted") == "steel"  # перегруз не для акустики
    assert resolve_tone("bass", "auto") == "finger"


def test_auto_tone_takes_the_preset_picked_by_the_analysis() -> None:
    assert resolve_tone("electric", "auto", "clean", "funk") == "funk"
    assert resolve_tone("electric", "auto", "distorted", "metal") == "metal"
    assert resolve_tone("electric", "chorus", "distorted", "metal") == "chorus"  # выбор игрока
    assert resolve_tone("acoustic", "auto", "clean", "funk") == "steel"
    assert resolve_tone("electric", "auto", "distorted", "что-то новое") == "drive"


def test_every_tone_has_a_label_and_a_synth_program() -> None:
    for tones in TONES.values():
        for tone in tones:
            assert tone in TONE_LABELS
            assert tone in TONE_PROGRAMS


@pytest.mark.parametrize("tone", ["fuzz", "metal"])
def test_heavy_tones_play_power_chords(song: Transcription, tone: str) -> None:
    player = PlayerSetup(id="p1", name="", kind="electric", roles=("rhythm",), tone=tone)  # type: ignore[arg-type]
    part = arrange(song, [player]).parts[0]
    assert part.tone == tone
    assert {s.name for s in part.shapes} == {"C5", "G5", "A5", "F5"}


def test_transcription_keeps_the_picked_sound(song: Transcription) -> None:
    tx = replace(song, guitar_tone="clean", guitar_sound="ambient")
    assert Transcription.from_dict(tx.to_dict()).guitar_sound == "ambient"
    player = PlayerSetup(id="p1", name="", kind="electric", roles=("rhythm",))
    assert arrange(tx, [player]).parts[0].tone == "ambient"


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
