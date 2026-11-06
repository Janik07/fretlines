import pytest

from arranger.theory import Chord, Key, midi_name, parse_chord


@pytest.mark.parametrize("name", ["C", "Am", "F#m7", "Bbmaj7", "G7", "Dsus4", "E5", "C/G", "Bdim"])
def test_chord_names_round_trip(name: str) -> None:
    chord = parse_chord(name)
    flats = "b" in name
    assert chord.name(flats=flats) == name


def test_transposition_moves_root_and_bass() -> None:
    chord = parse_chord("C/E").transposed(2)
    assert chord.name() == "D/F#"
    assert parse_chord("A").transposed(-12) == parse_chord("A")


def test_simplification_keeps_major_or_minor() -> None:
    assert parse_chord("Am7").simplified() == Chord(9, "min")
    assert parse_chord("Gmaj7").simplified() == Chord(7, "maj")
    assert parse_chord("Dsus4").simplified() == Chord(2, "maj")


def test_essential_tones_drop_the_fifth() -> None:
    assert parse_chord("C").essential == {0, 4}
    assert parse_chord("G7").essential == {7, 11, 5}
    assert parse_chord("E5").essential == {4, 11}


def test_key_spelling() -> None:
    assert Key(10, "major").name == "Bb"
    assert Key(2, "minor").name == "Dm"
    assert Key(6, "major").name == "F#"
    assert midi_name(60) == "C4"
    assert midi_name(63, flats=True) == "Eb4"


def test_bad_chord_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="аккорд"):
        parse_chord("H7")
