"""Prosody similarity between the real and clone clip sets.

Timbre (the speaker embedding) can match while delivery does not — wrong pitch
register, wrong pace, wrong pausing. This module compares the *prosody* of the
two sets so the gate notices a clone that sounds like the right person reading
in the wrong cadence.

Features per clip (aggregated across each set):

- pitch:  median voiced F0 (Hz) and its spread in semitones (via librosa.pyin).
- rate:   voiced fraction and voiced-onset rate (a transcript-free proxy for
          speaking rate — how many voiced runs per second).
- pauses: silence fraction and mean silent-segment duration (pause structure).

Similarity is 1 minus the mean symmetric relative difference across features,
so identical delivery scores 1.0 and every feature contributes on a comparable
[0, 1] scale without needing a trained model.
"""

from __future__ import annotations

from dataclasses import dataclass

_F0_MIN_HZ = 70.0
_F0_MAX_HZ = 400.0
_HOP = 512
_FRAME = 1024
_SILENCE_DB = -40.0  # frame RMS below this (rel. to peak) counts as a pause


@dataclass(frozen=True)
class ProsodyFeatures:
    """Prosodic summary of a single clip."""

    median_f0: float
    f0_spread_semitones: float
    voiced_fraction: float
    voiced_onset_rate: float
    silence_fraction: float
    mean_pause_seconds: float


def _mean_features(feature_list: list[ProsodyFeatures]) -> dict[str, float]:
    keys = (
        "median_f0",
        "f0_spread_semitones",
        "voiced_fraction",
        "voiced_onset_rate",
        "silence_fraction",
        "mean_pause_seconds",
    )
    return {
        key: sum(getattr(f, key) for f in feature_list) / len(feature_list)
        for key in keys
    }


def prosody_features(wav, sr: int) -> ProsodyFeatures:
    """Extract the prosodic feature summary for one waveform."""
    import librosa
    import numpy as np

    f0, voiced_flag, _voiced_prob = librosa.pyin(
        wav, fmin=_F0_MIN_HZ, fmax=_F0_MAX_HZ, sr=sr,
        frame_length=_FRAME, hop_length=_HOP,
    )
    voiced_f0 = f0[~np.isnan(f0)]
    if voiced_f0.size:
        median_f0 = float(np.median(voiced_f0))
        semitones = 12.0 * np.log2(voiced_f0 / median_f0)
        f0_spread = float(np.std(semitones))
    else:
        median_f0 = 0.0
        f0_spread = 0.0

    voiced_bool = np.nan_to_num(voiced_flag).astype(bool)
    voiced_fraction = float(np.mean(voiced_bool)) if voiced_bool.size else 0.0

    # Voiced onsets = rising edges of the voiced flag; per-second rate is a
    # transcript-free stand-in for speaking rate.
    duration = len(wav) / sr
    onsets = int(np.sum((~voiced_bool[:-1]) & voiced_bool[1:])) if voiced_bool.size > 1 else 0
    voiced_onset_rate = onsets / duration if duration > 0 else 0.0

    # Pause structure from frame energy.
    rms = librosa.feature.rms(y=wav, frame_length=_FRAME, hop_length=_HOP)[0]
    peak = float(np.max(rms)) if rms.size else 0.0
    if peak > 0:
        db = 20.0 * np.log10(np.maximum(rms, 1e-8) / peak)
        silent = db < _SILENCE_DB
    else:
        silent = np.ones_like(rms, dtype=bool)
    silence_fraction = float(np.mean(silent)) if silent.size else 0.0

    seconds_per_frame = _HOP / sr
    pause_lengths = _run_lengths(silent)
    mean_pause = (
        float(np.mean(pause_lengths)) * seconds_per_frame if pause_lengths else 0.0
    )

    return ProsodyFeatures(
        median_f0=median_f0,
        f0_spread_semitones=f0_spread,
        voiced_fraction=voiced_fraction,
        voiced_onset_rate=voiced_onset_rate,
        silence_fraction=silence_fraction,
        mean_pause_seconds=mean_pause,
    )


def _run_lengths(mask) -> list[int]:
    """Lengths of consecutive True runs in a boolean array."""
    runs: list[int] = []
    current = 0
    for value in mask:
        if value:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def _relative_similarity(a: float, b: float) -> float:
    """Symmetric closeness of two non-negative scalars, in [0, 1]."""
    denom = abs(a) + abs(b)
    if denom == 0:
        return 1.0  # both zero -> identical
    return 1.0 - abs(a - b) / denom


@dataclass(frozen=True)
class ProsodySimilarity:
    """Aggregate prosody comparison between the real and clone sets."""

    score: float
    per_feature: dict[str, float]
    real: dict[str, float]
    clone: dict[str, float]


def prosody_similarity(
    real_features: list[ProsodyFeatures],
    clone_features: list[ProsodyFeatures],
) -> ProsodySimilarity:
    """Compare set-level prosody, returning an overall [0, 1] similarity.

    Raises:
        ValueError: if either feature list is empty.
    """
    if not real_features or not clone_features:
        raise ValueError("need prosody features for at least one clip per set.")

    real_mean = _mean_features(real_features)
    clone_mean = _mean_features(clone_features)

    per_feature = {
        key: _relative_similarity(real_mean[key], clone_mean[key])
        for key in real_mean
    }
    score = sum(per_feature.values()) / len(per_feature)

    return ProsodySimilarity(
        score=score,
        per_feature=per_feature,
        real=real_mean,
        clone=clone_mean,
    )
