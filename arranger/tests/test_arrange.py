import re
import time

import pytest

from arranger import PRESETS, arrange, arrangement_to_dict, preset_players, to_alphatex
from arranger.arrange import PlayerSetup
from arranger.instruments import make_instrument
from arranger.model import STEPS_PER_BEAT, Difficulty, Part, Transcription
from arranger.parts import playability_issues
from arranger.voicings import SPAN


def _issues(part: Part) -> list[str]:
    instrument = make_instrument(part.instrument_kind, part.tuning_id, part.capo)
    return playability_issues(part.beats, instrument, SPAN[part.difficulty])


@pytest.mark.parametrize("preset", list(PRESETS))
@pytest.mark.parametrize("level", ["easy", "medium", "full"])
def test_every_preset_is_playable(song: Transcription, preset: str, level: Difficulty) -> None:
    players = [
        PlayerSetup(p.id, p.name, roles=p.roles, difficulty=level) for p in preset_players(preset)
    ]
    result = arrange(song, players)
    assert len(result.parts) == len(players)
    for part in result.parts:
        assert part.beats, part.title
        assert _issues(part) == []
        total = song.bars * song.beats_per_bar * STEPS_PER_BEAT
        assert all(0 <= b.start < total and b.duration > 0 for b in part.beats)


def test_easy_rhythm_is_quarter_strums_with_chord_names(song: Transcription) -> None:
    rhythm = arrange(song, [PlayerSetup("r", "Аня", roles=("rhythm",), difficulty="easy")]).parts[0]
    first_bar = [b for b in rhythm.beats if b.start < 16]
    assert [b.start for b in first_bar] == [0, 4, 8, 12]
    assert all(b.stroke == "down" for b in first_bar)
    labels = [b.chord for b in rhythm.beats if b.chord]
    assert labels == ["C", "G", "Am", "F"]


def test_bass_stays_on_low_strings(song: Transcription) -> None:
    bass = arrange(song, [PlayerSetup("b", "Бас", roles=("bass",))]).parts[0]
    assert all(n.string >= 4 for b in bass.beats for n in b.notes)


def test_melody_follows_the_transcription(song: Transcription) -> None:
    melody = arrange(song, [PlayerSetup("m", "", roles=("melody",), difficulty="full")]).parts[0]
    pitches = [b.notes[0].pitch % 12 for b in melody.beats]
    assert pitches == [n.pitch % 12 for n in song.melody]


def test_transpose_moves_everything(song: Transcription) -> None:
    up = arrange(song, [PlayerSetup("r", "", roles=("rhythm",))], transpose=2)
    names = [c.name for bar in up.chart for c in bar]
    assert names == ["D", "A", "Bm", "G"]
    assert up.key.name == "D"

    base = arrange(song, [PlayerSetup("m", "", roles=("melody",), difficulty="full")])
    shifted = arrange(song, [PlayerSetup("m", "", roles=("melody",), difficulty="full")], 2)
    for a, b in zip(base.parts[0].beats, shifted.parts[0].beats, strict=True):
        assert (b.notes[0].pitch - a.notes[0].pitch) % 12 == 2


def test_capo_shapes_are_named_relative_to_capo(song: Transcription) -> None:
    capo = arrange(song, [PlayerSetup("r", "", capo=5, roles=("rhythm",))]).parts[0]
    labels = [b.chord for b in capo.beats if b.chord]
    assert labels == ["G", "D", "Em", "C"]  # звучат как C G Am F


def test_bass_guitar_refuses_chords(song: Transcription) -> None:
    part = arrange(
        song, [PlayerSetup("b", "", kind="bass", tuning="bass-standard", roles=("rhythm",))]
    ).parts[0]
    assert part.roles == ("bass",)
    assert part.warnings
    assert all(n.string <= 4 for b in part.beats for n in b.notes)


def test_rearrangement_is_fast(song: Transcription) -> None:
    long_song = Transcription(
        tempo=song.tempo,
        beats_per_bar=4,
        bars=song.bars * 12,
        key=song.key,
        chords=tuple(
            type(c)(c.start + k * 32, c.end + k * 32, c.chord)
            for k in range(12)
            for c in song.chords
        ),
        melody=tuple(
            type(n)(n.start + k * 32, n.duration, n.pitch) for k in range(12) for n in song.melody
        ),
        bass=tuple(
            type(n)(n.start + k * 32, n.duration, n.pitch) for k in range(12) for n in song.bass
        ),
        accents=song.accents,
    )
    started = time.perf_counter()
    for level in ("easy", "medium", "full"):
        players = [
            PlayerSetup(p.id, p.name, roles=p.roles, difficulty=level)  # type: ignore[arg-type]
            for p in preset_players("quartet")
        ]
        arrange(long_song, players, transpose=3)
    assert (time.perf_counter() - started) / 3 < 1.0  # SPEC §1.5: пересчёт ≤ 1 с


def test_alphatex_has_a_track_per_part_and_all_bars(song: Transcription) -> None:
    result = arrange(song, preset_players("trio"))
    text = to_alphatex(result, title="Тест", artist="Мы")
    assert text.count("\\track") == 3
    assert "\\tuning (E4 B3 G3 D3 A2 E2)" in text
    assert '\\title "\\u0422\\u0435\\u0441\\u0442"' in text
    for track in text.split("\\track")[1:]:
        assert track.count("|") == song.bars
    assert re.search(r"\{[^}]*bd[^}]*ch \"C\"", text)


_BEAT = re.compile(r"(?:\([^)]*\)|r|[-\d]+\.\d+)\.(1|2|4|8|16)(?: \{([^}]*)\})?")


def test_alphatex_bars_add_up(song: Transcription) -> None:
    values = {"1": 16, "2": 8, "4": 4, "8": 2, "16": 1}
    result = arrange(song, preset_players("quartet"))
    for track in to_alphatex(result, title="t").split("\\track")[1:]:
        bars = [line for line in track.splitlines() if line.endswith("|")]
        assert len(bars) == song.bars
        for bar in bars:
            body = re.sub(r"^\\ts \(\d+ \d+\) ", "", bar)
            steps = sum(
                values[v] * (1.5 if p and "d" in p.split() else 1) for v, p in _BEAT.findall(body)
            )
            assert steps == 16, bar


def test_serialization_for_the_ui(song: Transcription) -> None:
    data = arrangement_to_dict(arrange(song, preset_players("duo")))
    assert data["key"] == "C"
    assert len(data["parts"]) == 2
    assert data["chart"][0][0] == {"offset": 0, "name": "C"}
    assert data["capo_hints"]


def test_transcription_round_trip(song: Transcription) -> None:
    assert Transcription.from_dict(song.to_dict()) == song
