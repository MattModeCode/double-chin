"""Delivery-parameter tuning: search the four knobs against real recordings.

`evalset` prepares the genuine-voice clips the gate scores against; `sweep`
runs the coordinate-descent search that picks the values Studio opens with.
"""

from double_chin.tuning.evalset import prepare_real_clips
from double_chin.tuning.sweep import (
    AXIS_GRID,
    BudgetExhausted,
    Ledger,
    SweepContext,
    SweepResult,
    coordinate_pass,
    noise_floor,
    run_sweep,
    score,
)

__all__ = [
    "AXIS_GRID",
    "BudgetExhausted",
    "Ledger",
    "SweepContext",
    "SweepResult",
    "coordinate_pass",
    "noise_floor",
    "prepare_real_clips",
    "run_sweep",
    "score",
]
