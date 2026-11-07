"""Звук записи (сведение без дорожек) и текст песни через API."""

import json

import numpy as np
from fastapi.testclient import TestClient

from fretlines_api.settings import Settings
from fretlines_worker.audio import SAMPLE_RATE, encode_mp3

LINES = [
    {
        "start": 0.5,
        "end": 2.0,
        "words": [
            {"text": "Ой", "start": 0.5, "end": 0.9},
            {"text": "то", "start": 1.2, "end": 1.6},
        ],
    }
]


def test_lyrics_are_empty_then_saved(client: TestClient, ready_song: str) -> None:
    empty = client.get(f"/api/songs/{ready_song}/lyrics").json()
    assert empty["lines"] == []
    saved = client.put(f"/api/songs/{ready_song}/lyrics", json={"lines": LINES, "language": "ru"})
    assert saved.status_code == 200
    body = client.get(f"/api/songs/{ready_song}/lyrics").json()
    assert body["source"] == "edited"
    assert body["lines"][0]["words"][1]["text"] == "то"


def test_words_are_signed_under_the_tabs(
    client: TestClient, ready_song: str, settings: Settings
) -> None:
    folder = settings.song_dir(ready_song)
    analysis = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    analysis["beats"] = [i * 0.6 for i in range(32)]
    (folder / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    client.put(f"/api/songs/{ready_song}/lyrics", json={"lines": LINES})
    players = [{"id": "p1", "roles": ["melody"]}]
    body = client.post(f"/api/songs/{ready_song}/arrangement", json={"players": players}).json()
    assert "lyrics " in body["alphatex"]
    off = client.post(
        f"/api/songs/{ready_song}/arrangement", json={"players": players, "lyrics_in_tabs": False}
    ).json()
    assert "lyrics " not in off["alphatex"]


def test_analysis_reports_version_and_counts(client: TestClient, ready_song: str) -> None:
    body = client.get(f"/api/songs/{ready_song}/analysis").json()
    assert body["outdated"] is True  # разбор версии 1
    assert body["counts"]["guitar"] == 0
    assert body["bar_seconds"] == []


def test_mix_without_a_stem(client: TestClient, ready_song: str, settings: Settings) -> None:
    assert client.get(f"/api/songs/{ready_song}/mix?without=guitar").status_code == 404
    stems = settings.song_dir(ready_song) / "stems"
    stems.mkdir()
    t = np.arange(SAMPLE_RATE // 2) / SAMPLE_RATE
    for i, name in enumerate(["mix", "vocals", "bass", "drums", "guitar", "piano", "other"]):
        tone = (0.1 * np.sin(2 * np.pi * (220 + 40 * i) * t)).astype(np.float32)
        encode_mp3(np.stack([tone, tone]), stems / f"{name}.mp3", bitrate="64k")
    response = client.get(f"/api/songs/{ready_song}/mix?without=guitar,vocals,bogus")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert (stems / "mix-without-guitar+vocals.mp3").exists()
    whole = client.get(f"/api/songs/{ready_song}/mix")
    assert whole.status_code == 200
    assert whole.content == (stems / "mix.mp3").read_bytes()


def test_stem_downloads_and_instrumental(
    client: TestClient, ready_song: str, settings: Settings
) -> None:
    stems = settings.song_dir(ready_song) / "stems"
    (stems / "flac").mkdir(parents=True)
    t = np.arange(SAMPLE_RATE // 4) / SAMPLE_RATE
    tone = (0.1 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    for name in ["mix", "vocals", "bass", "drums", "guitar", "piano", "other", "instrumental"]:
        encode_mp3(np.stack([tone, tone]), stems / f"{name}.mp3", bitrate="64k")
    (stems / "flac" / "instrumental.flac").write_bytes(b"fLaC-test")
    (stems / "flac" / "vocals.flac").write_bytes(b"fLaC-test")

    flac = client.get(f"/api/songs/{ready_song}/download/instrumental?format=flac")
    assert flac.status_code == 200
    assert "attachment" in flac.headers["content-disposition"]
    assert client.get(f"/api/songs/{ready_song}/download/guitar?format=flac").status_code == 404
    assert client.get(f"/api/songs/{ready_song}/download/guitar?format=mp3").status_code == 200
    # «Без вокала» — это готовый инструментал, а не сведение дорожек.
    karaoke = client.get(f"/api/songs/{ready_song}/mix?without=vocals")
    assert karaoke.content == (stems / "instrumental.mp3").read_bytes()
    archive = client.get(f"/api/songs/{ready_song}/download-all")
    assert archive.status_code == 200
    assert archive.content[:2] == b"PK"
    body = client.get(f"/api/songs/{ready_song}/analysis").json()
    assert body["lossless"] == ["instrumental", "vocals"]
    assert body["separation"]["quality"] == "standard"
