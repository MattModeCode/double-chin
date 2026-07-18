"""Naturalness proxy (MOS-style) — a documented signal-based heuristic.

IMPORTANT: this is NOT a mean-opinion-score (MOS) predictor. A true MOS needs a
trained perceptual model (e.g. UTMOS/NISQA); those require downloading large
weights and network access, which this suite forbids. Instead we combine four
cheap, free, offline signal checks into a 0-1 "naturalness proxy" and label it
as such everywhere it surfaces. It answers a narrower question — *does this clip
have the gross signal characteristics of natural speech, or the tell-tale marks
of a synthetic artifact (clipping, dead air, noise-like spectrum, robotic
monotone)?* — and must never be presented as a calibrated MOS.

Sub-scores (each in [0, 1], 1 = natural), combined as a geometric mean so any
single failure mode drags the proxy down:

1. clipping        - fraction of samples pinned near full scale.
2. silence balance - fraction of the clip that is silence/dead air.
3. spectral shape  - mean spectral flatness (noise-like spectra score low).
4. pitch variation - voiced-F0 spread in semitones (robotic monotone scores low).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- clipping ---------------------------------------------------------------
_CLIP_LEVEL = 0.99          # |sample| above this counts as clipped
_CLIP_FRAC_ZERO = 0.02      # >=2% clipped samples -> score 0

# --- silence balance --------------------------------------------------------
_SILENCE_DB = -40.0         # frames below this (rel. to peak) are silence
_SILENCE_OK_MAX = 0.55      # up to 55% silence is fine (pauses, breaths)
_SILENCE_DEAD = 0.90        # >=90% silence -> score 0 (mostly dead air)

# --- spectral shape ---------------------------------------------------------
_FLATNESS_OK_MAX = 0.20     # speech is spectrally peaky; flatness <=0.20 -> 1
_FLATNESS_NOISE = 0.55      # flatness >=0.55 is noise-like -> score 0

# --- pitch variation --------------------------------------------------------
_F0_MIN_HZ = 70.0
_F0_MAX_HZ = 400.0
_SEMITONES_FULL = 1.5       # >=1.5 semitones of F0 spread reads as natural
_MIN_VOICED_FRAMES = 3      # too few voiced frames -> can't judge, treat as flat


@dataclass(frozen=True)
class Naturalness:
    """Per-clip naturalness-proxy breakdown (heuristic, not a true MOS)."""

    score: float
    clipping: float
    silence_balance: float
    spectral_shape: float
    pitch_variation: float


def _clipping_score(wav) -> float:
    import numpy as np

    frac = float(np.mean(np.abs(wav) >= _CLIP_LEVEL))
    if _CLIP_FRAC_ZERO <= 0:
        return 1.0
    return max(0.0, 1.0 - frac / _CLIP_FRAC_ZERO)


def _silence_score(wav, sr: int) -> float:
    import librosa
    import numpy as np

    rms = librosa.feature.rms(y=wav, frame_length=1024, hop_length=256)[0]
    peak = float(np.max(rms))
    if peak <= 0:
        return 0.0
    db = 20.0 * np.log10(np.maximum(rms, 1e-8) / peak)
    silence_frac = float(np.mean(db < _SILENCE_DB))
    if silence_frac <= _SILENCE_OK_MAX:
        return 1.0
    if silence_frac >= _SILENCE_DEAD:
        return 0.0
    # Linear decay across the "too much dead air" band.
    return 1.0 - (silence_frac - _SILENCE_OK_MAX) / (_SILENCE_DEAD - _SILENCE_OK_MAX)


def _spectral_score(wav) -> float:
    import librosa
    import numpy as np

    flatness = float(np.mean(librosa.feature.spectral_flatness(y=wav)[0]))
    if flatness <= _FLATNESS_OK_MAX:
        return 1.0
    if flatness >= _FLATNESS_NOISE:
        return 0.0
    return 1.0 - (flatness - _FLATNESS_OK_MAX) / (_FLATNESS_NOISE - _FLATNESS_OK_MAX)


def _pitch_variation_score(wav, sr: int) -> float:
    import librosa
    import numpy as np

    f0, _voiced_flag, _voiced_prob = librosa.pyin(
        wav,
        fmin=_F0_MIN_HZ,
        fmax=_F0_MAX_HZ,
        sr=sr,
        frame_length=1024,
        hop_length=512,
    )
    voiced = f0[~np.isnan(f0)]
    if voiced.size < _MIN_VOICED_FRAMES:
        return 0.0
    # Spread in semitones is perceptually meaningful and level-independent.
    semitones = 12.0 * np.log2(voiced / float(np.median(voiced)))
    spread = float(np.std(semitones))
    return max(0.0, min(1.0, spread / _SEMITONES_FULL))


def naturalness_proxy(wav, sr: int) -> Naturalness:
    """Compute the naturalness proxy for one waveform.

    This is a labelled heuristic, not a calibrated MOS — see the module
    docstring. Returns sub-scores plus their geometric-mean aggregate.
    """
    clipping = _clipping_score(wav)
    silence = _silence_score(wav, sr)
    spectral = _spectral_score(wav)
    pitch = _pitch_variation_score(wav, sr)

    parts = [clipping, silence, spectral, pitch]
    # Geometric mean: any single near-zero sub-score collapses the proxy, which
    # is the point — one glaring artifact should sink "naturalness".
    product = 1.0
    for value in parts:
        product *= max(value, 1e-6)
    score = product ** (1.0 / len(parts))

    return Naturalness(
        score=score,
        clipping=clipping,
        silence_balance=silence,
        spectral_shape=spectral,
        pitch_variation=pitch,
    )
