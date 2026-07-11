"""End-to-end test exercising the real Chatterbox model.

Skipped unless MYNA_E2E=1, since it downloads/loads real model weights and
performs CPU/GPU inference against a real reference clip.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_WAV = REPO_ROOT / "demo" / "assets" / "standin_reference.wav"

_SIMILARITY_RE = re.compile(r"Speaker similarity vs [^:]+:\s*([0-9.]+)")


@pytest.mark.skipif(
    os.environ.get("MYNA_E2E") != "1",
    reason="set MYNA_E2E=1 to run real-model end-to-end tests",
)
def test_say_produces_audio_with_real_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MYNA_HOME", str(tmp_path / "home"))
    from myna.cli import main

    out_path = tmp_path / "out.wav"
    exit_code = main(
        [
            "say",
            "This is a short end to end test of Myna.",
            "--ref",
            str(REFERENCE_WAV),
            "-o",
            str(out_path),
            "--verify",
        ]
    )

    assert exit_code == 0
    assert out_path.is_file()
    assert out_path.stat().st_size > 0

    # Parse the similarity score from stdout only; stderr carries
    # unstructured chunk-progress noise and must not affect parsing.
    captured = capsys.readouterr()
    match = _SIMILARITY_RE.search(captured.out)
    assert match is not None, f"no similarity score found in stdout: {captured.out!r}"

    score = float(match.group(1))
    assert score > 0.75
