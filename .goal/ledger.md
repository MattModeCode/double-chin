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
| G3 | Phase 1b — Chatterbox MPS fine-tune smoke-train (the gate) | LEAD | BLOCKED(quota) | 1 | env verified OK (torch2.6+MPS, 52GB, weights cached); agent stopped by session limit BEFORE any training — NOT a technical failure. Resume: run the smoke-train. |
| G4 | Phase 2 — recording-script kit (79 takes, ~48 min) DONE; ingest/train pipeline pending | team | PARTIAL | 1 | recording-scripts/ + manifest.tsv shipped; pipeline = G6 |
| G5 | Phase 2 — HUMAN HAND-OFF: scripts delivered to owner | LEAD | DELIVERED | 1 | recording-scripts/README.md; awaiting owner audio (non-blocking) |
| G6 | Phase 3 — engine swap behind existing interface (engine.py, voices.py, config cap) | team | TODO | 0 | preserve synthesize() signature + progress callback |
| G7 | Phase 3 — prosody/style controls through engine→JobRequest→Studio UI→CLI | team | TODO | 0 | levers.md as spec |
| G8 | Phase 4 — indistinguishability suite (ABX/EER/MOS/prosody) + numeric gate + e2e | team | TODO | 0 | reuse demo/quiz pairs |
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

HEARTBEAT: 2026-07-17T22:50:00Z BLOCKED on session usage limit (resets 7pm ET). State committed. Resume via /goal -> G3 smoke-train.


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
