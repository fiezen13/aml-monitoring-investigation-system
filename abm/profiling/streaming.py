"""Bounded-memory accumulators for profiling files that do not fit in memory.

The largest IBM AML transaction file is roughly 180 million rows and tens of
gigabytes. Nothing here may keep a per-row list. Each accumulator holds a fixed
or sparse-but-small amount of state, so memory depends on the number of distinct
accounts rather than the number of rows.

Quantiles come from a logarithmic histogram rather than sampling. Sampling would
make a profile depend on a random seed; a histogram makes the same file always
produce the same numbers, which is what a provenance artifact needs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# 20 bins per decade puts each bin about 12% wide in value terms. That is finer
# than any decision this profile feeds, and keeps a full 0.01..10^12 range under
# 300 bins.
BINS_PER_DECADE = 20

# Amounts below this are treated as the zero bucket. IBM records some crypto
# amounts as small as 3.4e-6, so the floor has to sit well below one unit.
_MIN_POSITIVE = 1e-12


def _bin_index(value: float) -> int:
    return math.floor(math.log10(value) * BINS_PER_DECADE)


def _bin_lower_bound(index: int) -> float:
    return 10.0 ** (index / BINS_PER_DECADE)


@dataclass(slots=True)
class NumericAccumulator:
    """Exact count/sum/min/max plus histogram-approximated quantiles."""

    count: int = 0
    zero_count: int = 0
    negative_count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    histogram: dict[int, int] = field(default_factory=dict)

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        if self.minimum is None or value < self.minimum:
            self.minimum = value
        if self.maximum is None or value > self.maximum:
            self.maximum = value
        if value < 0:
            self.negative_count += 1
            return
        if value < _MIN_POSITIVE:
            self.zero_count += 1
            return
        index = _bin_index(value)
        self.histogram[index] = self.histogram.get(index, 0) + 1

    @property
    def mean(self) -> float | None:
        return self.total / self.count if self.count else None

    def quantile(self, fraction: float) -> float | None:
        """Approximate quantile over non-negative values.

        Negative values are excluded rather than silently folded in; the IBM
        files should not contain any, and a profile that hides them would defeat
        the purpose. `negative_count` reports them separately.
        """
        positive_total = sum(self.histogram.values())
        population = positive_total + self.zero_count
        if population == 0:
            return None
        target = fraction * population
        if target <= self.zero_count:
            return 0.0
        target -= self.zero_count
        seen = 0
        for index in sorted(self.histogram):
            seen += self.histogram[index]
            if seen >= target:
                # Report the bin's geometric midpoint. Claiming more precision
                # than a bin boundary would be inventing digits.
                lower = _bin_lower_bound(index)
                upper = _bin_lower_bound(index + 1)
                return math.sqrt(lower * upper)
        return self.maximum

    def summary(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "zero_count": self.zero_count,
            "negative_count": self.negative_count,
            "sum": self.total,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
            "p01_approx": self.quantile(0.01),
            "p25_approx": self.quantile(0.25),
            "median_approx": self.quantile(0.50),
            "p75_approx": self.quantile(0.75),
            "p95_approx": self.quantile(0.95),
            "p99_approx": self.quantile(0.99),
            "quantile_method": f"log10 histogram, {BINS_PER_DECADE} bins per decade",
        }


@dataclass(slots=True)
class CappedCounter:
    """Value counts that stop growing once the key space is implausibly wide.

    Currency and payment format have a handful of values, so an uncapped counter
    is right for them. Bank and account identifiers have millions, so the cap
    keeps a profiling run from turning into an out-of-memory failure. Whether the
    cap was reached is itself reported, because a truncated count that looks
    complete is worse than no count.
    """

    cap: int = 1000
    counts: dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    ignored_after_cap: int = 0

    def add(self, value: str) -> None:
        if value in self.counts:
            self.counts[value] += 1
        elif len(self.counts) < self.cap:
            self.counts[value] = 1
        else:
            self.truncated = True
            self.ignored_after_cap += 1

    def summary(self, top: int = 25) -> dict[str, Any]:
        ordered = sorted(self.counts.items(), key=lambda item: (-item[1], item[0]))
        return {
            "distinct_observed": len(self.counts),
            "truncated": self.truncated,
            "occurrences_ignored_after_cap": self.ignored_after_cap,
            "top_values": [{"value": key, "count": value} for key, value in ordered[:top]],
        }


@dataclass(slots=True)
class CappedSet:
    """Distinct-value set with an explicit ceiling and a truncation flag."""

    cap: int
    values: set[str] = field(default_factory=set)
    truncated: bool = False

    def add(self, value: str) -> None:
        if len(self.values) < self.cap:
            self.values.add(value)
        elif value not in self.values:
            self.truncated = True

    def __len__(self) -> int:
        return len(self.values)


def shannon_entropy(counts: dict[str, int]) -> float:
    """Entropy in bits. 0.0 means one value dominates completely."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in counts.values():
        if value <= 0:
            continue
        share = value / total
        entropy -= share * math.log2(share)
    return entropy


def dominant_share(counts: dict[str, int]) -> tuple[str | None, float]:
    """The most frequent key and the fraction of observations it holds."""
    total = sum(counts.values())
    if total <= 0:
        return None, 0.0
    key = max(sorted(counts), key=lambda name: counts[name])
    return key, counts[key] / total
