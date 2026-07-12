"""Voice enrollment and lookup for ChinAI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from chinai.config import (
    MAX_REFERENCE_SECONDS,
    MIN_REFERENCE_SECONDS,
    SAMPLE_RATE,
    ensure_dir,
    voices_dir,
)

_NAME_PATTERN = re.compile(r"^[a-z0-9_-]{1,40}$")
_SILENCE_GAP_SECONDS = 0.3
_PEAK_TARGET = 0.9
_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a"}
_FFMPEG_FALLBACK_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


@dataclass
class VoiceInfo:
    """Metadata describing an enrolled voice."""

    name: str
    created: str
    source_files: list[str]
    duration_seconds: float
    sample_rate: int
    holdout_file: str | None = None

    @property
    def reference_wav(self) -> Path:
        return voices_dir() / self.name / "reference.wav"

    @property
    def holdout_wav(self) -> Path | None:
        path = voices_dir() / self.name / "holdout.wav"
        return path if path.is_file() else None


def _validate_name(name: str) -> None:
    if not _NAME_PATTERN.match(name):
        raise ValueError(
            f"invalid voice name '{name}'; use 1-40 lowercase letters, "
            "digits, '-' or '_'."
        )


def _collect_source_files(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        if not source.exists():
            raise ValueError(f"source path does not exist: {source}")

        if source.is_dir():
            found = sorted(
                p for p in source.iterdir()
                if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS
            )
            if not found:
                raise ValueError(
                    f"no wav/flac/mp3/m4a files found in directory: {source}"
                )
            files.extend(found)
            continue

        if source.suffix.lower() not in _AUDIO_EXTENSIONS:
            raise ValueError(
                f"unsupported audio file type: {source} "
                "(expected .wav, .flac, .mp3, or .m4a)"
            )
        files.append(source)

    if not files:
        raise ValueError("no source audio files were provided.")

    return files


def _find_ffmpeg() -> str | None:
    """Locate an ffmpeg binary, checking PATH then common Homebrew locations."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for directory in _FFMPEG_FALLBACK_DIRS:
        candidate = Path(directory) / "ffmpeg"
        if candidate.is_file():
            return str(candidate)
    return None


def _load_waveform(audio_path: Path):
    """Decode `audio_path` into a (waveform, sample_rate) pair.

    torchaudio can decode wav/flac/mp3 directly, but has no bundled AAC
    decoder on most systems and so fails on .m4a. When direct decode fails,
    fall back to transcoding via the ffmpeg CLI into a temporary PCM16 wav
    (channel count preserved) and decoding that instead.

    Raises:
        ValueError: if the file cannot be decoded directly or via ffmpeg.
    """
    import torchaudio

    try:
        return torchaudio.load(str(audio_path))
    except Exception as exc:
        ffmpeg_path = _find_ffmpeg()
        if ffmpeg_path is None:
            raise ValueError(
                f"could not decode audio file: {audio_path} ({exc}); "
                "install ffmpeg (brew install ffmpeg) to support this format."
            ) from exc

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            result = subprocess.run(
                [
                    ffmpeg_path, "-y", "-i", str(audio_path),
                    "-c:a", "pcm_s16le", str(tmp_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ValueError(
                    f"could not decode audio file: {audio_path}; ffmpeg "
                    f"transcoding failed: {result.stderr.strip()}; "
                    "install ffmpeg (brew install ffmpeg) if it's missing "
                    "or outdated."
                )
            return torchaudio.load(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)


def enroll(name: str, sources: list[Path]) -> VoiceInfo:
    """Build a reference clip for `name` from one or more source recordings.

    Each source is converted to mono, resampled to SAMPLE_RATE, and
    peak-normalized, then concatenated with short silence gaps and trimmed
    to MAX_REFERENCE_SECONDS.

    When at least two source files are given and every file except the last
    (in the same deterministic order used to build the reference) still
    totals at least MIN_REFERENCE_SECONDS on its own, the last file is
    reserved as a held-out clip (voices/<name>/holdout.wav) and excluded
    from reference.wav, so `chinai say --verify` can score against audio the
    model was never conditioned on.

    Raises:
        ValueError: on an invalid name, a missing/unsupported source, or a
            combined reference shorter than MIN_REFERENCE_SECONDS.
    """
    _validate_name(name)
    files = _collect_source_files(sources)

    import torch
    import torchaudio

    processed: list[torch.Tensor] = []
    for audio_path in files:
        waveform, source_sr = _load_waveform(audio_path)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if source_sr != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, source_sr, SAMPLE_RATE)

        peak = waveform.abs().max()
        if peak > 0:
            waveform = waveform * (_PEAK_TARGET / peak)

        processed.append(waveform)

    holdout_index: int | None = None
    if len(files) >= 2:
        remaining_seconds = sum(w.shape[1] for w in processed[:-1]) / SAMPLE_RATE
        if remaining_seconds >= MIN_REFERENCE_SECONDS:
            holdout_index = len(files) - 1

    reference_waveforms = processed[:-1] if holdout_index is not None else processed

    silence_samples = int(_SILENCE_GAP_SECONDS * SAMPLE_RATE)
    silence = torch.zeros(1, silence_samples)

    segments: list[torch.Tensor] = []
    for waveform in reference_waveforms:
        segments.append(waveform)
        segments.append(silence)

    # Drop the trailing silence gap that follows the last source clip.
    combined = torch.cat(segments[:-1], dim=1) if segments else torch.zeros(1, 0)

    max_samples = int(MAX_REFERENCE_SECONDS * SAMPLE_RATE)
    combined = combined[:, :max_samples]

    duration_seconds = combined.shape[1] / SAMPLE_RATE
    if duration_seconds < MIN_REFERENCE_SECONDS:
        raise ValueError(
            f"combined reference audio is only {duration_seconds:.1f}s; "
            f"need at least {MIN_REFERENCE_SECONDS:.0f}s. Record more audio "
            "and try again."
        )

    voice_dir = ensure_dir(voices_dir() / name)
    reference_path = voice_dir / "reference.wav"
    torchaudio.save(str(reference_path), combined, SAMPLE_RATE)

    holdout_file: str | None = None
    if holdout_index is not None:
        holdout_path = voice_dir / "holdout.wav"
        torchaudio.save(str(holdout_path), processed[holdout_index], SAMPLE_RATE)
        holdout_file = str(files[holdout_index])

    info = VoiceInfo(
        name=name,
        created=datetime.now(timezone.utc).isoformat(),
        source_files=[str(f) for f in files],
        duration_seconds=duration_seconds,
        sample_rate=SAMPLE_RATE,
        holdout_file=holdout_file,
    )
    meta_path = voice_dir / "meta.json"
    meta_path.write_text(json.dumps(asdict(info), indent=2))
    return info


def list_voices() -> list[VoiceInfo]:
    """Return metadata for all enrolled voices, sorted by name."""
    base = voices_dir()
    if not base.exists():
        return []

    infos: list[VoiceInfo] = []
    for voice_dir in sorted(base.iterdir()):
        meta_path = voice_dir / "meta.json"
        if meta_path.is_file():
            infos.append(_load_meta(meta_path))
    return infos


def get_voice(name: str) -> VoiceInfo:
    """Look up an enrolled voice by name.

    Raises:
        ValueError: if no voice with that name is enrolled.
    """
    meta_path = voices_dir() / name / "meta.json"
    if not meta_path.is_file():
        available = [v.name for v in list_voices()]
        available_text = ", ".join(available) if available else "(none enrolled yet)"
        raise ValueError(
            f"no voice named '{name}' is enrolled. "
            f"Available voices: {available_text}"
        )
    return _load_meta(meta_path)


def _load_meta(meta_path: Path) -> VoiceInfo:
    data = json.loads(meta_path.read_text())
    return VoiceInfo(**data)
