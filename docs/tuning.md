# Delivery tuning — method and results

`double-chin tune` searches the four delivery controls for the values that
make synthesized takes least distinguishable from your own recordings. This
page records the run against the owner's voice, and what it found.

**Headline: three of the four knobs came back a tie, and the fourth has a
large, one-sided result.** Expression, reference adherence and variation could
not be shown to beat the engine's own defaults on held-out text — every
difference sat inside run-to-run noise. Speaking rate is different: any value
other than 1.00× measurably damages the voice.

## Setup

| | |
|---|---|
| Voice | `owner` (LoRA fine-tuned, 20 s reference) |
| Machine | M-series Mac, MPS, 2026-09-09 |
| Real clips | 8 recordings for the search, 6 disjoint ones for the held-out check |
| Scripts | two plain-prose passages, ~10 s of audio each |
| Takes per candidate | 3, deterministic seeds derived from the candidate key |
| Candidates measured | 24 on the tuning script, plus 2 held-out checks |
| Cost | ~5.5 min per candidate (3 syntheses + one gate run) |

Recordings 001–010 are excluded from both sets: `reference.wav` is built from
the start of the corpus and caps at 20 s, so scoring against them would compare
the clone to its own conditioning audio.

The eval scripts carry no prosody markup. `*emphasis*` raises exaggeration and
lowers cfg_weight for the chunk it spans and clamps at the knob's range, which
would distort exactly the candidates near the ends of the grid. Marks layer on
top of whatever profile wins; they are not part of what is being measured.

## What is being maximized

Each candidate's three takes are scored as a *set* against the real clips with
`verification.gate.indistinguishability_gate`. The gate's own composite turns
out to be unusable as a ranking signal here: its `discrimination` component is
**0.000 for every candidate**, because with eight real clips against three
clone clips the classifier separates the two sets outright. A weighted
geometric mean with a zero in it collapses — every candidate scores ~0.026 —
and a component that never varies cannot order anything.

So the search ranks on the three components that do respond, using the gate's
own weights:

```
objective = weighted geometric mean of
  speaker_similarity (0.30), naturalness (0.25), prosody (0.20)
```

The full gate result is still recorded for every candidate. The objective is a
parameter of the search (`SweepContext.objective`), not a hidden assumption.

## Noise floor

The baseline profile was measured three times with different seeds before the
search started:

| repeat | objective | speaker | prosody |
|---|---|---|---|
| v0 | 0.7777 | 0.637 | 0.766 |
| v1 | 0.7698 | 0.632 | 0.747 |
| v2 | 0.7943 | 0.673 | 0.763 |

**mean 0.781, sd 0.012.** A candidate has to beat 0.781 by more than 0.012 to
be worth anything.

## Results

Best candidates on the tuning script (all at rate 1.00×):

| exaggeration | cfg_weight | temperature | objective | speaker | prosody |
|---|---|---|---|---|---|
| 0.50 | 0.80 | 0.45 | **0.8018** | 0.668 | 0.800 |
| 0.50 | 0.20 | 0.80 | 0.7991 | 0.664 | 0.798 |
| 0.50 | 0.80 | 0.50 | 0.7942 | 0.657 | 0.792 |
| 0.50 | 0.80 | 0.80 | 0.7881 | 0.656 | 0.771 |
| 0.50 | 0.50 | 0.80 | 0.7806 (baseline) | 0.647 | 0.759 |
| 0.50 | 0.80 | 0.65 | 0.7625 | 0.621 | 0.740 |

Every rate-1.00× candidate measured, best to worst, spans 0.7625 to 0.8018 — a
range of 0.039, or about three standard deviations of the noise floor, across
the entire grid. Individual differences are one to one and a half sd.

The search's winner (0.50 / 0.80 / 0.45 / 1.00×) beat the baseline by +0.021 on
the tuning script, which clears the noise floor. It then **failed the held-out
check**:

| profile | tuning script | held-out script + held-out clips |
|---|---|---|
| winner 0.50 / 0.80 / 0.45 | 0.8018 | 0.8104 |
| baseline 0.50 / 0.50 / 0.80 | 0.7806 | **0.8213** |

On unseen text and unseen real clips the baseline scores *higher* than the
winner. The +0.021 was fitted to the tuning passage. Note also that the
baseline moved 0.781 → 0.821 between conditions: the variance between
script/clip-set conditions (~0.04) is larger than any parameter effect measured
within one (~0.02). This measurement cannot resolve a winner among those three
knobs, and reporting one anyway would be reporting noise.

### Speaking rate is the exception

| rate | objective | speaker similarity |
|---|---|---|
| 1.00× | 0.7942 | 0.657 |
| 0.95× | 0.6556 | 0.421 |
| 1.05× | 0.6182 | 0.403 |
| 1.10× | 0.6483 | 0.389 |

Every departure from 1.00× costs 0.13–0.18 objective — roughly ten standard
deviations — and speaker similarity falls from ~0.66 to ~0.40. That is the
expected consequence of how the knob works: rate is a pitch-preserving
time-stretch applied to *finished* audio (`engine.synthesize`), so it resamples
away formant and timing detail the speaker embedding relies on. It is a real
control for pacing, and it is the wrong tool for sounding more like yourself.

## Conclusion

`delivery.TUNED_PROFILE` is set to **0.50 / 0.50 / 0.80 / 1.00×** — identical to
the neutral baseline, because nothing beat it out of sample. Studio opens on
that profile, "Match my voice" restores it, and "Reset to neutral" goes to the
same place today. The two buttons diverge as soon as a run on a different
corpus writes a different profile with `tune --write-defaults`.

The plausible reading of this result: the LoRA fine-tune is already doing the
voice matching, and the delivery knobs have little headroom left on top of it.
That is a finding about this voice, not a defect in the search.

## Limits

- 24 candidates, one coordinate pass plus refinement — a fuller search might
  find a real effect, though the noise floor sets a hard limit on how small an
  effect this method can resolve at all.
- Three takes per candidate. More repeats would shrink the noise floor; the
  cost is linear.
- ~10 s clips. Longer clips give the prosody metric more to work with and cost
  proportionally more.
- The gate composite is unreadable in this configuration (~0.026 for
  everything) because of the collapsed `discrimination` component. Compare
  candidates on the objective, and use `double-chin gate` — which uses a
  balanced set — for an absolute verdict on a voice.
- The real clips were part of the fine-tune's training corpus, so the absolute
  similarity numbers are optimistic. This affects every candidate equally, so
  it does not bias the ranking.

## Re-running

```bash
double-chin tune owner --real-dir Recording-scripts-audio --takes 3 --budget 120
```

Add `--write-defaults` to save the winner to `~/.double-chin/delivery.json`,
which is what Studio then opens with. Measurements are appended to
`~/.double-chin/tuning/<voice>/ledger.jsonl` and reused on the next run, so an
interrupted sweep continues where it stopped and re-running costs only the
candidates it has not seen.
