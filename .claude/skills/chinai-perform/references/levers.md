# ChinAI rendering levers (ground truth)

ChinAI's engine is Chatterbox TTS, and it reads text **verbatim** — there is
no SSML, no `<break>` tag, no `[pause]` token, no markup of any kind. Every
lever below is either punctuation the model itself voices, or structural
whitespace the chunker turns into stitched silence. Do not invent syntax
outside this list; the engine will simply speak it aloud as literal
characters.

## What actually reaches the audio

| Lever | Mechanism | Effect | Citation |
|---|---|---|---|
| `,` mid-clause | passed to the model as part of the chunk text | brief voiced pause / breath | text flows verbatim into `model.generate(chunk.text, ...)` — `src/chinai/engine.py:120-125` |
| `—` / `…` | same — voiced hold, longer than a comma | longer voiced pause, no *added* silence | same |
| Sentence end (`. ? !` or `…`) | ends a `Chunk`; chunker attaches `pause_after` | **+0.35s** stitched silence between the audio of this chunk and the next | `INTRA_PARAGRAPH_PAUSE_SECONDS = 0.35` — `src/chinai/chunk.py:15`; realized as `torch.zeros` padding — `src/chinai/engine.py:128-131` |
| Blank line (paragraph break) | ends a paragraph; last chunk of the paragraph gets the larger pause | **+0.7s** stitched silence | `INTER_PARAGRAPH_PAUSE_SECONDS = 0.7` — `src/chinai/chunk.py:16` |
| `--exaggeration` | Chatterbox emotional-intensity control, used both when conditioning on the reference and at generation | whole-utterance delivery energy | default `0.5` — `src/chinai/engine.py:15`; `cli.py:55` |
| `--cfg` (reference adherence) | classifier-free-guidance weight | higher = sticks closer to the reference recording's delivery | default `0.5` — `src/chinai/engine.py:16`; `cli.py:56` |
| `--temperature` | sampling temperature | lower = more consistent between takes, higher = more variation | default `0.8` — `src/chinai/engine.py:17`; `cli.py:57` |

There is no speaking-rate/speed knob, no per-word emphasis, no top_k/top_p.

## What does NOT work (do not emit these)

- `<break time="0.4s"/>` or any SSML — Chatterbox has no SSML parser; it will
  be read aloud as literal text.
- `[pause]`, `(pause)`, `...pause...` style bracket tokens — same problem,
  read aloud verbatim.
- Markdown emphasis (`**bold**`, `*italic*`) — no effect on delivery; the
  asterisks would be read as characters.
- A "pause=0.8" style inline directive — the engine has no variable-pause
  mechanism at all; only the two fixed durations above exist.

## The only two silence durations that exist

0.35s (sentence-internal-to-chunk boundary) and 0.7s (paragraph boundary).
There is no way to request, say, a 1.2s dramatic pause exactly — the closest
approximation is a blank line (0.7s) plus a trailing `…` on the prior
sentence to add a bit of voiced hold before the stitched silence starts.
Always be upfront in the output that this is an approximation, not an exact
reproduction, when a source pause is much longer than 0.7s.

## Letter elongation (explicitly requested)

Chatterbox will attempt to pronounce repeated letters as a held/stretched
sound (e.g. `sooo`, `reeeally`) since it is reading literal text — this is
the one available lever for reproducing a word the speaker visibly drew out.
Use sparingly, only on words the style profile actually flags as elongation
candidates (`profile.json` → `elongation_candidates`), and keep the letter
repetition modest (2-3 extra letters) — excessive repetition tends to
confuse the model rather than sound natural.

## Verification caveat

`chinai say --verify` (`src/chinai/verify.py`) scores **speaker identity**
(cosine similarity against the held-out enrolment clip) — it does not score
prosody, pacing, or how natural the delivery sounds. A high verify score
tells you the clone sounds like the right person; it says nothing about
whether the performance script actually reproduced the target pauses.
