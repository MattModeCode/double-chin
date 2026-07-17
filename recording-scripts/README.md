# Fine-tuning recording kit

This folder is the big recording kit — the one you read to build a **fine-tuning
dataset** for ChinAI, not the quick 1–2 minute enrolment kit in
[`docs/recording-scripts.md`](../docs/recording-scripts.md).

You read the numbered scripts (`001.txt` … `079.txt`) aloud, one file per
recording, and save each recording under the **same number**. ChinAI pairs your
audio `001.<ext>` with the transcript for take `001`, and so on down the list.
That number-to-audio match is the whole contract — get the numbers right and the
rest takes care of itself.

**Target: about 50 minutes of clean audio across the 79 takes.** More is better,
but even 30 minutes of clean, consistent recordings meaningfully improves the
clone. You do **not** have to do it all at once — see "Do it in sittings" below.

## What each take is

- Every `NNN.txt` holds the exact words to read in one recording, and nothing
  else — no headings, no notes. The file doubles as the transcript.
- A take runs roughly 20–60 seconds (a few short sentences, or one short
  passage). Read the whole file in a single recording.
- The set is deliberately varied — plain sentences, questions, lists, different
  emotional registers, and longer stories — so the clone learns your **rhythm and
  inflection**, not just the sound of your voice. Read each one the way its words
  want to be read (a question sounds like a question; an excited line sounds
  excited). That variety is the point, so lean into it.

## Room and mic setup

Same rules as the quick kit — consistency across every file is what matters most.

1. **Sit ~20cm from the mic ("two fists" from your mouth to the device).**
   Consistent distance keeps loudness and tone even across every file.
2. **Record in a quiet, soft-furnished room, or a closet full of clothes.** Hard,
   empty rooms produce reverb, and ChinAI clones the room along with your voice.
3. **No music, no other speakers, no background noise.** Anything audible in the
   recording becomes part of the clone.
4. **Turn off noise gates, compressors, and noise-reduction / AI enhancement.**
   These processors distort the natural pace and inflection the clone needs.
5. **Aim for peaks around -6 to -3 dB (avoid clipping / red on the meter).** Too
   quiet loses detail; too loud distorts.
6. **Use a wired mic or a phone's built-in mic — not AirPods-style earbuds.**
   Bluetooth earbuds compress audio and apply noise suppression, which corrupts
   the recording.
7. **Deliver every line at the pace and register you want the clone to use.**
   ChinAI clones your pacing and inflection exactly as recorded.

## Recording settings

**macOS Voice Memos:** Settings > Voice Memos > Audio Quality > set to
**Lossless**. Then record as normal — one tap to start, one to stop per take.

**QuickTime Player:** File > New Audio Recording. Click the dropdown arrow next
to the record button and set quality to **Maximum**. Record and save each take.

**Any other recorder app:** match these settings as closely as possible — mono,
16- or 24-bit, 44.1kHz or 48kHz sample rate, no compression / limiter /
noise-reduction effects enabled.

File format doesn't matter — `.m4a`, `.wav`, `.mp3`, and `.flac` all work. ChinAI
converts automatically. Sit down for each session in the same spot, at the same
distance, with the same settings, so all your files match.

## The workflow, one take at a time

1. Open `001.txt` and read it silently once so nothing surprises you mid-take.
2. Start recording, read the whole file at a natural pace, then stop.
3. Save the recording as `001` — `001.m4a` or `001.wav`, whatever your app
   produces. **The number must match the script.**
4. Move to `002.txt`, and repeat down to `079.txt`.
5. Put every recording in one folder (all named to match their take number).

Read at conversational pace, in the voice register you want ChinAI to reproduce.
Re-record any take where you stumble, cough, or get interrupted — don't talk
around a mistake, just do that one file again. A clean re-read always beats a
patched one.

### Reading the trickier takes

- **Questions, exclamations, commands:** let the punctuation lead you. Say them
  the way you'd say them to a person.
- **Lists:** keep the rising "still going…" tone on each item, then fall on the
  last one.
- **Emotional takes:** the words are plain on purpose — carry the feeling in your
  voice (warm, excited, calm, firm), not in what's being said.
- **Numbers, dates, spelling:** read them the natural way. Digits written with
  commas (like `6, 4, 7`) are meant to be read one digit at a time; spelled
  letters (like `S, T, E, P`) are read as letters. Times like `9:45` are "nine
  forty-five", `$49.99` is "forty-nine dollars and ninety-nine cents".
- **Long passages (the stories and the rainbow reading):** read them straight
  through as one flowing take, pausing briefly at each sentence, the way you'd
  read aloud to someone.

## Self-check before you finish

Listen back with headphones. For each file confirm:

- [ ] The recording's number matches the script you read
- [ ] No echo or room reverb audible
- [ ] No hum, hiss, or background noise under your voice
- [ ] No clipping or distortion on loud syllables
- [ ] Distance from the mic sounds steady across all files
- [ ] It sounds like how you want the clone to sound — same pace, same energy

If a file fails a check, re-record just that one — don't redo everything.

## How long it takes

Plan on roughly **60–75 minutes** to record all 79 takes, including the pauses to
read ahead and the odd re-take. That yields about **50 minutes** of actual speech,
which is a strong fine-tuning set.

### Do it in sittings

You don't need to record everything in one go, and you probably shouldn't —
tired voices drift. Do 15–20 takes at a stretch, then come back later. Just keep
the **same room, same mic, same distance, and same settings** every session so
the files stay consistent. Any order is fine; the numbers, not the sequence, are
what tie audio to transcript.

## Licence note

The Rainbow Passage (Fairbanks, 1960) is in the public domain. The Harvard
Sentences (IEEE, 1969) are de facto public domain and freely republished for
speech testing. The fables (Aesop, from pre-1928 public-domain translations) and
"The North Wind and the Sun" are in the public domain. The remaining
sentences — questions, lists, emotional lines, everyday narratives, and the
number and pronunciation drills — are original text written for this kit. Nothing
here is under copyright.
