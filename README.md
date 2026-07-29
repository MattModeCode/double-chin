# Double Chin

Your voice, on script.

Double Chin is a local voice-cloning application. Give it a few minutes of someone's voice and a text script, and it reads the script aloud in that voice — entirely on your machine. No cloud, no account, no audio leaving the laptop. One command opens the app: pick a voice, paste a script, hit Generate, and watch it synthesize chunk by chunk with a live speaker-similarity verdict on every take.

![Double Chin Studio](demo/studio/double-chin-studio-demo.gif)

Watch a real session, script to spoken take: [`demo/double-chin-studio-demo.mp4`](demo/double-chin-studio-demo.mp4).

## Hear it

These are real clips of the owner's voice, cloned by Double Chin from a fine-tuned local model — nothing here is a recording:

- 🔊 [`demo/owner_finetuned_demo.wav`](demo/owner_finetuned_demo.wav) — 17.8s
- 🔊 [`demo/examples/example-1.mp3`](demo/examples/example-1.mp3) — 8.4s
- 🔊 [`demo/examples/example-2.mp3`](demo/examples/example-2.mp3) — 7.4s
- 🔊 [`demo/examples/example-3.mp3`](demo/examples/example-3.mp3) — 7.0s
- 🔊 [`demo/examples/example-4.mp3`](demo/examples/example-4.mp3) — 8.9s
- 🔊 [`demo/examples/example-5.mp3`](demo/examples/example-5.mp3) — 7.0s

Each one verifies against a held-out reference clip the model never saw. The underlying voice — the reference audio, the fine-tuned adapter — never leaves this machine and isn't in this repo; only these generated clips are. Full method and numbers: [`.goal/ledger.md`](.goal/ledger.md) (gate **PASS 0.822**, near-indistinguishable, threshold 0.70).

## Requirements

- macOS on Apple Silicon (tested: M5 Pro, macOS 26) — Linux/CUDA and CPU also work, slower on CPU
- Python 3.12 (a managed one is fine; `uv` handles it)
- ~6 GB disk for model weights (downloaded once from Hugging Face on first run)

## Setup

```bash
git clone <this-repo> && cd double-chin
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
source .venv/bin/activate
double-chin doctor          # checks device, deps, disk — everything should PASS
double-chin studio          # starts http://127.0.0.1:8787 and opens your browser
```

## Clone your own voice

Record the [79-take corpus](recording-scripts/) (~50 minutes), then:

```bash
double-chin enroll yourvoice path/to/recordings/
double-chin train yourvoice path/to/recordings/ --manifest path/to/recordings/manifest.tsv
double-chin say "Hello, world." --voice yourvoice -o out.wav --verify
```

Every enrolled voice lives only in `~/.double-chin/voices/`; deleting that folder revokes it entirely. Don't clone a voice you don't have the right to clone — every output carries an inaudible [Perth watermark](https://github.com/resemble-ai/chatterbox#watermarking), but it's a provenance signal, not a control.

## Licences

Double Chin: MIT. Engine ([Chatterbox TTS](https://github.com/resemble-ai/chatterbox)): MIT. Verifier ([resemblyzer](https://github.com/resemble-ai/Resemblyzer)): Apache 2.0.
