"""Pure-stdlib script chunking for ChinAI.

Splits a script into small, speakable chunks: paragraphs become sentence
groups merged up to a character budget, and any sentence that still exceeds
the budget is split at the nearest safe boundary. Downstream synthesis
engines consume these chunks one at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 280
INTRA_PARAGRAPH_PAUSE_SECONDS = 0.35
INTER_PARAGRAPH_PAUSE_SECONDS = 0.7

_SENTENCE_END_CHARS = ".!?…"

# Known abbreviations whose trailing period must not be treated as a
# sentence boundary. Matched (case-insensitively) against the token that
# immediately precedes the period.
_KNOWN_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "approx", "inc", "ltd", "co", "corp", "ave", "blvd",
    "no", "u.s", "u.k", "vol", "fig", "dept", "p.m", "a.m",
}

_TRAILING_WORD_PATTERN = re.compile(r"([A-Za-z.]+)$")


@dataclass
class Chunk:
    """A single speakable unit of a script.

    `emphasis` marks a chunk that overlapped an inline emphasis span
    (`*word*` / `[emph]...[/emph]`); the engine delivers it with raised
    exaggeration. Plain chunking never sets it — see `chinai.prosody`.
    """

    text: str
    pause_after: float
    emphasis: bool = False


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines)


def _split_paragraphs(text: str) -> list[str]:
    normalized = _normalize_whitespace(text)
    raw_paragraphs = re.split(r"\n\s*\n", normalized)
    return [p.replace("\n", " ").strip() for p in raw_paragraphs if p.strip()]


def _ends_with_known_abbreviation(text_up_to_period: str) -> bool:
    match = _TRAILING_WORD_PATTERN.search(text_up_to_period)
    if not match:
        return False
    token = match.group(1).rstrip(".").lower()
    return token in _KNOWN_ABBREVIATIONS


def _split_sentences(paragraph: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    length = len(paragraph)

    for index, char in enumerate(paragraph):
        if char not in _SENTENCE_END_CHARS:
            continue

        is_end_of_text = index + 1 == length
        followed_by_space = not is_end_of_text and paragraph[index + 1] == " "
        if not (is_end_of_text or followed_by_space):
            continue

        candidate = paragraph[start:index + 1]
        if char == "." and _ends_with_known_abbreviation(candidate):
            continue

        stripped = candidate.strip()
        if stripped:
            sentences.append(stripped)
        start = index + 1

    remainder = paragraph[start:].strip()
    if remainder:
        sentences.append(remainder)

    return sentences


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]

    pieces: list[str] = []
    remaining = sentence
    while len(remaining) > max_chars:
        window = remaining[:max_chars]

        split_at = -1
        for separator in (",", ";"):
            idx = window.rfind(separator)
            if idx > split_at:
                split_at = idx

        if split_at == -1:
            split_at = window.rfind(" ")

        if split_at <= 0:
            split_at = max_chars - 1

        pieces.append(remaining[:split_at + 1].strip())
        remaining = remaining[split_at + 1:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces


def _merge_sentences(sentences: list[str], max_chars: int) -> list[str]:
    merged: list[str] = []
    current = ""

    for sentence in sentences:
        for piece in _split_long_sentence(sentence, max_chars):
            if not current:
                current = piece
                continue

            candidate = f"{current} {piece}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                merged.append(current)
                current = piece

    if current:
        merged.append(current)

    return merged


def split_script(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Split `text` into speakable Chunks.

    Paragraphs (separated by blank lines) are split into sentences, which are
    then greedily merged up to `max_chars`. Sentences longer than max_chars
    are split at the nearest comma, semicolon, or space below the limit.
    Chunks within a paragraph pause 0.35s after speaking; the last chunk of
    a paragraph pauses 0.7s.

    Raises:
        ValueError: if `text` is empty or contains no speakable content.
    """
    if not text or not text.strip():
        raise ValueError("the script is empty; provide text to synthesize.")

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        raise ValueError("the script is empty; provide text to synthesize.")

    chunks: list[Chunk] = []
    for paragraph in paragraphs:
        sentences = _split_sentences(paragraph)
        merged = _merge_sentences(sentences, max_chars)

        for position, chunk_text in enumerate(merged):
            is_last_in_paragraph = position == len(merged) - 1
            pause = (
                INTER_PARAGRAPH_PAUSE_SECONDS
                if is_last_in_paragraph
                else INTRA_PARAGRAPH_PAUSE_SECONDS
            )
            chunks.append(Chunk(text=chunk_text, pause_after=pause))

    return chunks
