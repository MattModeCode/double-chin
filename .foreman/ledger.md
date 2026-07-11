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
| T7 | Brand identity, README, recap.html (mashuai-brand constraints) | LEAD (judgment/user-facing) | IN PROGRESS — README + logo mark done; recap.html pending final numbers | 1 |
| T8 | Demo video + walkthrough video (ffmpeg pipeline, cloned-voice narration) | WORKHORSE (sonnet) | DISPATCHED (bg; write set demo/video/**, demo/*.mp4, assets/brand/fonts/**) | 1 |
| T9 | Red team: adversarial review of claims + product | Opus agent (read-only) | DONE — 9 findings (1 CRITICAL .m4a); published docs/red-team.md; code fixes dispatched to batch fix worker (sonnet, write set src/{voices,engine,cli}.py + tests); docs reworded by LEAD | 1 |
| T13 | Mirror-test quiz (unexpected deliverable): 3 real vs 3 clone held-out clips + demo/mirror-test.html | LEAD + bg myna runs | DONE — clone-vs-real similarity 0.843–0.912 (strong match on held-out sentences) | 1 |
| T10 | Blind verification: core package on committed state | foreman-verifier | DONE — PASS_WITH_NOTES (2 LOW code findings held for batch fix; e2e say verified by LEAD: 39.4 s, similarity 0.954) | 1 |
| T11 | Completeness critic vs definition of done | verifier-style agent | PENDING | 0 |
| T12 | Commit + push per auto-ship rule | LEAD | PENDING | 0 |

## Attempts log (append-only)
- T1 attempt 1: dispatched general-purpose bg agent (model landscape) — pre-foreman, reconciled here.
- T2 attempt 1: dispatched general-purpose bg agent (data/verification) — pre-foreman, reconciled here.
- T3 attempt 1: bg bash job bd90n7u3t running smoke_chatterbox.py (model download + 1-line synth).

## Decisions (never-ask log lives in docs/build-log.md once created)
- D1: Codex excluded (see Mode above).
- D2: Front-runner model = Chatterbox TTS (MIT code+weights, pip-installable, zero-shot cloning) — pending empirical T3 + T1 research confirmation.
