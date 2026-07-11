"""Command-line interface for Myna."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from myna import __version__
from myna.config import myna_home
from myna.engine import DEFAULT_CFG_WEIGHT, DEFAULT_EXAGGERATION, DEFAULT_TEMPERATURE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="myna",
        description="Local voice-cloning CLI powered by Chatterbox TTS.",
    )
    parser.add_argument("--version", action="version", version=f"myna {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll_parser = subparsers.add_parser(
        "enroll", help="Enroll a voice from one or more reference recordings."
    )
    enroll_parser.add_argument("name", help="Voice name (lowercase letters, digits, '-', '_').")
    enroll_parser.add_argument(
        "sources", nargs="+", type=Path,
        help="Audio files (.wav/.flac/.mp3) or a directory containing them.",
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
        "-o", "--out", type=Path, default=Path("myna_out.wav"),
        help="Output wav path (default: ./myna_out.wav).",
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

    subparsers.add_parser("voices", help="List enrolled voices.")

    verify_parser = subparsers.add_parser(
        "verify", help="Compare speaker similarity between two wav files."
    )
    verify_parser.add_argument("ref", type=Path)
    verify_parser.add_argument("other", type=Path)

    subparsers.add_parser("doctor", help="Report environment diagnostics.")

    return parser


def _cmd_enroll(args: argparse.Namespace) -> int:
    from myna.voices import enroll

    info = enroll(args.name, args.sources)
    print(f"Enrolled voice '{info.name}': {info.duration_seconds:.1f}s reference audio.")
    print(f"Saved to {info.reference_wav}")
    return 0


def _cmd_say(args: argparse.Namespace) -> int:
    from myna.engine import MynaEngine
    from myna.verify import similarity, verdict
    from myna.voices import get_voice

    if args.script:
        if not args.script.is_file():
            raise ValueError(f"script file not found: {args.script}")
        script_text = args.script.read_text()
    else:
        script_text = args.text

    if args.voice:
        voice = get_voice(args.voice)
        reference_wav = voice.reference_wav
    else:
        reference_wav = args.ref
        if not reference_wav.is_file():
            raise ValueError(f"reference wav not found: {reference_wav}")

    engine = MynaEngine(device=args.device)
    report = engine.synthesize(
        script=script_text,
        reference_wav=reference_wav,
        out_path=args.out,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg,
        temperature=args.temperature,
        seed=args.seed,
    )

    print(
        f"Wrote {report.out_path} ({report.audio_seconds:.1f}s audio, "
        f"{report.chunk_count} chunks)"
    )
    print(
        f"Device: {report.device}; wall time {report.wall_seconds:.1f}s; "
        f"realtime factor {report.realtime_factor:.2f}x"
    )

    if args.verify:
        score = similarity(reference_wav, report.out_path)
        print(f"Speaker similarity: {score:.3f} ({verdict(score)})")

    return 0


def _cmd_voices(args: argparse.Namespace) -> int:
    from myna.voices import list_voices

    voices = list_voices()
    if not voices:
        print("No voices enrolled yet. Use 'myna enroll NAME SOURCE...' to add one.")
        return 0

    name_width = max(len("name"), *(len(v.name) for v in voices))
    print(f"{'name'.ljust(name_width)}  duration  created")
    for voice in voices:
        print(f"{voice.name.ljust(name_width)}  {voice.duration_seconds:6.1f}s  {voice.created}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from myna.verify import similarity, verdict

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
        import resemblyzer  # noqa: F401

        print("PASS resemblyzer: importable")
    except ImportError:
        print("WARN resemblyzer: not installed; 'myna verify' will fail")

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

    home = myna_home()
    print(f"PASS myna home: {home}")

    disk_check_path = home if home.exists() else Path.home()
    usage = shutil.disk_usage(disk_check_path)
    free_gb = usage.free / (1024 ** 3)
    print(f"PASS free disk: {free_gb:.1f} GB")

    return 0


_HANDLERS = {
    "enroll": _cmd_enroll,
    "say": _cmd_say,
    "voices": _cmd_voices,
    "verify": _cmd_verify,
    "doctor": _cmd_doctor,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _HANDLERS[args.command](args)
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        print(f"myna: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
