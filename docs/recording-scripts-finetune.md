# Fine-tuning recording corpus

This document points to the **large** recording kit used to build a
fine-tuning dataset for a Chatterbox TTS fine-tune. For the reading guide,
setup, and self-check, see [`recording-scripts/README.md`](../recording-scripts/README.md).

## Two kits, two jobs

| | Quick enrolment kit | Fine-tuning corpus |
|---|---|---|
| Location | [`docs/recording-scripts.md`](recording-scripts.md) | [`recording-scripts/`](../recording-scripts/) |
| Speech | ~1–2 minutes | **~50 minutes** (target) across 79 takes |
| Use | Reference-based cloning: pick the best short window | **Fine-tuning**: teach the model your cadence, not just timbre |
| Format | A couple of long reads | 79 numbered one-take files, `001.txt` … `079.txt` |

The quick kit is enough for reference-based cloning. This corpus is for an actual
**fine-tune**, where the model needs enough of your connected speech — across
sentence types, registers, and lengths — to learn how you talk, not only how you
sound.

## The number-to-audio contract

Each take is one file. The owner reads `NNN.txt` in a single recording and saves
the audio under the **same number** (`001.txt` → `001.m4a` / `001.wav`). The
ingest pipeline pairs audio `NNN.<ext>` with the transcript for take `NNN`.

- `recording-scripts/NNN.txt` — the exact words to read; the file **is** the
  transcript (no headers, no notes inside it).
- `recording-scripts/manifest.tsv` — the training-data contract, one row per
  take: `take_id`, `filename`, `bucket`, `est_seconds`, `transcript` (the full
  text on a single line). Ingest can read this directly to pair each recording
  with its transcript and its coverage bucket.

## Coverage design

The set is deliberately spread across buckets so the fine-tune learns prosody and
connected-speech rhythm, not just voice colour. Roughly 48 minutes of estimated
speech, distributed as:

| Bucket | Takes | ~Minutes | Purpose |
|---|---:|---:|---|
| Phonetic — Harvard sentences | 24 | 10.8 | Broad phoneme coverage; a wide spread of Harvard lists |
| Phonetic — pangrams | 3 | 1.4 | Dense, phonetically rich sentences |
| Prosodic variety | 9 | 4.0 | Yes/no and wh- questions, exclamations, imperatives, list intonation, contrastive emphasis |
| Emotional / register | 15 | 7.5 | Neutral, warm, excited, serious, gentle, firm — original neutral-content lines |
| Long-form — public-domain passages | 14 | 12.9 | Rainbow Passage, "The North Wind and the Sun", and Aesop's fables, for natural connected speech |
| Long-form — original narratives | 9 | 8.3 | Everyday first-person monologues for spontaneous-sounding cadence |
| Numbers / dates / spelling / hard cases | 5 | 2.9 | Digits, money, dates, times, acronyms, spelled-out letters, tricky pronunciations |
| **Total** | **79** | **~47.9** | |

Fine buckets (e.g. `emotion-warm`, `prosody-question-wh`, `longform-passage`) are
recorded per take in the `bucket` column of `manifest.tsv`.

## Source and licensing

All text is public-domain or original — no copyrighted lyrics, books, or
articles. Harvard Sentences (IEEE, 1969, de facto public domain), the Rainbow
Passage (Fairbanks, 1960, public domain), Aesop's fables and "The North Wind and
the Sun" (pre-1928 public-domain translations), plus original sentences and
narratives written for this kit. See the licence note in
[`recording-scripts/README.md`](../recording-scripts/README.md).
