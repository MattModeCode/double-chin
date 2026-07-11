"""Offline tests for MynaEngine, using a fake Chatterbox model."""

from __future__ import annotations

import pytest

from myna.engine import MynaEngine


class FakeModel:
    """Stands in for ChatterboxTTS: returns 0.5 s of silence per chunk."""

    sr = 24000

    def __init__(self) -> None:
        self.prepared_with: str | None = None
        self.generated_texts: list[str] = []

    def prepare_conditionals(self, reference_path: str, exaggeration: float) -> None:
        self.prepared_with = reference_path

    def generate(self, text: str, **kwargs):
        import torch

        self.generated_texts.append(text)
        return torch.zeros(1, self.sr // 2)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    fake = FakeModel()
    eng = MynaEngine(device="cpu")
    monkeypatch.setattr(eng, "_load_model", lambda: fake)

    reference = tmp_path / "ref.wav"
    import torch
    import torchaudio

    torchaudio.save(str(reference), torch.zeros(1, 24000), 24000)
    return eng, fake, reference


def test_synthesize_reports_progress_per_chunk(engine, tmp_path):
    eng, fake, reference = engine
    events: list[tuple[int, int, str]] = []

    script = "First sentence here.\n\nSecond paragraph sentence."
    report = eng.synthesize(
        script=script,
        reference_wav=reference,
        out_path=tmp_path / "out.wav",
        progress=lambda index, total, text: events.append((index, total, text)),
    )

    assert report.chunk_count == 2
    assert events == [
        (1, 2, "First sentence here."),
        (2, 2, "Second paragraph sentence."),
    ]
    assert fake.generated_texts == [
        "First sentence here.",
        "Second paragraph sentence.",
    ]


def test_synthesize_without_progress_callback_still_works(engine, tmp_path):
    eng, _fake, reference = engine

    out_path = tmp_path / "out.wav"
    report = eng.synthesize(
        script="Just one sentence.",
        reference_wav=reference,
        out_path=out_path,
    )

    assert out_path.is_file()
    assert report.chunk_count == 1
    assert report.audio_seconds == pytest.approx(0.5, abs=0.01)
