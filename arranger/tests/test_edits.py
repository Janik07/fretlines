"""Ручная правка аккордов: замена на отрезке и переименование по всей песне."""

# ruff: noqa: PT011

import copy
import random
from collections.abc import Sequence
from itertools import pairwise

import pytest

from arranger.edits import ChordEdit, apply_chord_edits, rename_chords
from arranger.model import ChordSpan
from arranger.theory import Chord, parse_chord


def sp(start: float, end: float, name: str) -> ChordSpan:
    return ChordSpan(start, end, parse_chord(name))


def view(spans: Sequence[ChordSpan]) -> list[tuple[float, float, str]]:
    return [(round(s.start, 5), round(s.end, 5), s.chord.name()) for s in spans]


def test_replace_across_two_spans() -> None:
    out = apply_chord_edits([sp(0, 4, "C"), sp(4, 8, "G")], [ChordEdit(2, 6, "Am")], 8)
    assert view(out) == [(0, 2, "C"), (2, 6, "Am"), (6, 8, "G")]


def test_split_one_span() -> None:
    out = apply_chord_edits([sp(0, 8, "C")], [ChordEdit(2, 4, "F")], 8)
    assert view(out) == [(0, 2, "C"), (2, 4, "F"), (4, 8, "C")]


def test_none_leaves_a_gap() -> None:
    out = apply_chord_edits([sp(0, 8, "C")], [ChordEdit(2, 4, None)], 8)
    assert view(out) == [(0, 2, "C"), (4, 8, "C")]


def test_fills_a_gap() -> None:
    out = apply_chord_edits([sp(0, 2, "C"), sp(6, 8, "G")], [ChordEdit(2, 6, "Am")], 8)
    assert view(out) == [(0, 2, "C"), (2, 6, "Am"), (6, 8, "G")]


def test_later_edit_wins() -> None:
    out = apply_chord_edits([sp(0, 8, "C")], [ChordEdit(0, 8, "Am"), ChordEdit(2, 4, "F")], 8)
    assert view(out) == [(0, 2, "Am"), (2, 4, "F"), (4, 8, "Am")]


def test_earlier_edit_survives_outside_the_later_one() -> None:
    out = apply_chord_edits(
        [], [ChordEdit(0, 4, "F"), ChordEdit(2, 8, "G"), ChordEdit(3, 5, None)], 8
    )
    assert view(out) == [(0, 2, "F"), (2, 3, "G"), (5, 8, "G")]


def test_clipped_to_the_song() -> None:
    edits = [ChordEdit(-3, 2, "D"), ChordEdit(6, 20, "E"), ChordEdit(9, 12, "A")]
    out = apply_chord_edits([sp(0, 8, "C")], edits, 8)
    assert view(out) == [(0, 2, "D"), (2, 6, "C"), (6, 8, "E")]


def test_empty_and_reversed_edits_are_skipped() -> None:
    out = apply_chord_edits([sp(0, 8, "C")], [ChordEdit(4, 4, "G"), ChordEdit(5, 3, "G")], 8)
    assert view(out) == [(0, 8, "C")]


def test_bad_name_raises_even_when_the_edit_would_be_skipped() -> None:
    with pytest.raises(ValueError):
        apply_chord_edits([sp(0, 8, "C")], [ChordEdit(100, 200, "H#x")], 8)
    with pytest.raises(ValueError):
        apply_chord_edits([sp(0, 8, "C")], [ChordEdit(5, 3, "нет")], 8)


def test_bad_name_after_good_ones_raises() -> None:
    with pytest.raises(ValueError):
        apply_chord_edits([sp(0, 8, "C")], [ChordEdit(0, 2, "G"), ChordEdit(2, 4, "???")], 8)


def test_untouched_equal_neighbours_are_merged() -> None:
    out = apply_chord_edits([sp(0, 2, "C"), sp(2, 4, "C"), sp(4, 8, "G")], [], 8)
    assert view(out) == [(0, 4, "C"), (4, 8, "G")]


def test_edit_that_makes_neighbours_equal_merges_them() -> None:
    out = apply_chord_edits([sp(0, 4, "C"), sp(4, 8, "G")], [ChordEdit(4, 8, "C")], 8)
    assert view(out) == [(0, 8, "C")]


def test_unsorted_input_is_sorted() -> None:
    out = apply_chord_edits([sp(4, 8, "G"), sp(0, 4, "C")], [], 8)
    assert view(out) == [(0, 4, "C"), (4, 8, "G")]


def test_slivers_are_dropped() -> None:
    out = apply_chord_edits([sp(0, 4, "C")], [ChordEdit(1e-7, 4, "G")], 4)
    assert len(out) == 1
    assert out[0].chord == parse_chord("G")
    assert out[0].end == pytest.approx(4)


def test_enharmonic_names_merge() -> None:
    out = apply_chord_edits([sp(0, 4, "G#m")], [ChordEdit(4, 8, "Abm")], 8)
    assert len(out) == 1
    assert (out[0].start, out[0].end) == (0, 8)


def test_tiny_gap_between_equal_chords_is_closed() -> None:
    out = apply_chord_edits([sp(0, 4, "C"), sp(4 + 5e-7, 8, "C")], [], 8)
    assert len(out) == 1
    assert out[0].start == 0
    assert out[0].end == 8


def test_real_gap_is_kept() -> None:
    out = apply_chord_edits([sp(0, 4, "C"), sp(4.01, 8, "C")], [], 8)
    assert len(out) == 2


def test_removal_over_spans_and_gaps() -> None:
    spans = [sp(0, 2, "C"), sp(3, 5, "G"), sp(6, 8, "Am")]
    out = apply_chord_edits(spans, [ChordEdit(1, 7, None)], 8)
    assert view(out) == [(0, 1, "C"), (7, 8, "Am")]


def test_slash_chord() -> None:
    out = apply_chord_edits([], [ChordEdit(0, 4, "C/G")], 4)
    assert out[0].chord == parse_chord("C/G")


def test_inputs_are_not_mutated_and_result_is_a_tuple() -> None:
    spans = [sp(4, 8, "G"), sp(0, 4, "C")]
    edits = [ChordEdit(2, 6, "Am")]
    before = (copy.deepcopy(spans), copy.deepcopy(edits))
    out = apply_chord_edits(spans, edits, 8)
    assert (spans, edits) == before
    assert isinstance(out, tuple)
    assert isinstance(rename_chords(spans, {}), tuple)


def test_zero_length_song_ignores_edits() -> None:
    assert view(apply_chord_edits([], [ChordEdit(0, 4, "C")], 0)) == []


def test_edit_is_frozen() -> None:
    edit = ChordEdit(0, 1, "C")
    with pytest.raises(AttributeError):
        edit.start = 2  # type: ignore[misc]


def test_rename_everywhere() -> None:
    out = rename_chords([sp(0, 4, "C"), sp(4, 8, "G"), sp(8, 12, "C")], {"C": "Am"})
    assert view(out) == [(0, 4, "Am"), (4, 8, "G"), (8, 12, "Am")]


def test_rename_does_not_chain() -> None:
    out = rename_chords([sp(0, 4, "C"), sp(4, 8, "G")], {"C": "G", "G": "D"})
    assert view(out) == [(0, 4, "G"), (4, 8, "D")]


def test_rename_swap() -> None:
    out = rename_chords([sp(0, 4, "C"), sp(4, 8, "G")], {"C": "G", "G": "C"})
    assert view(out) == [(0, 4, "G"), (4, 8, "C")]


def test_rename_matches_enharmonic_key() -> None:
    out = rename_chords([sp(0, 4, "G#m7")], {"Abm7": "G#m"})
    assert out[0].chord == parse_chord("G#m")


def test_rename_duplicate_keys_raise() -> None:
    with pytest.raises(ValueError):
        rename_chords([sp(0, 4, "C")], {"G#m": "A", "Abm": "B"})


def test_rename_none_removes() -> None:
    out = rename_chords([sp(0, 4, "C"), sp(4, 8, "G")], {"G": None})
    assert view(out) == [(0, 4, "C")]


def test_rename_merges_neighbours() -> None:
    out = rename_chords([sp(0, 4, "C"), sp(4, 8, "G")], {"G": "C"})
    assert view(out) == [(0, 8, "C")]


def test_rename_bad_names_raise() -> None:
    with pytest.raises(ValueError):
        rename_chords([sp(0, 4, "C")], {"C": "???"})
    with pytest.raises(ValueError):
        rename_chords([sp(0, 4, "C")], {"???": "C"})
    with pytest.raises(ValueError):
        rename_chords([], {"Zz": "C"})


def test_rename_normalizes_without_rules() -> None:
    out = rename_chords([sp(4, 8, "C"), sp(0, 4, "C")], {})
    assert view(out) == [(0, 8, "C")]


def test_rename_keeps_bass_distinct() -> None:
    out = rename_chords([sp(0, 4, "C/G"), sp(4, 8, "C")], {"C": "F"})
    assert view(out) == [(0, 4, "C/G"), (4, 8, "F")]


NAMES = ["C", "G", "Am", "F", "D7", "Em"]
CELL = 0.25


def _expected(
    cells: int, spans: Sequence[ChordSpan], edits: Sequence[ChordEdit], total: float
) -> list[Chord | None]:
    grid: list[Chord | None] = [None] * cells
    for span in spans:
        for i in range(round(span.start / CELL), round(span.end / CELL)):
            grid[i] = span.chord
    for edit in edits:
        start, end = max(0.0, edit.start), min(total, edit.end)
        if end <= start:
            continue
        chord = parse_chord(edit.chord) if edit.chord else None
        for i in range(round(start / CELL), round(end / CELL)):
            grid[i] = chord
    return grid


@pytest.mark.parametrize("seed", range(150))
def test_random_edits_match_a_brute_force_grid(seed: int) -> None:
    rng = random.Random(seed)
    cells = rng.randint(4, 40)
    total = cells * CELL
    cuts = sorted(rng.sample(range(cells + 1), rng.randint(2, min(8, cells + 1))))
    spans = [
        sp(a * CELL, b * CELL, rng.choice(NAMES)) for a, b in pairwise(cuts) if rng.random() < 0.75
    ]
    rng.shuffle(spans)
    edits = []
    for _ in range(rng.randint(0, 6)):
        a = rng.randint(-4, cells + 4)
        b = rng.randint(-4, cells + 4)
        edits.append(ChordEdit(a * CELL, b * CELL, rng.choice([*NAMES, None])))
    out = apply_chord_edits(spans, edits, total)
    grid = _expected(cells, spans, edits, total)
    got: list[Chord | None] = [None] * cells
    for span in out:
        assert span.end - span.start > 1e-6
        for i in range(round(span.start / CELL), round(span.end / CELL)):
            assert got[i] is None, "участки пересекаются"
            got[i] = span.chord
    assert got == grid
    for a, b in pairwise(out):
        assert a.end <= b.start + 1e-9  # отсортировано и без наложений
        assert not (a.chord == b.chord and b.start - a.end <= 1e-6), "соседи не склеены"
