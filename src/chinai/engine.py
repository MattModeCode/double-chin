"""Voice-cloned speech synthesis engine for ChinAI."""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from chinai.chunk import DEFAULT_MAX_CHARS, split_script

DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5
DEFAULT_TEMPERATURE = 0.8


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


class ChinaiEngine:
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

        from chinai.finetune import build_lora_config

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
    ) -> SynthesisReport:
        """Synthesize `script` in the voice from `reference_wav`, writing `out_path`.

        `progress`, when given, is called at the start of each chunk with
        (chunk_index_1based, chunk_count, chunk_text).

        `lora_path`, when given, is a fine-tuned LoRA adapter (voices/<name>/
        lora.pt) injected into the T3 backbone before generation; when omitted,
        synthesis is plain zero-shot and any previously loaded adapter is
        disabled. This trailing optional argument keeps every existing caller
        working unchanged.

        Raises:
            ValueError: if `reference_wav` or `lora_path` does not exist, or
                `script` is empty.
        """
        import torch
        import torchaudio

        if not reference_wav.is_file():
            raise ValueError(f"reference audio not found: {reference_wav}")

        chunks = split_script(script, max_chars=max_chars)

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
            wav = model.generate(
                chunk.text,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
            )
            pieces.append(wav)

            is_last_chunk = index == len(chunks)
            if not is_last_chunk and chunk.pause_after > 0:
                silence_samples = int(chunk.pause_after * model.sr)
                pieces.append(torch.zeros(1, silence_samples))

        audio = torch.cat(pieces, dim=1)
        wall_seconds = time.monotonic() - start_time

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
