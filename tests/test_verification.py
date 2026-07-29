"""Tests for the indistinguishability verification suite.

Two layers, both offline:

- Pure numeric/signal unit tests that never load a model (fast).
- Integration tests over the in-repo demo/quiz real/clone pairs, which load
  Resemblyzer's *bundled* encoder weights (no download, no network) and so stay
  in the default "not slow" suite.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from double_chin.verification import (
    GATE_PASS_THRESHOLD,
    format_scorecard,
    gate_verdict,
    indistinguishability_gate,
    naturalness_proxy,
    prosody_features,
    prosody_similarity,
    speaker_discrimination,
)
from double_chin.verification.gate import _cosine_to_unit, _weighted_geometric_mean
from double_chin.verification.prosody import ProsodyFeatures, _relative_similarity

SR = 16000
DEMO_IDS = ("a0010", "a0036", "a0060")


# --------------------------------------------------------------------------- #
# synthetic-signal helpers (no model)                                         #
# --------------------------------------------------------------------------- #

def _tone(frequency: float, seconds: float = 2.0, sr: int = SR, amp: float = 0.4):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def _vibrato(seconds: float = 2.0, sr: int = SR):
    t = np.arange(int(seconds * sr)) / sr
    freq = 200 * (1 + 0.15 * np.sin(2 * np.pi * 3 * t))
    return (0.4 * np.sin(2 * np.pi * np.cumsum(freq) / sr)).astype(np.float32)


def _noise(seconds: float = 2.0, sr: int = SR, seed: int = 0):
    rng = np.random.default_rng(seed)
    return (0.3 * rng.standard_normal(int(seconds * sr))).astype(np.float32)


# --------------------------------------------------------------------------- #
# 1. speaker discrimination (pure vectors, no model)                          #
# --------------------------------------------------------------------------- #

def _unit(vec):
    vec = np.asarray(vec, dtype=float)
    return vec / np.linalg.norm(vec)


def test_speaker_discrimination_identical_sets_indistinguishable():
    a, b = _unit([1, 0, 0]), _unit([0.9, 0.1, 0])
    result = speaker_discrimination([a, b], [a, b])
    assert result.indistinguishability == pytest.approx(1.0)
    assert result.separability == pytest.approx(0.0)
    assert result.mean_cross_cosine == pytest.approx(1.0, abs=0.05)


def test_speaker_discrimination_separate_clusters_distinguishable():
    reals = [_unit([1, 0, 0]), _unit([0.98, 0.02, 0])]
    clones = [_unit([0, 1, 0]), _unit([0.02, 0.98, 0])]
    result = speaker_discrimination(reals, clones)
    assert result.separability == pytest.approx(1.0)
    assert result.indistinguishability == pytest.approx(0.0)
    assert result.mean_cross_cosine < 0.2


def test_speaker_discrimination_requires_both_sets():
    a = _unit([1, 0, 0])
    with pytest.raises(ValueError):
        speaker_discrimination([a], [])


# --------------------------------------------------------------------------- #
# 2. naturalness proxy (synthetic signals, no model)                          #
# --------------------------------------------------------------------------- #

def test_naturalness_high_for_pitch_varying_signal():
    assert naturalness_proxy(_vibrato(), SR).score > 0.8


def test_naturalness_low_for_robotic_monotone():
    result = naturalness_proxy(_tone(200), SR)
    assert result.pitch_variation < 0.2
    assert result.score < 0.5


def test_naturalness_low_for_noise():
    result = naturalness_proxy(_noise(), SR)
    assert result.spectral_shape < 0.2
    assert result.score < 0.2


def test_naturalness_low_for_clipping():
    t = np.arange(int(2.0 * SR)) / SR
    clipped = np.clip(3 * np.sin(2 * np.pi * 200 * t), -1, 1).astype(np.float32)
    result = naturalness_proxy(clipped, SR)
    assert result.clipping < 0.2
    assert result.score < 0.3


# --------------------------------------------------------------------------- #
# 3. prosody similarity                                                       #
# --------------------------------------------------------------------------- #

def _features(**overrides) -> ProsodyFeatures:
    base = dict(
        median_f0=150.0,
        f0_spread_semitones=3.0,
        voiced_fraction=0.6,
        voiced_onset_rate=2.0,
        silence_fraction=0.3,
        mean_pause_seconds=0.25,
    )
    base.update(overrides)
    return ProsodyFeatures(**base)


def test_prosody_similarity_identical_features_is_one():
    feats = [_features()]
    result = prosody_similarity(feats, feats)
    assert result.score == pytest.approx(1.0)


def test_prosody_similarity_drops_when_delivery_differs():
    real = [_features(median_f0=150.0, voiced_onset_rate=2.0, silence_fraction=0.30)]
    clone = [_features(median_f0=450.0, voiced_onset_rate=0.2, silence_fraction=0.05)]
    result = prosody_similarity(real, clone)
    assert result.score < 0.8
    assert result.per_feature["median_f0"] < 0.6


def test_prosody_similarity_requires_features():
    with pytest.raises(ValueError):
        prosody_similarity([], [_features()])


def test_relative_similarity_both_zero_is_one():
    assert _relative_similarity(0.0, 0.0) == pytest.approx(1.0)
    assert _relative_similarity(1.0, 0.0) == pytest.approx(0.0)


def test_prosody_features_on_synthetic_tone():
    feats = prosody_features(_vibrato(), SR)
    assert 150 < feats.median_f0 < 260  # ~200 Hz carrier
    assert feats.voiced_fraction > 0.5


# --------------------------------------------------------------------------- #
# 4. gate helpers (pure)                                                      #
# --------------------------------------------------------------------------- #

def test_cosine_to_unit_mapping():
    assert _cosine_to_unit(0.60) == pytest.approx(0.0)
    assert _cosine_to_unit(0.90) == pytest.approx(1.0)
    assert _cosine_to_unit(0.50) == pytest.approx(0.0)  # clamped
    assert _cosine_to_unit(1.0) == pytest.approx(1.0)   # clamped
    assert 0.0 < _cosine_to_unit(0.75) < 1.0


def test_weighted_geometric_mean_collapses_on_zero_component():
    # A single near-zero component must drag the aggregate toward zero even
    # when every other component is perfect — the core anti-gaming property.
    high_only = _weighted_geometric_mean([(1.0, 0.75), (0.0, 0.25)])
    all_high = _weighted_geometric_mean([(1.0, 0.75), (1.0, 0.25)])
    assert all_high == pytest.approx(1.0)
    assert high_only < 0.2


def test_gate_verdict_bands():
    assert gate_verdict(0.95) == "indistinguishable"
    assert gate_verdict(0.75) == "near-indistinguishable"
    assert gate_verdict(0.60) == "distinguishable"
    assert gate_verdict(0.30) == "clearly synthetic"


# --------------------------------------------------------------------------- #
# 5. integration on the in-repo demo/quiz pairs (bundled encoder, offline)    #
# --------------------------------------------------------------------------- #

def _demo(kind: str) -> list:
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "demo" / "quiz"
    return [base / f"{kind}_{clip_id}.wav" for clip_id in DEMO_IDS]


def test_gate_documented_shape_and_pass_on_demo_clones():
    result = indistinguishability_gate(_demo("real"), _demo("clone"))

    # documented shape
    assert set(result.keys()) == {"passed", "score", "verdict", "components"}
    assert set(result["components"].keys()) == {
        "speaker_similarity",
        "discrimination",
        "naturalness",
        "prosody",
    }
    assert result["components"]["naturalness"]["is_proxy"] is True
    assert isinstance(result["passed"], bool)
    assert 0.0 <= result["score"] <= 1.0

    # the demo clones are genuinely good clones -> the gate must clear.
    assert result["passed"] is True
    assert result["score"] >= GATE_PASS_THRESHOLD
    assert result["verdict"] in {"indistinguishable", "near-indistinguishable"}

    # scorecard renders without error and labels the proxy honestly.
    card = format_scorecard(result)
    assert "Indistinguishability gate: PASS" in card
    assert "proxy, not MOS" in card


def test_gate_identical_clips_near_perfect():
    result = indistinguishability_gate(_demo("real"), _demo("real"))
    assert result["passed"] is True
    assert result["score"] > 0.9
    assert result["components"]["discrimination"]["component"] == pytest.approx(1.0)


def test_gate_fails_on_obviously_synthetic_clone(tmp_path):
    # Robotic monotone "buzz" clips: right ballpark energy, wrong everything
    # else. A high timbre cosine cannot rescue this — the gate must fail.
    clone_dir = tmp_path / "buzz"
    clone_dir.mkdir()
    for index in range(3):
        t = np.arange(int(2.5 * SR)) / SR
        envelope = ((t % 0.5) < 0.4).astype(np.float32)
        buzz = (0.3 * np.sign(np.sin(2 * np.pi * 220 * t)) * envelope).astype(np.float32)
        sf.write(str(clone_dir / f"buzz_{index}.wav"), buzz, SR)

    result = indistinguishability_gate(_demo("real"), clone_dir)
    assert result["passed"] is False
    assert result["score"] < GATE_PASS_THRESHOLD
    assert result["verdict"] in {"distinguishable", "clearly synthetic"}
