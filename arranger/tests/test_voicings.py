import pytest

from arranger.instruments import make_instrument
from arranger.model import ChordSpan
from arranger.theory import Chord, parse_chord
from arranger.voicings import (
    SPAN,
    Voicing,
    choose_voicings,
    chord_voicings,
    suggest_capo,
    transition_cost,
)

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


@pytest.mark.parametrize(
    ("chord", "expected"),
    [
        ("F", "133211"),
        ("Bb", "x13331"),
        ("B", "x24442"),
        ("C#", "x46664"),
        ("Bm", "x24432"),
        ("Cm", "x35543"),
        ("F#m", "244222"),
        ("Gm", "355333"),
        ("G#m", "466444"),
        ("D#m", "x68876"),
        ("F#7", "242322"),
        ("Bm7", "x24232"),
        ("Fmaj7", "xx3210"),
    ],
)
def test_barre_chords_are_the_shapes_guitarists_use(chord: str, expected: str) -> None:
    best = chord_voicings(parse_chord(chord), STANDARD, "full")[0]
    assert best.frets == shape(expected)


@pytest.mark.parametrize("level", ["easy", "medium", "full"])
@pytest.mark.parametrize(
    "quality", ["maj", "min", "7", "min7", "maj7", "sus2", "sus4", "dim", "aug"]
)
def test_best_voicing_fits_a_human_hand(level: str, quality: str) -> None:
    for root in range(12):
        best = chord_voicings(Chord(root, quality), STANDARD, level)[0]  # type: ignore[arg-type]
        fretted = [f for f in best.frets if f]
        assert not (0 in best.frets and max(fretted) > 4), best  # открытые — только у порожка
        assert len({f for f in best.fingers if f}) <= 4
        for fret, finger in zip(best.frets, best.fingers, strict=True):
            assert (fret is None) == (finger is None)
            assert (fret == 0) == (finger == 0)
        if best.barre is not None:  # под баррэ нет ни открытых, ни заглушённых струн
            thickest = max(i for i, f in enumerate(best.fingers) if f == 1)
            assert all(f is not None and f >= best.barre for f in best.frets[: thickest + 1])


def test_fingers_are_the_textbook_ones() -> None:
    def fingers(chord: str, level: str = "medium") -> tuple[int | None, ...]:
        return chord_voicings(parse_chord(chord), STANDARD, level)[0].fingers  # type: ignore[arg-type]

    assert fingers("C") == shape("x32010")
    assert fingers("Am") == shape("x02310")
    assert fingers("E") == shape("023100")
    assert fingers("D") == shape("xx0132")
    assert fingers("F") == shape("134211")
    assert chord_voicings(parse_chord("F"), STANDARD, "medium")[0].barre == 1


def test_easy_level_gets_small_shapes_instead_of_the_barre() -> None:
    for chord, expected in [("Bm", "xx4432"), ("F#m", "xx4222"), ("B", "xx4442")]:
        best = chord_voicings(parse_chord(chord), STANDARD, "easy")[0]
        assert best.frets == shape(expected)
        assert best.barre is None


def test_shared_fingers_and_slides_make_a_change_easy() -> None:
    def best(chord: str) -> Voicing:
        return chord_voicings(parse_chord(chord), STANDARD, "full")[0]

    # C → Am: два пальца остаются на месте; C → G: переставлять все.
    assert transition_cost(best("C"), best("Am"), "full") < transition_cost(
        best("C"), best("G"), "full"
    )
    # F → G — то же баррэ на два лада выше; F → Cm — другая форма на том же расстоянии.
    assert transition_cost(best("F"), best("G#"), "full") < transition_cost(
        best("F"), best("Cm"), "full"
    )


def test_one_shape_per_chord_and_fast_changes_keep_the_hand_in_place() -> None:
    chords = [parse_chord(n) for n in ["Gm", "Cm", "Dm"] * 4]
    slow = choose_voicings(chords, STANDARD, "full", seconds=[4.0] * len(chords))
    fast = choose_voicings(chords, STANDARD, "full", seconds=[0.5] * len(chords))
    loose = choose_voicings(chords, STANDARD, "full", seconds=[0.5] * len(chords), smooth=False)
    assert slow[2] is not None
    assert slow[2].frets == shape("xx0231")
    assert fast[2] is not None
    assert fast[2].frets == shape("x57765")
    assert loose[2] == slow[2]
    for voicings in (slow, fast):
        assert voicings[2] == voicings[5] == voicings[8]  # у аккорда одна форма на всю песню


def test_pinned_shape_is_kept() -> None:
    chords = [parse_chord(n) for n in ["C", "G", "Am", "F"]]
    pins = {parse_chord("F"): shape("xx3211"), parse_chord("G"): shape("999999")}
    voicings = choose_voicings(chords, STANDARD, "full", pins=pins)
    assert voicings[3] is not None
    assert voicings[3].frets == shape("xx3211")
    assert voicings[1] is not None
    assert voicings[1].frets == shape("320003")


def test_drop_d_mixes_its_own_shapes_with_the_library() -> None:
    drop_d = make_instrument("acoustic", "drop-d")

    def best(chord: str) -> tuple[int | None, ...]:
        return chord_voicings(parse_chord(chord), drop_d, "medium")[0].frets

    assert best("Em") == shape("222000")  # свой аккорд строя: три струны одним ладом
    assert best("Bm") == shape("x24432")  # шестая струна не нужна — обычное баррэ
    assert best("C") == shape("x32010")
