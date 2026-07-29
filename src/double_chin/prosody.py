"""Inline prosody markup for Double Chin scripts.

Chatterbox has no SSML. This module compiles a tiny, honest markup into the
real levers the engine already has — controlled stitched silence and
per-chunk emotional intensity — rather than faking tags the model would only
read aloud. Two directives are supported:

    [pause:N]  /  [break]        insert N seconds (or DEFAULT_BREAK_SECONDS)
                                 of stitched silence at that point in the text.
    *emphasis* / [emph]...[/emph]  deliver the spanned words with raised
                                 exaggeration (and slightly lower cfg_weight).

Everything else flows through verbatim. Unknown or unbalanced markup degrades
gracefully: stray/mismatched tags are stripped so they are never spoken aloud,
malformed pause tokens are dropped, and lone asterisks that aren't part of a
pair are kept as literal text.

`compile_script` is the single entry point the engine uses. With no markup it
is byte-for-byte equivalent to `chunk.split_script`, so existing callers are
unaffected.
"""

from __future__ import annotations

import re
from dataclasses import replace

from double_chin.chunk import DEFAULT_MAX_CHARS, Chunk, split_script

# Default silence for a bare `[break]`, in seconds.
DEFAULT_BREAK_SECONDS = 0.5
# Clamp explicit `[pause:N]` requests so a typo can't stitch a minute of dead air.
MAX_PAUSE_SECONDS = 10.0
# How much an emphasized chunk raises generation-time exaggeration, and lowers
# cfg_weight, relative to the run's base values. Applied in engine.synthesize.
EMPHASIS_EXAGGERATION_BONUS = 0.3
EMPHASIS_CFG_WEIGHT_REDUCTION = 0.1

# [pause:0.8] (captured group) or [break] (no group). Case-insensitive.
_PAUSE_RE = re.compile(r"\[pause:\s*([0-9]*\.?[0-9]+)\s*\]|\[break\]", re.IGNORECASE)


def _split_runs(text: str) -> list[tuple[str, float | None]]:
    """Split `text` on explicit pause directives.

    Returns (segment_text, pause_after) pairs: the pause is the silence to
    stitch immediately after that segment, or None for the final segment.
    """
    runs: list[tuple[str, float | None]] = []
    pos = 0
    for match in _PAUSE_RE.finditer(text):
        segment = text[pos:match.start()]
        if match.group(1) is not None:
            seconds = min(float(match.group(1)), MAX_PAUSE_SECONDS)
        else:
            seconds = DEFAULT_BREAK_SECONDS
        runs.append((segment, seconds))
        pos = match.end()
    runs.append((text[pos:], None))
    return runs


def _closing_star_on_line(text: str, start: int) -> bool:
    """True if a closing `*` appears before the next newline at/after `start`."""
    star = text.find("*", start)
    if star == -1:
        return False
    newline = text.find("\n", start)
    return newline == -1 or star < newline


def _extract_emphasis(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Strip emphasis markup, returning clean text and emphasized char ranges.

    Handles `*word*` pairs and `[emph]...[/emph]` spans in a single pass so
    mixed, nested-looking, or unbalanced markup never crashes and never leaks a
    tag into the spoken text. Ranges are half-open `(start, end)` offsets into
    the returned clean text.
    """
    out: list[str] = []
    clean_len = 0
    ranges: list[tuple[int, int]] = []
    open_kind: str | None = None  # "*" or "[" — the currently open emphasis
    emph_start = 0
    index = 0
    length = len(text)

    while index < length:
        rest_lower = text[index:index + 7].lower()

        if rest_lower.startswith("[emph]"):
            if open_kind is None:
                open_kind, emph_start = "[", clean_len
            index += len("[emph]")
            continue
        if text[index:index + 7].lower() == "[/emph]":
            if open_kind == "[":
                ranges.append((emph_start, clean_len))
                open_kind = None
            # a stray [/emph] with nothing open is simply dropped
            index += len("[/emph]")
            continue
        if rest_lower.startswith("[pause:"):
            # A malformed / unsplit pause token (valid ones are removed before
            # this pass): drop it so it is never read aloud.
            end = text.find("]", index)
            newline = text.find("\n", index)
            if end != -1 and (newline == -1 or end < newline):
                index = end + 1
                continue

        char = text[index]
        if char == "*":
            if open_kind == "*":
                ranges.append((emph_start, clean_len))
                open_kind = None
            elif open_kind is None and _closing_star_on_line(text, index + 1):
                open_kind, emph_start = "*", clean_len
            else:
                # lone asterisk, or a `*` inside a bracket span: keep literal
                out.append("*")
                clean_len += 1
            index += 1
            continue

        out.append(char)
        clean_len += 1
        index += 1

    # An unterminated emphasis span just doesn't emphasize; its text is kept.
    return "".join(out), ranges


def _emphasized_word_flags(clean: str, ranges: list[tuple[int, int]]) -> list[bool]:
    """Per-word emphasis flags, in order, for each whitespace-delimited word."""
    if not ranges:
        return []
    flags: list[bool] = []
    for match in re.finditer(r"\S+", clean):
        word_start, word_end = match.start(), match.end()
        flags.append(
            any(rs < word_end and word_start < re_ for rs, re_ in ranges)
        )
    return flags


def compile_script(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Compile a script with inline prosody markup into speakable Chunks.

    Explicit `[pause:N]` / `[break]` directives set the stitched silence after
    the preceding chunk (overriding the default sentence/paragraph pause).
    `*emphasis*` / `[emph]...[/emph]` marks any chunk overlapping the span for
    raised delivery (see `Chunk.emphasis`). With no markup the result is
    identical to `chunk.split_script`.

    Raises:
        ValueError: if `text` has no speakable content once markup is removed.
    """
    result: list[Chunk] = []

    for segment_text, pause_after in _split_runs(text):
        clean, ranges = _extract_emphasis(segment_text)
        flags = _emphasized_word_flags(clean, ranges)

        try:
            segment_chunks = split_script(clean, max_chars=max_chars)
        except ValueError:
            # Whitespace-only run (e.g. text between two adjacent pauses).
            segment_chunks = []

        cursor = 0
        annotated: list[Chunk] = []
        for chunk in segment_chunks:
            word_count = len(chunk.text.split())
            chunk_flags = flags[cursor:cursor + word_count]
            cursor += word_count
            annotated.append(replace(chunk, emphasis=any(chunk_flags)))

        if pause_after is not None:
            if annotated:
                annotated[-1] = replace(annotated[-1], pause_after=pause_after)
            elif result:
                # No speech in this run: fold the pause into the prior chunk so
                # adjacent/leading pauses still add silence where possible.
                result[-1] = replace(
                    result[-1], pause_after=result[-1].pause_after + pause_after
                )
            # else: a leading pause with nothing before it has nowhere to land.

        result.extend(annotated)

    if not result:
        raise ValueError("the script is empty; provide text to synthesize.")

    return result
