#!/usr/bin/env python
"""Feasibility gate: LoRA fine-tune Chatterbox's T3 (Llama) stage on Apple-Silicon MPS.

This is a SMOKE TEST, not a good model. PASS = the training loop runs on
device='mps' (no CUDA) and the speech-token cross-entropy loss drops.

CUDA-isms patched for MPS (see report):
  - device forced to 'mps' (fallback 'cpu'); no device='cuda' anywhere
  - fp32 throughout; NO fp16 autocast / GradScaler (both CUDA-only on this torch)
  - PYTORCH_ENABLE_MPS_FALLBACK=1 so any op without an MPS kernel silently
    runs on CPU instead of crashing
  - transcripts supplied inline -> no whisper auto-transcribe (its default is
    device='cuda' in the community toolkits)
  - peft adapters injected IN PLACE (inject_adapter_in_model) so t3.tfmr stays a
    LlamaModel and the custom HF inference backend keeps working

Run:
  PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python scripts/finetune_chatterbox_smoke.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# Must be set before torch touches MPS.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import librosa
import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model_state_dict, inject_adapter_in_model, set_peft_model_state_dict

from chatterbox.tts import ChatterboxTTS
from chatterbox.models.s3tokenizer import S3_SR

STEPS = 60
LR = 1e-3
LORA_R = 16
LORA_ALPHA = 32
ADAPTER_DIR = Path(os.path.expanduser("~/.chinai/finetune_smoke"))
REPO = Path(__file__).resolve().parent.parent

# (wav, transcript). Transcripts are the standard CMU-ARCTIC prompts for the
# arctic clips; ref_a/ref_b use a nominal Harvard sentence. Exact text<->audio
# alignment is NOT required for this gate (it only asks "does MPS loss drop?"),
# but real ARCTIC text keeps the objective meaningful.
DATA = [
    ("demo/assets/arctic_0001.wav", "Author of the danger trail, Philip Steels, etc."),
    ("demo/assets/arctic_0002.wav", "Not at this particular case, Tom, apologized Whittemore."),
    ("demo/assets/arctic_0003.wav", "For the twentieth time that evening the two men shook hands."),
    ("demo/assets/arctic_0005.wav", "Will we ever forget it."),
    ("demo/assets/arctic_0008.wav", "And you always want to see it in the superlative degree."),
    ("demo/assets/ref_a.wav", "The birch canoe slid on the smooth planks."),
    ("demo/assets/ref_b.wav", "The boy was there when the sun rose."),
]


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def build_example(model: ChatterboxTTS, wav_path: str, text: str, device: str):
    """Return (t3_cond, text_tokens, text_len, speech_tokens, speech_len)."""
    hp = model.t3.hp

    # Speaker/prosody conditioning from the same clip (voice-encoder + S3 prompt).
    model.prepare_conditionals(wav_path)
    cond = model.conds.t3

    # Target speech tokens via the S3 tokenizer (25 tok/s), wrapped with the
    # model's start/stop speech tokens (== S3 SOS/EOS).
    wav16, _ = librosa.load(wav_path, sr=S3_SR)
    s3_tokens, _ = model.s3gen.tokenizer.forward([wav16])
    s3_tokens = s3_tokens.to(device)
    sos = torch.full((1, 1), hp.start_speech_token, dtype=torch.long, device=device)
    eos = torch.full((1, 1), hp.stop_speech_token, dtype=torch.long, device=device)
    speech = torch.cat([sos, s3_tokens, eos], dim=1)

    # Text tokens, padded with start/stop text tokens.
    tt = model.tokenizer.text_to_tokens(text).to(device)
    tt = F.pad(tt, (1, 0), value=hp.start_text_token)
    tt = F.pad(tt, (0, 1), value=hp.stop_text_token)

    tlen = torch.tensor([tt.size(1)], dtype=torch.long, device=device)
    slen = torch.tensor([speech.size(1)], dtype=torch.long, device=device)
    return cond, tt, tlen, speech, slen


def speech_ce(model: ChatterboxTTS, cond, tt, tlen, speech, slen) -> torch.Tensor:
    """Next-token cross-entropy on speech tokens (the TTS objective)."""
    # Recompute cond prompt embedding fresh each step (avoid stale autograd graph).
    cond.cond_prompt_speech_emb = None
    out = model.t3.forward(
        t3_cond=cond,
        text_tokens=tt,
        text_token_lens=tlen,
        speech_tokens=speech,
        speech_token_lens=slen,
        training=True,
    )
    logits = out.speech_logits  # (1, L, V)
    vocab = logits.size(-1)
    # hidden at position j predicts token j+1 (causal), matching t3.inference().
    pred = logits[:, :-1, :].reshape(-1, vocab)
    tgt = speech[:, 1:].reshape(-1)
    return F.cross_entropy(pred, tgt)


def main() -> None:
    device = pick_device()
    torch.manual_seed(0)
    print(f"[env] torch={torch.__version__}  device={device}  "
          f"mps_available={torch.backends.mps.is_available()}  "
          f"fallback={os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK')}")
    assert device == "mps", "MPS not available -- this gate must run on MPS"

    print("[load] ChatterboxTTS.from_pretrained ...")
    model = ChatterboxTTS.from_pretrained(device)
    t3 = model.t3
    print(f"[load] t3 backbone = {type(t3.tfmr).__name__}  dim={t3.dim}  "
          f"param_dtype={next(t3.parameters()).dtype}")

    # --- Attach LoRA to the Llama attention + MLP projections, in place ---
    lora_cfg = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=0.0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    inject_adapter_in_model(lora_cfg, t3.tfmr)

    # Freeze everything, train only LoRA params.
    for p in t3.parameters():
        p.requires_grad_(False)
    trainable = []
    for n, p in t3.named_parameters():
        if "lora_" in n:
            p.requires_grad_(True)
            trainable.append(p)
    n_train = sum(p.numel() for p in trainable)
    n_total = sum(p.numel() for p in t3.parameters())
    print(f"[lora] trainable params = {n_train:,} / {n_total:,} "
          f"({100 * n_train / n_total:.3f}%)")

    # --- Build the tiny training set ---
    print(f"[data] building {len(DATA)} (text, speech-token) examples ...")
    examples = []
    for rel, text in DATA:
        cond, tt, tlen, speech, slen = build_example(model, str(REPO / rel), text, device)
        examples.append((cond, tt, tlen, speech, slen))
        print(f"[data]   {Path(rel).name:20s} text_tok={tt.size(1):3d} "
              f"speech_tok={speech.size(1):3d}")

    # --- Train ---
    opt = torch.optim.AdamW(trainable, lr=LR)
    t3.train()
    print(f"[train] {STEPS} steps, batch=1, fp32, lr={LR} on {device}")
    losses = []
    step_times = []
    for step in range(STEPS):
        cond, tt, tlen, speech, slen = examples[step % len(examples)]
        t0 = time.time()
        opt.zero_grad()
        loss = speech_ce(model, cond, tt, tlen, speech, slen)
        loss.backward()
        opt.step()
        if device == "mps":
            torch.mps.synchronize()
        dt = time.time() - t0
        step_times.append(dt)
        losses.append(loss.item())
        if step % 5 == 0 or step == STEPS - 1:
            print(f"[train] step {step:3d}  device={loss.device.type}  "
                  f"speech_ce={loss.item():.4f}  {dt*1000:.0f} ms/step")

    warm = step_times[3:] or step_times
    sec_per_step = sum(warm) / len(warm)
    print(f"\n[result] first_loss={losses[0]:.4f}  last_loss={losses[-1]:.4f}  "
          f"min_loss={min(losses):.4f}  drop={losses[0]-losses[-1]:.4f}")
    print(f"[result] steady-state ~{sec_per_step:.3f} s/step on {device}")

    # --- Save + reload the adapter, then a sanity generate ---
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    adapter_path = ADAPTER_DIR / "t3_lora.pt"
    sd = get_peft_model_state_dict(t3.tfmr)
    torch.save(sd, adapter_path)
    print(f"[save] adapter -> {adapter_path} ({len(sd)} tensors, "
          f"{sum(v.numel() for v in sd.values()):,} params)")

    # Reload into the (still-injected) model from disk to prove serialization.
    reloaded = torch.load(adapter_path, map_location=device)
    set_peft_model_state_dict(t3.tfmr, reloaded)
    print("[reload] adapter state reloaded from disk")

    print("[gen] sanity generate with the LoRA-adapted model ...")
    try:
        t3.eval()
        model.prepare_conditionals(str(REPO / "demo/assets/ref_a.wav"))
        wav = model.generate("This is a smoke test of the fine-tuned model.")
        out_wav = ADAPTER_DIR / "sanity.wav"
        import torchaudio
        torchaudio.save(str(out_wav), wav, model.sr)
        dur = wav.shape[-1] / model.sr
        print(f"[gen] OK -> {out_wav}  ({dur:.2f}s audio, shape={tuple(wav.shape)})")
    except Exception as e:  # noqa: BLE001 - report but don't fail the gate
        print(f"[gen] WARN generate raised: {type(e).__name__}: {e}")

    verdict = "PASS" if losses[-1] < losses[0] - 0.5 else "REVIEW"
    print(f"\n[VERDICT] {verdict}  (loss {losses[0]:.3f} -> {losses[-1]:.3f} on mps)")


if __name__ == "__main__":
    main()
