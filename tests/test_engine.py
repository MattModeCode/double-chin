"""Offline tests for DoubleChinEngine, using a fake Chatterbox model."""

from __future__ import annotations

import pytest

from double_chin.engine import DoubleChinEngine


class FakeModel:
    """Stands in for ChatterboxTTS: returns 0.5 s of silence per chunk."""

    sr = 24000

    def __init__(self) -> None:
        self.prepared_with: str | None = None
        self.generated_texts: list[str] = []
        self.generated_kwargs: list[dict] = []

    def prepare_conditionals(self, reference_path: str, exaggeration: float) -> None:
        self.prepared_with = reference_path

    def generate(self, text: str, **kwargs):
        import torch

        self.generated_texts.append(text)
        self.generated_kwargs.append(kwargs)
        return torch.zeros(1, self.sr // 2)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    fake = FakeModel()
    eng = DoubleChinEngine(device="cpu")
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


def test_emphasis_markup_raises_generation_exaggeration(engine, tmp_path):
    eng, fake, reference = engine

    eng.synthesize(
        script="Plain line here.\n\nA *hot* line here.",
        reference_wav=reference,
        out_path=tmp_path / "out.wav",
        exaggeration=0.5,
        cfg_weight=0.5,
    )

    assert fake.generated_texts == ["Plain line here.", "A hot line here."]
    plain_kwargs, emph_kwargs = fake.generated_kwargs
    assert plain_kwargs["exaggeration"] == pytest.approx(0.5)
    # Emphasized chunk is delivered hotter and slightly less reference-bound.
    assert emph_kwargs["exaggeration"] > plain_kwargs["exaggeration"]
    assert emph_kwargs["cfg_weight"] < plain_kwargs["cfg_weight"]


def test_pause_directive_lengthens_stitched_silence(engine, tmp_path):
    eng, fake, reference = engine

    # Each generated chunk is 0.5 s (12000 samples at 24 kHz); a [pause:1.0]
    # between two chunks stitches 24000 extra samples of silence.
    report = eng.synthesize(
        script="First part here. [pause:1.0] Second part here.",
        reference_wav=reference,
        out_path=tmp_path / "out.wav",
    )
    assert report.chunk_count == 2
    # 0.5 + 1.0 pause + 0.5 = 2.0 s of audio.
    assert report.audio_seconds == pytest.approx(2.0, abs=0.02)


def test_rate_time_stretch_shortens_audio(engine, tmp_path):
    eng, _fake, reference = engine

    report = eng.synthesize(
        script="One sentence spoken here.",
        reference_wav=reference,
        out_path=tmp_path / "out.wav",
        rate=2.0,
    )
    # rate=2.0 speeds up: ~half the 0.5 s baseline.
    assert report.audio_seconds == pytest.approx(0.25, abs=0.03)


def test_rate_must_be_positive(engine, tmp_path):
    eng, _fake, reference = engine
    with pytest.raises(ValueError):
        eng.synthesize(
            script="Anything.",
            reference_wav=reference,
            out_path=tmp_path / "out.wav",
            rate=0.0,
        )
