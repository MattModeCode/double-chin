# Red-team report

My mandate was purely adversarial: to refute, weaken, or bound every load-bearing claim Double Chin makes, so that anything left standing is trustworthy. Conducted 2026-07-11 against branch `build/double-chin` by reading all source, docs, the installed `chatterbox`/`resemblyzer`/`resemble-perth` packages in `.venv`, and by running the offline unit suite (28 passed). I did not run `double-chin say`/`enroll` or load the TTS model. Findings are ranked by severity, then mapped back to the seven claims of record.

> **Foreman postscript (added after remediation):** F1, F2, F5 (code), F6, and F7 (code) were fixed in the same session; the remaining findings were addressed by rewording the claims in README/design.md as recommended. The original findings are preserved below unedited, because the definition of done requires the objections to stay visible. Remediation status per finding is marked with ▸.

## Verdict summary

| # | Claim of record | Verdict |
|---|---|---|
| 1 | Clone works; 0.902 / 0.954 vs 0.75 threshold | **HOLDS WITH BOUNDS** |
| 2 | Speaker-agnostic → stand-in proves the user's voice | **HOLDS WITH BOUNDS** |
| 3 | Everything local / nothing leaves the machine | **OVERSTATED** |
| 4 | Licence-safe for personal use | **HOLDS** (minor omissions) |
| 5 | Verification design (RMS gate, similarity) | **BROKEN** (as a quality gate) |
| 6 | Product honesty / no test theatre | **OVERSTATED** |
| 7 | Misuse mitigation / Perth watermark | **HOLDS** (watermark real; story weak) |

## Findings, ranked

### F1 — CRITICAL. The documented "clone your own voice" path is broken: `.m4a` is rejected. (Claims 2, 6)

The recording kit tells users to record with macOS Voice Memos or QuickTime, both of which emit `.m4a`, and states "File format doesn't matter — .m4a, .wav, .mp3, and .flac all work." The code supported no such thing: `_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3"}`. A user following the kit hits `ValueError: no wav/flac/mp3 files found in directory`. The stand-in demo only works because it ships pre-converted `.wav`, so this defect is invisible in every documented demo but fires on the first real user.

▸ **Fixed:** `.m4a` added with a torchaudio-first, ffmpeg-fallback decode path, verified against a real AAC file.

### F2 — HIGH. `--verify` is close to tautological and does not implement the held-out check the kit promises. (Claims 1, 5)

`double-chin say --verify` scored the output against the exact clip Chatterbox conditioned on — asking "does the output resemble the audio I told the model to imitate," which the generator was directly optimized to satisfy. That is why it lands at 0.9+. Meanwhile the recording kit sold the opposite: "hold out the rest for verification." No holdout existed in code.

▸ **Fixed:** `enroll` now reserves the last source file as `holdout.wav` (when enough audio remains), and `--verify` scores against the holdout when present, printing which clip was used.

### F3 — HIGH. The judge is not independent, and the operating margin is thin. (Claim 1)

README and design called resemblyzer an "independent speaker-verification model." Package metadata says otherwise: Resemblyzer's author is Resemble AI's Corentin Jemine — the same vendor as Chatterbox, and both are speaker-embedding models. The judge scores exactly the axis the generator conditions on. "Independent" is overstated; the correct wording is "separate weights, same family."

Fresh negative controls make the margin concrete: clone-vs-*different* real speaker **0.713**, two real different speakers **0.672**, same-speaker clone **0.954**. The different-speaker floor for similar-register male English narrators is ~0.67–0.71 — not the 0.3–0.6 implied by community lore. The 0.75 "match" line sits ~0.04 above where a wrong speaker already lands, and `<0.60` "no match" is essentially unreachable.

▸ **Addressed in docs:** "independent" dropped; negative controls now shown next to the headline numbers; band caveat added. The bands themselves were kept (they sit on the correct side of both controls) with the floor disclosed.

### F4 — HIGH. No intelligibility or content check exists; the RMS gate only stops silence. (Claim 5)

The RMS gate catches digital silence and nothing else. A constant hum, gibberish, mangled prosody, or the *wrong words* in the right timbre all pass the gate and score high, because resemblyzer measures speaker identity, not content — there is no transcription/ASR step anywhere. A degenerate output can be stamped "0.9 — strong match" while being unusable.

▸ **Addressed in docs:** disclosed plainly — `--verify` scores *who* it sounds like, not *what* was said. An ASR cross-check is documented as the known upgrade path, not implemented.

### F5 — MEDIUM. "Nothing leaves the machine" is overstated. (Claim 3)

The engine downloads ~6 GB of weights from Hugging Face on first run, and the hub is contacted on every cold load unless `HF_HUB_OFFLINE=1`. To the project's credit: **no telemetry, analytics, or phone-home exists in `src/`** — audio genuinely stays local. Also, design.md claimed the engine sets `HF_HUB_DISABLE_XET=1`; it did not.

▸ **Fixed (code):** the engine now sets `HF_HUB_DISABLE_XET=1` before loading. ▸ **Addressed in docs:** locality claim scoped to "your audio and voices never leave the machine; model weights download once from Hugging Face."

### F6 — MEDIUM. The e2e test did not regenerate or assert the headline numbers. (Claim 6)

`tests/test_e2e.py` asserted only that a non-empty WAV was written — coverage theatre relative to the claim "the e2e test regenerates these numbers."

▸ **Fixed:** the slow e2e test now runs with `--verify` and asserts similarity > 0.75.

### F7 — MEDIUM. The headline score was inconsistent across artifacts, and RTF was mislabeled. (Claim 6)

0.902 (single sentence) vs 0.954 (39 s script) were never reconciled side by side; and the CLI printed `realtime factor 0.21x` while the design doc said "RTF 4.8" — the same quantity, inverted.

▸ **Fixed:** both numbers now appear together with their conditions; the CLI reports an unambiguous "speed 0.21x realtime (33.5 s wall for 7.0 s audio)" convention, matched by the docs.

### F8 — LOW. Misuse mitigation: watermark is real but the story is thin; the bar is 5 s, not 17 s. (Claim 7)

The watermark claim checks out: `perth.PerthImplicitWatermarker` is applied unconditionally to every generation. But Perth is an imperceptible provenance signal, defeatable by re-encoding, and Double Chin exposes no detector — it deters no determined misuser. And the actual enrolment floor is `MIN_REFERENCE_SECONDS = 5.0`: the tool clones from 5 seconds, an even lower misuse bar than the 17 s implied elsewhere.

▸ **Addressed in docs:** responsible-use section now states the 5 s floor and the watermark's limits honestly.

### F9 — LOW. Licence table essentially correct, with two omissions. (Claim 4)

Chatterbox weights verified MIT on the live HF model card; resemblyzer Apache-2.0 confirmed. Omissions: `resemble-perth` (MIT, baked into every output) was missing from the inventory, and the CMU Arctic licence was named three different ways across docs.

▸ **Addressed in docs:** perth row added; licence naming unified.

## Round 2 — the application layer (Double Chin), 2026-07-11

A second adversarial pass ran after the FastAPI application was built, with the same mandate against `src/double_chin/studio/`, the CLI `studio` command, and the §10 claims. It ran the offline suite, built a real wheel, and read every source file; it did not start a server or load the model. Findings and remediation (▸):

### C1 — CRITICAL (process, not code). At review time the whole application was uncommitted; `pip install -e .` at HEAD gave the old CLI.
▸ **Resolved by shipping:** this changeset commits `src/double_chin/studio/`, tests, the `studio` subcommand, the three new dependencies, and every doc together. Verified positive by the reviewer: `uv build` produces a wheel containing `double_chin/studio/**` including the self-hosted fonts, so packaging works once committed.

### C2 — CRITICAL. "Loopback only ⇒ no auth bypass matters" was false. A local server with no auth is reachable by *any* web page in the same browser: cross-origin CSRF (a `no-cors` POST is always sent) could enroll or silently overwrite a voice or start a job; DNS rebinding could then read history and audio.
▸ **Fixed in code:** `app.py` now runs a `local_origin_guard` middleware that rejects any request whose `Host` header isn't loopback (defeats DNS rebinding) and any request carrying a cross-origin `Origin` (defeats browser CSRF) — the Jupyter/Ollama pattern. Verified live: same-origin browser → 200; `Origin: http://evil.example` POST → 403; `Host: attacker.example` → 403 (`tests/test_studio.py::test_cross_origin_and_bad_host_refused`). The doc claim is reworded from "no auth bypass matters" to describe the actual guard.

### H1 — HIGH. Enrolling a name that already exists silently overwrote the prior voice's reference.
▸ **Fixed in code:** the enroll endpoint returns **409** on a name collision unless `overwrite=true` is sent explicitly (`test_enroll_collision_then_overwrite`). (The CLI's own `enroll` still overwrites, as a local user typing a name owns that name; the network endpoint is the untrusted surface.)

### H2 — HIGH. §10 said its bullets were "verifiable in tests/test_studio.py"; several weren't (SSE replay-from-cursor, the 20k-char cap, history corrupt-line resilience).
▸ **Fixed:** those tests now exist (`test_sse_replay_from_cursor`, `test_job_text_over_limit_422`, `test_history_skips_corrupt_lines`), suite up from 44 to 51.

### M1 — MEDIUM. The in-memory job dict grew unbounded over a long session.
▸ **Fixed in code:** finished jobs are pruned to the most recent 50 (`_MAX_RETAINED_JOBS`, `test_jobs_pruned_to_cap`); the durable record is `history.jsonl` on disk, so nothing is lost.

### M2 — MEDIUM. The enroll upload had no file-count or size cap (disk-fill DoS, amplified by C2).
▸ **Fixed in code:** max 24 files and 200 MB total, streamed to disk in 1 MB chunks (`test_enroll_too_many_files`; 413 on byte overflow).

### M3 / L1 / L2 — the 0.921 figure is a single measurement (honestly caveated as not bit-exact); engine stderr prints during a run (cosmetic); `job_id.isalnum()` accepts more than hex but still blocks traversal. Accepted as-is with the caveats stated in §10.

**What round 2 confirmed holds (verified, not assumed):** no external requests from the UI (only a `data:` favicon); no XSS (every user/job string rendered via `textContent`/`createTextNode`); no path traversal on `/api/audio` or in upload filename handling; the 409 guard and the SSE `Condition` design are race-free by inspection (status and terminal event written under one lock); the demo screenshots contain no personal content (D16 re-record verified); `.gitignore` correctly excludes the owner's recordings and scripts.

## Bounding claim 2 (speaker-agnostic)

The mechanism argument is sound: no per-speaker training exists, so the code path is identical for any reference. But "proven on a stand-in proves it for you" is bounded by: (1) the stand-in is a studio-clean, same-register, native-English male narrator — the *easy* case; accents, non-native speakers, atypical voices, and cross-register requests are untested and the zero-shot literature shows they degrade; (2) quality-in/quality-out means the result is dominated by reference capture, and F1 showed the capture path itself was broken for the recommended tools; (3) the design doc's "honest limits" paragraph is the strongest honesty in the repo and should stay. Net: speaker-agnostic in code, "proven for one favourable speaker, plausibly generalizes, untested at the distribution edges."

## What survived

- Chatterbox weights are MIT (verified live). Licence posture for personal local use is sound.
- The Perth watermark is real and unconditional on every output.
- No telemetry or phone-home in `src/`; user audio and enrolled voices stay on disk under `DOUBLECHIN_HOME`.
- The negative controls *do* separate (0.95 vs 0.71/0.67) — the clone is not noise, and the 0.75 threshold is on the correct side of the controls, just with a thinner margin than the prose implied.
- `chunk.py`, lazy-import discipline, and the offline unit suite are clean and do what they say.

The core result — "Chatterbox produces a recognizably same-speaker clone, and Double Chin measures it" — is real. What was oversold, and has now been either fixed or reworded: the *independence* of the measurement, the *coverage* of the tests, the *locality* absolutism, and, most seriously, the *usability of the documented user path*.
