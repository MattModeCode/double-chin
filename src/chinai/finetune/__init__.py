"""LoRA fine-tuning of Chatterbox's T3 (Llama) stage on Apple-Silicon MPS.

This package turns the proven MPS smoke-train
(`scripts/finetune_chatterbox_smoke.py`) into an integrated feature: build a
dataset from the recording kit (`dataset.py`), fine-tune a LoRA adapter for an
enrolled voice (`train.py`), and load that adapter back through the existing
engine at synthesis time.

The LoRA hyper-parameters below are shared by training (`train.py`) and
inference (`engine.py`); they MUST stay in lock-step, since a saved adapter's
tensor shapes are fixed by `r`, `lora_alpha`, and `target_modules`.
"""

from __future__ import annotations

# Filename of the saved adapter inside a voice directory (voices/<name>/lora.pt).
ADAPTER_FILENAME = "lora.pt"

# LoRA config — identical to the proven smoke-train. `target_modules` covers the
# Llama attention + MLP projections; `inject_adapter_in_model` (not
# `get_peft_model`) is used so `t3.tfmr` stays a plain LlamaModel and Chatterbox's
# custom HF inference backend keeps working.
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.0
LORA_TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)


def build_lora_config():
    """Return the shared peft LoraConfig for the T3 backbone.

    Imported lazily so `import chinai.finetune` stays cheap and free of a hard
    peft dependency for callers that only need the constants above.
    """
    from peft import LoraConfig

    return LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        target_modules=list(LORA_TARGET_MODULES),
    )


def __getattr__(name):
    # Lazy re-exports keep the package import light (no torch/peft/chatterbox at
    # import time) while still allowing `from chinai.finetune import finetune_voice`.
    if name == "finetune_voice":
        from chinai.finetune.train import finetune_voice

        return finetune_voice
    if name in ("build_examples", "split_examples", "resolve_audio", "TrainingExample"):
        from chinai.finetune import dataset

        return getattr(dataset, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
