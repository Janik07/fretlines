"""Партия «как в записи», темп по тактам и слова под нотами."""

import re
from dataclasses import replace

from arranger import arrange, to_alphatex
from arranger.alphatex import bar_tempos
from arranger.arrange import PlayerSetup
from arranger.fingering import chord_options, finger_events
from arranger.instruments import make_instrument
from arranger.model import STEPS_PER_BEAT, Note, Transcription


def _strummed_then_riff(song: Transcription) -> Transcription:
    """Такты 1–2 — бой восьмыми по C (ноты удара чуть врозь), такт 5 — рифф по одной ноте."""
    notes: list[Note] = []
    for eighth in range(16):
        start = eighth * 0.5
        for k, pitch in enumerate((48, 52, 55, 60, 64)):
            notes.append(Note(start + k * 0.03, 0.45, pitch, 100))
    for k, pitch in enumerate((55, 57, 59, 60, 62, 60, 59, 57)):
        notes.append(Note(16.0 + k * 0.5, 0.45, pitch, 90))
    return replace(song, guitar=tuple(notes), guitar_source="guitar")


def _player(level: str = "medium") -> PlayerSetup:
    return PlayerSetup(id="p1", name="Гитара", roles=("original",), difficulty=level)  # type: ignore[arg-type]


def test_strums_become_chord_shapes_and_riffs_single_notes(song: Transcription) -> None:
    tx = _strummed_then_riff(song)
    part = arrange(tx, [_player("medium")]).parts[0]
    assert part.roles == ("original",)
    bar = 4 * STEPS_PER_BEAT
    strums = [b for b in part.beats if b.start < 2 * bar]
    riff = [b for b in part.beats if 4 * bar <= b.start < 5 * bar]
    assert len(strums) == 16  # восьмые, ни один удар не развалился на два
    assert all(len(b.notes) >= 4 and b.stroke for b in strums)
    assert {b.stroke for b in strums} == {"down", "up"}  # вниз на долю, вверх между
    assert strums[0].chord == "C"
    assert [len(b.notes) for b in riff] == [1] * 8
    assert [b.notes[0].pitch for b in riff] == [55, 57, 59, 60, 62, 60, 59, 57]
    assert any(s.name == "C" for s in part.shapes)


def test_strum_heard_only_by_its_top_string_is_played_as_full_strokes(song: Transcription) -> None:
    # На отделённой дорожке модель часто слышит в бое лишь верхнюю струну: E4, E4, G4, E4…
    tops = [64, 64, 67, 64] * 4
    notes = tuple(Note(i * 0.25, 0.2, pitch, 90) for i, pitch in enumerate(tops))
    part = arrange(replace(song, guitar=notes, guitar_source="guitar"), [_player("full")]).parts[0]
    bar = [b for b in part.beats if b.start < 4 * STEPS_PER_BEAT]
    assert len(bar) == 16
    assert all(len(b.notes) >= 3 for b in bar)
    assert [b.stroke for b in bar[:4]] == ["down", "up", "down", "up"]
    assert all(b.notes[0].string == 1 for b in bar)  # и вниз, и вверх задевают тонкие струны


def test_shape_is_taken_where_the_recording_is_played(song: Transcription) -> None:
    # Перебор по C на восьмом ладу: C4 E4 G4 C5 — внизу грифа так не взять.
    pattern = [60, 64, 67, 72, 67, 64] * 2
    notes = tuple(Note(i * 0.5, 0.45, pitch, 90) for i, pitch in enumerate(pattern))
    part = arrange(replace(song, guitar=notes, guitar_source="guitar"), [_player("full")]).parts[0]
    picked = [b for b in part.beats if b.start < 8 * STEPS_PER_BEAT]
    assert [b.notes[0].pitch for b in picked] == pattern  # высоты те же, без переноса октав
    frets = [n.fret for b in picked for n in b.notes]
    assert min(frets) >= 5  # не внизу грифа
    assert max(frets) - min(frets) < 4  # одна аппликатура


def test_picked_notes_stay_in_the_chord_and_stray_ones_are_dropped(song: Transcription) -> None:
    # Перебор по C восьмыми; C#4 — просочившийся соседний инструмент.
    pattern = [*[48, 55, 60, 64, 60, 55, 48, 55], *[48, 55, 61, 64, 60, 55, 48, 55]]
    notes = tuple(Note(i * 0.5, 0.45, pitch, 90) for i, pitch in enumerate(pattern))
    part = arrange(replace(song, guitar=notes, guitar_source="guitar"), [_player("full")]).parts[0]
    pitches = [n.pitch for b in part.beats for n in b.notes]
    assert len(pitches) == len(pattern) - 1
    assert all(p % 12 in (0, 4, 7) for p in pitches)
    assert all(b.stroke is None for b in part.beats)  # это перебор, а не бой


def test_note_an_octave_above_everything_else_is_dropped(song: Transcription) -> None:
    pattern = [48, 55, 60, 64, 60, 55, 84, 55]  # C6 — обертон, его не играют
    notes = tuple(Note(i * 0.5, 0.45, pitch, 90) for i, pitch in enumerate(pattern))
    part = arrange(replace(song, guitar=notes, guitar_source="guitar"), [_player("full")]).parts[0]
    pitches = [n.pitch for b in part.beats for n in b.notes]
    assert max(pitches) <= 64
    assert max(n.fret for b in part.beats for n in b.notes) <= 5


def test_easy_level_keeps_only_strums_on_the_beat(song: Transcription) -> None:
    part = arrange(_strummed_then_riff(song), [_player("easy")]).parts[0]
    strums = [b for b in part.beats if b.start < 2 * 4 * STEPS_PER_BEAT]
    assert len(strums) == 8
    assert all(b.start % STEPS_PER_BEAT == 0 and b.stroke == "down" for b in strums)


def test_without_recorded_notes_original_falls_back_to_rhythm(song: Transcription) -> None:
    part = arrange(song, [_player()]).parts[0]
    assert part.roles == ("rhythm",)
    assert part.beats
    assert any("как в записи" in w for w in part.warnings)


def test_chord_options_use_distinct_strings_within_the_span() -> None:
    guitar = make_instrument("acoustic", "standard", 0)
    options = chord_options([48, 52, 55, 60], guitar, span=4, top=12)
    assert options
    for option in options:
        strings = [s for s, _ in option]
        assert len(set(strings)) == len(strings)
        fretted = [f for _, f in option if f > 0]
        assert not fretted or max(fretted) - min(fretted) < 4


def test_finger_events_skip_what_cannot_be_played_and_keep_fixed_shapes() -> None:
    guitar = make_instrument("acoustic", "standard", 0)
    fixed = ((2, 1), (4, 2), (5, 3))
    result = finger_events(
        [(0.0, (60, 64), None), (1.0, (40, 41), None), (2.0, (48, 52, 60), fixed)],
        guitar,
        span=4,
        max_fret=12,
    )
    assert result[0] is not None
    assert result[1] is None  # E2 и F2 — только на шестой струне разом не взять
    assert result[2] == fixed


def test_bar_tempos_follow_the_recording() -> None:
    assert bar_tempos([0.0, 2.0, 4.1, 6.0], 4, 3) == [120.0, 114.29, 126.32]
    assert bar_tempos([0.0, 2.0], 4, 3) is None


def test_alphatex_writes_live_tempo_and_lyrics(song: Transcription) -> None:
    seconds = tuple(round(i * 2.5 + (0.1 if i % 2 else 0.0), 3) for i in range(song.bars + 1))
    tx = replace(song, bar_seconds=seconds)
    result = arrange(tx, [PlayerSetup(id="p1", name="", roles=("melody",))])
    text = to_alphatex(result, title="t", words=[(0, "Ой"), (8, "то-"), (9, "поль")])
    tempos = re.findall(r"\\tempo ([\d.]+)", text)
    assert len(tempos) >= 4
    assert float(tempos[0]) != round(float(tempos[0]))
    assert 'lyrics "\\u041e\\u0439"' in text  # «Ой» под первой нотой
    # «то-» и «поль» спеты на одной ноте — подпись одна, слова через пробел.
    assert text.count("lyrics ") == 2
    assert 'lyrics "\\u0442\\u043e- \\u043f\\u043e\\u043b\\u044c"' in text
