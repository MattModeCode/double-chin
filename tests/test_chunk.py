"""Unit tests for double_chin.chunk."""

from __future__ import annotations

import pytest

from double_chin.chunk import (
    INTER_PARAGRAPH_PAUSE_SECONDS,
    INTRA_PARAGRAPH_PAUSE_SECONDS,
    split_script,
)


def test_basic_split_produces_one_chunk_for_short_sentence():
    chunks = split_script("Hello there.")
    assert len(chunks) == 1
    assert chunks[0].text == "Hello there."


def test_merges_short_sentences_into_one_chunk():
    text = "This is one. This is two. This is three."
    chunks = split_script(text, max_chars=280)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_long_sentence_is_split_at_comma():
    sentence = (
        "This is a very long sentence that keeps going, and going, "
        "and going well past the limit we have set for a single chunk of speech."
    )
    chunks = split_script(sentence, max_chars=60)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 60
    assert chunks[0].text.endswith(",")


def test_paragraph_pause_differs_from_intra_paragraph_pause():
    sentence_one = "Alpha bravo charlie delta echo."
    sentence_two = "Foxtrot golf hotel india juliet."
    paragraph_one = f"{sentence_one} {sentence_two}"
    paragraph_two = "Second paragraph sentence here."
    text = f"{paragraph_one}\n\n{paragraph_two}"

    # Choose max_chars so each sentence fits alone but the pair does not,
    # forcing two separate chunks within the first paragraph.
    max_chars = max(len(sentence_one), len(sentence_two)) + 1
    chunks = split_script(text, max_chars=max_chars)

    assert len(chunks) == 3
    assert chunks[0].text == sentence_one
    assert chunks[0].pause_after == pytest.approx(INTRA_PARAGRAPH_PAUSE_SECONDS)
    assert chunks[1].text == sentence_two
    assert chunks[1].pause_after == pytest.approx(INTER_PARAGRAPH_PAUSE_SECONDS)
    assert chunks[2].text == paragraph_two
    assert chunks[2].pause_after == pytest.approx(INTER_PARAGRAPH_PAUSE_SECONDS)


def test_known_abbreviations_are_not_split():
    text = "Dr. Smith met Mrs. Jones at noon."
    chunks = split_script(text)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_empty_input_raises_value_error():
    with pytest.raises(ValueError):
        split_script("")

    with pytest.raises(ValueError):
        split_script("   \n\n  ")


def test_whitespace_is_normalized():
    text = "Hello    there.\n\n\n   This   is  fine.  "
    chunks = split_script(text)
    assert all("  " not in chunk.text for chunk in chunks)


def test_max_chars_is_respected_across_many_sentences():
    text = " ".join(f"Sentence number {i}." for i in range(50))
    chunks = split_script(text, max_chars=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 100
