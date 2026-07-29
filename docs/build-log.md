# Build log

Running log of every decision made during the autonomous build, per the master prompt's never-ask rule: each entry records the question I would have asked, the answer I chose, and why.

Format: **Q** (the question) / **A** (the call) / **Why** (the reasoning and evidence).

---

## 2026-07-11 — Session start

### D1 — Orchestration seats
**Q:** Should Codex CLI workers be used alongside Claude workers?
**A:** No. Claude seats only (Fable 5 lead, Sonnet workhorse, Haiku fast).
**Why:** Codex dispatch spends a separate account's money and the foreman contract requires explicit billing consent before first dispatch. Guardrail 1 (no new spending) plus guardrail 3 (never ask) make that consent impossible to obtain. Claude workers run inside this session's existing plan.

### D2 — Python runtime
**Q:** Which Python? System default is 3.14.6.
**A:** Dedicated `.venv` pinned to CPython 3.12.13 via `uv`.
**Why:** ML wheels (torch, torchaudio, TTS packages) lag the newest CPython; 3.12 is the widest-support stable target. `uv` was already installed, downloads a managed interpreter, and is fast.

### D3 — Voice-cloning engine (front-runner)
**Q:** Which local zero-shot voice-cloning model?
**A:** Chatterbox TTS (Resemble AI) as front-runner, pending (a) the parallel research scout's landscape report and (b) an empirical smoke test on this machine.
**Why:** MIT-licensed code *and* weights (safe for personal local use), single `pip install chatterbox-tts` that resolved cleanly on Python 3.12/arm64, zero-shot cloning from seconds of reference audio, documented MPS (Apple GPU) support. Empirical installability on *this* Mac beats paper benchmarks. Fallback candidates researched in parallel: F5-TTS, XTTS-v2, OpenAudio S1-mini.

### D4 — Demo voice without the user's audio
**Q:** The mission says the only permitted stop is to request the user's training recordings. Stop now, or build first?
**A:** Build the entire pipeline first using a stand-in reference voice from free corpora (CMU Arctic speaker `bdl`, CMU's BSD-style free licence; VOiCES/torchaudio tutorial clip, CC-BY 4.0). Ship a recording-script kit so the user can swap in their own voice with one command.
**Why:** Stopping first would idle the whole build on a human round-trip. Zero-shot cloning is voice-agnostic: proving the pipeline on a stand-in voice proves it for the user's voice, because the engine never trains — it conditions on whatever reference WAV is supplied. The recording kit makes the swap trivial.

### D5 — ffmpeg
**Q:** `/usr/local/bin/ffmpeg` is an x86_64 binary and fails with "bad CPU type" on this arm64 Mac. Videos are a required deliverable.
**A:** Install the arm64 ffmpeg via Homebrew (free, already the machine's package manager).
**Why:** Needed for audio concatenation and for rendering the demo/walkthrough videos. Free software, no spending.

### D6 — Product name
**Q:** What is this software called?
**A:** **Double Chin** — CLI `double-chin`, package `double-chin`. Tagline: "Your voice, on script."
**Why:** The double-chin is the bird that learns to speak in a human's voice — exact metaphor for the product, one breath to say, four letters to type, no obvious collision in the local/personal-tool space. Runner-ups considered: Doppel (generic, taken by several apps), Lyrebird (taken by Descript's ancestor), EchoTwin (clunky). Local-only software, so trademark exposure is nil (guardrail 2: publish nothing).

### D8 — Verification stack
**Q:** SpeechBrain ECAPA-TDNN or resemblyzer for the "does the clone match" score?
**A:** resemblyzer (GE2E), with an RMS silence gate. Verdict bands: ≥0.80 strong match, ≥0.75 match, ≥0.60 borderline, <0.60 no match.
**Why:** The research scout *tested it on this exact machine*: installs on Python 3.12/arm64 (with `setuptools<81`), 17 MB model, ~0.04 s per clip on CPU. ECAPA is more discriminative (0.8% EER) but drags a heavier dependency tree; for a relative "sounds like the reference" score, light and tested beats heavy and theoretical. Same-vendor bonus: resemblyzer is also by Resemble AI. Caveat handled: it scores noise-vs-noise at 0.99, so a silence/energy gate runs before any score. Supersedes the initial SpeechBrain spec in the T5 ticket (worker redirected mid-flight).

### D9 — Smoke-test results locked the engine choice
**Q:** Does Chatterbox actually clone on this Mac?
**A:** Yes. Model loads on MPS in 7–9 s; a novel sentence cloned against the 16.7 s CMU Arctic stand-in reference scored **0.902** cosine similarity (resemblyzer GE2E) — above the 0.80 "strong match" bar. RTF ≈ 4.8 on first calls.
**Why it took three attempts:** (1) uv venvs ship no setuptools → perth watermarker degraded to `None` → `TypeError` at load; (2) setuptools 83 still lacks `pkg_resources`; fix is `setuptools<81`, now a hard pin. Logged as reproducible landmines in design.md §2.

### D10 — Negative control for the similarity claim
**Q:** Is 0.95 clone-vs-reference similarity meaningful without a different-speaker baseline?
**A:** Measured it. Clone vs a *different* real speaker (VOiCES sp0307): 0.713. Two real different speakers against each other: 0.672. Same-speaker clone vs its reference: 0.954.
**Why:** Pre-empts the obvious red-team objection. The 0.75 match threshold correctly separates both different-speaker controls from the clone; the honest caveat is that similar-register male English narrators sit ~0.7, not 0.3–0.6, so scores must be read against that floor. Numbers recorded before the red team reported, and handed to it.

### D11 — Red-team remediation scope
**Q:** The red team found one CRITICAL (.m4a rejected), three HIGH, three MEDIUM, two LOW. Fix everything or reword?
**A:** Fix in code: F1 (.m4a with ffmpeg fallback), F2 (real holdout verification at enrolment), F5 (set `HF_HUB_DISABLE_XET=1` in the engine), F6 (e2e asserts similarity > 0.75), F7 (one speed convention). Reword in docs with full disclosure: F3 (judge is same-family, negative controls beside headline numbers), F4 (verify measures who, not what), F5 (locality scoped to audio), F8 (5 s floor, watermark limits), F9 (licence rows). Not built: ASR intelligibility gate (documented as the upgrade path).
**Why:** Everything that changes what a user experiences got a code fix; everything that was a truth-in-advertising problem got the honest sentence the red team asked for. An ASR pass would add a Whisper-class dependency for a check the user's own ears do better at this scale — documented instead of built (ship the strong 80%).

## 2026-07-11 — Second mission: the application (`application-prompt.md`)

### D12 — Application shape (tournament)
**Q:** The CLI exists; the new mission demands one launchable application with a real interface. What shape?
**A:** **Double Chin** — a FastAPI backend + hand-built single-page frontend (vanilla HTML/CSS/JS, no build step), launched with `double-chin studio`, which starts a loopback-only server and opens the browser. Live chunk progress over SSE; one synthesis job at a time (HTTP 409 otherwise); history appended to a jsonl under `DOUBLECHIN_HOME`.
**Why:** Three independent architect agents pitched competing shapes (FastAPI+SPA, Gradio 6, pywebview desktop shell); an independent judge scored them on product feel, launch robustness, progress UX, offline testability, autonomous-build risk, and brandability. FastAPI+SPA won 845/1000 vs 705 (pywebview) and 580 (Gradio). Deciding facts: the demo video must be recorded by driving the real interface in Chrome — impossible against a WKWebView native window — and Gradio's component chrome can't carry a bespoke brand. Salvaged from the losers: jsonl history (Gradio pitch) and the explicit 127.0.0.1-only bind as a stated security property (pywebview pitch). Conditions honoured from the judge: sentinel-terminated SSE stream and the 409 concurrent-job guard.

### D13 — Engine progress surface
**Q:** The app needs live per-chunk progress, but the engine only printed progress to stderr. Scrape stderr or change the engine?
**A:** Added an optional `progress(index, total, text)` callback parameter to `DoubleChinEngine.synthesize` — backward compatible, covered by two new offline tests against a fake model (suite now 32 passing).
**Why:** A real callback is testable and race-free; stderr scraping (what the Gradio pitch had to invent) is fragile and couples the UI to log formatting. The stderr print stays for CLI users.

### D14 — The owner's private content stays out of the repo
**Q:** The owner dropped personal scripts (`voice clone scripts/`: a school piece and a message to a partner) and their real voice recordings into the working tree. Commit them?
**A:** No — `voice clone scripts/` joined `*.m4a` in `.gitignore`. Everything the owner feeds the app stays local; committed demo artifacts use only the licence-free stand-in voice.
**Why:** Guardrail 2 (publish nothing). The GitHub remote outlives this session's privacy expectations; the repo is private today, but a repo's visibility is one click from changing, and personal messages and biometric-adjacent audio don't belong in git history at all.

### D15 — Demo recording toolchain
**Q:** The demo must show the real interface being driven, but this machine has no Google Chrome (Arc and Safari only) and the Chrome-extension automation path refused to connect. Stall, or reroute?
**A:** Playwright (free pip install) driving its own Chromium, which also records the session as video natively — the webm becomes the demo mp4's core footage.
**Why:** Guardrail 3: blocked is not an option. Playwright turned out stronger than the original plan — deterministic scripted driving, pixel-exact viewport, built-in video — and it doubles as the live E2E harness. Irony noted: the tournament judged the pywebview pitch partly on Chrome-extension recordability, but the deciding criterion — "a localhost page any Chromium can drive" — held; only the specific tool changed.

### D16 — Privacy re-record of the demo video
**Q:** Frame-by-frame review of the first demo cut caught the owner's personal message run ("Hi my love…", voice `me`) visible in the app's History panel. Ship it, blur it, or re-record?
**A:** Re-record the whole session against an isolated `DOUBLECHIN_HOME` containing only the licence-free stand-in voice, so no personal content can appear in any committed pixel.
**Why:** Guardrail 2. Blurring is fragile and admits the leak into git history; a clean-room re-record is cheap (the take is seeded, so the audio is byte-identical: same 1,211,600-byte wav, same 0.921 score) and structurally safe. This is also why watching your own videos is a real step, not a checkbox.

### D17 — Whose audio plays in the demo
**Q:** The demo video needs sound. Narrate it, or let the product speak?
**A:** The audio the video ends on is the exact take generated during the recorded session (seed 7, stand-in voice) — the product demonstrating itself. The owner's cloned voice is never committed; their UI run (0.885 vs holdout on their own script) is reported as a number only.
**Why:** A demo that plays its own output is the strongest honest evidence the interface produces audio; using the owner's voice would trade a guardrail for flair.

### D18 — What "my voice rules" means
**Q:** The definition of done requires "the demo script passes my voice rules," but no voice-rules document exists in the repo. Whose rules?
**A:** The owner's brand voice system (the MashuAI contract that governs everything user-facing here): plain and confident, sentence case, say what the thing does, no hype, no exclamation marks, no emoji. The Studio demo script and every on-screen string were written and checked against those rules.
**Why:** It is the only voice standard the owner maintains, it is loaded into every session that builds user-facing work, and the completeness critic flagged the criterion as unfalsifiable without naming a standard — so the standard is now named.

### D7 — Hook friction
**Q:** A GateGuard fact-forcing hook intercepts first writes/commands and demands stated facts. Disable it?
**A:** No — comply inline by stating the facts before gated operations.
**Why:** Silently editing the user's hook configuration to smooth my own path is exactly the kind of side effect the hook exists to catch. Compliance costs a sentence per gate.
