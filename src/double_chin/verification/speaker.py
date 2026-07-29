"""Speaker-verification discrimination metric.

Frames the question a speaker-verification model would ask: *can it tell the
real clips from the clone clips above chance?* We reduce that to a
leave-one-out nearest-centroid classification over Resemblyzer embeddings.

- If a clone sits inside the real speaker's embedding cloud, a classifier does
  no better than a coin flip (accuracy ~= 0.5) -> the clone is
  indistinguishable.
- If clones form their own cluster, the classifier separates them cleanly
  (accuracy -> 1.0) -> the clone is distinguishable.

We report the raw mean cross cosine (the classic single number) alongside a
separability score, so the richer signal sits next to the old one rather than
replacing it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Below this margin, the two centroid similarities are treated as a tie
# (classifier can't decide) and scored as half-credit, i.e. chance. Keeps
# identical real/clone sets at accuracy 0.5 -> separability 0.
_TIE_MARGIN = 1e-9


@dataclass(frozen=True)
class SpeakerDiscrimination:
    """Result of the speaker-discrimination metric.

    Attributes:
        mean_cross_cosine: mean cosine over all (real_i, clone_j) pairs — the
            classic timbre-match number, higher = more similar.
        centroid_cosine: cosine between the real and clone embedding centroids.
        classifier_accuracy: leave-one-out nearest-centroid accuracy in [0, 1];
            0.5 = chance (can't tell them apart).
        separability: clamp(2 * (accuracy - 0.5), 0, 1); 0 = indistinguishable,
            1 = trivially separable.
        indistinguishability: 1 - separability; the component the gate consumes.
    """

    mean_cross_cosine: float
    centroid_cosine: float
    classifier_accuracy: float
    separability: float
    indistinguishability: float


def _centroid(embeddings):
    import numpy as np

    mean = np.mean(np.asarray(embeddings), axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0:
        return mean
    return mean / norm


def _loo_accuracy(reals, clones) -> float:
    """Leave-one-out nearest-centroid accuracy over the two labelled sets.

    Each clip is classified against the centroid of its own class (computed
    with that clip held out) versus the centroid of the other class. Ties count
    as half-credit (chance).
    """
    import numpy as np

    correct = 0.0
    total = 0
    for own, other in ((reals, clones), (clones, reals)):
        other_centroid = _centroid(other)
        for i, clip in enumerate(own):
            rest = [own[j] for j in range(len(own)) if j != i]
            # With a single clip in a class there is no held-out centroid; fall
            # back to the clip itself so the comparison stays defined.
            own_centroid = _centroid(rest) if rest else _centroid([clip])
            to_own = float(np.dot(clip, own_centroid))
            to_other = float(np.dot(clip, other_centroid))
            if abs(to_own - to_other) < _TIE_MARGIN:
                correct += 0.5
            elif to_own > to_other:
                correct += 1.0
            total += 1
    return correct / total if total else 0.5


def speaker_discrimination(real_embeddings, clone_embeddings) -> SpeakerDiscrimination:
    """Score how separable the clone embeddings are from the real embeddings.

    Args:
        real_embeddings: list of L2-normalized real-clip embeddings.
        clone_embeddings: list of L2-normalized clone-clip embeddings.

    Raises:
        ValueError: if either set is empty.
    """
    import numpy as np

    if not real_embeddings or not clone_embeddings:
        raise ValueError("need at least one real and one clone embedding.")

    reals = [np.asarray(e) for e in real_embeddings]
    clones = [np.asarray(e) for e in clone_embeddings]

    cross = [float(np.dot(r, c)) for r in reals for c in clones]
    mean_cross = float(np.mean(cross))

    centroid_cos = float(np.dot(_centroid(reals), _centroid(clones)))

    accuracy = _loo_accuracy(reals, clones)
    separability = max(0.0, min(1.0, 2.0 * (accuracy - 0.5)))

    return SpeakerDiscrimination(
        mean_cross_cosine=mean_cross,
        centroid_cosine=centroid_cos,
        classifier_accuracy=accuracy,
        separability=separability,
        indistinguishability=1.0 - separability,
    )
