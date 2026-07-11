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
**A:** Build the entire pipeline first using a stand-in reference voice from free corpora (CMU Arctic speaker `bdl`, free X11-style license; VOiCES/torchaudio tutorial clip, CC-BY 4.0). Ship a recording-script kit so the user can swap in their own voice with one command.
**Why:** Stopping first would idle the whole build on a human round-trip. Zero-shot cloning is voice-agnostic: proving the pipeline on a stand-in voice proves it for the user's voice, because the engine never trains — it conditions on whatever reference WAV is supplied. The recording kit makes the swap trivial.

### D5 — ffmpeg
**Q:** `/usr/local/bin/ffmpeg` is an x86_64 binary and fails with "bad CPU type" on this arm64 Mac. Videos are a required deliverable.
**A:** Install the arm64 ffmpeg via Homebrew (free, already the machine's package manager).
**Why:** Needed for audio concatenation and for rendering the demo/walkthrough videos. Free software, no spending.

### D6 — Product name
**Q:** What is this software called?
**A:** **Myna** — CLI `myna`, package `myna`. Tagline: "Your voice, on script."
**Why:** The myna is the bird that learns to speak in a human's voice — exact metaphor for the product, one breath to say, four letters to type, no obvious collision in the local/personal-tool space. Runner-ups considered: Doppel (generic, taken by several apps), Lyrebird (taken by Descript's ancestor), EchoTwin (clunky). Local-only software, so trademark exposure is nil (guardrail 2: publish nothing).

### D8 — Verification stack
**Q:** SpeechBrain ECAPA-TDNN or resemblyzer for the "does the clone match" score?
**A:** resemblyzer (GE2E), with an RMS silence gate. Verdict bands: ≥0.80 strong match, ≥0.75 match, ≥0.60 borderline, <0.60 no match.
**Why:** The research scout *tested it on this exact machine*: installs on Python 3.12/arm64 (with `setuptools<81`), 17 MB model, ~0.04 s per clip on CPU. ECAPA is more discriminative (0.8% EER) but drags a heavier dependency tree; for a relative "sounds like the reference" score, light and tested beats heavy and theoretical. Same-vendor bonus: resemblyzer is also by Resemble AI. Caveat handled: it scores noise-vs-noise at 0.99, so a silence/energy gate runs before any score. Supersedes the initial SpeechBrain spec in the T5 ticket (worker redirected mid-flight).

### D9 — Smoke-test results locked the engine choice
**Q:** Does Chatterbox actually clone on this Mac?
**A:** Yes. Model loads on MPS in 7–9 s; a novel sentence cloned against the 16.7 s CMU Arctic stand-in reference scored **0.902** cosine similarity (resemblyzer GE2E) — above the 0.80 "strong match" bar. RTF ≈ 4.8 on first calls.
**Why it took three attempts:** (1) uv venvs ship no setuptools → perth watermarker degraded to `None` → `TypeError` at load; (2) setuptools 83 still lacks `pkg_resources`; fix is `setuptools<81`, now a hard pin. Logged as reproducible landmines in design.md §2.

### D7 — Hook friction
**Q:** A GateGuard fact-forcing hook intercepts first writes/commands and demands stated facts. Disable it?
**A:** No — comply inline by stating the facts before gated operations.
**Why:** Silently editing the user's hook configuration to smooth my own path is exactly the kind of side effect the hook exists to catch. Compliance costs a sentence per gate.
