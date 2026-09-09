"""Wire the real engine and gate into a sweep, and report what it found.

`sweep.py` knows nothing about Chatterbox or Resemblyzer — it takes a
synthesize callable and a gate callable. This module supplies the real ones,
picks which genuine recordings to score against, and renders the result as a
scorecard a person can read.
"""

from __future__ import annotations

from pathlib import Path

from double_chin.delivery import DeliveryProfile
from double_chin.tuning.evalset import prepare_real_clips
from double_chin.tuning.sweep import Ledger, SweepContext, SweepResult

_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a"}

# Components the delivery knobs can actually move, with the gate's own weights.
# `discrimination` is deliberately absent: with several real clips against three
# clone clips the classifier separates the sets outright, so that component sits
# at 0.0 for every candidate. Left in, it multiplies every score by the same
# near-zero constant — it cannot order candidates, it just makes the number
# unreadable. The full gate composite is still recorded and reported.
_OBJECTIVE_WEIGHTS = {
    "speaker_similarity": 0.30,
    "naturalness": 0.25,
    "prosody": 0.20,
}
OBJECTIVE_NAME = "speaker+naturalness+prosody (gate weights, discrimination excluded)"


def delivery_objective(entry: dict) -> float:
    """Rank candidates on the gate components that respond to delivery.

    Weighted geometric mean, matching how the gate itself combines components:
    one weak component drags the result down rather than being averaged away.
    """
    import math

    components = entry.get("components", {})
    total = weight_sum = 0.0
    for name, weight in _OBJECTIVE_WEIGHTS.items():
        if name not in components:
            continue
        total += weight * math.log(max(components[name], 1e-6))
        weight_sum += weight
    return math.exp(total / weight_sum) if weight_sum else 0.0


# The first few recordings are what `reference.wav` is built from (it caps at
# 20 s), so scoring against them would compare the clone to its own
# conditioning audio. Start well past them.
DEFAULT_SKIP = 10
DEFAULT_TUNING_CLIPS = 8
DEFAULT_HOLDOUT_CLIPS = 6


def list_recordings(real_dir: Path) -> list[Path]:
    """Every audio file in `real_dir`, sorted by name.

    Raises:
        ValueError: if the directory is missing or holds no audio.
    """
    real_dir = Path(real_dir)
    if not real_dir.is_dir():
        raise ValueError(f"recordings directory not found: {real_dir}")
    found = sorted(
        path
        for path in real_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    )
    if not found:
        raise ValueError(f"no audio files in {real_dir}")
    return found


def select_real_clips(
    recordings: list[Path],
    tuning_count: int = DEFAULT_TUNING_CLIPS,
    holdout_count: int = DEFAULT_HOLDOUT_CLIPS,
    skip: int = DEFAULT_SKIP,
) -> tuple[list[Path], list[Path]]:
    """Split recordings into disjoint tuning and holdout sets.

    Both sets are spread evenly across the corpus rather than taken as blocks,
    so neither is dominated by one recording session, and they never overlap.

    Raises:
        ValueError: if there are not enough recordings for both sets.
    """
    pool = recordings[skip:]
    needed = tuning_count + holdout_count
    if len(pool) < needed:
        raise ValueError(
            f"need {needed} recordings after skipping {skip}, found {len(pool)}"
        )

    stride = len(pool) // needed
    picked = [pool[index * stride] for index in range(needed)]
    return picked[:tuning_count], picked[tuning_count:]


def build_context(
    voice,
    real_clips: list[Path],
    scripts: dict[str, str],
    work_dir: Path,
    takes: int,
    budget: int | None = None,
    device: str | None = None,
    on_event=None,
) -> SweepContext:
    """A sweep context backed by the real engine and the real gate."""
    from double_chin.engine import DoubleChinEngine
    from double_chin.verification import indistinguishability_gate

    engine = DoubleChinEngine(device=device)
    lora_path = voice.lora_path

    def synth(profile: DeliveryProfile, script: str, out_path: Path, seed: int):
        return engine.synthesize(
            script=script,
            reference_wav=voice.reference_wav,
            out_path=out_path,
            seed=seed,
            lora_path=lora_path,
            **profile.as_dict(),
        )

    def gate(real, clone):
        return indistinguishability_gate(real, clone)

    work_dir = Path(work_dir)
    return SweepContext(
        synth=synth,
        gate=gate,
        real_clips=real_clips,
        scripts=scripts,
        work_dir=work_dir / "takes",
        ledger=Ledger(work_dir / "ledger.jsonl"),
        takes=takes,
        budget=budget,
        on_event=on_event,
        objective=delivery_objective,
        objective_name=OBJECTIVE_NAME,
    )


def prepare_sets(real_dir: Path, work_dir: Path, **selection) -> tuple[list, list]:
    """Normalize the chosen recordings into wav sets the gate can read."""
    tuning_sources, holdout_sources = select_real_clips(
        list_recordings(real_dir), **selection
    )
    work_dir = Path(work_dir)
    return (
        prepare_real_clips(tuning_sources, work_dir / "real", prefix="tuning"),
        prepare_real_clips(holdout_sources, work_dir / "real", prefix="holdout"),
    )


def _knob_line(name: str, tuned: float, baseline: float) -> str:
    suffix = "x" if name == "rate" else ""
    delta = tuned - baseline
    move = "unchanged" if abs(delta) < 1e-9 else f"{delta:+.2f}"
    return f"  {name:<13} {tuned:.2f}{suffix:<2} (was {baseline:.2f}{suffix}, {move})"


def format_report(result: SweepResult, holdout: dict | None = None) -> str:
    """Render a sweep result as a readable scorecard.

    Deliberately states the noise floor and refuses to call a win a win when
    the margin sits inside it.
    """
    lines = [
        f"Delivery sweep on script '{result.script_id}'",
        f"  ranked on: {result.objective_name}",
        f"  {result.synthesis_count} clips synthesized"
        + ("  (budget exhausted)" if result.budget_exhausted else ""),
        "",
        "Winning profile:",
    ]
    baseline_values = result.baseline.as_dict()
    for name, value in result.best.as_dict().items():
        lines.append(_knob_line(name, value, baseline_values[name]))

    floor = result.noise_floor
    lines += [
        "",
        f"  score      {result.best_score:.3f}   (baseline {result.baseline_score:.3f}, "
        f"{result.margin:+.3f})",
        f"  noise floor sd {floor.get('sd', 0.0):.3f} over {floor.get('repeats', 0)} "
        "repeats of the baseline",
        f"  full gate composite at the winner: {result.best_gate_score:.3f}",
    ]
    if result.beats_noise:
        lines.append("  the gain clears the noise floor")
    else:
        lines.append(
            "  the gain does NOT clear the noise floor — treat this as a tie "
            "and keep the baseline"
        )

    if result.best_components:
        lines.append("")
        lines.append("Components at the winner:")
        for name, value in result.best_components.items():
            lines.append(f"  {name:<18} {value:.3f}")

    if holdout is not None:
        lines += [
            "",
            f"Held-out script: winner {holdout['best']:.3f} vs baseline "
            f"{holdout['baseline']:.3f} ({holdout['best'] - holdout['baseline']:+.3f})",
            (
                "  holds up on unseen text"
                if holdout["best"] > holdout["baseline"]
                else "  does NOT hold up on unseen text — likely overfit to the "
                "tuning script"
            ),
        ]

    return "\n".join(lines)
