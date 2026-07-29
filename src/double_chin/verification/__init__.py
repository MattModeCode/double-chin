"""Double Chin indistinguishability verification suite.

A free, local, offline-capable set of metrics that score how indistinguishable a
cloned voice is from the real voice, combined into one numeric gate. This
extends the single-cosine check in `double_chin.verify` (whose `similarity` /
`verdict` API is unchanged) rather than replacing it.

Public API:
    indistinguishability_gate(real_clips, clone_clips) -> dict
    format_scorecard(result) -> str
    gate_verdict(score) -> str
    GATE_PASS_THRESHOLD

Lower-level metrics (speaker discrimination, naturalness proxy, prosody
similarity) are available from the submodules for direct/unit use.
"""

from __future__ import annotations

from double_chin.verification.gate import (
    GATE_PASS_THRESHOLD,
    GateResult,
    format_scorecard,
    gate_verdict,
    indistinguishability_gate,
)
from double_chin.verification.naturalness import Naturalness, naturalness_proxy
from double_chin.verification.prosody import (
    ProsodyFeatures,
    ProsodySimilarity,
    prosody_features,
    prosody_similarity,
)
from double_chin.verification.speaker import SpeakerDiscrimination, speaker_discrimination

__all__ = [
    "GATE_PASS_THRESHOLD",
    "GateResult",
    "Naturalness",
    "ProsodyFeatures",
    "ProsodySimilarity",
    "SpeakerDiscrimination",
    "format_scorecard",
    "gate_verdict",
    "indistinguishability_gate",
    "naturalness_proxy",
    "prosody_features",
    "prosody_similarity",
    "speaker_discrimination",
]
