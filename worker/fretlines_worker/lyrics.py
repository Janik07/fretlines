"""Текст песни с таймингом каждого слова — для караоке и подписей под табами.

1. Готовый текст ищется в открытой базе LRCLIB (lrclib.net) по названию и исполнителю —
   туда уходят только они, не звук. Там часто есть тайминг строк.
2. Whisper (faster-whisper) слушает вокальную дорожку и даёт слова с таймингом.
3. Если текст нашёлся, слова сверяются по порядку: у совпавших — время Whisper, остальные
   раскладываются по строке. Не нашёлся — показываем то, что услышал Whisper.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger("fretlines.lyrics")

WHISPER_SR = 16_000
LRCLIB = "https://lrclib.net/api"
USER_AGENT = "Fretlines/0.3 (guitar arranger; personal use)"

# Whisper на тишине и музыке любит «досочинять» титры — такие фразы выбрасываем.
_JUNK = (
    "субтитр",
    "продолжение следует",
    "спасибо за просмотр",
    "подписывайтесь",
    "редактор",
    "корректор",
    "dimatorzok",
    "amara.org",
    "thank you for watching",
    "thanks for watching",
    "subscribe",
)


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class Line:
    start: float
    end: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(frozen=True)
class Lyrics:
    source: str  # "lrclib", "lrclib+whisper", "whisper"
    language: str | None
    lines: tuple[Line, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "source": self.source,
            "language": self.language,
            "lines": [
                {
                    "start": round(line.start, 3),
                    "end": round(line.end, 3),
                    "words": [
                        {"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)}
                        for w in line.words
                    ],
                }
                for line in self.lines
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lyrics:
        return cls(
            source=str(data.get("source", "")),
            language=data.get("language"),
            lines=tuple(
                Line(
                    float(line["start"]),
                    float(line["end"]),
                    tuple(
                        Word(str(w["text"]), float(w["start"]), float(w["end"]))
                        for w in line["words"]
                    ),
                )
                for line in data.get("lines", [])
            ),
        )


# ─── LRCLIB ───────────────────────────────────────────────────────────────

_LRC_TIME = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_NOISE = re.compile(
    r"\((?:[^)]*(?:official|video|audio|lyric|клип|remaster|hd|hq|live|версия)[^)]*)\)"
    r"|\[(?:[^\]]*)\]",
    re.IGNORECASE,
)


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """«[01:02.50] слова» → [(62.5, "слова")]. Несколько меток на строке — повтор строки."""
    out: list[tuple[float, str]] = []
    for raw in text.splitlines():
        stamps = _LRC_TIME.findall(raw)
        words = _LRC_TIME.sub("", raw).strip()
        for minutes, seconds in stamps:
            out.append((int(minutes) * 60 + float(seconds), words))
    out.sort(key=lambda item: item[0])
    return out


def search_terms(title: str, artist: str | None) -> tuple[str, str | None]:
    """Название с YouTube «Исполнитель - Песня (Official Video)» → ("Песня", "Исполнитель")."""
    clean = _NOISE.sub("", title).strip()
    clean = re.sub(r"\s+", " ", clean)
    if " - " in clean or " – " in clean or " — " in clean:
        # «Исполнитель - Песня»: левая часть надёжнее, чем имя канала, который залил видео.
        left, right = re.split(r"\s+[-–—]\s+", clean, maxsplit=1)
        return right.strip(" \"'«»"), left.strip()
    if artist and artist.lower().endswith(" - topic"):
        artist = artist[: -len(" - topic")]
    return clean.strip(" \"'«»"), artist


def fetch_lrclib(
    title: str, artist: str | None, duration: float, timeout: float = 8.0
) -> dict[str, Any] | None:
    """Лучшая запись LRCLIB: совпадает по длительности (±8 с), с таймингом — в приоритете."""
    track, who = search_terms(title, artist)
    if not track:
        return None
    query = {"track_name": track}
    if who:
        query["artist_name"] = who
    url = f"{LRCLIB}/search?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            found = json.loads(response.read())
    except (OSError, ValueError) as error:
        log.warning("LRCLIB недоступен: %s", error)
        return None
    if not isinstance(found, list):
        return None

    def rank(item: dict[str, Any]) -> tuple[int, float]:
        gap = abs(float(item.get("duration") or 0) - duration)
        return (0 if item.get("syncedLyrics") else 1, gap)

    candidates = [
        item
        for item in found
        if isinstance(item, dict)
        and not item.get("instrumental")
        and (item.get("syncedLyrics") or item.get("plainLyrics"))
        and abs(float(item.get("duration") or 0) - duration) <= 8
    ]
    if not candidates:
        return None
    return min(candidates, key=rank)


# ─── Whisper ──────────────────────────────────────────────────────────────


def _is_junk(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _JUNK)


def hear_words(
    vocals: NDArray[np.float32],
    *,
    model_name: str,
    device: str,
    language: str | None,
    download_root: Path,
) -> tuple[list[Word], str | None]:
    """Слова вокальной дорожки (16 кГц моно) с таймингом и язык."""
    from faster_whisper import WhisperModel

    def load(on: str) -> Any:  # noqa: ANN401 — у faster-whisper нет типов
        return WhisperModel(
            model_name,
            device=on,
            compute_type="int8" if on == "cpu" else "float16",
            download_root=str(download_root),
        )

    try:
        model = load(device)
    except Exception:  # нет CUDA-библиотек для CTranslate2 — работаем на процессоре
        if device == "cpu":
            raise
        log.warning("Whisper не запустился на %s — перехожу на процессор", device)
        model = load("cpu")

    segments, info = model.transcribe(
        vocals,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 600},
        condition_on_previous_text=False,
        beam_size=5,
        temperature=(0.0, 0.2, 0.4),
        no_speech_threshold=0.6,
        hallucination_silence_threshold=2.0,
    )
    words: list[Word] = []
    for segment in segments:
        if _is_junk(segment.text):
            continue
        if segment.no_speech_prob > 0.6 and segment.avg_logprob < -0.8:
            continue
        for w in segment.words or ():
            text = w.word.strip()
            if text and w.end > w.start:
                words.append(Word(text, float(w.start), float(w.end)))
    return words, getattr(info, "language", language)


# ─── Сборка строк ─────────────────────────────────────────────────────────


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower().replace("ё", "е"))


def _split_words(text: str) -> list[str]:
    return [w for w in text.split() if _norm(w)]


def _spread(texts: list[str], start: float, end: float) -> list[Word]:
    """Слова без своего тайминга — равномерно по длине между start и end."""
    if not texts:
        return []
    weights = [max(1, len(_norm(t))) + 1 for t in texts]
    total = sum(weights)
    out: list[Word] = []
    t = start
    for text, weight in zip(texts, weights, strict=True):
        length = (end - start) * weight / total
        out.append(Word(text, t, t + length * 0.92))
        t += length
    return out


def lines_from_words(words: list[Word], gap: float = 0.75, longest: int = 9) -> list[Line]:
    """Только Whisper: строка обрывается на паузе или когда в ней слишком много слов."""
    lines: list[Line] = []
    current: list[Word] = []
    for word in words:
        too_long = len(current) >= longest
        paused = bool(current) and word.start - current[-1].end > gap
        ends_phrase = bool(current) and current[-1].text.endswith((".", "!", "?", ","))
        if current and (paused or too_long or (ends_phrase and len(current) >= 4)):
            lines.append(Line(current[0].start, current[-1].end, tuple(current)))
            current = []
        current.append(word)
    if current:
        lines.append(Line(current[0].start, current[-1].end, tuple(current)))
    return lines


def align(
    text_lines: list[tuple[float | None, str]], heard: list[Word], duration: float
) -> tuple[list[Line], float]:
    """Готовый текст + услышанные слова → строки с таймингом. Второе значение — доля совпавших.

    Метки времени из LRC могут быть сдвинуты относительно нашей записи (вступление в клипе):
    сдвиг оцениваем по совпавшим словам.
    """
    tokens: list[tuple[int, str]] = []  # (номер строки, слово)
    for index, (_, text) in enumerate(text_lines):
        tokens.extend((index, w) for w in _split_words(text))
    if not tokens:
        return [], 0.0
    matcher = difflib.SequenceMatcher(
        None, [_norm(w) for _, w in tokens], [_norm(w.text) for w in heard], autojunk=False
    )
    timing: dict[int, Word] = {}
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            timing[block.a + k] = heard[block.b + k]
    share = len(timing) / len(tokens)

    # Сдвиг LRC-меток: где первое слово строки совпало — сравниваем со временем строки.
    offsets = []
    first_token: dict[int, int] = {}
    for position, (index, _) in enumerate(tokens):
        first_token.setdefault(index, position)
    for index, position in first_token.items():
        stamp = text_lines[index][0]
        if stamp is not None and position in timing:
            offsets.append(timing[position].start - stamp)
    shift = statistics.median(offsets) if len(offsets) >= 3 else 0.0
    if abs(shift) < 0.25:
        shift = 0.0

    # Опорные начала строк: метка LRC (со сдвигом) или время первого совпавшего слова.
    starts: list[float | None] = []
    for index, (stamp, _) in enumerate(text_lines):
        own = [timing[p].start for p, (i, _) in enumerate(tokens) if i == index and p in timing]
        if stamp is not None:
            starts.append(stamp + shift)
        elif own:
            starts.append(own[0])
        else:
            starts.append(None)
    known = [i for i, s in enumerate(starts) if s is not None]
    if not known:
        return [], share
    for i in range(len(starts)):  # строки без опоры — между соседями
        if starts[i] is None:
            before = max((k for k in known if k < i), default=None)
            after = min((k for k in known if k > i), default=None)
            if before is not None and after is not None:
                a, b = starts[before], starts[after]
                assert a is not None
                assert b is not None
                starts[i] = a + (b - a) * (i - before) / (after - before)
            else:
                anchor = starts[before if before is not None else after]  # type: ignore[index]
                assert anchor is not None
                starts[i] = anchor + 3.0 * (i - (before if before is not None else after or 0))

    lines: list[Line] = []
    for index in range(len(text_lines)):
        positions = [p for p, (i, _) in enumerate(tokens) if i == index]
        if not positions:
            continue
        start = float(starts[index] or 0.0)
        following = [s for s in starts[index + 1 :] if s is not None and s > start]
        limit = min(following[0] if following else duration, duration)
        # Строка не длиннее, чем её реально поют: ~0.45 с на слово плюс запас.
        end = min(limit - 0.05, start + 0.45 * len(positions) + 1.2)
        matched = [timing[p] for p in positions if p in timing and start - 1 <= timing[p].start]
        if matched:
            end = max(end, min(limit - 0.05, matched[-1].end))
        words: list[Word] = []
        pending: list[str] = []
        cursor = start
        for p in positions:
            word = tokens[p][1]
            got = timing.get(p)
            if got is not None and cursor - 0.3 <= got.start <= end + 0.5:
                words.extend(_spread(pending, cursor, got.start))
                pending = []
                words.append(Word(word, got.start, got.end))
                cursor = got.end
            else:
                pending.append(word)
        words.extend(_spread(pending, cursor, max(end, cursor + 0.3 * len(pending))))
        if words:
            last = max(words[-1].end, words[0].start + 0.2)
            lines.append(Line(words[0].start, last, tuple(words)))
    return lines, share


def build(
    *,
    found: dict[str, Any] | None,
    heard: list[Word],
    language: str | None,
    duration: float,
) -> Lyrics:
    """Итоговый текст из того, что есть: LRCLIB, Whisper или оба."""
    if found is not None:
        synced = parse_lrc(str(found.get("syncedLyrics") or ""))
        text_lines: list[tuple[float | None, str]]
        if synced:
            text_lines = [(t, line) for t, line in synced if line]
        else:
            plain = str(found.get("plainLyrics") or "")
            text_lines = [(None, line.strip()) for line in plain.splitlines() if line.strip()]
        lines, share = align(text_lines, heard, duration)
        # Без меток и почти без совпадений — значит, текст от другой песни или версии.
        if lines and (synced or share >= 0.25):
            source = "lrclib+whisper" if share >= 0.15 else "lrclib"
            return Lyrics(source, language, tuple(lines))
    return Lyrics("whisper", language, tuple(lines_from_words(heard)))


def has_cyrillic(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return sum("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in letters) / len(letters) > 0.3
