# Foreman ledger — ChinAI voice clone build

## Baseline
- Commit: d810d59 (Initial commit), branch main
- Dirty at start: untracked `master-prompt.md`
- Mode: **Full** (Agent tool + real shell). Codex unprobed/unused: master-prompt guardrail 1 (no new spending) + guardrail 3 (never ask) make Codex billing consent impossible. Claude seats only.
- LEAD: Fable 5 (frontier-class, verified via system context).

## Tasks
| ID | Task | Seat | Status | Attempts |
|----|------|------|--------|----------|
| T1 | Research: local voice-clone model landscape (licenses, MPS, URLs) | FAST/scout (bg agent) | DONE — Chatterbox #1 (MIT, MPS), fallback mlx-audio | 1 |
| T2 | Research: recording best practices, phonetic scripts, speaker verification | FAST/scout (bg agent) | DONE — resemblyzer tested on-machine; Rainbow/Harvard scripts; recipe | 1 |
| T3 | Deterministic check: chatterbox-tts installs + synthesizes on M5 Pro (MPS) | LEAD-run check | DONE — load 7-9s MPS; clone vs stand-in similarity **0.902**; RTF 4.8 (attempts: pkg_resources → setuptools<81) | 3 |
| T4 | Judgment: pick approach, write design doc + build log skeleton | LEAD | DONE — docs/design.md + docs/build-log.md (D1–D9) | 1 |
| T5 | Implement core package (CLI, engine, chunking, enroll, verify) + tests | WORKHORSE (sonnet) | DONE (worker) — 28 unit tests pass; LEAD re-ran suite + doctor + enroll OK; blind verify pending | 1 |
| T6 | Recording-script kit for user (the one allowed hand-off) | WORKHORSE (sonnet) | DONE — LEAD review fixed truncated Rainbow Passage | 1 |
| T7 | Brand identity, README, recap.html (mashuai-brand constraints) | WORKHORSE (sonnet) + LEAD review | PENDING | 0 |
| T8 | Demo video + walkthrough video (ffmpeg pipeline, cloned-voice narration) | WORKHORSE (sonnet) | PENDING | 0 |
| T9 | Red team: adversarial review of claims + product | FRONTIER-adjacent agent | PENDING | 0 |
| T10 | Blind verification: end-to-end script→audio on committed state | foreman-verifier | PENDING | 0 |
| T11 | Completeness critic vs definition of done | verifier-style agent | PENDING | 0 |
| T12 | Commit + push per auto-ship rule | LEAD | PENDING | 0 |

## Attempts log (append-only)
- T1 attempt 1: dispatched general-purpose bg agent (model landscape) — pre-foreman, reconciled here.
- T2 attempt 1: dispatched general-purpose bg agent (data/verification) — pre-foreman, reconciled here.
- T3 attempt 1: bg bash job bd90n7u3t running smoke_chatterbox.py (model download + 1-line synth).

## Decisions (never-ask log lives in docs/build-log.md once created)
- D1: Codex excluded (see Mode above).
- D2: Front-runner model = Chatterbox TTS (MIT code+weights, pip-installable, zero-shot cloning) — pending empirical T3 + T1 research confirmation.
