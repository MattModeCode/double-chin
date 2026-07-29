# Double Chin rendering levers (ground truth)

Double Chin's engine is Chatterbox TTS. Chatterbox itself has **no SSML** — it
reads whatever text it is handed verbatim. But Double Chin now runs a thin,
**honest prosody layer** (`src/double_chin/prosody.py`) that parses a tiny inline
markup *before* the text reaches the model and compiles it into the real
levers the engine already has: variable stitched silence and per-chunk
emotional intensity. Plus a genuine speaking-rate control applied as a
pitch-preserving time-stretch on the finished audio.

So there are two kinds of lever: the **inline markup** Double Chin parses (below),
and the punctuation/whitespace Chatterbox voices on its own. Anything outside
the supported markup is passed through verbatim — unrecognized brackets are
stripped so they are never spoken, but invented SSML-style tags are not
understood. Stick to the markup documented here.

## Inline markup Double Chin parses (compiled before the model sees the text)

Parsed in `src/double_chin/prosody.py::compile_script`, which the engine calls in
place of the raw chunker.

| Markup | Mechanism | Effect |
|---|---|---|
| `[pause:N]` | splits the script at that point; `N` seconds (clamped to ≤10) becomes the `pause_after` of the preceding chunk, overriding the default | **exactly N s** of stitched silence — any duration you want, not just the two defaults |
| `[break]` | same, with the default duration | **+0.5s** stitched silence (`DEFAULT_BREAK_SECONDS`) |
| `*word*` | marks any chunk overlapping the span as `emphasis=True`; the engine raises that chunk's generation exaggeration by `+0.3` and lowers `cfg_weight` by `0.1` (both clamped) | that span is delivered **hotter / more intense** than the rest |
| `[emph]…[/emph]` | same as `*word*`, bracketed form for multi-word or asterisk-containing spans | same |

Notes on the markup:
- **Granularity is the chunk, not the exact word.** Chatterbox's exaggeration
  is a per-`generate()` (per-chunk) control — there is no sub-chunk knob — so
  emphasizing a word raises intensity for the whole chunk that contains it.
  Put a `[pause:…]` or sentence break around a phrase to isolate it if you
  need tighter targeting.
- **Markup never leaks into audio.** Unbalanced `*`, stray `[/emph]`, or a
  malformed `[pause:abc]` are stripped/dropped, never spoken. A lone `*` that
  isn't part of a pair is left as literal text.
- A `[pause:…]` with no speech before it (leading, or two in a row) folds into
  the nearest prior chunk, or is dropped if there is nothing before it.

## Global delivery params

| Lever | Mechanism | Effect | Citation |
|---|---|---|---|
| `--rate` / `rate` (0.5–2.0) | **pitch-preserving time-stretch** of the finished audio via `librosa.effects.time_stretch` | genuine speaking-rate / cadence control — `1.0` unchanged, `>1` faster, `<1` slower. Chatterbox has no native rate knob; this is layered on after generation, so pitch is preserved. | default `1.0` — `src/double_chin/engine.py` (`DEFAULT_RATE`); `cli.py --rate`; Studio "Speaking rate" slider |
| `--exaggeration` | Chatterbox emotional-intensity control, used both when conditioning on the reference and at generation | whole-utterance delivery energy (the **style/intensity** knob) | default `0.5` — `src/double_chin/engine.py`; `cli.py` |
| `--cfg` (reference adherence) | classifier-free-guidance weight | higher = sticks closer to the reference recording's delivery | default `0.5` — `src/double_chin/engine.py`; `cli.py` |
| `--temperature` | sampling temperature | lower = more consistent between takes, higher = more variation | default `0.8` — `src/double_chin/engine.py`; `cli.py` |

## Punctuation/whitespace Chatterbox voices on its own

| Lever | Mechanism | Effect |
|---|---|---|
| `,` mid-clause | passed to the model as part of the chunk text | brief voiced pause / breath |
| `—` / `…` | same — voiced hold, longer than a comma | longer voiced pause, no *added* silence |
| Sentence end (`. ? !` or `…`) | ends a `Chunk`; chunker attaches `pause_after` | **+0.35s** stitched silence (`INTRA_PARAGRAPH_PAUSE_SECONDS`), unless overridden by `[pause:N]` |
| Blank line (paragraph break) | ends a paragraph; last chunk gets the larger pause | **+0.7s** stitched silence (`INTER_PARAGRAPH_PAUSE_SECONDS`) |

## What still does NOT work (do not emit these)

- `<break time="0.4s"/>` or any real SSML — Chatterbox has no SSML parser and
  Double Chin's markup is not SSML. Use `[pause:0.4]` instead.
- `[pause]`/`(pause)` with no number — only `[pause:N]` (numeric) and `[break]`
  are recognized; a bare `[pause]` is treated as unknown and stripped.
- Per-word emphasis at sub-chunk resolution — emphasis is per chunk (see above).
- `top_k` / `top_p` — not exposed by Chatterbox's `generate()`.
- Taking cadence from one clip and timbre from another (a separate "style
  reference") — Chatterbox has a single conditioning path (`prepare_conditionals`
  takes exactly one clip and it defines the *speaker*). Seeding it from a second
  clip would swap the voice identity, so Double Chin does **not** offer a `style_ref`.
  Use `--exaggeration`, `--rate`, and inline markup for delivery instead.

## Silence durations now available

Any duration via `[pause:N]` (0–10s), plus `[break]` (0.5s) and the two
structural defaults (0.35s sentence, 0.7s paragraph). A 1.2s dramatic pause is
now exact: write `[pause:1.2]`. The old blank-line-plus-`…` approximation is no
longer necessary.

## Letter elongation (explicitly requested)

Chatterbox will attempt to pronounce repeated letters as a held/stretched
sound (e.g. `sooo`, `reeeally`) since it is reading literal text — this is
the one available lever for reproducing a word the speaker visibly drew out.
Use sparingly, only on words the style profile actually flags as elongation
candidates (`profile.json` → `elongation_candidates`), and keep the letter
repetition modest (2-3 extra letters) — excessive repetition tends to
confuse the model rather than sound natural.

## Verification caveat

`double-chin say --verify` (`src/double_chin/verify.py`) scores **speaker identity**
(cosine similarity against the held-out enrolment clip) — it does not score
prosody, pacing, or how natural the delivery sounds. A high verify score
tells you the clone sounds like the right person; it says nothing about
whether the performance script actually reproduced the target pauses.
