---
name: chinai-perform
description: Rewrite a plain script into a ChinAI "performance script" that reproduces the user's own pauses, pacing, and speech style. Use when preparing text for ChinAI, making the voice clone sound natural or like the user, or when the user mentions performance scripts, pauses, delivery, or speech style for ChinAI.
---

# ChinAI Perform

Rewrite a plain script into a ChinAI-ready performance script whose
punctuation, line breaks, and inserted fillers reproduce the user's own
pause rhythm and speech style — because ChinAI's engine reads text
**verbatim** with no SSML or pause markup. See
[references/levers.md](references/levers.md) for the exact, code-verified
list of what does and doesn't affect delivery. Read it before transforming
anything; do not invent syntax outside it.

## When to use

- The user asks to "prepare," "style," or "perform" a script for ChinAI.
- The user wants ChinAI's output to sound natural, like them, or to keep
  their pauses/pacing/filler words.
- The user provides a new reference recording to learn their speech style
  from.

## Workflow

### 1. Get (or build) the style profile

The profile lives at `$CHINAI_HOME/style/profile.json` (default
`~/.chinai/style/profile.json`). If it exists, read it and skip to step 2.

If it doesn't exist, or the user supplies a new/different reference
recording, build it:

```bash
.claude/skills/chinai-perform/.venv/bin/python \
  .claude/skills/chinai-perform/scripts/profile_audio.py \
  "<path to reference recording(s)>"
```

Default source (if the user doesn't name one): `~/Downloads/New Recording
63.m4a`. Multiple files can be passed to pool statistics across them (e.g.
adding `Part B - Harvard sentences.m4a`, which was read with natural gaps
between sentences and is a decent secondary pause-rhythm source — note Part
A/B are primarily voice-*enrolment* audio, not style samples, so prefer a
dedicated natural-speech recording when one exists).

The script prints where it wrote `profile.json` / `profile.md`. Read
`profile.md` — it's the human-readable summary with the numbers you need for
step 2.

**Setup note:** the profiler needs `mlx-whisper`, installed in a dedicated
venv at `.claude/skills/chinai-perform/.venv` (already provisioned; not the
system Python — Homebrew's Python is externally managed). If that venv is
ever missing, recreate it: `python3 -m venv .claude/skills/chinai-perform/.venv
&& .claude/skills/chinai-perform/.venv/bin/pip install mlx-whisper`.

### 2. Read the plain script the user wants performed

Either pasted inline or from a file path they give you.

### 3. Rewrite it using the pause-tier → lever mapping

For every place in the script where a natural speaker would pause, choose
the lever using the profile's own measured tier durations
(`profile.json` → `pause_tiers_seconds`) as the boundaries between rows:

| Where the user would naturally pause | Lever to insert | ChinAI result |
|---|---|---|
| Below the profile's `micro` tier — a light beat mid-clause | comma `,` | brief voiced pause |
| Between `micro` and `short` — mid-thought hesitation | em-dash `—` or ellipsis `…` | longer voiced hold, no added silence |
| Between `short` and `sentence` — end of a clause/thought | end the sentence (`.` `?` `!`) | **+0.35s** stitched silence |
| Between `sentence` and `beat` — a breath, a topic shift | blank line (paragraph break) | **+0.7s** stitched silence |
| Above `beat` — a long, dramatic pause | blank line **+** trailing `…` on the prior line | approximated only — flag this to the user; the engine has no longer fixed silence |

Judgment calls (this is the part that isn't mechanical):
- **Match clause length** to the profile's `clause_words` mean — split
  run-on sentences or fuse clipped ones so the rewritten script reads in
  chunks close to the user's actual clause length.
- **Sprinkle the user's fillers** (`profile.json` → `fillers_per_100w`) at
  natural hesitation points — at, not above, the measured rate. These are
  read verbatim by the engine, so they *are* the nuance the user asked for,
  not decoration.
- **Apply letter elongation** only on words the profile flags in
  `elongation_candidates`, and only if a semantically similar word appears
  in the new script — 2-3 extra letters, per
  [references/levers.md](references/levers.md#letter-elongation-explicitly-requested).
  Don't invent elongation the profile didn't observe.
- Never introduce SSML, bracket tokens, or markdown emphasis — see
  [references/levers.md](references/levers.md#what-does-not-work-do-not-emit-these).

### 4. Emit the performance script with a ready-to-run header

Write the rewritten script to a plain `.txt` file next to the source (or
wherever the user asks), with a leading comment block:

```
# chinai say --script <this-file> --voice <name> \
#   --exaggeration <profile.recommended_knobs.exaggeration> \
#   --cfg <profile.recommended_knobs.cfg> \
#   --temperature <profile.recommended_knobs.temperature>
```

Pull the three knob values straight from `profile.json` →
`recommended_knobs`; don't recompute them by hand.

### 5. Report the fidelity ceiling honestly

Tell the user: pauses beyond ChinAI's two fixed silence durations (0.35s /
0.7s) are approximated, not exact — see
[references/levers.md](references/levers.md#the-only-two-silence-durations-that-exist).
If they run `chinai say --verify`, remind them it scores speaker identity,
not prosody, so a high score doesn't confirm the pacing landed —
listening is the only way to check that.

## Worked example

Profile shows: `micro=0.15s short=0.35s sentence=0.5s beat=0.85s`,
fillers `so: 2.4, like: 1.2`, clause length ~9 words.

**Plain script (input):**
```
I think we should launch the new feature next week. The team has been working hard and the tests are passing. We just need final approval from leadership.
```

**Performance script (output):**
```
# chinai say --script launch-update.txt --voice me --exaggeration 0.5 --cfg 0.65 --temperature 0.7

So, I think we should launch the new feature — next week.

The team's been working hard, and the tests are passing.

We just need final approval, from leadership.
```

Blank lines mark the two topic-shift beats (launch decision → team status →
approval ask); the em-dash reproduces a mid-thought hesitation before
"next week"; commas mark lighter beats; "So," opens at the user's measured
filler rate.

## Limits

- ChinAI's silence model has exactly two fixed durations (0.35s sentence,
  0.7s paragraph) — see
  [references/levers.md](references/levers.md#the-only-two-silence-durations-that-exist).
  This skill approximates longer or more variable pauses; it cannot
  reproduce them exactly without an engine change (out of scope here).
- `--verify` measures speaker identity via cosine similarity against the
  held-out enrolment clip (`src/chinai/verify.py`) — it does not measure
  prosody or naturalness.
- The profile is only as good as the reference recording. A short or
  atypical sample (e.g. someone reading instructions aloud rather than
  speaking casually) will under- or over-estimate pause tiers and filler
  rate — sanity-check `profile.md` against how the user actually talks
  before trusting it blindly.
