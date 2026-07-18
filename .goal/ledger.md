# /goal ledger — ChinAI: make the cloned voice indistinguishable

**Mission:** Replace the zero-shot Chatterbox backend with a fine-tuned, local, free,
Apple-Silicon voice model that is *indistinguishable* from the owner's real voice, add
prosody/cadence/style control, and keep the whole app integrated and usable. Only human
input allowed: recording audio from supplied scripts.

**Branch:** `build/indistinguishable-voice` (base `main` @ e4e9f83)
**Machine:** M5 Pro (Apple Silicon, MPS). **Guardrails:** no spend · publish nothing ·
never ask · nothing leaves the machine · keep offline unit suite green.

## Definition of done
See `.claude/commands/goal.md` §9. Summary: new backend integrated behind the existing
engine interface; app works end-to-end in owner's voice via Studio + CLI + desktop;
prosody/style controls work; recording kit + one-command train delivered; model clears a
numeric indistinguishability gate on the owner's real voice (blind ABX / EER / MOS, not
just cosine); `pytest -m "not slow"` green + new `CHINAI_E2E=1` e2e passes; shipped as PR.

## Tasks
| ID | Task | Owner | Status | Attempts | Notes |
|----|------|-------|--------|----------|-------|
| G0 | Bootstrap: branch + `.goal/` + ledger | LEAD | DONE | 1 | branch build/indistinguishable-voice |
| G1 | Phase 0 — research fan-out (12 models, 6 researchers) | Workflow team | DONE | 1 | seed: StyleTTS2, GPT-SoVITS, XTTS-v2, F5-TTS, Fish/OpenAudio, IndexTTS-2, CosyVoice2, Llasa, VibeVoice, Chatterbox-finetune, RVC, so-vits-svc |
| G2 | Phase 1 — judge tournament + decision record | Workflow judges + LEAD | DONE | 1 | criteria: indistinguishability ≫ prosody > proven-local-Mac > latency > risk |
| G3 | Phase 1b — Chatterbox MPS fine-tune smoke-train (the gate) | LEAD | **PASS** | 2 | MPS LoRA trains: loss 3.53->0.03/60 steps, ~0.2s/step, adapter save+reload+generate OK. Primary decision validated; GPT-SoVITS fallback NOT triggered. Script: scripts/finetune_chatterbox_smoke.py |
| G4 | Phase 2 — recording kit + ingest/train pipeline | team | DONE | 2 | kit + finetune/dataset.py ingest of manifest.tsv+NNN audio |
| G5 | Phase 2 — HUMAN HAND-OFF: scripts delivered to owner | LEAD | DELIVERED | 1 | recording-scripts/README.md; awaiting owner audio (non-blocking) |
| G6 | Phase 3 — finetune pipeline + LoRA-aware engine integration | team | DONE | 1 | src/chinai/finetune/; `chinai train`; engine lora_path kwarg; 63 tests green |
| G7 | Phase 3 — prosody controls (pause/emphasis markup + rate) | team | DONE | 1 | src/chinai/prosody.py; --rate; UI slider; 89 tests green |
| G8 | Phase 4 — indistinguishability gate (EER/ABX+naturalness+prosody) | team | DONE | 1 | src/chinai/verification/; `chinai gate`; 107 tests; demo/quiz 0.886 PASS |
| G9 | Phase 5 — integrate Studio+CLI+desktop, docs, recap, red-team, ship PR | LEAD | TODO | 0 | auto-ship |

## Decisions (append-only)
- D0 (2026-07-17): Backend boundary = local + free + Apple-Silicon only (owner's call: no
  cloud GPU, no paid API). Execution = single session, heavy internal orchestration.
- D1 (2026-07-17): Root cause of "distinguishable" = zero-shot conditioning (≤6–10 s of
  reference used; extra audio discarded; no prosody control). Fix requires a fine-tuned
  speaker model, not tuning. Source: docs/design.md:56, engine.py:76-137, config.py:11.

- D2 (2026-07-17): WINNER = fine-tuned **Chatterbox** (primary); fallback GPT-SoVITS v2Pro/v4
  (CPU) + optional RVC re-timbre pass; RVC as universal stage-2 booster. Diverged from panel
  #1 (GPT-SoVITS) for English-fit + smallest-integration-delta + fast-MPS-iteration +
  MPS-training-plausibility. Full reasoning in `.goal/decision.md`. Research in `.goal/research/`.
- D3 (2026-07-17): Workflow decision-agent crashed (oversized structured-output input, retry cap).
  Recovered 13/14 cached agent results from journal; lead synthesized the decision. Fix for
  future workflows: pass compacted summaries to synthesis agents, not full raw JSON.

## Attempts log (append-only)
- G0 attempt 1: branch + .goal scaffold created.
- G1 attempt 1: Workflow wf_81ffd69b-235 — 6 researchers + shortlist + 6 debates DONE (692k tok).
- G2 attempt 1: decision synthesized by lead from recovered cache → .goal/decision.md.
- G3 attempt 1: NEXT — set up Chatterbox fine-tune env + MPS device patch + short smoke-train.

HEARTBEAT: 2026-07-18T00:05:00Z G8 DONE (gate, 107 tests). Next: G9 docs + open PR; then audio-gated pause.


## RESUME NOTE (2026-07-17T22:50Z — session usage limit, resets 7pm America/Toronto)
State is fully committed on branch build/indistinguishable-voice. Nothing lost.
Next action when capacity returns (run `/goal`, or `/loop /goal`):
1. G3 smoke-train (the gate): install peft+datasets+accelerate (free); inspect
   .venv/lib/python3.12/site-packages/chatterbox (T3 Llama + S3 tokenizer); write
   scripts/finetune_chatterbox_smoke.py with LoRA on T3, fp32, device='mps',
   PYTORCH_ENABLE_MPS_FALLBACK=1 (no fp16/GradScaler, no cuda-hardcoded whisper);
   run 30-100 steps on a tiny stand-in set; PASS if loss drops on mps. FAIL -> GPT-SoVITS fallback.
2. Then G6 ingest pipeline (manifest.tsv + NNN.wav -> dataset), G6/G7 engine+prosody,
   G8 indistinguishability suite, G9 integrate+ship. Full real fine-tune needs owner's audio.
Owner action (parallel, non-blocking): record recording-scripts/001..079.txt -> 001.m4a...


## G3 RESULT (2026-07-17 — PASS)
Chatterbox T3 LoRA fine-tunes on MPS. Real fine-tune est ~20-40 min for a 48-min corpus.
Deps added (uv pip): peft 0.19.1, datasets 5.0.0, accelerate 1.14.0 (transformers 5.2.0 kept).
Load-bearing MPS gotchas for the real fine-tune (from scripts/finetune_chatterbox_smoke.py):
- device='mps', fp32 only (no autocast/GradScaler/fp16), PYTORCH_ENABLE_MPS_FALLBACK=1.
- peft: inject_adapter_in_model(cfg, t3.tfmr) IN-PLACE (NOT get_peft_model — breaks T3 inference backend).
- reset cond.cond_prompt_speech_emb=None each step (else 'backward through freed graph').
- don't use T3.loss(); compute next-token CE: speech_logits[:,:-1] vs speech_tokens[:,1:].
- target speech seq = S3 tokens wrapped with start=6561 / stop=6562.
NEXT: G6 build src/chinai/finetune/ (ingest manifest.tsv+NNN.wav -> dataset; train() using the
above), a `chinai train` CLI command, and engine loads a voice's LoRA adapter if present (else
zero-shot). Testable now with stand-in voices; real fine-tune runs on owner's audio.
