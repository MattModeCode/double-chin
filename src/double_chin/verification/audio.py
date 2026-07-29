"""Shared audio loading and speaker-embedding helpers for the verification suite.

Every metric in the suite reads clips through this module so decoding,
resampling and the Resemblyzer encoder are handled in exactly one place.
Loading goes through librosa (soundfile backend), which transparently handles
the mixed formats in this repo — 16 kHz PCM16 reference clips and 24 kHz float
synthesized clips — and always returns mono float32 in [-1, 1].
"""

from __future__ import annotations

from pathlib import Path

# Analysis sample rate for signal-based metrics (naturalness, prosody). 16 kHz
# is plenty for speech F0/formant/pause structure and keeps pyin fast.
ANALYSIS_SR = 16000

# A clip whose peak amplitude is below this is treated as empty: scoring
# silence-versus-silence is meaningless (Resemblyzer will happily rate two
# noise clips at ~0.99). Matches the spirit of verify._SILENCE_RMS_THRESHOLD.
_MIN_PEAK = 0.01


def load_mono(path: Path, sr: int = ANALYSIS_SR):
    """Decode `path` to a mono float32 numpy array at `sr`.

    Raises:
        ValueError: if the clip is empty or near-silent, so downstream metrics
            never run on meaningless input.
    """
    import librosa
    import numpy as np

    wav, _ = librosa.load(str(path), sr=sr, mono=True)
    wav = wav.astype(np.float32)
    if wav.size == 0 or float(np.max(np.abs(wav))) < _MIN_PEAK:
        raise ValueError(
            f"audio is empty or near-silent ({path}); verification metrics on "
            "silence are meaningless."
        )
    return wav


def embed_clip(path: Path):
    """Return the L2-normalized Resemblyzer speaker embedding for one clip.

    Reuses the same process-wide cached encoder and preprocessing as
    `double_chin.verify.similarity`, so embeddings are directly comparable via dot
    product (cosine similarity).
    """
    from resemblyzer import preprocess_wav

    from double_chin.verify import _get_encoder

    encoder = _get_encoder()
    return encoder.embed_utterance(preprocess_wav(Path(path)))


def embed_clips(paths: list[Path]) -> list:
    """Embed a list of clips, preserving order."""
    return [embed_clip(p) for p in paths]


def as_paths(clips) -> list[Path]:
    """Coerce a directory, a single file, or an iterable of paths into a
    sorted list of wav Paths.

    Passing a directory selects its ``*.wav`` files (sorted); this is what
    lets the CLI point the suite at a folder of clips.
    """
    if isinstance(clips, (str, Path)):
        path = Path(clips)
        if path.is_dir():
            found = sorted(path.glob("*.wav"))
            if not found:
                raise ValueError(f"no .wav files found in directory: {path}")
            return found
        return [path]
    return [Path(p) for p in clips]
