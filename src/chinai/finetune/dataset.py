"""Build (text, target-speech-token) training examples from the recording kit.

Pairs each `take_id` in a `manifest.tsv` with an audio file `NNN.{wav,m4a,mp3,
flac}` in the recordings directory (matched by the 3-digit id), then tokenizes
each pair exactly as the proven smoke-train does: the transcript through the T3
text tokenizer, and the audio through the S3 speech tokenizer wrapped with the
model's start/stop speech tokens (== S3 SOS/EOS, 6561/6562).

Decoding reuses `voices._load_waveform`, which has an ffmpeg fallback for the
`.m4a` clips the recording kit produces. Missing or corrupt takes are logged and
skipped rather than crashing the build.
"""

from __future__ import annotations

import csv
import logging
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chinai.voices import _load_waveform

logger = logging.getLogger(__name__)

# Audio extensions probed, in priority order, when matching a take id to a file.
_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".m4a")

# Sample rate the S3 speech tokenizer expects (== chatterbox.models.s3tokenizer
# .S3_SR). Hardcoded so this module imports without pulling in chatterbox; a
# mismatch would surface immediately in the slow real-train test.
S3_TARGET_SR = 16000

DEFAULT_VAL_FRACTION = 0.15


@dataclass
class TrainingExample:
    """One tokenized (text, speech) pair plus its per-clip T3 conditioning."""

    take_id: str
    audio_path: Path
    text: str
    cond: Any  # T3Cond for this clip (from model.prepare_conditionals)
    text_tokens: Any  # (1, T) long tensor, start/stop-text wrapped
    text_len: Any  # (1,) long tensor
    speech_tokens: Any  # (1, S) long tensor, start/stop-speech wrapped
    speech_len: Any  # (1,) long tensor


def iter_manifest(manifest_path: Path):
    """Yield (take_id, transcript) rows from a recording-kit manifest.tsv."""
    with Path(manifest_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            take_id = (row.get("take_id") or "").strip()
            transcript = (row.get("transcript") or "").strip()
            if take_id and transcript:
                yield take_id, transcript


def resolve_audio(recordings_dir: Path, take_id: str) -> Path | None:
    """Return the audio file for `take_id` (matched by 3-digit id), or None."""
    recordings_dir = Path(recordings_dir)
    for extension in _AUDIO_EXTENSIONS:
        candidate = recordings_dir / f"{take_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def build_example(model, audio_path: Path, text: str, device: str, take_id: str = "") -> TrainingExample:
    """Tokenize one (audio, text) pair into a TrainingExample.

    Mirrors `scripts/finetune_chatterbox_smoke.py`'s `build_example`: per-clip
    speaker/prosody conditioning, S3 speech tokens wrapped with the model's
    start/stop speech tokens, and start/stop-text-wrapped text tokens.
    """
    import torch
    import torch.nn.functional as functional
    import torchaudio

    hp = model.t3.hp
    audio_path = Path(audio_path)

    # Decode once through the shared loader (ffmpeg fallback covers .m4a), then
    # reuse that waveform for both the conditioning clip and the tokenizer so
    # every supported format follows one decode path.
    waveform, source_sr = _load_waveform(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    # prepare_conditionals wants a file path; feed it a temp wav of the decoded
    # clip so .m4a/.flac inputs condition just like a native .wav would.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        torchaudio.save(str(tmp_path), waveform, source_sr)
        model.prepare_conditionals(str(tmp_path))
        cond = model.conds.t3
    finally:
        tmp_path.unlink(missing_ok=True)

    # Target speech tokens via the S3 tokenizer (needs 16 kHz mono), wrapped with
    # the model's start/stop speech tokens (== S3 SOS/EOS).
    if source_sr != S3_TARGET_SR:
        wav16 = torchaudio.functional.resample(waveform, source_sr, S3_TARGET_SR)
    else:
        wav16 = waveform
    wav16_np = wav16.squeeze(0).cpu().numpy()
    s3_tokens, _ = model.s3gen.tokenizer.forward([wav16_np])
    s3_tokens = s3_tokens.to(device)
    sos = torch.full((1, 1), hp.start_speech_token, dtype=torch.long, device=device)
    eos = torch.full((1, 1), hp.stop_speech_token, dtype=torch.long, device=device)
    speech = torch.cat([sos, s3_tokens, eos], dim=1)

    # Text tokens, padded with start/stop text tokens.
    text_tokens = model.tokenizer.text_to_tokens(text).to(device)
    text_tokens = functional.pad(text_tokens, (1, 0), value=hp.start_text_token)
    text_tokens = functional.pad(text_tokens, (0, 1), value=hp.stop_text_token)

    text_len = torch.tensor([text_tokens.size(1)], dtype=torch.long, device=device)
    speech_len = torch.tensor([speech.size(1)], dtype=torch.long, device=device)
    return TrainingExample(
        take_id=take_id,
        audio_path=audio_path,
        text=text,
        cond=cond,
        text_tokens=text_tokens,
        text_len=text_len,
        speech_tokens=speech,
        speech_len=speech_len,
    )


def split_examples(examples, *, val_fraction: float = DEFAULT_VAL_FRACTION, seed: int = 0):
    """Deterministically split into (train, val).

    A seeded shuffle keeps the split reproducible. With fewer than two examples
    there is nothing to hold out, so everything goes to train; otherwise at least
    one example stays in each side.
    """
    items = list(examples)
    random.Random(seed).shuffle(items)
    if len(items) < 2:
        return items, []
    n_val = max(1, round(len(items) * val_fraction))
    n_val = min(n_val, len(items) - 1)  # always leave at least one in train
    return items[n_val:], items[:n_val]


def build_examples(
    recordings_dir,
    manifest_path,
    model,
    *,
    device: str = "cpu",
    val_fraction: float = DEFAULT_VAL_FRACTION,
    seed: int = 0,
):
    """Build (train, val) TrainingExample lists from a recordings dir + manifest.

    `model` is a loaded ChatterboxTTS (or a test double exposing the same
    tokenizer/`s3gen`/`conds`/`t3.hp` surface). Takes whose audio is missing or
    fails to decode/tokenize are logged and skipped.

    Raises:
        ValueError: if the manifest is missing, or no take produced a usable
            example.
    """
    recordings_dir = Path(recordings_dir)
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise ValueError(f"manifest not found: {manifest_path}")

    examples: list[TrainingExample] = []
    skipped = 0
    for take_id, text in iter_manifest(manifest_path):
        audio_path = resolve_audio(recordings_dir, take_id)
        if audio_path is None:
            logger.warning(
                "take %s: no audio file (%s) found in %s; skipping",
                take_id,
                "/".join(f"{take_id}{ext}" for ext in _AUDIO_EXTENSIONS),
                recordings_dir,
            )
            skipped += 1
            continue
        try:
            examples.append(build_example(model, audio_path, text, device, take_id=take_id))
        except Exception as exc:  # noqa: BLE001 - a bad clip must not sink the run
            logger.warning(
                "take %s (%s): failed to build example (%s); skipping",
                take_id,
                audio_path.name,
                exc,
            )
            skipped += 1

    if not examples:
        raise ValueError(
            f"no usable training examples: matched 0 decodable audio files under "
            f"{recordings_dir} for manifest {manifest_path}"
        )
    logger.info("built %d training examples (%d skipped)", len(examples), skipped)
    return split_examples(examples, val_fraction=val_fraction, seed=seed)
