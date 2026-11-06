import io
import time

from fastapi.testclient import TestClient

from fretlines_api.settings import Settings


def test_health_reports_components(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["storage"]["ok"] is True
    assert body["checks"]["ffmpeg"]["ok"] is True
    assert body["torch_build"] in ("cpu", "cuda")


def test_meta_lists_tunings_and_presets(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    assert {t["id"] for t in body["tunings"]} >= {"standard", "drop-d", "bass-standard"}
    assert [p["id"] for p in body["presets"]] == ["solo", "duo", "trio", "quartet"]
    standard = next(t for t in body["tunings"] if t["id"] == "standard")
    assert standard["notes"] == ["E4", "B3", "G3", "D3", "A2", "E2"]


def test_upload_creates_a_queued_song(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/api/songs",
        files={"file": ("Моя_песня.mp3", io.BytesIO(b"ID3" + b"\0" * 2048), "audio/mpeg")},
    )
    assert response.status_code == 201
    song = response.json()
    assert song["title"] == "Моя песня"
    assert song["status"] == "queued"
    assert (settings.song_dir(song["id"]) / "source.mp3").stat().st_size == 2051
    assert [s["id"] for s in client.get("/api/songs").json()] == [song["id"]]


def test_upload_rejects_unknown_format_and_big_files(
    client: TestClient, settings: Settings
) -> None:
    bad = client.post("/api/songs", files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")})
    assert bad.status_code == 415
    assert "mp3" in bad.json()["detail"]
    big = client.post(
        "/api/songs", files={"file": ("big.wav", io.BytesIO(b"0" * (2 * 1024 * 1024)), "audio/wav")}
    )
    assert big.status_code == 413
    assert "1 МБ" in big.json()["detail"]
    assert not any((settings.storage_dir / "songs").iterdir())


def test_import_checks_the_link(client: TestClient) -> None:
    bad = client.post("/api/songs/import", json={"url": "просто текст"})
    assert bad.status_code == 422
    ok = client.post("/api/songs/import", json={"url": "https://www.youtube.com/watch?v=abc"})
    assert ok.status_code == 201
    song = ok.json()
    assert song["source_kind"] == "url"
    assert song["title"] == "Трек с youtube.com"


def test_arrangement_for_a_band(client: TestClient, ready_song: str) -> None:
    players = [
        {"id": "a", "name": "Аня", "roles": ["melody"], "difficulty": "medium"},
        {"id": "b", "name": "Макс", "roles": ["rhythm"], "difficulty": "easy", "capo": 0},
        {
            "id": "c",
            "name": "Лёша",
            "roles": ["bass"],
            "instrument": "bass",
            "tuning": "bass-standard",
        },
    ]
    started = time.perf_counter()
    response = client.post(
        f"/api/songs/{ready_song}/arrangement", json={"players": players, "transpose": 2}
    )
    assert time.perf_counter() - started < 1.0
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "Bm"
    assert [p["player_id"] for p in body["parts"]] == ["a", "b", "c"]
    assert body["alphatex"].count("\\track") == 3
    assert body["chart"][0][0]["name"] == "Bm"
    assert "b" in body["capo_hints"]


def test_arrangement_needs_a_finished_analysis(client: TestClient) -> None:
    song = client.post("/api/songs/import", json={"url": "https://youtu.be/xyz"}).json()
    response = client.post(
        f"/api/songs/{song['id']}/arrangement", json={"players": [{"id": "a", "roles": ["rhythm"]}]}
    )
    assert response.status_code == 409


def test_setup_is_saved_with_the_song(client: TestClient, ready_song: str) -> None:
    setup = {
        "players": [{"id": "p1", "name": "Я", "roles": ["rhythm"]}],
        "transpose": -1,
        "mine": "p1",
    }
    client.patch(f"/api/songs/{ready_song}", json={"setup": setup, "title": "Новое имя"})
    song = client.get(f"/api/songs/{ready_song}").json()
    assert song["setup"] == setup
    assert song["title"] == "Новое имя"


def test_delete_removes_files(client: TestClient, ready_song: str, settings: Settings) -> None:
    assert client.delete(f"/api/songs/{ready_song}").status_code == 204
    assert not settings.song_dir(ready_song).exists()
    assert client.get(f"/api/songs/{ready_song}").status_code == 404


def test_missing_audio_is_404(client: TestClient, ready_song: str) -> None:
    assert client.get(f"/api/songs/{ready_song}/audio/vocals").status_code == 404
    assert client.get(f"/api/songs/{ready_song}/audio/../../secret").status_code in (404, 422)


def test_frontend_placeholder_when_not_built(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "start.bat" in response.text
