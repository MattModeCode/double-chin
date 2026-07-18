"""Aggregate indistinguishability gate.

Combines four signals into a single numeric verdict on how indistinguishable a
cloned voice is from the real voice:

1. speaker_similarity - mean real-vs-clone embedding cosine (the classic number).
2. discrimination     - can a speaker model separate real from clone? (1 = no).
3. naturalness        - signal-based naturalness proxy on the clones (not a MOS).
4. prosody            - pitch / rate / pause similarity between the two sets.

The components are combined with a **weighted geometric mean**, deliberately,
not a weighted average. A geometric mean lets any single weak component drag the
whole score down, which is the entire point of this gate: today's single-cosine
check can report a high score for output that is obviously synthetic. Here a
high timbre cosine can no longer paper over a robotic-monotone naturalness
score or an easily-separable embedding cluster — every component has to hold up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chinai.verification.audio import ANALYSIS_SR, as_paths, embed_clips, load_mono
from chinai.verification.naturalness import naturalness_proxy
from chinai.verification.prosody import prosody_features, prosody_similarity
from chinai.verification.speaker import speaker_discrimination

# --- component weights (must sum to 1.0) ------------------------------------
_WEIGHT_SPEAKER = 0.30
_WEIGHT_DISCRIMINATION = 0.25
_WEIGHT_NATURALNESS = 0.25
_WEIGHT_PROSODY = 0.20

# --- speaker-cosine -> [0, 1] mapping ---------------------------------------
# Anchored to verify.py's bands: at/below 0.60 (borderline floor) contributes
# nothing; a strong same-speaker match (~0.90) saturates near 1.0.
_COSINE_FLOOR = 0.60
_COSINE_CEIL = 0.90

# --- gate threshold + verdict bands (on the aggregate score) ----------------
# Rationale: the good, real clones in demo/quiz score ~0.90 here (see tests);
# an obviously-different / synthetic clip lands well below. 0.70 sits in the
# gap: it clears genuinely indistinguishable clones while rejecting anything
# with a collapsed component. It is a named, documented, honest cut — not a
# calibrated probability.
GATE_PASS_THRESHOLD = 0.70

_VERDICT_INDISTINGUISHABLE = 0.85
_VERDICT_NEAR = 0.70
_VERDICT_DISTINGUISHABLE = 0.55


def _cosine_to_unit(cosine: float) -> float:
    if _COSINE_CEIL <= _COSINE_FLOOR:
        return 0.0
    return max(0.0, min(1.0, (cosine - _COSINE_FLOOR) / (_COSINE_CEIL - _COSINE_FLOOR)))


def gate_verdict(score: float) -> str:
    """Honest verdict band for an aggregate indistinguishability score."""
    if score >= _VERDICT_INDISTINGUISHABLE:
        return "indistinguishable"
    if score >= _VERDICT_NEAR:
        return "near-indistinguishable"
    if score >= _VERDICT_DISTINGUISHABLE:
        return "distinguishable"
    return "clearly synthetic"


@dataclass(frozen=True)
class GateResult:
    """Structured result of the indistinguishability gate."""

    passed: bool
    score: float
    verdict: str
    components: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "verdict": self.verdict,
            "components": self.components,
        }


def _weighted_geometric_mean(values_and_weights) -> float:
    import math

    total = 0.0
    weight_sum = 0.0
    for value, weight in values_and_weights:
        total += weight * math.log(max(value, 1e-6))
        weight_sum += weight
    if weight_sum == 0:
        return 0.0
    return math.exp(total / weight_sum)


def indistinguishability_gate(real_clips, clone_clips, sr: int = ANALYSIS_SR) -> dict:
    """Run the full verification suite and return the aggregate gate result.

    Args:
        real_clips: a directory, a single wav path, or an iterable of wav paths
            for the genuine voice.
        clone_clips: the same, for the cloned/synthesized voice.
        sr: analysis sample rate for the signal-based metrics.

    Returns:
        A dict of the shape::

            {
              "passed": bool,
              "score": float,          # aggregate indistinguishability in [0, 1]
              "verdict": str,          # honest band label
              "components": {
                "speaker_similarity": {...},
                "discrimination": {...},
                "naturalness": {...},
                "prosody": {...},
              },
            }

    Raises:
        ValueError: if either side has no clips, or clips are silent.
    """
    real_paths = as_paths(real_clips)
    clone_paths = as_paths(clone_clips)
    if not real_paths or not clone_paths:
        raise ValueError("need at least one real clip and one clone clip.")

    # 1. Speaker discrimination (embeddings).
    real_embeddings = embed_clips(real_paths)
    clone_embeddings = embed_clips(clone_paths)
    speaker = speaker_discrimination(real_embeddings, clone_embeddings)
    speaker_component = _cosine_to_unit(speaker.mean_cross_cosine)

    # Load waveforms once for the signal-based metrics.
    real_waves = [load_mono(p, sr) for p in real_paths]
    clone_waves = [load_mono(p, sr) for p in clone_paths]

    # 2. Naturalness proxy (clones carry the gate; reals reported for context).
    clone_naturalness = [naturalness_proxy(w, sr) for w in clone_waves]
    real_naturalness = [naturalness_proxy(w, sr) for w in real_waves]
    naturalness_component = sum(n.score for n in clone_naturalness) / len(clone_naturalness)
    real_naturalness_mean = sum(n.score for n in real_naturalness) / len(real_naturalness)

    # 3. Prosody similarity.
    real_prosody = [prosody_features(w, sr) for w in real_waves]
    clone_prosody = [prosody_features(w, sr) for w in clone_waves]
    prosody = prosody_similarity(real_prosody, clone_prosody)

    # 4. Aggregate (weighted geometric mean).
    score = _weighted_geometric_mean(
        [
            (speaker_component, _WEIGHT_SPEAKER),
            (speaker.indistinguishability, _WEIGHT_DISCRIMINATION),
            (naturalness_component, _WEIGHT_NATURALNESS),
            (prosody.score, _WEIGHT_PROSODY),
        ]
    )
    passed = score >= GATE_PASS_THRESHOLD

    components = {
        "speaker_similarity": {
            "component": speaker_component,
            "weight": _WEIGHT_SPEAKER,
            "mean_cross_cosine": speaker.mean_cross_cosine,
            "centroid_cosine": speaker.centroid_cosine,
        },
        "discrimination": {
            "component": speaker.indistinguishability,
            "weight": _WEIGHT_DISCRIMINATION,
            "classifier_accuracy": speaker.classifier_accuracy,
            "separability": speaker.separability,
        },
        "naturalness": {
            "component": naturalness_component,
            "weight": _WEIGHT_NATURALNESS,
            "clone_mean": naturalness_component,
            "real_mean": real_naturalness_mean,
            "is_proxy": True,
            "note": "signal-based heuristic, not a calibrated MOS",
        },
        "prosody": {
            "component": prosody.score,
            "weight": _WEIGHT_PROSODY,
            "per_feature": prosody.per_feature,
        },
    }

    return GateResult(
        passed=passed,
        score=score,
        verdict=gate_verdict(score),
        components=components,
    ).as_dict()


def format_scorecard(result: dict) -> str:
    """Render a gate result dict as a readable multi-line scorecard."""
    lines: list[str] = []
    verdict = result["verdict"]
    status = "PASS" if result["passed"] else "FAIL"
    lines.append(f"Indistinguishability gate: {status}")
    lines.append(
        f"  score {result['score']:.3f}  (threshold {GATE_PASS_THRESHOLD:.2f})  "
        f"-> {verdict}"
    )
    lines.append("  components:")
    for name, data in result["components"].items():
        component = data["component"]
        weight = data["weight"]
        extra = ""
        if name == "speaker_similarity":
            extra = f"  mean cosine {data['mean_cross_cosine']:.3f}"
        elif name == "discrimination":
            extra = (
                f"  classifier acc {data['classifier_accuracy']:.2f} "
                f"(0.50 = chance)"
            )
        elif name == "naturalness":
            extra = "  [proxy, not MOS]"
        lines.append(
            f"    {name:<18} {component:.3f}  x{weight:.2f}{extra}"
        )
    return "\n".join(lines)
