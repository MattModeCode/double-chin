# Decision record — Double Chin voice backend (2026-07-17)

Synthesized by the lead from the Phase-0 research (12 models) + Phase-1 champion/skeptic
tournament (raw data: `.goal/research/`). The final `decision` workflow agent crashed on
oversized input; this record replaces it, made from the recovered cached results.

## Winner (primary): **fine-tuned Chatterbox** (Resemble AI, 0.5B Llama-backbone TTS)
LoRA / adapter fine-tune of the T3 Llama stage on the owner's ~30–60 min of audio, running
on Apple Silicon (MPS), with the existing S3Gen vocoder + voice encoder frozen.

## Fallback (fidelity ceiling): **GPT-SoVITS v2Pro/v4**, CPU-trained, optionally **+ RVC pass**
Invoked only if the Chatterbox smoke-train can't complete on this Mac, or the fine-tuned
Chatterbox can't clear the blind-test gate after data/iteration.

## Universal stage-2 booster: **RVC re-timbre pass** (MIT, Mac-trainable)
Available behind either TTS to lock speaker identity if standalone output doesn't pass the
blind test.

---

## Why Chatterbox over the panel's #1 (GPT-SoVITS) — logged divergence
The panel ranked GPT-SoVITS 85/88 vs Chatterbox 76, weighting the fidelity ceiling (40 pts)
heavily. I am overriding the headline pick for four decisive, well-evidenced reasons the
fidelity-only score under-weighted (per the "make every call yourself, write it down"
contract):

1. **English fit (indistinguishability risk).** The owner's voice is English. GPT-SoVITS is
   Chinese-optimized with *documented residual artifacts on English* (skeptic brief +
   research). For an *indistinguishable* English clone that is a direct hit to the one metric
   that matters most. Chatterbox is English-native.
2. **Smallest integration delta / invariant preservation.** Double Chin's entire engine, enroll,
   Studio, tests, `doctor`, and the mandatory **Perth watermark** are already built around
   Chatterbox (`src/chinai/engine.py:71`). Fine-tuning Chatterbox keeps every mission
   invariant intact and makes the "keep the app fully integrated" DoD nearly free. GPT-SoVITS
   is a two-stage pipeline + separate macOS env pin = large integration + fragility surface.
3. **Fast MPS iteration.** Reaching "indistinguishable" needs many retrain passes. Chatterbox
   MPS *inference* is proven near-real-time, and its *training* is architecturally the most
   plausible MPS path (champion **source-verified** no CUDA-only deps — no
   bitsandbytes/DeepSpeed/flash-attn; trainable part is a plain HF Llama transformer via HF
   Trainer / peft-LoRA, both MPS-capable). GPT-SoVITS's maintainers **disown MPS training**
   and force CPU (~37× slower) — iterating an indistinguishable clone on CPU is impractical.
4. **Prosody.** Chatterbox ships a dial-able "exaggeration" emotion knob (a real, native
   delivery lever), a head start on the mission's cadence/style requirement.

Fidelity gap (8 vs 9): Chatterbox already scores 0.88–0.95 speaker-cosine *zero-shot* on the
owner (`docs/design.md`); fine-tuning + the optional RVC booster closes the 1-point ceiling
gap, and English-native quality likely nets ahead for this specific voice.

## The honest risk (what the smoke-train must resolve)
No repo yet ships a *reproduced* Chatterbox fine-tune on MPS — `example_for_mac.py` is
inference-only. It needs a device patch (add `mps` to the cuda/cpu ternary; fp32 or
partial-bf16, **not** fp16 — MPS autocast/GradScaler are CUDA-only; `PYTORCH_ENABLE_MPS_
FALLBACK=1`; pre-transcribe to skip the hardcoded `whisper device=cuda`). Fine-tune toolkits:
gokhaneraslan (Apache-2.0, peft-LoRA), stlohrey / davidbrowne17 (MIT).

## Local fine-tune plan (G3 — the disqualifying gate, run BEFORE committing)
1. Stand up an isolated env; pin torch 2.6 / transformers per toolkit; confirm MPS is live.
2. Grab a few minutes of public-domain stand-in audio (e.g. LibriVox) for the smoke-train.
3. Patch a Chatterbox fine-tune toolkit for MPS (device patch + fp32/bf16 + fallback + skip
   cuda-whisper). Run a **short** LoRA (few steps) to prove the training loop **completes on
   this Mac** and lowers loss.
4. Synthesize with the tiny checkpoint; confirm it moves speaker-similarity vs base zero-shot.
5. Log command + output in `.goal/ledger.md`. **This is the gate**, not a README claim.

## Prosody plan
Native Chatterbox `exaggeration` (emotion) + `cfg_weight` + `temperature` already exist; add a
real prosody layer on top: inline pause/break markup (compiled to the existing silence-stitch
in `chunk.py`, extended beyond the two fixed lengths), speaking-rate, and per-span emphasis,
plus optional style-reference conditioning — threaded engine → `JobRequest` → Studio UI + CLI,
using `.claude/skills/chinai-perform/references/levers.md` as the spec.

## Kill-criteria → fall back to GPT-SoVITS (CPU) [+ RVC]
- Chatterbox MPS training cannot complete on this Mac after reasonable device-patching, OR
- fine-tuned Chatterbox plateaus below the blind-test indistinguishability gate after data
  iteration AND the RVC booster doesn't close it.

## Full field (why the others lost)
Gate-PASSERS (real Apple-Silicon fine-tune evidence): GPT-SoVITS, XTTS-v2 (CPU-only, but
**non-commercial CPML** license), RVC, so-vits-svc (converters, not TTS), Chatterbox
(plausible/verify). Gate-FAILERS (CUDA-only trainers, Mac inference-only) despite high
fidelity: CosyVoice 2, IndexTTS-2, StyleTTS2, F5-TTS, VibeVoice, Fish-Speech, Llasa — several
also non-commercial/gated licenses. Full per-model reports + URLs in `.goal/research/`.
