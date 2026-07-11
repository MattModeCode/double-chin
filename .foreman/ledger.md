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
| T11 | Completeness critic vs definition of done | foreman-verifier | DONE — PASS_WITH_NOTES; both notes (test count 28→30, doctor warning) fixed | 1 |
| T12 | Commit + push per auto-ship rule | LEAD | DONE — 6 commits pushed to build/myna; PR #1 opened to main | 1 |
| T14 | Slow e2e proof (real model asserts similarity>0.75) | LEAD-run | DONE — `MYNA_E2E=1 pytest -m slow`: 1 passed, 17.1s | 1 |
| T8 | Demo + walkthrough videos | WORKHORSE (sonnet) | DONE — demo 65.4s, walkthrough 90.9s, both h264+aac, audio -17.8/-19.8 dB; narration verified 0.948 | 1 |
| T7 | Brand + README + recap.html | LEAD | DONE — recap.html validated (clean markup, valid fonts, 18/18 links resolve, 2 audio + 2 video embeds) | 1 |

## Second mission — the application (application-prompt.md, 2026-07-11)
| ID | Task | Seat | Status | Attempts |
|----|------|------|--------|----------|
| A1 | Architecture tournament: 3 pitches (FastAPI+SPA, Gradio, pywebview) + independent judge | 3× WORKHORSE pitches + WORKHORSE judge | DONE — FastAPI+SPA 845/1000; D12 | 1 |
| A2 | Engine progress callback (tests first) | LEAD | DONE — 2 tests, suite 32 | 1 |
| A3 | Studio backend: app.py, jobs.py, history.py + CLI `studio` + pyproject deps | LEAD | DONE — SSE replay-from-cursor design, 409 guard, loopback-only | 1 |
| A4 | Studio frontend: branded SPA (index/style/app), fonts bundled | LEAD (mashuai-brand loaded) | DONE — no external requests | 1 |
| A5 | Offline app test suite | LEAD | DONE — 12 studio tests, suite 44 passing | 1 |
| A6 | Live E2E through the UI (Playwright; Chrome absent → D15) | LEAD-run | DONE — 0.921 vs holdout via browser; owner's voice 0.885 (local only) | 2 |
| A7 | Studio demo video (session recording + take audio) | LEAD-run | DONE — 69 s, watched frame-by-frame; privacy re-record D16 | 2 |
| A8 | Docs: README app section, design §10, build-log D12–D17, recap rework | LEAD | DONE | 1 |
| A9 | Unexpected deliverable: voice passport (generator + standin card) | LEAD | DONE — rendered verified | 1 |
| A10 | Red team round 2 (app claims) | WORKHORSE (adversarial) | DISPATCHED | 1 |
| A11 | Completeness critic vs DoD | WORKHORSE | DISPATCHED | 1 |
| A12 | Wheel packaging check (static assets ship) | LEAD-run | DONE — static/, fonts in wheel | 1 |
| A13 | Ship: commit, push, PR update | LEAD | PENDING | 0 |

## Attempts log (append-only)
- T1 attempt 1: dispatched general-purpose bg agent (model landscape) — pre-foreman, reconciled here.
- T2 attempt 1: dispatched general-purpose bg agent (data/verification) — pre-foreman, reconciled here.
- T3 attempt 1: bg bash job bd90n7u3t running smoke_chatterbox.py (model download + 1-line synth).

## Decisions (never-ask log lives in docs/build-log.md once created)
- D1: Codex excluded (see Mode above).
- D2: Front-runner model = Chatterbox TTS (MIT code+weights, pip-installable, zero-shot cloning) — pending empirical T3 + T1 research confirmation.
