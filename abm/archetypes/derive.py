"""Phase 3 — derive behavioral archetypes from IBM account behavior.

Method: standardize the scale-free features, choose k by silhouette score on a
subsample, check that the chosen k is stable across seeds and across disjoint
subsamples, fit on a subsample, then assign every account.

Two things this deliberately does not do.

It does not read the laundering label. Archetypes describe how accounts behave,
and a bank deriving customer segments has no labels. The label is used *after*
the fact, in `evaluate.py`, purely to test whether the archetypes accidentally
encode it — which is a validation, not an input.

It does not fix k in advance. The candidate archetype names in the project brief
(SALARIED_DIGITAL, CASH_HEAVY, and so on) are examples, not targets. Names are
assigned to clusters after reading their centroids, never before.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from abm.archetypes.features import (
    FEATURE_DESCRIPTIONS,
    FEATURE_NAMES,
    SOURCE_COLUMNS,
    build_feature_matrix,
)

ARCHETYPE_SCHEMA_VERSION = "1.0"

# An account with fewer than this many transactions has no stable median, no
# meaningful fan ratio, and no inter-arrival estimate. 33.5% of IBM accounts
# fall below it (Finding B1). Clustering them would create clusters of noise
# that outnumber the real ones.
MIN_TRANSACTIONS = 10

# Model selection and stability run on subsamples; the final assignment covers
# every account. 150k rows is far past the point where silhouette scores stop
# moving, and keeps the O(n^2)-ish silhouette computation affordable.
MODEL_SELECTION_SAMPLE = 150_000
SILHOUETTE_SAMPLE = 20_000
FIT_SAMPLE = 300_000

CANDIDATE_K = range(3, 13)
STABILITY_SEEDS = (11, 23, 37, 53, 71)


def load_behavior_table(path: Path) -> pa.Table:
    return pacsv.read_csv(
        str(path),
        convert_options=pacsv.ConvertOptions(include_columns=list(SOURCE_COLUMNS)),
    )


def _sample(matrix: np.ndarray, size: int, seed: int) -> np.ndarray:
    if len(matrix) <= size:
        return matrix
    rng = np.random.default_rng(seed)
    return matrix[rng.choice(len(matrix), size=size, replace=False)]


def select_k(scaled: np.ndarray, *, seed: int = 20260807) -> dict[str, Any]:
    """Score every candidate k on one subsample.

    Silhouette is computed on a further subsample because it is quadratic in the
    number of points; Davies-Bouldin and Calinski-Harabasz are cheap and are
    reported alongside so the choice does not rest on one index.
    """
    sample = _sample(scaled, MODEL_SELECTION_SAMPLE, seed)
    rng = np.random.default_rng(seed)
    silhouette_idx = rng.choice(len(sample), size=min(SILHOUETTE_SAMPLE, len(sample)), replace=False)

    scores = []
    for k in CANDIDATE_K:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed)
        labels = model.fit_predict(sample)
        scores.append(
            {
                "k": k,
                "silhouette": float(silhouette_score(sample[silhouette_idx], labels[silhouette_idx])),
                "davies_bouldin": float(davies_bouldin_score(sample, labels)),
                "calinski_harabasz": float(calinski_harabasz_score(sample, labels)),
                "inertia": float(model.inertia_),
                "smallest_cluster_share": float(np.bincount(labels).min() / len(labels)),
            }
        )
    return {"candidates": scores}


def measure_stability(scaled: np.ndarray, k: int) -> dict[str, Any]:
    """Do independent runs recover the same partition?

    Two checks. Seed stability re-fits on the same points with different
    initializations. Subsample stability fits on disjoint halves and compares
    their predictions on a common holdout — the harder test, and the one that
    catches a k that only exists because of one particular sample.
    """
    seed_sample = _sample(scaled, MODEL_SELECTION_SAMPLE, seed=1)
    reference = KMeans(n_clusters=k, n_init=10, random_state=STABILITY_SEEDS[0]).fit_predict(seed_sample)
    seed_scores = [
        float(
            adjusted_rand_score(
                reference,
                KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(seed_sample),
            )
        )
        for seed in STABILITY_SEEDS[1:]
    ]

    rng = np.random.default_rng(4242)
    shuffled = rng.permutation(len(scaled))
    holdout = scaled[shuffled[: min(20_000, len(scaled) // 4)]]
    remainder = shuffled[len(holdout) :]
    half = len(remainder) // 2
    first = KMeans(n_clusters=k, n_init=10, random_state=101).fit(scaled[remainder[:half]][:MODEL_SELECTION_SAMPLE])
    second = KMeans(n_clusters=k, n_init=10, random_state=202).fit(scaled[remainder[half:]][:MODEL_SELECTION_SAMPLE])
    subsample_ari = float(adjusted_rand_score(first.predict(holdout), second.predict(holdout)))

    return {
        "k": k,
        "seed_stability_ari": seed_scores,
        "seed_stability_ari_min": min(seed_scores),
        "disjoint_subsample_ari": subsample_ari,
        "interpretation": (
            "ARI 1.0 is an identical partition, 0.0 is chance agreement. "
            "Disjoint-subsample ARI is the stricter of the two."
        ),
    }


def describe_clusters(
    scaled: np.ndarray,
    raw: np.ndarray,
    labels: np.ndarray,
    table: pa.Table,
) -> list[dict[str, Any]]:
    """Summarize each cluster in the units a human can argue with.

    Centroids are reported in raw feature units, not standardized ones, because
    "fan-in ratio 0.9" is reviewable and "fan-in ratio +1.7 sigma" is not.
    """
    entity_kind = table.column("entity_kind").to_pylist()
    transaction_count = table.column("transaction_count").to_numpy(zero_copy_only=False)
    turnover = table.column("turnover_amount").to_numpy(zero_copy_only=False)

    summaries = []
    for cluster in sorted(set(labels.tolist())):
        mask = labels == cluster
        members = int(mask.sum())
        kinds: dict[str, int] = {}
        for index in np.flatnonzero(mask):
            kind = entity_kind[int(index)] or "UNKNOWN"
            kinds[kind] = kinds.get(kind, 0) + 1
        summaries.append(
            {
                "cluster": int(cluster),
                "accounts": members,
                "share": members / len(labels),
                "centroid": {name: float(np.median(raw[mask, index])) for index, name in enumerate(FEATURE_NAMES)},
                "centroid_scaled": {
                    name: float(scaled[mask, index].mean()) for index, name in enumerate(FEATURE_NAMES)
                },
                "median_transaction_count": float(np.median(transaction_count[mask])),
                "median_turnover": float(np.median(turnover[mask])),
                "entity_kind_mix": dict(sorted(kinds.items(), key=lambda item: -item[1])),
            }
        )
    return summaries


def derive_archetypes(
    behavior_csv: Path,
    *,
    output: Path,
    report: Path,
    min_transactions: int = MIN_TRANSACTIONS,
    k: int | None = None,
    seed: int = 20260807,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    table = load_behavior_table(behavior_csv)
    total_accounts = table.num_rows

    active = table.filter(pc.greater_equal(table.column("transaction_count"), min_transactions))
    raw, usable = build_feature_matrix(active)
    active = active.filter(pa.array(usable))
    raw = raw[usable]

    scaler = StandardScaler()
    scaled = scaler.fit_transform(raw)

    selection = select_k(scaled, seed=seed)
    chosen_k = k if k is not None else _choose_k(selection["candidates"])
    stability = measure_stability(scaled, chosen_k)

    model = KMeans(n_clusters=chosen_k, n_init=10, random_state=seed)
    model.fit(_sample(scaled, FIT_SAMPLE, seed))
    labels = model.predict(scaled)

    clusters = describe_clusters(scaled, raw, labels, active)
    named = assign_names(clusters)

    _write_assignments(active, labels, named, output)

    summary = {
        "archetype_schema_version": ARCHETYPE_SCHEMA_VERSION,
        "derived_at": started.isoformat(timespec="seconds"),
        "source": str(behavior_csv),
        "label_usage": {
            "is_laundering_read": False,
            "note": "Archetypes are derived without the label. Leakage is tested separately.",
        },
        "population": {
            "accounts_in_profile": total_accounts,
            "min_transactions": min_transactions,
            "accounts_clustered": int(len(labels)),
            "accounts_excluded_sparse": int(total_accounts - active.num_rows),
            "accounts_excluded_unusable_features": int((~usable).sum()),
        },
        "features": {
            "names": list(FEATURE_NAMES),
            "descriptions": FEATURE_DESCRIPTIONS,
            "excluded": {
                "absolute_amounts": "IBM mixes 15 currencies across 18 orders of magnitude.",
                "time_of_day_and_weekday": "IBM assigns times uniformly at random (Finding B2).",
                "payment_format_identity": (
                    "Format predicts the laundering label at 7.2x lift (Finding L1). "
                    "Only its concentration is used, never which format it is."
                ),
            },
            "preprocessing": "log1p on heavy-tailed features, then z-score standardization",
        },
        "model_selection": selection,
        "chosen_k": chosen_k,
        "stability": stability,
        "archetypes": named,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "status": "PASS",
        "chosen_k": chosen_k,
        "accounts_clustered": int(len(labels)),
        "output": str(output.resolve()),
        "report": str(report.resolve()),
    }


def _choose_k(candidates: list[dict[str, Any]]) -> int:
    """Pick k by silhouette, rejecting solutions with a degenerate cluster.

    A cluster holding under 1% of accounts is usually an outlier pocket rather
    than a segment worth naming and matching against, so those k values are
    skipped unless nothing else qualifies.
    """
    viable = [row for row in candidates if row["smallest_cluster_share"] >= 0.01]
    pool = viable or candidates
    return int(max(pool, key=lambda row: row["silhouette"])["k"])


def _write_assignments(table: pa.Table, labels: np.ndarray, named: list[dict[str, Any]], output: Path) -> None:
    names = {entry["cluster"]: entry["archetype"] for entry in named}
    output.parent.mkdir(parents=True, exist_ok=True)
    pacsv.write_csv(
        pa.table(
            {
                "account_key": table.column("account_key"),
                "entity_kind": table.column("entity_kind"),
                "cluster": pa.array(labels.astype("int32")),
                "archetype": pa.array([names[int(label)] for label in labels]),
                "transaction_count": table.column("transaction_count"),
                "turnover_amount": table.column("turnover_amount"),
            }
        ),
        str(output),
    )


# Features that say the same thing about an account are grouped, so a name is
# built from two *different* things rather than one thing said twice. Flow and
# value balance, for instance, are both direction.
_FEATURE_FAMILY = {
    "flow_direction_balance": "direction",
    "value_direction_balance": "direction",
    "fan_in_ratio": "counterparties",
    "fan_out_ratio": "counterparties",
    "activity_density": "rhythm",
    "log_transactions_per_active_day": "rhythm",
    "log_turnover_multiple": "turnover",
    "self_transfer_share": "self_dealing",
    "dominant_format_share": "instrument",
    "log_distinct_currencies": "currency",
}

# The readable term for a feature being unusually high or unusually low.
_FEATURE_TERMS = {
    "flow_direction_balance": ("INBOUND", "OUTBOUND"),
    "value_direction_balance": ("ACCUMULATING", "DISBURSING"),
    "fan_in_ratio": ("WIDE_FAN_IN", "REPEAT_SENDERS"),
    "fan_out_ratio": ("WIDE_FAN_OUT", "REPEAT_RECIPIENTS"),
    "activity_density": ("CONTINUOUS", "SPORADIC"),
    "log_transactions_per_active_day": ("BURSTY", "SLOW"),
    "log_turnover_multiple": ("HIGH_TURNOVER", "LOW_TURNOVER"),
    "self_transfer_share": ("SELF_CYCLING", "NO_SELF_DEALING"),
    "dominant_format_share": ("SINGLE_INSTRUMENT", "MIXED_INSTRUMENT"),
    "log_distinct_currencies": ("MULTI_CURRENCY", "SINGLE_CURRENCY"),
}

# Below this many standard deviations from the population mean, a feature is not
# saying anything distinctive about the cluster and does not belong in its name.
_DISTINCTIVE_Z = 0.5


def assign_names(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Name each cluster from whichever features actually distinguish it.

    The name is composed from the standardized centroid: rank features by how
    far the cluster sits from the population mean, then take the strongest one
    from each of the two leading feature families. This is deliberately not a
    fixed cascade of thresholds. A cascade encodes what the author expected to
    find and quietly mislabels a cluster it did not anticipate; ranking by
    distinctiveness renames itself when the data changes.

    The candidate names in the project brief — SALARIED_DIGITAL, CASH_HEAVY —
    were examples, and none of them survived contact with the data.
    """
    named = []
    for cluster in clusters:
        name, rationale = _interpret(cluster["centroid_scaled"], cluster["centroid"])
        named.append({**cluster, "archetype": name, "naming_rationale": rationale})

    seen: dict[str, int] = {}
    for entry in named:
        base = entry["archetype"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            entry["archetype"] = f"{base}_{seen[base]}"
    return named


def _interpret(scaled: dict[str, float], raw: dict[str, float]) -> tuple[str, str]:
    ranked = sorted(scaled.items(), key=lambda item: -abs(item[1]))
    terms: list[str] = []
    evidence: list[str] = []
    used_families: set[str] = set()

    for feature, z in ranked:
        if abs(z) < _DISTINCTIVE_Z or len(terms) >= 2:
            continue
        family = _FEATURE_FAMILY[feature]
        if family in used_families:
            continue
        used_families.add(family)
        high, low = _FEATURE_TERMS[feature]
        terms.append(high if z > 0 else low)
        evidence.append(f"{feature} {z:+.2f} sd (raw {raw[feature]:.2f})")

    if not terms:
        return "BALANCED_ROUTINE", "no feature reaches 0.5 sd from the population mean"
    return "_".join(terms), "; ".join(evidence)
