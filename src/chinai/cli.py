"""Command-line interface for ChinAI."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from chinai import __version__
from chinai.config import chinai_home, migrate_legacy_home
from chinai.engine import DEFAULT_CFG_WEIGHT, DEFAULT_EXAGGERATION, DEFAULT_TEMPERATURE

# Commands that actually touch chinai_home(); migration only needs to run
# ahead of these, so `chinai verify` (arbitrary wav files, no storage) and
# argparse-level exits (--help, unknown/missing command) never trigger it.
_STORAGE_COMMANDS = frozenset({"enroll", "say", "train", "voices", "doctor", "studio", "app"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chinai",
        description="Local voice-cloning CLI powered by Chatterbox TTS.",
    )
    parser.add_argument("--version", action="version", version=f"chinai {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll_parser = subparsers.add_parser(
        "enroll", help="Enroll a voice from one or more reference recordings."
    )
    enroll_parser.add_argument("name", help="Voice name (lowercase letters, digits, '-', '_').")
    enroll_parser.add_argument(
        "sources", nargs="+", type=Path,
        help="Audio files (.wav/.flac/.mp3/.m4a) or a directory containing them.",
    )

    say_parser = subparsers.add_parser(
        "say", help="Synthesize a script in an enrolled or reference voice."
    )
    text_group = say_parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("text", nargs="?", help="Text to speak.")
    text_group.add_argument("--script", type=Path, help="Path to a text file containing the script.")
    voice_group = say_parser.add_mutually_exclusive_group(required=True)
    voice_group.add_argument("--voice", help="Name of an enrolled voice.")
    voice_group.add_argument("--ref", type=Path, help="Path to a reference wav file.")
    say_parser.add_argument(
        "-o", "--out", type=Path, default=Path("chinai_out.wav"),
        help="Output wav path (default: ./chinai_out.wav).",
    )
    say_parser.add_argument(
        "--verify", action="store_true",
        help="Verify speaker similarity against the reference after synthesis.",
    )
    say_parser.add_argument("--exaggeration", type=float, default=DEFAULT_EXAGGERATION)
    say_parser.add_argument("--cfg", type=float, default=DEFAULT_CFG_WEIGHT)
    say_parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    say_parser.add_argument("--seed", type=int, default=None)
    say_parser.add_argument("--device", default=None, help="Force a device (mps/cuda/cpu).")

    train_parser = subparsers.add_parser(
        "train",
        help="Fine-tune a LoRA voice adapter for an enrolled voice on your recordings.",
    )
    train_parser.add_argument("name", help="Name of an already-enrolled voice.")
    train_parser.add_argument(
        "recordings_dir", type=Path,
        help="Directory of recordings named NNN.{wav,m4a,mp3,flac} matching the manifest.",
    )
    train_parser.add_argument(
        "--manifest", type=Path, default=None,
        help="Path to manifest.tsv (default: <recordings_dir>/manifest.tsv).",
    )
    train_parser.add_argument("--epochs", type=int, default=5, help="Passes over the training set.")
    train_parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Cap total optimizer steps (overrides --epochs when set).",
    )
    train_parser.add_argument("--device", default=None, help="Force a device (mps/cpu).")

    subparsers.add_parser("voices", help="List enrolled voices.")

    verify_parser = subparsers.add_parser(
        "verify", help="Compare speaker similarity between two wav files."
    )
    verify_parser.add_argument("ref", type=Path)
    verify_parser.add_argument("other", type=Path)

    subparsers.add_parser("doctor", help="Report environment diagnostics.")

    studio_parser = subparsers.add_parser(
        "studio", help="Launch ChinAI, the local web application."
    )
    studio_parser.add_argument(
        "--port", type=int, default=8787, help="Port to serve on (default: 8787)."
    )
    studio_parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't open the browser automatically.",
    )

    subparsers.add_parser(
        "app", help="Launch ChinAI as a native desktop window (no browser tab)."
    )

    return parser


def _cmd_enroll(args: argparse.Namespace) -> int:
    from chinai.voices import enroll

    info = enroll(args.name, args.sources)
    print(f"Enrolled voice '{info.name}': {info.duration_seconds:.1f}s reference audio.")
    print(f"Saved to {info.reference_wav}")
    return 0


def _cmd_say(args: argparse.Namespace) -> int:
    from chinai.engine import ChinaiEngine
    from chinai.verify import similarity, verdict
    from chinai.voices import get_voice

    if args.script:
        if not args.script.is_file():
            raise ValueError(f"script file not found: {args.script}")
        script_text = args.script.read_text()
    else:
        script_text = args.text

    if args.voice:
        voice = get_voice(args.voice)
        reference_wav = voice.reference_wav
        lora_path = voice.lora_path
    else:
        reference_wav = args.ref
        lora_path = None
        if not reference_wav.is_file():
            raise ValueError(f"reference wav not found: {reference_wav}")

    engine = ChinaiEngine(device=args.device)
    report = engine.synthesize(
        script=script_text,
        reference_wav=reference_wav,
        out_path=args.out,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg,
        temperature=args.temperature,
        seed=args.seed,
        lora_path=lora_path,
    )
    if lora_path is not None:
        print(f"Using fine-tuned adapter: {lora_path}")

    print(
        f"Wrote {report.out_path} ({report.audio_seconds:.1f}s audio, "
        f"{report.chunk_count} chunks)"
    )
    print(
        f"Device: {report.device}; speed {report.speed_ratio:.2f}x realtime "
        f"({report.wall_seconds:.1f} s wall for {report.audio_seconds:.1f} s audio)"
    )

    if args.verify:
        if args.voice and voice.holdout_wav is not None:
            compare_wav = voice.holdout_wav
            label = "held-out clip"
        else:
            compare_wav = reference_wav
            label = "reference (no holdout enrolled)"
        score = similarity(compare_wav, report.out_path)
        print(f"Speaker similarity vs {label}: {score:.3f} ({verdict(score)})")

    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from chinai.finetune.train import finetune_voice

    def on_progress(step: int, total: int, loss: float) -> None:
        if step == 1 or step == total or step % 5 == 0:
            print(f"step {step}/{total}  loss={loss:.4f}", file=sys.stderr)

    print(f"Fine-tuning voice '{args.name}' on {args.recordings_dir} ...", file=sys.stderr)
    adapter_path = finetune_voice(
        args.name,
        args.recordings_dir,
        manifest_path=args.manifest,
        epochs=args.epochs,
        max_steps=args.max_steps,
        device=args.device,
        progress=on_progress,
    )
    print(f"Fine-tuned voice '{args.name}'. Adapter saved to {adapter_path}")
    print(f"Synthesize with it: chinai say \"Hello.\" --voice {args.name}")
    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    from chinai.voices import list_voices

    voices = list_voices()
    if not voices:
        print("No voices enrolled yet. Use 'chinai enroll NAME SOURCE...' to add one.")
        return 0

    name_width = max(len("name"), *(len(v.name) for v in voices))
    print(f"{'name'.ljust(name_width)}  duration  created")
    for voice in voices:
        print(f"{voice.name.ljust(name_width)}  {voice.duration_seconds:6.1f}s  {voice.created}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from chinai.verify import similarity, verdict

    if not args.ref.is_file():
        raise ValueError(f"reference wav not found: {args.ref}")
    if not args.other.is_file():
        raise ValueError(f"comparison wav not found: {args.other}")

    score = similarity(args.ref, args.other)
    print(f"Similarity: {score:.3f} ({verdict(score)})")
    return 0


def _which_in(directories: list[str], name: str) -> str | None:
    for directory in directories:
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)
    return None


def _cmd_doctor(args: argparse.Namespace) -> int:
    import platform

    print(f"PASS python: {platform.python_version()}")

    try:
        import torch

        print(f"PASS torch: {torch.__version__}")
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
        print(f"PASS best device: {device}")
    except ImportError:
        print("WARN torch: not installed")

    try:
        import warnings

        with warnings.catch_warnings():
            # webrtcvad (a resemblyzer dep) imports the deprecated pkg_resources
            # on import; that notice is harmless noise on a diagnostics command.
            warnings.simplefilter("ignore")
            import resemblyzer  # noqa: F401

        print("PASS resemblyzer: importable")
    except ImportError:
        print("WARN resemblyzer: not installed; 'chinai verify' will fail")

    hf_cache = Path.home() / ".cache" / "huggingface"
    chatterbox_dirs = [p for p in hf_cache.rglob("*chatterbox*") if p.is_dir()] if hf_cache.is_dir() else []
    if chatterbox_dirs:
        print(f"PASS model weights cached: {chatterbox_dirs[0]}")
    else:
        print("WARN model weights not found in the local Hugging Face cache; first synthesis will download them.")

    ffmpeg_path = shutil.which("ffmpeg") or _which_in(["/opt/homebrew/bin"], "ffmpeg")
    if ffmpeg_path:
        print(f"PASS ffmpeg: {ffmpeg_path}")
    else:
        print("WARN ffmpeg not found on PATH.")

    home = chinai_home()
    print(f"PASS chinai home: {home}")

    disk_check_path = home if home.exists() else Path.home()
    usage = shutil.disk_usage(disk_check_path)
    free_gb = usage.free / (1024 ** 3)
    print(f"PASS free disk: {free_gb:.1f} GB")

    return 0


def _cmd_studio(args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from chinai.studio.app import create_app

    url = f"http://127.0.0.1:{args.port}"
    print(f"ChinAI: {url}  (Ctrl-C to stop)")

    if not args.no_browser:
        # Give uvicorn a moment to bind before the browser asks for the page.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    # Loopback only, by design: Studio has no auth layer and must never
    # listen on a routable interface.
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def _cmd_app(args: argparse.Namespace) -> int:
    from chinai import desktop

    return desktop.run()


_HANDLERS = {
    "enroll": _cmd_enroll,
    "say": _cmd_say,
    "train": _cmd_train,
    "voices": _cmd_voices,
    "verify": _cmd_verify,
    "doctor": _cmd_doctor,
    "studio": _cmd_studio,
    "app": _cmd_app,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in _STORAGE_COMMANDS:
        migrated = migrate_legacy_home()
        if migrated:
            print(f"chinai: migrated existing voice data to {migrated}", file=sys.stderr)

    try:
        return _HANDLERS[args.command](args)
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        print(f"chinai: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # torch/audio backends raise their own types
        print(f"chinai: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
