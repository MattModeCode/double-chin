# Recording kit: clone your voice with Double Chin

Fifteen minutes from now, Double Chin can speak in your voice.

## What you need

- A phone, laptop, or dedicated microphone (built-in mic is fine — earbuds are not; see below)
- A quiet room with soft furnishings, or a closet full of clothes
- 15 minutes, uninterrupted

## Room and mic setup

1. **Sit ~20cm from the mic ("two fists" from your mouth to the device).** Consistent distance keeps loudness and tone even across every file.
2. **Record in a quiet, soft-furnished room, or a closet full of clothes.** Hard, empty rooms produce reverb, and Double Chin clones the room along with your voice.
3. **No music, no other speakers, no background noise.** Anything audible in the reference becomes part of the clone.
4. **Turn off noise gates, compressors, and noise-reduction/AI enhancement.** These processors distort the natural pace and inflection the clone needs to learn.
5. **Aim for peaks around -6 to -3 dB (avoid clipping/red on the meter).** Too quiet loses detail; too loud distorts.
6. **Use a wired mic or a phone's built-in mic — not AirPods-style earbuds.** Bluetooth earbuds compress audio and apply noise suppression, which corrupts the reference.
7. **Deliver every line at the pace and register you want the clone to use.** Double Chin clones your pacing and inflection exactly as recorded — a rushed take produces a rushed clone.

## The scripts

Read naturally, at conversational pace, in the voice register you want Double Chin to reproduce. Re-record any line where you stumble, cough, or get interrupted — don't try to fix it by talking around it.

### Part A — Rainbow Passage (Take 1)

Read both paragraphs below **continuously, in one file** (about 45–60 seconds total).

> When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow. The rainbow is a division of white light into many beautiful colors. These take the shape of a long round arch, with its path high above, and its two ends apparently beyond the horizon. There is, according to legend, a boiling pot of gold at one end. People look, but no one ever finds it. When a man looks for something beyond his reach, his friends say he is looking for the pot of gold at the end of the rainbow.
>
> Throughout the centuries people have explained the rainbow in various ways. Some have accepted it as a miracle without physical explanation. To the Hebrews it was a token that there would be no more universal floods. The Greeks used to imagine that it was a sign from the gods to foretell war or heavy rain. The Norsemen considered the rainbow as a bridge over which the gods passed from earth to their home in the sky.

### Part B — Harvard sentences (Takes 2–13)

Read each sentence below as its own file, **or** all 12 continuously in one file — both work for enrolment. One sentence = one clean, natural utterance; pause briefly between sentences if recording continuously.

1. The birch canoe slid on the smooth planks.
2. Glue the sheet to the dark blue background.
3. It's easy to tell the depth of a well.
4. These days a chicken leg is a rare dish.
5. Rice is often served in round bowls.
6. The juice of lemons makes fine punch.
7. The box was thrown beside the parked truck.
8. The hogs were fed chopped corn and garbage.
9. Four hours of steady work faced us.
10. A large size in stockings is hard to sell.
11. The boy was there when the sun rose.
12. A rod is used to catch pink salmon.

That's roughly 1–2 minutes of speech across 13 files (or 2 files) — enough for Double Chin to pick the best 10–15 second window and hold out the rest for verification.

## Recording settings

**macOS Voice Memos:** Settings > Voice Memos > Audio Quality > set to **Lossless**. Then record as normal — one tap to start, one to stop per take.

**QuickTime Player:** File > New Audio Recording. Click the dropdown arrow next to the record button and set quality to **Maximum**. Record and save each take.

**Any other recorder app:** match these settings as closely as possible — mono, 16- or 24-bit, 44.1kHz or 48kHz sample rate, no compression/limiter/noise-reduction effects enabled.

File format doesn't matter — .m4a, .wav, .mp3, and .flac all work. Double Chin converts automatically on enrolment.

## Self-check before enrolling

Listen back to every file with headphones before moving on. Confirm:

- [ ] No echo or room reverb audible
- [ ] No hum, hiss, or background noise under your voice
- [ ] No clipping or distortion on loud syllables
- [ ] Distance from the mic sounds steady across all files
- [ ] It sounds like how you want the clone to sound — same pace, same energy

If any file fails a check, re-record just that one — don't re-record everything.

## Enrol

Put all your recordings in one folder, then run:

```bash
double-chin enroll me ~/Desktop/my-voice/
```

Test it immediately:

```bash
double-chin say "This is my voice clone speaking." --voice me -o test.wav --verify
```

`--verify` prints a similarity score comparing the generated audio to a held-out clip from your recordings (when you enrolled two or more files, Double Chin reserves the last one for exactly this check — it is never part of the reference the model imitates). The score measures who the output sounds like, not what was said, so still listen to your first take:

- **≥ 0.75** — good match, you're done
- **0.60–0.75** — usable but marginal; a re-recording of the noisiest file will likely improve it
- **< 0.60** — the reference is too noisy or inconsistent; re-record before relying on this voice

## If the clone sounds off

| Symptom | Cause | Fix |
|---|---|---|
| Robotic or muffled | Mic too far away, or room too noisy/reverberant | Re-record closer to the mic (two fists), in a quieter, softer room |
| Wrong pace (too fast/slow, wrong energy) | Double Chin clones the exact pace and register you recorded | Re-record at the pace and register you actually want the clone to use |
| Echoey or hollow | Hard-surfaced room | Move to a softer room or a closet full of clothes |
| Verification score < 0.60 | Reference audio is noisy or inconsistent | Re-record the flagged file(s) following the room/mic rules above |

## Licence note

The Rainbow Passage (Fairbanks, 1960) is in the public domain. The Harvard Sentences (IEEE, 1969) are de facto public domain and freely republished for speech-testing purposes. Both are reproduced here in full for personal use with Double Chin.
