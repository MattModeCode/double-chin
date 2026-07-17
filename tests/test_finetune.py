"""Tests for the fine-tune backend.

The unit tests exercise `dataset.build_examples` id-matching, skip, and split
logic against a fake tokenizer/model, so they stay fast and need no weights. The
slow test (CHINAI_E2E=1) runs a real ~20-step MPS LoRA fine-tune on the stand-in
voice and asserts the loss drops, mirroring tests/test_e2e.py.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import wave
from pathlib import Path

import pytest

from chinai.finetune.dataset import build_examples, resolve_audio, split_examples

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_sine_wav(path: Path, seconds: float, sample_rate: int = 16000, frequency: float = 440.0) -> None:
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


# --- fake model: mirrors the ChatterboxTTS surface build_example touches ------


class _FakeHP:
    start_text_token = 255
    stop_text_token = 0
    start_speech_token = 6561
    stop_speech_token = 6562


class _FakeT3:
    hp = _FakeHP()


class _FakeTextTokenizer:
    def text_to_tokens(self, text: str):
        import torch

        n = max(1, min(8, len(text.split())))
        return torch.arange(n, dtype=torch.long).unsqueeze(0)


class _FakeS3Tokenizer:
    def forward(self, wavs):
        import torch

        # ~25 tokens/sec at 16 kHz; at least one token for any clip.
        n = max(1, len(wavs[0]) // 640)
        return torch.zeros(1, n, dtype=torch.long), None


class _FakeS3Gen:
    def __init__(self) -> None:
        self.tokenizer = _FakeS3Tokenizer()


class _FakeConds:
    def __init__(self) -> None:
        self.t3 = object()


class FakeModel:
    """Fake ChatterboxTTS: enough surface for dataset.build_example, no weights."""

    def __init__(self) -> None:
        self.t3 = _FakeT3()
        self.tokenizer = _FakeTextTokenizer()
        self.s3gen = _FakeS3Gen()
        self.conds = _FakeConds()
        self.prepared: list[str] = []

    def prepare_conditionals(self, path: str, **kwargs) -> None:
        self.prepared.append(path)


def _write_manifest(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["take_id\tfilename\tbucket\test_seconds\ttranscript"]
    for take_id, transcript in rows:
        lines.append(f"{take_id}\t{take_id}.txt\tphonetic\t5\t{transcript}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- unit tests ---------------------------------------------------------------


def test_resolve_audio_matches_by_id_across_extensions(tmp_path):
    (tmp_path / "005.m4a").write_bytes(b"stub")
    (tmp_path / "012.wav").write_bytes(b"stub")

    assert resolve_audio(tmp_path, "005").name == "005.m4a"
    assert resolve_audio(tmp_path, "012").name == "012.wav"
    assert resolve_audio(tmp_path, "999") is None


def test_split_examples_is_deterministic_and_holds_out():
    items = list(range(10))
    train, val = split_examples(items, val_fraction=0.2, seed=0)

    assert len(val) == 2
    assert len(train) == 8
    assert set(train + val) == set(items)
    # Deterministic for a fixed seed.
    assert (train, val) == split_examples(list(range(10)), val_fraction=0.2, seed=0)


def test_split_examples_single_item_has_empty_val():
    train, val = split_examples([42], val_fraction=0.5, seed=0)
    assert train == [42]
    assert val == []


def test_build_examples_matches_skips_and_splits(tmp_path):
    recordings = tmp_path / "rec"
    recordings.mkdir()
    _write_sine_wav(recordings / "001.wav", seconds=1.0)
    _write_sine_wav(recordings / "002.wav", seconds=1.0)
    # 003 is present but corrupt (undecodable) -> skipped.
    (recordings / "003.wav").write_bytes(b"this is not audio")
    # 004 has no audio file at all -> skipped.

    manifest = tmp_path / "manifest.tsv"
    _write_manifest(
        manifest,
        [
            ("001", "Hello world one."),
            ("002", "Hello world two."),
            ("003", "This take is corrupt."),
            ("004", "This take is missing its audio."),
        ],
    )

    train, val = build_examples(
        recordings, manifest, FakeModel(), device="cpu", val_fraction=0.5, seed=0
    )

    # Only the two decodable takes survive; skips did not crash the build.
    assert len(train) + len(val) == 2
    assert len(train) >= 1 and len(val) >= 1
    assert {ex.take_id for ex in train + val} == {"001", "002"}
    # Every surviving example carries wrapped speech tokens (start/stop present).
    for ex in train + val:
        assert int(ex.speech_tokens[0, 0]) == _FakeHP.start_speech_token
        assert int(ex.speech_tokens[0, -1]) == _FakeHP.stop_speech_token


def test_build_examples_missing_manifest_raises(tmp_path):
    with pytest.raises(ValueError, match="manifest not found"):
        build_examples(tmp_path, tmp_path / "nope.tsv", FakeModel())


def test_build_examples_no_matches_raises(tmp_path):
    recordings = tmp_path / "rec"
    recordings.mkdir()
    manifest = tmp_path / "manifest.tsv"
    _write_manifest(manifest, [("001", "No audio anywhere.")])

    with pytest.raises(ValueError, match="no usable training examples"):
        build_examples(recordings, manifest, FakeModel())


# --- slow real fine-tune (gated) ---------------------------------------------

# Stand-in transcripts for the arctic clips (CMU ARCTIC prompts), reused from
# scripts/finetune_chatterbox_smoke.py so no owner audio is needed.
_STANDIN_TAKES = [
    ("001", "demo/assets/arctic_0001.wav", "Author of the danger trail, Philip Steels, etc."),
    ("002", "demo/assets/arctic_0002.wav", "Not at this particular case, Tom, apologized Whittemore."),
    ("003", "demo/assets/arctic_0003.wav", "For the twentieth time that evening the two men shook hands."),
    ("005", "demo/assets/arctic_0005.wav", "Will we ever forget it."),
    ("008", "demo/assets/arctic_0008.wav", "And you always want to see it in the superlative degree."),
]


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("CHINAI_E2E") != "1",
    reason="set CHINAI_E2E=1 to run the real MPS fine-tune",
)
def test_finetune_standin_drops_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    from chinai.finetune.train import finetune_voice
    from chinai.voices import enroll, get_voice

    enroll("standin", [REPO_ROOT / "demo" / "assets" / "standin_reference.wav"])

    recordings = tmp_path / "rec"
    recordings.mkdir()
    for take_id, rel, _text in _STANDIN_TAKES:
        shutil.copy(REPO_ROOT / rel, recordings / f"{take_id}.wav")
    _write_manifest(
        recordings / "manifest.tsv",
        [(take_id, text) for take_id, _rel, text in _STANDIN_TAKES],
    )

    losses: list[float] = []
    adapter_path = finetune_voice(
        "standin",
        recordings,
        max_steps=20,
        progress=lambda step, total, loss: losses.append(loss),
    )

    assert adapter_path.is_file()
    assert len(losses) == 20
    # The training objective is actually optimizing on this hardware.
    assert losses[-1] < losses[0]

    # The voice is now flagged fine-tuned and resolves to the saved adapter.
    voice = get_voice("standin")
    assert voice.finetuned is True
    assert voice.lora_path == adapter_path
