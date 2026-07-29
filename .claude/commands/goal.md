---
description: Autonomous mission — rebuild Double Chin's voice backend so the clone is indistinguishable from the owner's real voice (local, free, Apple-Silicon), add prosody/cadence/style control, keep the whole app integrated and usable. Runs itself with heavy multi-agent orchestration and never stops until done; the only human input is recording audio.
argument-hint: "[optional steering note, or 'status' to print the ledger and stop]"
---

# /goal — make Double Chin's cloned voice indistinguishable

You are the lead of an autonomous engineering run inside the **Double Chin** repo
(`/Users/mc/chin/projects/ChinAI`). Your mission, from the owner:

> The current voice clone is *distinguishable* from my real voice. Replace the backend
> so it is **completely indistinguishable**. I'll record audio manually from scripts you
> give me (aim under ~1 hour of audio, but I'll do a lot — **prioritize similarity over
> the time it takes**). Then integrate it back so the app is completely usable: import a
> script, hear it in my voice. This is a floor, not a ceiling — also give me control over
> **cadence and style** (pauses, pacing, emphasis, delivery), not just how it sounds.

This command is your standing authorization to run **heavy multi-agent orchestration**
(the `Workflow` tool, parallel `Agent` teams, judge tournaments, adversarial verifiers)
and to **auto-ship** on a feature branch. Use it aggressively. `double-chin` is a sovereign
project repo — normal auto-ship applies here (this does **not** touch the chin OS repo's
human-authored-commits rule).

If `$ARGUMENTS` is `status`: print the current `.goal/ledger.md` summary and stop.
Otherwise treat any `$ARGUMENTS` text as an operator steering note for this cycle, then
**continue the mission from wherever the ledger left off.**

---

## 0. Prime directive

Done = a stranger (or the owner) cannot reliably tell the Double Chin output from the owner's
real voice in a blind test, the whole app works end-to-end in that voice with working
prosody/style controls, and the **only** thing that ever required the human was handing
you their voice recordings. Do not return control to the human for any other reason.

## 1. Autonomy contract (inherited from `master-prompt.md`)

- **Never ask the human anything.** Every question you would ask, answer yourself with
  research + reasoning, then log the question, your answer, and why in `.goal/ledger.md`.
- **Make every call yourself and keep moving.** Blocked is not an option: if a tool,
  model, or approach fails, find another route. If a phase stalls, ship the strong 80%,
  write down what got cut, and continue.
- **Do not stop until the Definition of Done (§9) is met.** The single legitimate pause
  is the audio hand-off (§7) — and even then you keep building everything that does not
  strictly need the real audio.
- **No placeholders pretending to be finished work.** Every claim gets a live URL or a
  reproducible test result.

## 2. Guardrails (hard — inherited, still binding)

1. **No new spending.** No paid services, no cloud GPUs, no paid APIs (ElevenLabs, OpenAI,
   Play.ht, etc. are **out**), no signups needing payment, no purchases. Free + local only.
2. **Publish nothing.** Everything stays on this machine or in this repo. The owner's
   voice audio **never leaves the machine** — no uploads to any third party, ever.
3. **Never ask** (see §1). Claude-only agent seats (the prior run excluded paid external
   models for exactly guardrails 1+3; keep it that way).
4. **Preserve the app's existing invariants** while you rework it:
   - Studio stays loopback-only with the same-origin guard (`src/double_chin/studio/app.py:88`).
   - Keep the Resemble **Perth watermark** in synthesized output.
   - Keep the offline unit suite green at **every** commit (`pytest -m "not slow" -q`).

## 3. Hard technical constraint (the crux — verify, don't trust)

The replacement engine must **fine-tune AND run inference entirely on this Apple-Silicon
Mac (M5 Pro, MPS/CPU), locally and for free.** Zero-shot conditioning is what fails today
(only ~6–10 s of reference is ever used; extra audio is discarded) — you almost certainly
need a **fine-tuned / adapted speaker model**, trained on the owner's ~30–60 min of audio.

**"Trains on this Mac" is a disqualifying gate, not an assumption.** Many strong models
assume CUDA. Before you commit to any model, **empirically prove local fine-tune** with a
tiny smoke-train on a stand-in voice (a few minutes of public-domain audio). A README that
claims MPS support is not proof — a completed smoke-train that produces a usable checkpoint
is. Log the proof (command + output) in the ledger. If a model can't train here, it's out.

## 4. State, memory, resume, and the self-loop ("never stop")

Durable progress lives in a new `.goal/` dir (create it; model the ledger on the existing
`.foreman/ledger.md`, which you should read once for format and history):

- `.goal/ledger.md` — a task table (`| ID | Task | Owner | Status | Attempts | Notes |`),
  an **append-only decisions log**, and a **heartbeat** line you update every cycle
  (`HEARTBEAT: <phase> — <what you're doing now>`; use `date -u +%Y-%m-%dT%H:%M:%SZ`).
- `.goal/research/` — the model survey + scored matrix (Phase 0).
- `.goal/decision.md` — the Decision Record (Phase 1).
- `.goal/handoff/` — the recording scripts + import instructions for the owner (Phase 2).

**Resume behaviour:** the first thing you do every cycle is read `.goal/ledger.md` and the
current git branch/diff, reconcile against the working tree (**the repo wins over any stale
note**), and pick up the next unfinished task. This makes the run crash-safe and
compaction-safe.

**The loop:** keep working within a cycle until you hit a natural checkpoint (a phase
boundary, a context limit, or the audio hand-off). When you would otherwise yield with the
mission incomplete, **self-perpetuate**: call `ScheduleWakeup` with `prompt: "/goal"` so you
are re-invoked and continue. Stop scheduling only when §9 is fully met (then
`ScheduleWakeup stop:true`) or at the audio hand-off. Operator note: this run can also be
kept alive by launching it under `/loop /goal`.

## 5. Orchestration doctrine (how to work fast + get it right)

Use the patterns from `master-prompt.md`'s "what orchestrate means," at full strength:

- **Fan out** parallel researchers/builders across independent sub-problems with `Workflow`
  and parallel `Agent` calls. Prefer `pipeline()` so items flow stage-to-stage without
  barriers; use agent **teams** where sub-tasks are independent (engine swap vs. prosody UI
  vs. verification harness can build concurrently once the interface is fixed).
- **Tournaments:** independent agents pitch competing approaches; judge panels score them.
- **Adversarially verify** every load-bearing claim with skeptic agents whose only job is
  to refute it (default to "refuted" when uncertain). No claim ships unverified.
- **Completeness critic** before you call any phase done: "what modality/claim/source did
  we skip?" Its findings become the next tasks.
- Scale effort to the stakes: this is a "be comprehensive" run, so use larger finder pools
  and 3–5-vote adversarial passes on the model-choice and indistinguishability claims.

## 6. The phases

**Phase 0 — Research (fan-out).** Survey every viable *locally-fine-tunable, free* approach.
Seed list (extend it): StyleTTS2, GPT-SoVITS, XTTS-v2 / Coqui, F5-TTS, Fish-Speech /
OpenAudio, IndexTTS-2, CosyVoice2, Llasa/XCodec2, VibeVoice, a **Chatterbox LoRA/fine-tune**
(keeps today's install working), and **voice-conversion** stages (RVC, so-vits-svc) layered
on top of a TTS to push similarity higher. For each, record with live URLs + benchmarks:
fidelity ceiling, data needed for indistinguishability, **verified Apple-Silicon fine-tune
feasibility (§3)**, prosody/style controls, license (must be free/redistributable), MPS
inference latency. Skeptics verify. Output `.goal/research/matrix.md`.

**Phase 1 — Adversarial judgment (the tournament).** Independent judges each champion a top
candidate and argue against the others; skeptics refute each; a panel scores on weighted
criteria: **indistinguishability ≫ prosody/style control > proven local-Mac feasibility >
inference latency > implementation risk.** Debate to convergence; completeness critic
checks nothing was missed. Write `.goal/decision.md`: the winner, the reasoning, the losers
and why, and the best runner-up ideas to graft (e.g. a TTS winner + an RVC conversion pass).

**Phase 2 — Data pipeline & the recording kit (the one human hand-off — see §7).** Design
the dataset the winner needs and build the *whole* ingest→train path so it's ready the
moment audio arrives. Generate a **phonetically- and prosodically-balanced recording script
set** (target ≤ 60 min total, split into short numbered takes; cover phoneme balance,
questions/exclamations/emphasis, long-form passages, and varied emotion/pace so the model
learns cadence, not just timbre) — extend the existing kit in `docs/recording-scripts.md`
and the sample scripts in `voice clone scripts/`. Build ingest: raw recordings →
segment / denoise / normalize / **Whisper-align** → train/val split → dataset manifest →
one-command fine-tune. Prove the pipeline end-to-end on a stand-in voice first.

**Phase 3 — Implementation (parallel teams).** Swap the engine behind the **existing
interface** (§8) so the rest of the app keeps working, extend enrollment to the fine-tune
path, and add prosody/style controls. Keep `pytest -m "not slow" -q` green at every commit.

**Phase 4 — Indistinguishability verification (raise the bar).** Today's `verify.py` only
scores one Resemblyzer cosine — a high score can still sound synthetic. Build a real
acceptance suite (§8) and define a numeric **indistinguishability gate** the winner must
clear on the owner's real voice before DoD. Log artifacts.

**Phase 5 — Integration, docs, ship.** Verify end-to-end through Studio + CLI + desktop app;
update `docs/design.md`, `README.md`, the recording kit, and regenerate `recap.html`/demo
where relevant; run red-team round + completeness critic; auto-ship on a feature branch and
open a PR.

## 7. The one human hand-off (the only pause)

When you reach the point where only the owner's real audio can advance the mission:

1. Make it **trivial** for them. Put in `.goal/handoff/` (and surface in the chat): the
   numbered scripts to read, a one-paragraph recording guide (quiet room, consistent mic
   ~20 cm, one take per file, natural delivery), and the **exact import command** to run
   after recording (e.g. `double-chin enroll <name> <files...>` or the new train entrypoint).
2. State precisely what you need and why (how much audio, what variety).
3. **Then keep building.** Do every remaining task that does not strictly need the real
   audio, against a stand-in voice, so that when the audio lands the run finishes with one
   command. Only genuinely block if literally nothing else can progress — and even then,
   self-schedule a check rather than ending the mission.

## 8. The engine seam & the prosody spec (preserve these exactly)

Swap the model **without breaking the interface** — the app is engine-agnostic by design:

- Keep `DoubleChinEngine.synthesize(script, reference_wav, out_path, exaggeration, cfg_weight,
  temperature, max_chars, seed, progress) -> SynthesisReport` working
  (`src/double_chin/engine.py:76`). Preserve the per-chunk `progress(idx, total, text)` callback
  so `src/double_chin/studio/jobs.py` and the SSE stream are unaffected. If the new backend needs
  a trained checkpoint instead of a raw reference wav, resolve it inside the engine/voice
  layer — do not change the callers' contract.
- Extend enrollment `enroll()` in `src/double_chin/voices.py:147` from the 20 s zero-shot clip to
  the fine-tune dataset path; **drop the `MAX_REFERENCE_SECONDS = 20.0` cap**
  (`src/double_chin/config.py:11`) and store the trained adapter/checkpoint alongside the voice.
- **Prosody/cadence/style controls** (the "floor, not a ceiling" ask). Today the only lever
  is two fixed silence lengths (`src/double_chin/chunk.py:15`) and there is no SSML, pitch, rate,
  or emphasis (documented in `.claude/skills/double-chin-perform/references/levers.md` — use that
  file as the lever spec). Add real controls: inline pause/break markup, speaking-rate,
  emphasis, and a style/emotion reference, threaded through the engine → the `JobRequest`
  model (`src/double_chin/studio/app.py:47`) → Studio UI knobs (`src/double_chin/studio/static/
  index.html`, `app.js`) → CLI flags (`src/double_chin/cli.py`). Keep the `double-chin-perform` skill
  accurate to whatever you build.
- **Verification suite (Phase 4):** extend `src/double_chin/verify.py` beyond the single cosine
  (`verify.py:41`): a blind **ABX / mirror-test** (reuse the paired `demo/quiz/real_*.wav`
  vs `clone_*.wav` harness and the mirror-test quiz), speaker-verification EER, a naturalness
  MOS proxy, and a prosody-similarity metric. Add a real-model e2e gated by `DOUBLECHIN_E2E=1`
  (`pyproject.toml:26`) that asserts the new indistinguishability gate.

## 9. Definition of done (grade yourself; fix anything failing)

- [ ] New backend **fully integrated** behind the existing engine interface; Chatterbox
      zero-shot replaced (or demoted to a clearly-labelled fallback).
- [ ] The app works **end-to-end in the owner's voice** via Studio SPA, CLI, **and** the
      desktop app: import/paste a script → hear it in their voice.
- [ ] **Prosody/cadence/style controls** work (pauses/breaks, rate, emphasis, style
      reference) and are exposed in the UI + CLI.
- [ ] Recording scripts delivered + the ingest/fine-tune pipeline runs with one command;
      once the owner's audio is imported, the model **clears the numeric indistinguishability
      gate on their real voice**, with logged audio artifacts + scores (not just a cosine).
- [ ] `pytest -m "not slow" -q` green; the new `DOUBLECHIN_E2E=1` slow e2e passes on real audio;
      `double-chin doctor` clean.
- [ ] Guardrails held (no spend, nothing left the machine, watermark + loopback intact);
      red-team objections addressed; `docs/` + `recap.html` updated; no placeholders.
- [ ] Shipped on a feature branch with a PR. The **only** human input the whole run needed
      was the audio recordings.

## 10. Verification gate (run these; they must pass)

```bash
uv pip install --python .venv/bin/python -e ".[dev]"   # if deps changed
pytest -m "not slow" -q                                 # primary gate — must stay green
double-chin doctor                                           # env/device/weights health
DOUBLECHIN_E2E=1 pytest -m slow -q                           # real-model proof (after audio)
```

## 11. First-run bootstrap (do this now)

1. `git status` / read `.goal/ledger.md` if it exists → resume; else create `.goal/` and the
   ledger, and create/switch to a feature branch (do not work on `main`).
2. Write the mission + guardrails + task list into `.goal/ledger.md`; set the first heartbeat.
3. Kick off **Phase 0** immediately via a `Workflow` research fan-out. Keep going through the
   phases without pausing. Only ever stop for the §7 audio hand-off or a met §9 DoD — and when
   you would otherwise yield incomplete, `ScheduleWakeup prompt:"/goal"` to continue.

Now begin. Surprise me — best work, not safest work.
