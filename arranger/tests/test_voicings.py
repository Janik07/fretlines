import pytest

from arranger.instruments import make_instrument
from arranger.model import ChordSpan
from arranger.theory import parse_chord
from arranger.voicings import SPAN, choose_voicings, chord_voicings, suggest_capo

STANDARD = make_instrument("acoustic", "standard")


def shape(text: str) -> tuple[int | None, ...]:
    """«x32010» (от толстой струны к тонкой) → лады по струнам, первая — тонкая."""
    return tuple(None if ch == "x" else int(ch) for ch in reversed(text))


@pytest.mark.parametrize(
    ("chord", "expected"),
    [
        ("C", "x32010"),
        ("G", "320003"),
        ("D", "xx0232"),
        ("A", "x02220"),
        ("E", "022100"),
        ("Am", "x02210"),
        ("Em", "022000"),
        ("Dm", "xx0231"),
        ("B7", "x21202"),
    ],
)
def test_open_chords_are_the_classic_shapes(chord: str, expected: str) -> None:
    best = chord_voicings(parse_chord(chord), STANDARD, "medium")[0]
    assert best.frets == shape(expected)


@pytest.mark.parametrize("level", ["easy", "medium", "full"])
@pytest.mark.parametrize("chord", ["C", "F", "Bm", "F#m7", "Bbmaj7", "Ebsus4", "G#dim", "C#7"])
def test_every_voicing_is_playable(level: str, chord: str) -> None:
    parsed = parse_chord(chord)
    voicings = chord_voicings(parsed, STANDARD, level)  # type: ignore[arg-type]
    assert voicings, chord
    for voicing in voicings:
        fretted = [f for f in voicing.frets if f]
        assert not fretted or max(fretted) - min(fretted) < SPAN[level]  # type: ignore[index]
        sounding = {p % 12 for _, _, p in voicing.notes(STANDARD)}
        assert parsed.essential <= sounding
        played = voicing.played
        assert played == list(range(min(played), max(played) + 1))  # без глушёных в середине


def test_easy_avoids_full_barre_when_possible() -> None:
    best = chord_voicings(parse_chord("F"), STANDARD, "easy")[0]
    assert best.frets == shape("xx3211")


def test_drop_d_uses_the_open_low_string() -> None:
    drop_d = make_instrument("acoustic", "drop-d")
    best = chord_voicings(parse_chord("D"), drop_d, "medium")[0]
    assert best.frets[5] == 0


def test_capo_three_turns_b_flat_into_open_chords() -> None:
    names = ["Bb", "Eb", "F", "Gm"]
    spans = [ChordSpan(i * 4.0, i * 4.0 + 4.0, parse_chord(n)) for i, n in enumerate(names)]
    best = suggest_capo(spans, STANDARD, "easy")[0]
    assert best.capo == 3
    assert best.barre_chords == 0


def test_sequence_prefers_nearby_positions() -> None:
    chords = [parse_chord(n) for n in ["C", "G", "Am", "F"]]
    voicings = choose_voicings(chords, STANDARD, "medium")
    assert all(v is not None and v.position <= 3 for v in voicings)
