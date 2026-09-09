"""Coordinate-descent search over the four delivery knobs.

The question this answers is narrow: of the settings the Studio sliders can
express, which one makes synthesized takes least distinguishable from the
owner's real recordings? Scoring is the existing
`verification.gate.indistinguishability_gate` — no new metric is invented here.
What the search *ranks* on is separate and pluggable (`SweepContext.objective`),
because a gate component can be saturated in this setting and then contributes
no ordering; the full gate result is recorded for every candidate either way.

Three properties matter more than the search itself:

* **Repeats.** Generation is stochastic, so one take per candidate measures
  luck. Each candidate is scored from `takes` clips at once, which is also how
  the gate wants its input (it measures set separability, not clip pairs).
* **A noise floor.** Before searching, the starting profile is re-measured
  several times with different seeds. A candidate only counts as better if it
  beats the baseline by more than that spread.
* **Resumability.** Every measurement is appended to a JSONL ledger keyed by
  (profile, script, variant), so an interrupted two-hour run continues instead
  of restarting, and a re-run costs nothing.
"""

from __future__ import annotations

import json
import statistics
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from double_chin.delivery import DeliveryProfile

# Coarse grid per axis: four values spanning the useful part of each range,
# with the neutral default among them so the baseline measurement is reused
# rather than repeated. Values sit on the studio's 0.05 slider step so a winner
# can be dialled in by hand, and stay inside the API's bounds. Four rather than
# more is a cost decision: a candidate costs three syntheses plus a gate run
# (~5 min on this machine), and `refine` walks the winner in 0.05 steps
# afterwards, which is where the last bit of resolution comes from.
AXIS_GRID: dict[str, tuple[float, ...]] = {
    "cfg_weight": (0.35, 0.50, 0.65, 0.80),
    "exaggeration": (0.25, 0.40, 0.50, 0.65),
    "temperature": (0.50, 0.65, 0.80, 0.95),
    "rate": (0.95, 1.00, 1.05, 1.10),
}

# Adherence first: it moves similarity most, so the later axes are searched
# from a sensible place rather than from an obviously wrong one.
AXIS_ORDER = ("cfg_weight", "exaggeration", "temperature", "rate")

SLIDER_STEP = 0.05
DEFAULT_TAKES = 3
DEFAULT_NOISE_REPEATS = 3


class BudgetExhausted(RuntimeError):
    """Raised when a sweep has used its allowance of syntheses."""


class Ledger:
    """Append-only JSONL record of every measurement, keyed for resume."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, dict] = {}
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a half-written final line from a killed run
            if "key" in entry:
                self._entries[entry["key"]] = entry

    @staticmethod
    def key(profile: DeliveryProfile, script_id: str, variant: int) -> str:
        values = profile.as_dict()
        knobs = "-".join(f"{name[0]}{values[name]:g}" for name in sorted(values))
        return f"{knobs}|{script_id}|v{variant}"

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def record(self, entry: dict) -> None:
        self._entries[entry["key"]] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")

    @property
    def entries(self) -> list[dict]:
        return list(self._entries.values())

    @property
    def synthesis_count(self) -> int:
        """How many clips have been synthesized across every recorded run."""
        return sum(entry.get("takes", 0) for entry in self._entries.values())


@dataclass
class SweepContext:
    """Everything a sweep needs: how to synthesize, how to score, and where."""

    synth: Callable[[DeliveryProfile, str, Path, int], Any]
    gate: Callable[[list[Path], list[Path]], dict]
    real_clips: list[Path]
    scripts: dict[str, str]
    work_dir: Path
    ledger: Ledger
    takes: int = DEFAULT_TAKES
    budget: int | None = None
    on_event: Callable[[str, dict], None] | None = None
    # What the search maximizes, given a ledger entry. Defaults to the gate's
    # own composite; supply one when a component of that composite is
    # saturated and therefore carries no ranking signal (see runner.py).
    objective: Callable[[dict], float] | None = None
    objective_name: str = "gate composite"

    def value(self, entry: dict) -> float:
        """The number the search compares candidates on."""
        return self.objective(entry) if self.objective is not None else entry["score"]

    def emit(self, kind: str, data: dict) -> None:
        if self.on_event is not None:
            self.on_event(kind, data)


@dataclass
class SweepResult:
    """The outcome of a sweep, honest about whether the win is real."""

    best: DeliveryProfile
    best_score: float
    best_components: dict
    baseline: DeliveryProfile
    baseline_score: float
    noise_floor: dict
    script_id: str
    synthesis_count: int
    budget_exhausted: bool = False
    history: list[dict] = field(default_factory=list)
    objective_name: str = "gate composite"
    # The full gate composite at the winner, kept alongside the objective so a
    # report can state both rather than only the number that was optimized.
    best_gate_score: float = 0.0

    @property
    def margin(self) -> float:
        return self.best_score - self.baseline_score

    @property
    def beats_noise(self) -> bool:
        """True only if the gain exceeds the baseline's own run-to-run spread."""
        return self.margin > self.noise_floor.get("sd", 0.0)


def _seed_for(key: str, take: int) -> int:
    """A stable per-take seed, so a resumed or repeated run reproduces."""
    return zlib.crc32(f"{key}#{take}".encode()) % (2**31)


def _take_dir(ctx: SweepContext, key: str) -> Path:
    return Path(ctx.work_dir) / key.replace("|", "_")


def score(
    ctx: SweepContext,
    profile: DeliveryProfile,
    script_id: str,
    variant: int = 0,
) -> dict:
    """Score one candidate: synthesize `ctx.takes` clips and run the gate.

    Cached by (profile, script, variant) through the ledger, so re-asking for
    a measurement already on disk costs nothing.

    Raises:
        BudgetExhausted: if the sweep has already used its synthesis budget.
        ValueError: if `script_id` is not in `ctx.scripts`.
    """
    if script_id not in ctx.scripts:
        raise ValueError(f"unknown script '{script_id}'")

    key = Ledger.key(profile, script_id, variant)
    cached = ctx.ledger.get(key)
    if cached is not None:
        return cached

    if ctx.budget is not None and ctx.ledger.synthesis_count >= ctx.budget:
        raise BudgetExhausted(
            f"synthesis budget of {ctx.budget} reached before scoring {key}"
        )

    ctx.emit("candidate", {"key": key, "profile": profile.as_dict()})
    out_dir = _take_dir(ctx, key)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "profile.json").write_text(
        json.dumps({"profile": profile.as_dict(), "variant": variant}, indent=2)
    )

    clone_clips: list[Path] = []
    for take in range(ctx.takes):
        out_path = out_dir / f"take-{take + 1}.wav"
        ctx.synth(profile, ctx.scripts[script_id], out_path, _seed_for(key, take))
        clone_clips.append(out_path)

    gate_result = ctx.gate(list(ctx.real_clips), clone_clips)
    entry = {
        "key": key,
        "profile": profile.as_dict(),
        "script_id": script_id,
        "variant": variant,
        "takes": ctx.takes,
        "score": gate_result["score"],
        "verdict": gate_result.get("verdict"),
        "components": {
            name: data["component"]
            for name, data in gate_result.get("components", {}).items()
        },
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    ctx.ledger.record(entry)
    ctx.emit("scored", entry)
    return entry


def noise_floor(
    ctx: SweepContext,
    profile: DeliveryProfile,
    script_id: str,
    repeats: int = DEFAULT_NOISE_REPEATS,
) -> dict:
    """Measure the same profile `repeats` times to size run-to-run variation."""
    scores = [
        ctx.value(score(ctx, profile, script_id, variant=variant))
        for variant in range(repeats)
    ]
    return {
        "scores": scores,
        "mean": statistics.fmean(scores),
        "sd": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "repeats": repeats,
    }


def _with(profile: DeliveryProfile, name: str, value: float) -> DeliveryProfile:
    return DeliveryProfile.from_mapping(profile.as_dict() | {name: value})


def coordinate_pass(
    ctx: SweepContext,
    start: DeliveryProfile,
    script_id: str,
    axes: tuple[str, ...] = AXIS_ORDER,
) -> tuple[DeliveryProfile, list[dict]]:
    """Walk each axis in turn, keeping the best value found before moving on."""
    best = start
    best_score = ctx.value(score(ctx, best, script_id))
    history: list[dict] = []

    for axis in axes:
        for value in AXIS_GRID[axis]:
            candidate = _with(best, axis, value)
            entry = score(ctx, candidate, script_id)
            history.append(entry)
            if ctx.value(entry) > best_score:
                best, best_score = candidate, ctx.value(entry)

    return best, history


def refine(
    ctx: SweepContext,
    start: DeliveryProfile,
    script_id: str,
    axes: tuple[str, ...] = AXIS_ORDER,
) -> tuple[DeliveryProfile, list[dict]]:
    """Try one slider step either side of the winner on each axis."""
    best = start
    best_score = ctx.value(score(ctx, best, script_id))
    history: list[dict] = []

    for axis in axes:
        current = getattr(best, axis)
        for value in (current - SLIDER_STEP, current + SLIDER_STEP):
            value = round(value, 2)
            try:
                candidate = _with(best, axis, value)
            except ValueError:
                continue  # stepped outside the knob's range
            entry = score(ctx, candidate, script_id)
            history.append(entry)
            if ctx.value(entry) > best_score:
                best, best_score = candidate, ctx.value(entry)

    return best, history


def run_sweep(
    ctx: SweepContext,
    start: DeliveryProfile,
    script_id: str,
    passes: int = 2,
    noise_repeats: int = DEFAULT_NOISE_REPEATS,
) -> SweepResult:
    """Run the full search: noise floor, coordinate passes, then refinement.

    Stops early and returns the best profile found so far if the synthesis
    budget runs out, so a capped run still produces a usable answer.

    Raises:
        ValueError: if `script_id` is not one of `ctx.scripts`.
    """
    if script_id not in ctx.scripts:
        raise ValueError(f"unknown script '{script_id}'")

    exhausted = False
    history: list[dict] = []
    best = start
    best_score = 0.0
    floor: dict = {"scores": [], "mean": 0.0, "sd": 0.0, "repeats": 0}

    try:
        floor = noise_floor(ctx, start, script_id, repeats=noise_repeats)

        for _ in range(passes):
            previous = best
            best, pass_history = coordinate_pass(ctx, best, script_id)
            history.extend(pass_history)
            if best == previous:
                break  # a whole pass moved nothing; further passes cannot either

        best, refine_history = refine(ctx, best, script_id)
        history.extend(refine_history)
    except BudgetExhausted:
        exhausted = True

    best_entry = ctx.ledger.get(Ledger.key(best, script_id, 0))
    if best_entry is not None:
        best_score = ctx.value(best_entry)

    return SweepResult(
        best=best,
        best_score=best_score,
        best_components=(best_entry or {}).get("components", {}),
        baseline=start,
        baseline_score=floor["mean"],
        noise_floor=floor,
        script_id=script_id,
        synthesis_count=ctx.ledger.synthesis_count,
        budget_exhausted=exhausted,
        history=history,
        objective_name=ctx.objective_name,
        best_gate_score=(best_entry or {}).get("score", 0.0),
    )
