"""Voice-cloned speech synthesis engine for Double Chin."""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from double_chin.chunk import DEFAULT_MAX_CHARS
from double_chin.prosody import (
    EMPHASIS_CFG_WEIGHT_REDUCTION,
    EMPHASIS_EXAGGERATION_BONUS,
    compile_script,
)

DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5
DEFAULT_TEMPERATURE = 0.8
# Speaking-rate range for the post-synthesis, pitch-preserving time-stretch.
# 1.0 is unchanged; >1 speeds up, <1 slows down.
DEFAULT_RATE = 1.0
MIN_RATE = 0.5
MAX_RATE = 2.0


@dataclass
class SynthesisReport:
    """Summary of a completed synthesis run.

    `speed_ratio` is audio seconds produced per wall-clock second (e.g. 0.21
    means synthesis ran at ~1/5th realtime speed, not "4.8x realtime").
    """

    chunk_count: int
    audio_seconds: float
    wall_seconds: float
    speed_ratio: float
    device: str
    out_path: Path


def _pick_device(requested: str | None) -> str:
    import torch

    if requested:
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class DoubleChinEngine:
    """Wraps a lazily-loaded ChatterboxTTS model for voice-cloned synthesis."""

    def __init__(self, device: str | None = None) -> None:
        self._requested_device = device
        self._device: str | None = None
        self._model = None
        # LoRA adapter state. The base model is loaded once and shared across
        # jobs, so we track whether an adapter has been injected and which one is
        # currently loaded, to swap/disable it per voice without reloading.
        self._lora_injected = False
        self._loaded_lora: Path | None = None

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = _pick_device(self._requested_device)
        return self._device

    def _load_model(self):
        if self._model is not None:
            return self._model

        # Xet-backed downloads have been observed to stall indefinitely on
        # this network; disable Xet before the chatterbox import triggers
        # any Hugging Face Hub activity.
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

        from chatterbox.tts import ChatterboxTTS

        self._model = ChatterboxTTS.from_pretrained(device=self.device)
        return self._model

    def _set_adapter_enabled(self, tfmr, enabled: bool) -> None:
        """Enable or disable every injected LoRA layer on `tfmr`."""
        from peft.tuners.tuners_utils import BaseTunerLayer

        for module in tfmr.modules():
            if isinstance(module, BaseTunerLayer):
                module.enable_adapters(enabled)

    def _apply_lora(self, lora_path: Path | None) -> None:
        """Attach, swap, or disable a fine-tuned LoRA adapter on the T3 backbone.

        The base model is shared across voices, so this keeps the injected
        adapter in sync with the requested voice: disabled when `lora_path` is
        None (zero-shot), injected once and (re)loaded when a path is given.
        """
        if lora_path is None:
            if self._lora_injected:
                self._set_adapter_enabled(self._model.t3.tfmr, False)
                self._loaded_lora = None
            return

        lora_path = Path(lora_path)
        if not lora_path.is_file():
            raise ValueError(f"LoRA adapter not found: {lora_path}")

        import torch
        from peft import inject_adapter_in_model, set_peft_model_state_dict

        from double_chin.finetune import build_lora_config

        tfmr = self._model.t3.tfmr
        if not self._lora_injected:
            # Inject IN PLACE so t3.tfmr stays a LlamaModel and Chatterbox's
            # custom inference backend keeps working (matches training).
            inject_adapter_in_model(build_lora_config(), tfmr)
            self._lora_injected = True
        self._set_adapter_enabled(tfmr, True)
        if self._loaded_lora != lora_path:
            state = torch.load(str(lora_path), map_location=self.device)
            set_peft_model_state_dict(tfmr, state)
            self._loaded_lora = lora_path

    def synthesize(
        self,
        script: str,
        reference_wav: Path,
        out_path: Path,
        exaggeration: float = DEFAULT_EXAGGERATION,
        cfg_weight: float = DEFAULT_CFG_WEIGHT,
        temperature: float = DEFAULT_TEMPERATURE,
        max_chars: int = DEFAULT_MAX_CHARS,
        seed: int | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        lora_path: Path | None = None,
        rate: float = DEFAULT_RATE,
    ) -> SynthesisReport:
        """Synthesize `script` in the voice from `reference_wav`, writing `out_path`.

        `progress`, when given, is called at the start of each chunk with
        (chunk_index_1based, chunk_count, chunk_text).

        `lora_path`, when given, is a fine-tuned LoRA adapter (voices/<name>/
        lora.pt) injected into the T3 backbone before generation; when omitted,
        synthesis is plain zero-shot and any previously loaded adapter is
        disabled. This trailing optional argument keeps every existing caller
        working unchanged.

        `rate` is a speaking-rate control applied as a pitch-preserving
        time-stretch to the finished audio (librosa); 1.0 leaves it untouched,
        >1 speaks faster, <1 slower. Chatterbox has no native rate knob, so
        this is genuine cadence control layered on top.

        Inline prosody markup in `script` is compiled by `double_chin.prosody`:
        `[pause:N]` / `[break]` become stitched silence, and `*emphasis*` /
        `[emph]...[/emph]` raise delivery intensity for the spanned chunk.

        Raises:
            ValueError: if `reference_wav` or `lora_path` does not exist,
                `script` is empty, or `rate` is not positive.
        """
        import torch
        import torchaudio

        if not reference_wav.is_file():
            raise ValueError(f"reference audio not found: {reference_wav}")
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate}")

        chunks = compile_script(script, max_chars=max_chars)

        if seed is not None:
            random.seed(seed)
            torch.manual_seed(seed)

        model = self._load_model()
        self._apply_lora(lora_path)
        model.prepare_conditionals(str(reference_wav), exaggeration=exaggeration)

        start_time = time.monotonic()
        pieces: list[torch.Tensor] = []
        for index, chunk in enumerate(chunks, start=1):
            if progress is not None:
                progress(index, len(chunks), chunk.text)
            print(
                f"chunk {index}/{len(chunks)}: {len(chunk.text)} chars",
                file=sys.stderr,
            )
            # An emphasized chunk is delivered hotter: more exaggeration and a
            # touch less reference adherence, clamped to Chatterbox's ranges.
            if chunk.emphasis:
                chunk_exaggeration = min(1.0, exaggeration + EMPHASIS_EXAGGERATION_BONUS)
                chunk_cfg_weight = max(0.0, cfg_weight - EMPHASIS_CFG_WEIGHT_REDUCTION)
            else:
                chunk_exaggeration = exaggeration
                chunk_cfg_weight = cfg_weight

            wav = model.generate(
                chunk.text,
                exaggeration=chunk_exaggeration,
                cfg_weight=chunk_cfg_weight,
                temperature=temperature,
            )
            pieces.append(wav)

            is_last_chunk = index == len(chunks)
            if not is_last_chunk and chunk.pause_after > 0:
                silence_samples = int(chunk.pause_after * model.sr)
                pieces.append(torch.zeros(1, silence_samples))

        audio = torch.cat(pieces, dim=1)
        wall_seconds = time.monotonic() - start_time

        if rate != DEFAULT_RATE:
            # Pitch-preserving time-stretch on the final mono audio. This is a
            # real cadence control Chatterbox lacks; the watermark applied at
            # generation is left intact (we resample, never strip it).
            import librosa

            samples = audio.detach().cpu().numpy().reshape(-1).astype("float32")
            stretched = librosa.effects.time_stretch(samples, rate=float(rate))
            audio = torch.from_numpy(stretched).reshape(1, -1)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(out_path), audio, model.sr)

        audio_seconds = audio.shape[1] / model.sr
        speed_ratio = audio_seconds / wall_seconds if wall_seconds > 0 else 0.0

        return SynthesisReport(
            chunk_count=len(chunks),
            audio_seconds=audio_seconds,
            wall_seconds=wall_seconds,
            speed_ratio=speed_ratio,
            device=self.device,
            out_path=out_path,
        )
