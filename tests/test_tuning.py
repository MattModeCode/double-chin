"""Offline tests for the delivery-parameter sweep.

The search is exercised against a stub synthesizer and a stub gate whose
optimum is known, so the coordinate descent, the ledger, the noise floor and
the budget cap are all tested without loading a model.
"""

from __future__ import annotations

import json

import pytest

from double_chin.delivery import NEUTRAL_PROFILE, DeliveryProfile
from double_chin.tuning import sweep as sweeplib

# Every value is a point on AXIS_GRID, so the search can actually reach it.
TARGET = DeliveryProfile(exaggeration=0.40, cfg_weight=0.65, temperature=0.65, rate=1.05)


class StubRig:
    """A synthesizer/gate pair whose score peaks at TARGET.

    Score falls off with distance from TARGET, so the coordinate descent has a
    single obvious optimum on the grid. `variant` perturbs the score slightly,
    standing in for the real engine's run-to-run randomness.
    """

    def __init__(self) -> None:
        self.syntheses = 0
        self.gate_calls = 0

    def synth(self, profile, script, out_path, seed):
        self.syntheses += 1
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake wav")

    def gate(self, real_clips, clone_clips):
        self.gate_calls += 1
        profile, variant = self._decode(clone_clips)
        distance = sum(
            abs(getattr(profile, name) - getattr(TARGET, name))
            for name in ("exaggeration", "cfg_weight", "temperature", "rate")
        )
        score = max(0.0, 0.9 - distance) + 0.001 * variant
        return {
            "passed": score >= 0.7,
            "score": score,
            "verdict": "near-indistinguishable",
            "components": {
                "speaker_similarity": {"component": score, "weight": 0.3},
                "discrimination": {"component": score, "weight": 0.25},
                "naturalness": {"component": score, "weight": 0.25},
                "prosody": {"component": score, "weight": 0.2},
            },
        }

    @staticmethod
    def _decode(clone_clips):
        """Recover the profile under test from the take directory."""
        meta = json.loads((clone_clips[0].parent / "profile.json").read_text())
        return DeliveryProfile.from_mapping(meta["profile"]), meta["variant"]


@pytest.fixture
def ctx(tmp_path):
    rig = StubRig()
    context = sweeplib.SweepContext(
        synth=rig.synth,
        gate=rig.gate,
        real_clips=[tmp_path / "real.wav"],
        scripts={"a": "a short line of script", "b": "a second, held-out line"},
        work_dir=tmp_path / "work",
        ledger=sweeplib.Ledger(tmp_path / "ledger.jsonl"),
        takes=2,
    )
    context.rig = rig
    return context


def test_score_writes_takes_and_records_the_result(ctx):
    result = sweeplib.score(ctx, TARGET, "a")

    assert result["score"] == pytest.approx(0.9)
    assert ctx.rig.syntheses == 2
    # The ledger keeps components flattened to one number each.
    assert result["components"]["prosody"] == pytest.approx(0.9)
    assert ctx.ledger.synthesis_count == 2


def test_score_is_cached_by_profile_script_and_variant(ctx):
    sweeplib.score(ctx, TARGET, "a")
    sweeplib.score(ctx, TARGET, "a")
    assert ctx.rig.syntheses == 2  # second call served from the ledger

    sweeplib.score(ctx, TARGET, "b")
    assert ctx.rig.syntheses == 4  # a different script is a different measurement

    sweeplib.score(ctx, TARGET, "a", variant=1)
    assert ctx.rig.syntheses == 6  # a different variant is a fresh sample


def test_ledger_resumes_from_disk(ctx, tmp_path):
    sweeplib.score(ctx, TARGET, "a")

    resumed = sweeplib.SweepContext(
        synth=ctx.synth,
        gate=ctx.gate,
        real_clips=ctx.real_clips,
        scripts=ctx.scripts,
        work_dir=ctx.work_dir,
        ledger=sweeplib.Ledger(tmp_path / "ledger.jsonl"),
        takes=2,
    )
    before = ctx.rig.syntheses
    result = sweeplib.score(resumed, TARGET, "a")

    assert ctx.rig.syntheses == before  # nothing re-synthesized
    assert result["score"] == pytest.approx(0.9)


def test_noise_floor_samples_distinct_variants(ctx):
    floor = sweeplib.noise_floor(ctx, NEUTRAL_PROFILE, "a", repeats=3)

    assert len(floor["scores"]) == 3
    assert floor["sd"] > 0  # the variants really did differ
    assert floor["mean"] == pytest.approx(sum(floor["scores"]) / 3)


def test_coordinate_pass_moves_each_axis_to_its_best_grid_value(ctx):
    best, _ = sweeplib.coordinate_pass(ctx, NEUTRAL_PROFILE, "a")

    assert best.exaggeration == pytest.approx(0.40)
    assert best.cfg_weight == pytest.approx(0.65)
    assert best.temperature == pytest.approx(0.65)
    assert best.rate == pytest.approx(1.05)


def test_run_sweep_finds_the_optimum_and_reports_the_noise_floor(ctx):
    result = sweeplib.run_sweep(ctx, start=NEUTRAL_PROFILE, script_id="a", passes=2)

    assert result.best == TARGET
    assert result.best_score > result.baseline_score
    assert result.noise_floor["sd"] >= 0
    assert result.beats_noise is True
    assert result.synthesis_count == ctx.ledger.synthesis_count


def test_run_sweep_stops_at_the_budget_and_returns_the_best_so_far(ctx):
    ctx.budget = 6
    result = sweeplib.run_sweep(ctx, start=NEUTRAL_PROFILE, script_id="a", passes=2)

    assert result.budget_exhausted is True
    assert ctx.rig.syntheses <= 8  # the in-flight candidate may finish
    assert isinstance(result.best, DeliveryProfile)


def test_run_sweep_refuses_an_unknown_script(ctx):
    with pytest.raises(ValueError, match="unknown script"):
        sweeplib.run_sweep(ctx, start=NEUTRAL_PROFILE, script_id="nope")


def test_grid_values_sit_on_the_slider_step():
    for name, values in sweeplib.AXIS_GRID.items():
        for value in values:
            steps = value / 0.05
            assert abs(steps - round(steps)) < 1e-6, f"{name}={value} is off-grid"


def test_grid_values_are_inside_the_profile_bounds():
    for name, values in sweeplib.AXIS_GRID.items():
        for value in values:
            profile = DeliveryProfile.from_mapping(
                NEUTRAL_PROFILE.as_dict() | {name: value}
            )
            assert getattr(profile, name) == value


def test_prepare_real_clips_normalizes_into_wavs(tmp_path):
    import torch
    import torchaudio

    from double_chin.config import SAMPLE_RATE
    from double_chin.tuning import evalset

    source = tmp_path / "source.wav"
    tone = torch.sin(torch.linspace(0, 400, 16000)).reshape(1, -1) * 0.05
    torchaudio.save(str(source), torch.cat([tone, tone], dim=0), 8000)

    out = evalset.prepare_real_clips([source], tmp_path / "real")

    assert len(out) == 1
    wav, sr = torchaudio.load(str(out[0]))
    assert sr == SAMPLE_RATE
    assert wav.shape[0] == 1  # collapsed to mono
    assert wav.abs().max() == pytest.approx(0.9, abs=0.01)  # peak-normalized


def test_prepare_real_clips_rejects_an_empty_selection(tmp_path):
    from double_chin.tuning import evalset

    with pytest.raises(ValueError, match="no source clips"):
        evalset.prepare_real_clips([], tmp_path / "real")


def test_search_follows_a_supplied_objective_not_the_raw_gate_score(ctx):
    """A saturated gate component must not decide the ranking.

    Here the raw score peaks at TARGET, but the objective is built to peak at
    the neutral profile instead; the search must follow the objective.
    """
    ctx.objective = lambda entry: 1.0 - abs(entry["profile"]["cfg_weight"] - 0.35)
    ctx.objective_name = "cfg-only stub"

    best, _ = sweeplib.coordinate_pass(ctx, NEUTRAL_PROFILE, "a", axes=("cfg_weight",))

    assert best.cfg_weight == pytest.approx(0.35)


def test_delivery_objective_ignores_the_saturated_discrimination_component():
    from double_chin.tuning.runner import delivery_objective

    collapsed = {
        "components": {
            "speaker_similarity": 0.64,
            "discrimination": 0.0,
            "naturalness": 1.0,
            "prosody": 0.77,
        }
    }
    better_prosody = {
        "components": dict(collapsed["components"], prosody=0.85)
    }

    assert delivery_objective(collapsed) > 0.5  # readable, not collapsed to ~0
    assert delivery_objective(better_prosody) > delivery_objective(collapsed)
