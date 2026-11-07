"""Текст песни: LRC, поиск по названию, сверка готового текста с услышанными словами."""

from fretlines_worker.lyrics import (
    Lyrics,
    Word,
    _is_junk,
    align,
    build,
    has_cyrillic,
    lines_from_words,
    parse_lrc,
    search_terms,
)


def test_lrc_lines_and_repeated_stamps() -> None:
    text = "[00:12.50] When I find myself\n[01:02.00][02:10.25] Let it be\n[ar: Beatles]\n"
    assert parse_lrc(text) == [
        (12.5, "When I find myself"),
        (62.0, "Let it be"),
        (130.25, "Let it be"),
    ]


def test_search_terms_from_youtube_titles() -> None:
    assert search_terms("Кино - Группа крови (Official Video)", "KinoTV") == (
        "Группа крови",
        "Кино",
    )
    assert search_terms("Let It Be (Remastered 2009)", "The Beatles - Topic") == (
        "Let It Be",
        "The Beatles",
    )
    assert search_terms("Yesterday", "The Beatles") == ("Yesterday", "The Beatles")


def _heard(words: str, start: float, step: float = 0.5) -> list[Word]:
    return [Word(w, start + i * step, start + i * step + 0.4) for i, w in enumerate(words.split())]


def test_align_takes_text_from_lrc_and_timing_from_whisper() -> None:
    # Whisper ослышался в одном слове, а клип на 3 с длиннее — метки LRC сдвинуты.
    lrc = [
        (10.0, "Тёплое место, но улицы ждут"),
        (14.0, "Отпечатков наших ног"),
        (18.0, "Звёздная пыль"),
    ]
    heard = _heard("Тёплое мясо но улицы ждут", 13.0) + _heard("отпечатков наших ног", 17.0)
    heard += _heard("звёздная пыль", 21.0)
    lines, share = align(lrc, heard, duration=60.0)
    assert share > 0.8
    assert [line.text for line in lines] == [
        "Тёплое место, но улицы ждут",
        "Отпечатков наших ног",
        "Звёздная пыль",
    ]
    assert abs(lines[0].start - 13.0) < 0.01
    assert abs(lines[1].words[0].start - 17.0) < 0.01
    # «место» Whisper не услышал — слово стоит между соседями, по порядку
    first = lines[0].words
    assert first[0].end <= first[1].start <= first[2].start


def test_wrong_song_text_is_rejected_without_timing() -> None:
    plain = {"plainLyrics": "совсем другая песня\nпро другое", "syncedLyrics": None}
    heard = _heard("я пою свои слова здесь и сейчас", 5.0)
    result = build(found=plain, heard=heard, language="ru", duration=60.0)
    assert result.source == "whisper"
    assert result.lines[0].words[0].text == "я"


def test_whisper_only_lines_break_on_pauses() -> None:
    words = _heard("раз два три", 1.0) + _heard("четыре пять", 6.0)
    lines = lines_from_words(words)
    assert [line.text for line in lines] == ["раз два три", "четыре пять"]


def test_round_trip_and_helpers() -> None:
    lyrics = build(found=None, heard=_heard("hello world", 2.0), language="en", duration=10.0)
    again = Lyrics.from_dict(lyrics.to_dict())
    assert again.lines[0].text == "hello world"
    assert _is_junk("Субтитры сделал DimaTorzok")
    assert not _is_junk("Группа крови на рукаве")
    assert has_cyrillic("Пожелай мне удачи")
    assert not has_cyrillic("Let it be")
