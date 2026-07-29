"""Unit tests for double_chin.verify.

These tests exercise verdict() banding and the RMS silence gate only; they
must not trigger a Resemblyzer model load (lazy-imported only on the
non-silent path of `similarity`), so no network access or model download
occurs.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from double_chin.verify import (
    BORDERLINE_THRESHOLD,
    MATCH_THRESHOLD,
    STRONG_MATCH_THRESHOLD,
    similarity,
    verdict,
)


def _write_wav(
    path: Path,
    seconds: float,
    amplitude: int,
    sample_rate: int = 24000,
    frequency: float = 440.0,
) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(frame_count):
            sample = (
                int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
                if amplitude
                else 0
            )
            frames += struct.pack("<h", sample)
        wav_file.writeframes(bytes(frames))


def test_verdict_bands():
    assert verdict(0.95) == "strong match"
    assert verdict(STRONG_MATCH_THRESHOLD) == "strong match"
    assert verdict(0.77) == "match"
    assert verdict(MATCH_THRESHOLD) == "match"
    assert verdict(0.65) == "borderline"
    assert verdict(BORDERLINE_THRESHOLD) == "borderline"
    assert verdict(0.1) == "no match"


def test_similarity_raises_on_silent_reference(tmp_path):
    silent_wav = tmp_path / "silent.wav"
    _write_wav(silent_wav, seconds=2.0, amplitude=0)
    loud_wav = tmp_path / "loud.wav"
    _write_wav(loud_wav, seconds=2.0, amplitude=16000)

    with pytest.raises(ValueError, match="silent"):
        similarity(silent_wav, loud_wav)


def test_similarity_raises_on_silent_comparison(tmp_path):
    loud_wav = tmp_path / "loud.wav"
    _write_wav(loud_wav, seconds=2.0, amplitude=16000)
    silent_wav = tmp_path / "silent.wav"
    _write_wav(silent_wav, seconds=2.0, amplitude=0)

    with pytest.raises(ValueError, match="silent"):
        similarity(loud_wav, silent_wav)
