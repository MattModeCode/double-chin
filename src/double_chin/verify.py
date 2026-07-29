"""Speaker-similarity verification for Double Chin, using Resemblyzer embeddings."""

from __future__ import annotations

from pathlib import Path

STRONG_MATCH_THRESHOLD = 0.80
MATCH_THRESHOLD = 0.75
BORDERLINE_THRESHOLD = 0.60

_SILENCE_RMS_THRESHOLD = 0.005

_encoder = None


def _get_encoder():
    """Return a process-wide cached Resemblyzer VoiceEncoder (CPU)."""
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder

        _encoder = VoiceEncoder("cpu")
    return _encoder


def _rms(wav_path: Path) -> float:
    import torchaudio

    waveform, _source_sr = torchaudio.load(str(wav_path))
    return float(waveform.pow(2).mean().sqrt())


def _check_not_silent(wav_path: Path) -> None:
    if _rms(wav_path) < _SILENCE_RMS_THRESHOLD:
        raise ValueError(
            f"audio is silent or near-silent ({wav_path}); similarity "
            "scores on noise are meaningless."
        )


def similarity(wav_a: Path, wav_b: Path) -> float:
    """Return the cosine similarity between the Resemblyzer speaker
    embeddings of two wav files.

    Embeddings are L2-normalized, so the dot product is the cosine
    similarity directly.

    Raises:
        ValueError: if either wav is silent or near-silent (RMS below the
            quality-gate threshold). Resemblyzer can confidently score
            noise-versus-noise pairs near 0.99, which would be meaningless.
    """
    # Run the cheap RMS quality gate before touching the (heavier)
    # Resemblyzer model, so obviously-bad input fails fast.
    _check_not_silent(Path(wav_a))
    _check_not_silent(Path(wav_b))

    import numpy as np
    from resemblyzer import preprocess_wav

    encoder = _get_encoder()
    embedding_a = encoder.embed_utterance(preprocess_wav(Path(wav_a)))
    embedding_b = encoder.embed_utterance(preprocess_wav(Path(wav_b)))

    return float(np.dot(embedding_a, embedding_b))


def verdict(score: float) -> str:
    """Classify a Resemblyzer cosine-similarity score.

    Thresholds follow community-reported bands for GE2E-trained speaker
    encoders such as Resemblyzer: scores at/above 0.80 indicate a strong
    same-speaker match, 0.75-0.80 a match, 0.60-0.75 a borderline/ambiguous
    result, and below 0.60 different speakers. These are heuristic bands,
    not a calibrated probability.
    """
    if score >= STRONG_MATCH_THRESHOLD:
        return "strong match"
    if score >= MATCH_THRESHOLD:
        return "match"
    if score >= BORDERLINE_THRESHOLD:
        return "borderline"
    return "no match"
