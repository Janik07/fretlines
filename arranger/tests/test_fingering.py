import pytest

from arranger.fingering import finger_line
from arranger.instruments import make_instrument

STANDARD = make_instrument("acoustic", "standard")


def test_c_major_scale_lands_in_open_position() -> None:
    # C3 … G4: классическая раскладка в первой позиции.
    scale = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67]
    expected = [
        (5, 3),
        (4, 0),
        (4, 2),
        (4, 3),
        (3, 0),
        (3, 2),
        (2, 0),
        (2, 1),
        (2, 3),
        (1, 0),
        (1, 1),
        (1, 3),
    ]
    path = finger_line([(i * 0.5, p) for i, p in enumerate(scale)], STANDARD)
    assert [(f.string, f.fret) for f in path] == expected
    assert all(STANDARD.pitch_at(f.string, f.fret) == p for f, p in zip(path, scale, strict=True))


def test_two_octave_scale_is_played_without_moving_the_hand() -> None:
    # Две октавы до мажора целиком не влезают в первую позицию — DP уходит в одну позицию выше.
    scale = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72]
    path = finger_line([(i * 0.5, p) for i, p in enumerate(scale)], STANDARD)
    assert len({f.hand for f in path if f.fret}) == 1


def test_every_fretted_note_is_under_the_hand() -> None:
    melody = [64, 67, 72, 76, 79, 76, 72, 71, 69, 74, 77, 81, 79, 76, 72, 64, 60, 55]
    for span in (3, 4):
        path = finger_line([(i * 0.25, p) for i, p in enumerate(melody)], STANDARD, span=span)
        for f in path:
            if f.fret:
                assert f.hand <= f.fret <= f.hand + span - 1


def test_fast_passage_stays_in_one_position() -> None:
    # Пентатоника ля минор шестнадцатыми: должна сыграться без сдвигов руки.
    riff = [57, 60, 62, 64, 67, 69, 72, 69, 67, 64, 62, 60]
    path = finger_line([(i * 0.25, p) for i, p in enumerate(riff)], STANDARD, max_fret=12)
    hands = {f.hand for f in path if f.fret}
    assert len(hands) <= 2


def test_capo_shifts_sounding_pitch() -> None:
    capo = make_instrument("acoustic", "standard", capo=2)
    path = finger_line([(0.0, 66)], capo)  # F#4 = открытая первая струна с каподастром на 2
    assert (path[0].string, path[0].fret) == (1, 0)


def test_note_outside_the_neck_is_an_error() -> None:
    with pytest.raises(ValueError, match="гриф"):
        finger_line([(0.0, 20)], STANDARD)


def test_drop_d_reaches_low_d() -> None:
    drop_d = make_instrument("acoustic", "drop-d")
    path = finger_line([(0.0, 38)], drop_d)
    assert (path[0].string, path[0].fret) == (6, 0)
