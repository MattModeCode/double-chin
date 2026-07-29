"""Unit tests for double_chin.prosody (inline markup compiler).

Pure parsing — no model, no audio, offline and fast.
"""

from __future__ import annotations

import pytest

from double_chin.chunk import (
    INTER_PARAGRAPH_PAUSE_SECONDS,
    INTRA_PARAGRAPH_PAUSE_SECONDS,
    split_script,
)
from double_chin.prosody import (
    DEFAULT_BREAK_SECONDS,
    MAX_PAUSE_SECONDS,
    compile_script,
)


def _texts(chunks):
    return [c.text for c in chunks]


# ---------- equivalence with plain chunking ----------

def test_no_markup_matches_split_script():
    text = "First sentence here. Second one too.\n\nA new paragraph entirely."
    compiled = compile_script(text)
    plain = split_script(text)
    assert _texts(compiled) == _texts(plain)
    assert [c.pause_after for c in compiled] == [c.pause_after for c in plain]
    assert all(c.emphasis is False for c in compiled)


def test_empty_script_raises():
    with pytest.raises(ValueError):
        compile_script("   \n  ")


def test_only_pause_directive_is_empty_script():
    with pytest.raises(ValueError):
        compile_script("[pause:1.0]")


# ---------- explicit pauses ----------

def test_pause_directive_sets_preceding_chunk_pause():
    chunks = compile_script("Hello there. [pause:1.5] World now.")
    assert _texts(chunks) == ["Hello there.", "World now."]
    # The pause before the break overrides the default sentence pause.
    assert chunks[0].pause_after == pytest.approx(1.5)


def test_break_uses_default_seconds():
    chunks = compile_script("Alpha bravo. [break] Charlie delta.")
    assert chunks[0].pause_after == pytest.approx(DEFAULT_BREAK_SECONDS)


def test_pause_is_clamped_to_max():
    chunks = compile_script("Alpha bravo. [pause:99] Charlie.")
    assert chunks[0].pause_after == pytest.approx(MAX_PAUSE_SECONDS)


def test_pause_mid_sentence_splits_into_two_chunks():
    chunks = compile_script("Hold on[pause:0.8]then go.")
    assert _texts(chunks) == ["Hold on", "then go."]
    assert chunks[0].pause_after == pytest.approx(0.8)


def test_leading_pause_is_dropped_gracefully():
    chunks = compile_script("[pause:2.0] Only sentence here.")
    assert _texts(chunks) == ["Only sentence here."]
    # Nothing precedes the pause, so it has nowhere to land — default remains.
    assert chunks[0].pause_after == pytest.approx(INTER_PARAGRAPH_PAUSE_SECONDS)


def test_adjacent_pauses_accumulate_onto_prior_chunk():
    chunks = compile_script("Done.[pause:0.5][pause:0.5]")
    assert _texts(chunks) == ["Done."]
    assert chunks[0].pause_after == pytest.approx(1.0)


def test_pause_tag_never_spoken():
    chunks = compile_script("Say this. [pause:0.4] And this.")
    joined = " ".join(_texts(chunks))
    assert "pause" not in joined.lower()
    assert "[" not in joined and "]" not in joined


# ---------- emphasis ----------

def test_asterisk_emphasis_marks_chunk_and_strips_markers():
    chunks = compile_script("I *really* mean it.")
    assert len(chunks) == 1
    assert chunks[0].text == "I really mean it."
    assert chunks[0].emphasis is True
    assert "*" not in chunks[0].text


def test_bracket_emphasis_marks_chunk():
    chunks = compile_script("This is [emph]very important[/emph] now.")
    assert chunks[0].text == "This is very important now."
    assert chunks[0].emphasis is True
    assert "emph" not in chunks[0].text.lower()


def test_emphasis_only_flags_the_containing_chunk():
    # Two paragraphs -> two separate chunks; only the second is emphasized.
    text = "Plain opening line.\n\nA *hot* closing line."
    chunks = compile_script(text)
    assert len(chunks) == 2
    assert chunks[0].emphasis is False
    assert chunks[1].emphasis is True
    assert chunks[1].text == "A hot closing line."


def test_mid_word_emphasis_still_flags_the_word():
    chunks = compile_script("so*ooo* good")
    assert chunks[0].text == "soooo good"
    assert chunks[0].emphasis is True


# ---------- graceful degradation of malformed markup ----------

def test_unbalanced_asterisk_is_kept_literal_not_emphasis():
    chunks = compile_script("A lone * star stays.")
    assert chunks[0].text == "A lone * star stays."
    assert chunks[0].emphasis is False


def test_stray_closing_emph_tag_is_dropped():
    chunks = compile_script("Nothing opened this [/emph] here.")
    assert chunks[0].text == "Nothing opened this  here." or \
        chunks[0].text == "Nothing opened this here."
    assert "emph" not in chunks[0].text.lower()
    assert chunks[0].emphasis is False


def test_unterminated_emphasis_does_not_crash_or_emphasize():
    chunks = compile_script("Start [emph]never closes.")
    assert "emph" not in chunks[0].text.lower()
    assert chunks[0].emphasis is False


def test_malformed_pause_token_is_not_spoken():
    chunks = compile_script("Careful [pause:abc] now please.")
    joined = " ".join(_texts(chunks))
    assert "pause" not in joined.lower()
    assert "abc" not in joined


def test_combined_pause_and_emphasis():
    chunks = compile_script("Wait *for* it. [pause:1.2] Boom now.")
    assert _texts(chunks) == ["Wait for it.", "Boom now."]
    assert chunks[0].emphasis is True
    assert chunks[0].pause_after == pytest.approx(1.2)
    assert chunks[1].emphasis is False


def test_intra_paragraph_default_pause_preserved_without_markup():
    sentence_one = "Alpha bravo charlie delta echo foxtrot."
    sentence_two = "Golf hotel india juliet kilo lima mike."
    text = f"{sentence_one} {sentence_two}"
    max_chars = max(len(sentence_one), len(sentence_two)) + 1
    chunks = compile_script(text, max_chars=max_chars)
    assert len(chunks) == 2
    assert chunks[0].pause_after == pytest.approx(INTRA_PARAGRAPH_PAUSE_SECONDS)
