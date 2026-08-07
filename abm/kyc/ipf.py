"""Iterative proportional fitting for joint tables with evidenced margins.

The problem this solves comes up everywhere in Phase 6. Sources publish
*margins* — 33.4% of adults are wage workers, each income quintile holds 20% of
people — but almost never the *joint*: how many wage workers are in the top
quintile. Two bad options present themselves:

1. Treat the dimensions as independent. Cheap, and produces a population where
   an employer is as likely to be poor as a family worker is to be rich.
2. Write the joint table by hand. Produces plausible-looking numbers whose
   margins no longer match any published statistic.

IPF gives a third: start from a seed matrix that encodes only the *shape* of the
association, then scale rows and columns alternately until the margins match the
published ones exactly. The evidence constrains the margins, the assumption
supplies the association, and the two stay separable — which means the
assumption can be varied in a sensitivity test without disturbing the evidence.

The seed is where the assumption lives, so `ordinal_seed` takes the association
strength as an explicit parameter rather than hiding a constant.
"""

from __future__ import annotations

import numpy as np

DEFAULT_TOLERANCE = 1e-10
DEFAULT_MAX_ITERATIONS = 2000


def fit(
    seed: np.ndarray,
    margins: list[np.ndarray],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> np.ndarray:
    """Scale `seed` until each axis matches its target margin.

    `margins[axis]` is the desired sum along that axis. All margins must sum to
    the same total, since they describe the same population counted different
    ways — a mismatch means the inputs disagree, and continuing would silently
    honour whichever axis was fitted last.
    """
    if seed.ndim != len(margins):
        raise ValueError(f"seed has {seed.ndim} axes but {len(margins)} margins were given")

    totals = [float(margin.sum()) for margin in margins]
    if max(totals) - min(totals) > 1e-6 * max(totals):
        raise ValueError(f"margins describe different totals: {totals}")

    table = np.array(seed, dtype=float)
    if table.min() < 0:
        raise ValueError("seed must be non-negative")
    table = np.clip(table, 1e-300, None)

    for _ in range(max_iterations):
        largest_gap = 0.0
        for axis, target in enumerate(margins):
            current = table.sum(axis=tuple(i for i in range(table.ndim) if i != axis))
            scale = np.divide(target, current, out=np.ones_like(target), where=current > 0)
            shape = [1] * table.ndim
            shape[axis] = -1
            table = table * scale.reshape(shape)
            largest_gap = max(largest_gap, float(np.abs(current - target).max()))
        if largest_gap < tolerance:
            break
    return table


def ordinal_seed(ranks: list[np.ndarray], strength: float) -> np.ndarray:
    """Seed matrix for an ordinal association of a stated strength.

    Each axis carries a rank vector saying where its categories sit on a shared
    ordering — for income, poorest to richest; for employment, least to most
    economically secure. The seed is `exp(strength * outer product of
    standardized ranks)`, so categories that rank high on two axes are drawn
    together more often.

    `strength` is the assumption, in one number:

    - 0.0 reproduces independence exactly, which is the honest null;
    - 0.5 gives a moderate association;
    - above about 1.5 the joint becomes nearly deterministic.

    Ranks are standardized so that `strength` means the same thing regardless of
    how many categories an axis has.
    """
    standardized = []
    for rank in ranks:
        values = np.asarray(rank, dtype=float)
        spread = values.std()
        standardized.append((values - values.mean()) / spread if spread > 0 else values * 0.0)

    exponent = np.zeros([len(rank) for rank in standardized])
    for axis, values in enumerate(standardized):
        shape = [1] * len(standardized)
        shape[axis] = -1
        exponent = exponent + values.reshape(shape)

    # The product of standardized ranks is what creates association; summing then
    # squaring would also couple an axis to itself, so build pairwise products.
    interaction = np.zeros_like(exponent)
    for first in range(len(standardized)):
        for second in range(first + 1, len(standardized)):
            shape_first = [1] * len(standardized)
            shape_first[first] = -1
            shape_second = [1] * len(standardized)
            shape_second[second] = -1
            interaction = interaction + (
                standardized[first].reshape(shape_first) * standardized[second].reshape(shape_second)
            )
    return np.exp(strength * interaction)


def joint_from_margins(
    margins: dict[str, dict[str, float]],
    ranks: dict[str, dict[str, float]],
    strength: float,
) -> tuple[np.ndarray, dict[str, list[str]]]:
    """Build a joint distribution over named dimensions.

    Returns the joint table and the category order per dimension, so a caller can
    map an index back to the categories it came from.
    """
    order = {name: list(values) for name, values in margins.items()}
    targets = [np.array([margins[name][key] for key in order[name]]) for name in order]
    rank_vectors = [np.array([ranks.get(name, {}).get(key, 0.0) for key in order[name]]) for name in order]
    seed = ordinal_seed(rank_vectors, strength)
    return fit(seed, targets), order
