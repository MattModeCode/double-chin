"""Prepare the genuine-voice clips a sweep scores its candidates against.

`voices.enroll` concatenates recordings into a single 20 s reference clip;
the indistinguishability gate instead wants a *set* of separate clips, so it
can measure how separable the real and cloned sets are. This module does the
same per-file conditioning as enrolment — mono, resampled, peak-normalized —
but writes each source out as its own wav.
"""

from __future__ import annotations

from pathlib import Path

from double_chin.config import SAMPLE_RATE, ensure_dir

# Matches voices._PEAK_TARGET: the reference clips the model conditions on are
# normalized to this peak, so the real set the gate compares against should be
# conditioned identically or the level difference leaks into the metrics.
_PEAK_TARGET = 0.9


def prepare_real_clips(sources, out_dir: Path, prefix: str = "real") -> list[Path]:
    """Write each clip in `sources` to `out_dir` as a normalized mono wav.

    Args:
        sources: paths to genuine recordings (any format enrolment accepts,
            including .m4a via the ffmpeg fallback).
        out_dir: directory to write into; created if missing.
        prefix: filename stem prefix, so several sets can share a directory.

    Returns:
        The written wav paths, in the order the sources were given.

    Raises:
        ValueError: if `sources` is empty, a clip is missing, or a clip is
            silent (silence would make every downstream metric meaningless).
    """
    import torchaudio

    from double_chin.voices import _load_waveform

    source_paths = [Path(s) for s in sources]
    if not source_paths:
        raise ValueError("no source clips were given for the real set.")

    out_dir = ensure_dir(Path(out_dir))
    written: list[Path] = []

    for index, source in enumerate(source_paths, start=1):
        if not source.is_file():
            raise ValueError(f"source clip does not exist: {source}")

        waveform, source_sr = _load_waveform(source)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if source_sr != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, source_sr, SAMPLE_RATE)

        peak = waveform.abs().max()
        if peak <= 0:
            raise ValueError(f"source clip is silent: {source}")
        waveform = waveform * (_PEAK_TARGET / peak)

        target = out_dir / f"{prefix}-{index:03d}.wav"
        torchaudio.save(str(target), waveform, SAMPLE_RATE)
        written.append(target)

    return written
