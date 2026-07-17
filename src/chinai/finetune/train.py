"""Real MPS LoRA fine-tune of Chatterbox's T3 stage on an owner's recordings.

Reuses the proven method from `scripts/finetune_chatterbox_smoke.py`:
  - device forced to 'mps' (fallback 'cpu'); fp32 throughout, no autocast /
    GradScaler / fp16 (all CUDA-only on this torch).
  - PYTORCH_ENABLE_MPS_FALLBACK=1 so ops without an MPS kernel run on CPU.
  - peft adapters injected IN PLACE (inject_adapter_in_model) so `t3.tfmr` stays
    a LlamaModel and Chatterbox's custom inference backend keeps working.
  - the cond prompt-speech embedding is reset each step (else autograd backpasses
    through a freed graph).
  - a custom next-token cross-entropy on the speech logits is the objective
    (T3.loss() is not used).

The trained adapter is saved to the voice directory as `lora.pt` and recorded in
the voice's meta.json (`finetuned: true`), so the engine loads it automatically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

# Must be set before torch touches MPS (mirrors the proven smoke script).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from chinai.config import voices_dir
from chinai.finetune import ADAPTER_FILENAME, build_lora_config
from chinai.voices import get_voice, set_finetuned

logger = logging.getLogger(__name__)

DEFAULT_EPOCHS = 5
DEFAULT_LR = 1e-3

# progress(step_1based, total_steps, loss) — mirrors the engine's per-chunk style.
ProgressFn = Callable[[int, int, float], None]


def _pick_device(requested: str | None) -> str:
    import torch

    if requested:
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_base_model(device: str):
    # Xet-backed downloads have been observed to stall on this network; disable
    # Xet before chatterbox triggers any Hugging Face Hub activity (as engine.py).
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from chatterbox.tts import ChatterboxTTS

    return ChatterboxTTS.from_pretrained(device=device)


def _speech_ce(model, example):
    """Next-token cross-entropy on the speech tokens (the TTS objective)."""
    import torch.nn.functional as functional

    # Recompute the cond prompt embedding fresh each step to avoid backpropping
    # through a freed autograd graph.
    example.cond.cond_prompt_speech_emb = None
    out = model.t3.forward(
        t3_cond=example.cond,
        text_tokens=example.text_tokens,
        text_token_lens=example.text_len,
        speech_tokens=example.speech_tokens,
        speech_token_lens=example.speech_len,
        training=True,
    )
    logits = out.speech_logits  # (1, L, V)
    vocab = logits.size(-1)
    # Hidden state at position j predicts token j+1 (causal), matching inference.
    pred = logits[:, :-1, :].reshape(-1, vocab)
    target = example.speech_tokens[:, 1:].reshape(-1)
    return functional.cross_entropy(pred, target)


def finetune_voice(
    name: str,
    recordings_dir,
    *,
    manifest_path=None,
    epochs: int = DEFAULT_EPOCHS,
    max_steps: int | None = None,
    lr: float = DEFAULT_LR,
    val_fraction: float = 0.15,
    seed: int = 0,
    device: str | None = None,
    progress: ProgressFn | None = None,
    model=None,
) -> Path:
    """Fine-tune a LoRA adapter for the enrolled voice `name` and save it.

    Pairs the recording kit (`manifest_path`, default `<recordings_dir>/
    manifest.tsv`) with the audio in `recordings_dir`, runs an in-place LoRA
    fine-tune of the T3 backbone, writes the adapter to `voices/<name>/lora.pt`,
    and flags the voice as fine-tuned in its meta.json.

    `progress`, when given, is called after each optimizer step with
    (step_1based, total_steps, loss). `max_steps`, when set, caps training and
    overrides `epochs * len(train_examples)`.

    Returns the path to the saved adapter.

    Raises:
        ValueError: if the voice is not enrolled, the recordings dir/manifest is
            missing, or no usable training examples are found.
    """
    import torch
    from peft import get_peft_model_state_dict, inject_adapter_in_model

    from chinai.finetune.dataset import build_examples

    # The voice must already be enrolled: synthesis still conditions on its
    # reference clip even with an adapter attached.
    get_voice(name)

    recordings_dir = Path(recordings_dir)
    if not recordings_dir.is_dir():
        raise ValueError(f"recordings directory not found: {recordings_dir}")
    manifest_path = Path(manifest_path) if manifest_path else recordings_dir / "manifest.tsv"
    if not manifest_path.is_file():
        raise ValueError(
            f"manifest not found: {manifest_path}; pass manifest_path or place "
            f"manifest.tsv in {recordings_dir}."
        )

    device = _pick_device(device)
    torch.manual_seed(seed)

    if model is None:
        logger.info("loading base Chatterbox model on %s ...", device)
        model = _load_base_model(device)
    t3 = model.t3

    train_examples, val_examples = build_examples(
        recordings_dir, manifest_path, model, device=device, val_fraction=val_fraction, seed=seed
    )
    logger.info(
        "fine-tune '%s': %d train / %d val examples on %s",
        name,
        len(train_examples),
        len(val_examples),
        device,
    )

    # Attach LoRA to the Llama projections IN PLACE, freeze everything else.
    inject_adapter_in_model(build_lora_config(), t3.tfmr)
    for param in t3.parameters():
        param.requires_grad_(False)
    trainable = [param for pname, param in t3.named_parameters() if "lora_" in pname]
    for param in trainable:
        param.requires_grad_(True)

    optimizer = torch.optim.AdamW(trainable, lr=lr)
    t3.train()

    total_steps = max_steps if max_steps is not None else epochs * len(train_examples)
    if total_steps <= 0:
        raise ValueError("nothing to train: computed zero training steps")

    losses: list[float] = []
    for step in range(total_steps):
        example = train_examples[step % len(train_examples)]
        optimizer.zero_grad()
        loss = _speech_ce(model, example)
        loss.backward()
        optimizer.step()
        if device == "mps":
            torch.mps.synchronize()
        loss_value = float(loss.item())
        losses.append(loss_value)
        if progress is not None:
            progress(step + 1, total_steps, loss_value)

    # Save the adapter into the voice dir and record it in meta.json.
    voice_dir = voices_dir() / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    adapter_path = voice_dir / ADAPTER_FILENAME
    t3.eval()
    torch.save(get_peft_model_state_dict(t3.tfmr), adapter_path)
    set_finetuned(name, True)

    logger.info(
        "saved LoRA adapter -> %s (loss %.3f -> %.3f over %d steps)",
        adapter_path,
        losses[0],
        losses[-1],
        total_steps,
    )
    return adapter_path
