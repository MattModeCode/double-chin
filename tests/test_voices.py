"""Unit tests for myna.voices."""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from myna import config
from myna.voices import enroll, get_voice, list_voices


def _write_sine_wav(
    path: Path, seconds: float, sample_rate: int = 24000, frequency: float = 440.0
) -> None:
    frame_count = int(seconds * sample_rate)
    amplitude = 16000
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(frame_count):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            frames += struct.pack("<h", sample)
        wav_file.writeframes(bytes(frames))


@pytest.fixture(autouse=True)
def _myna_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MYNA_HOME", str(tmp_path / "myna_home"))
    yield


def test_enroll_happy_path_writes_reference_and_meta(tmp_path):
    source = tmp_path / "clip.wav"
    _write_sine_wav(source, seconds=8.0)

    info = enroll("test-voice", [source])

    assert info.name == "test-voice"
    assert info.sample_rate == config.SAMPLE_RATE
    assert info.duration_seconds >= config.MIN_REFERENCE_SECONDS
    assert info.source_files == [str(source)]

    voice_dir = config.voices_dir() / "test-voice"
    assert (voice_dir / "reference.wav").is_file()

    meta = json.loads((voice_dir / "meta.json").read_text())
    assert meta["name"] == "test-voice"
    assert meta["sample_rate"] == config.SAMPLE_RATE
    assert meta["source_files"] == [str(source)]
    assert "created" in meta
    assert "duration_seconds" in meta


def test_enroll_too_short_input_raises_value_error(tmp_path):
    source = tmp_path / "short.wav"
    _write_sine_wav(source, seconds=1.0)

    with pytest.raises(ValueError, match="at least"):
        enroll("short-voice", [source])


def test_enroll_bad_name_raises_value_error(tmp_path):
    source = tmp_path / "clip.wav"
    _write_sine_wav(source, seconds=8.0)

    with pytest.raises(ValueError, match="invalid voice name"):
        enroll("Not Valid!", [source])


def test_enroll_from_directory_of_files(tmp_path):
    source_dir = tmp_path / "clips"
    source_dir.mkdir()
    _write_sine_wav(source_dir / "a.wav", seconds=4.0)
    _write_sine_wav(source_dir / "b.wav", seconds=4.0)

    info = enroll("dir-voice", [source_dir])

    assert info.duration_seconds >= config.MIN_REFERENCE_SECONDS


def test_list_voices_and_get_voice(tmp_path):
    source = tmp_path / "clip.wav"
    _write_sine_wav(source, seconds=8.0)
    enroll("alpha", [source])
    enroll("beta", [source])

    voices = list_voices()
    names = {v.name for v in voices}
    assert names == {"alpha", "beta"}

    found = get_voice("alpha")
    assert found.name == "alpha"


def test_get_voice_missing_raises_clear_error():
    with pytest.raises(ValueError, match="no voice named"):
        get_voice("does-not-exist")


def test_list_voices_empty_when_no_home():
    assert list_voices() == []
