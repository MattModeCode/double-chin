"""Unit tests for double_chin.voices."""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from double_chin import config
from double_chin.voices import enroll, get_voice, list_voices


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
def _double_chin_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "double_chin_home"))
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

    # A single source file has nothing to hold out.
    assert meta["holdout_file"] is None
    assert info.holdout_file is None
    assert info.holdout_wav is None
    assert not (voice_dir / "holdout.wav").exists()


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


def test_enroll_with_three_files_reserves_holdout(tmp_path):
    files = []
    for i in range(3):
        path = tmp_path / f"clip{i}.wav"
        _write_sine_wav(path, seconds=4.0, frequency=440.0 + i * 20)
        files.append(path)

    info = enroll("holdout-voice", files)

    voice_dir = config.voices_dir() / "holdout-voice"
    holdout_path = voice_dir / "holdout.wav"
    assert holdout_path.is_file()
    assert info.holdout_file == str(files[-1])
    assert info.holdout_wav == holdout_path

    meta = json.loads((voice_dir / "meta.json").read_text())
    assert meta["holdout_file"] == str(files[-1])

    # Reference audio excludes the held-out clip: only the first two ~4s
    # clips (plus a short silence gap) go into reference.wav, well under
    # all three clips combined (~12s).
    assert info.duration_seconds < 3 * 4.0


def _find_ffmpeg_for_test() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidate = Path("/opt/homebrew/bin/ffmpeg")
    return str(candidate) if candidate.is_file() else None


def test_enroll_accepts_m4a_via_ffmpeg_transcode(tmp_path):
    ffmpeg_path = _find_ffmpeg_for_test()
    if ffmpeg_path is None:
        pytest.skip("ffmpeg not available")

    wav_source = tmp_path / "clip.wav"
    _write_sine_wav(wav_source, seconds=8.0)
    m4a_source = tmp_path / "clip.m4a"
    result = subprocess.run(
        [ffmpeg_path, "-y", "-i", str(wav_source), "-c:a", "aac", str(m4a_source)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    info = enroll("m4a-voice", [m4a_source])

    assert info.duration_seconds >= config.MIN_REFERENCE_SECONDS
    assert (config.voices_dir() / "m4a-voice" / "reference.wav").is_file()


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
