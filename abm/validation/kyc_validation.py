"""Validate the generated KYC population, the matching, and their leakage.

Four questions, each answered with a number rather than a claim.

1. **Do the generated distributions reproduce their sources?** Every marginal
   that came from a published statistic is compared back against it.
2. **Is the matching any good?** Score distribution, archetype usage, and whether
   the matched accounts' behavior actually spans the range the entities needed.
3. **Does any KYC attribute predict the laundering label?** This is Phase 14's
   test, run early because the answer changes the design if it is wrong.
4. **Where is the synthetic population biased?** Stated, not hidden.

The third is the one that matters most. A KYC field that perfectly predicts the
label makes the whole dataset worthless for its purpose, and a field that
strongly predicts it makes every downstream evaluation optimistic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

# A single attribute value that separates the label completely is a hard failure.
PERFECT_PREDICTION_TOLERANCE = 1e-9

# Above this lift, an attribute value concentrates the label enough to distort
# evaluation even though it does not determine it.
STRONG_ASSOCIATION_LIFT = 3.0

# Attribute values held by fewer than this many entities produce lifts that are
# noise; they are reported but not judged.
MINIMUM_CELL_SIZE = 30


def validate_distributions(
    customers: list[dict[str, Any]], values: dict[str, Any], distributions: dict[str, Any]
) -> dict[str, Any]:
    """Compare every generated marginal against the statistic it came from."""
    population = distributions["population"]
    total = len(customers)
    checks = []

    for field, name in (
        ("age_band", "age_band"),
        ("gender", "gender"),
        ("urban_rural", "urban_rural"),
        ("employment_status", "employment_status"),
        ("education_band", "education_band"),
        ("income_band", "income_band"),
    ):
        observed = Counter(customer[field] for customer in customers)
        expected = population[name]["probabilities"]
        for category, probability in expected.items():
            generated = observed.get(category, 0) / total
            checks.append(
                {
                    "kind": "population_marginal",
                    "attribute": field,
                    "category": category,
                    "source_share": probability,
                    "generated_share": generated,
                    "absolute_error": abs(generated - probability),
                }
            )

    for field, indicator in (
        ("has_bank_account", "account_ownership"),
        ("uses_digital_payment", "digital_payment"),
        ("has_formal_saving", "formal_saving"),
        ("has_formal_borrowing", "borrowed_any"),
        ("has_mobile_money", "mobile_money_account"),
    ):
        generated = sum(bool(customer[field]) for customer in customers) / total
        source = float(values[indicator]["value"]) / 100.0
        checks.append(
            {
                "kind": "behavior_marginal",
                "attribute": field,
                "category": "true",
                "source_share": source,
                "generated_share": generated,
                "absolute_error": abs(generated - source),
            }
        )

    worst = max(checks, key=lambda check: check["absolute_error"])
    return {
        "checks": checks,
        "max_absolute_error": worst["absolute_error"],
        "worst_check": worst,
        "verdict": ("PASS" if worst["absolute_error"] < 0.02 else "REVIEW: a marginal drifts over 2 points"),
    }


def validate_conditional_gradients(customers: list[dict[str, Any]]) -> dict[str, Any]:
    """Confirm generation was conditional rather than independent.

    If attributes had been drawn independently, account ownership would be flat
    across education and income. The published gradients are steep, so a flat
    result here means the conditional structure was lost somewhere.
    """
    gradients = {}
    for field in ("education_band", "income_band", "urban_rural", "employment_status"):
        grouped: dict[str, list[bool]] = defaultdict(list)
        for customer in customers:
            grouped[customer[field]].append(bool(customer["has_bank_account"]))
        rates = {key: sum(value) / len(value) for key, value in sorted(grouped.items())}
        gradients[field] = {
            "account_ownership_rate": rates,
            "spread": max(rates.values()) - min(rates.values()),
        }
    return {
        "gradients": gradients,
        "verdict": (
            "PASS"
            if all(entry["spread"] > 0.05 for entry in gradients.values())
            else "FAIL: an attribute shows no gradient, suggesting independent draws"
        ),
    }


def validate_matching(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Score distribution, archetype usage, and account reuse."""
    scores = sorted(match["matching_score"] for match in matches)
    archetypes = Counter(match["archetype"] for match in matches)
    account_keys = [match["behavior"]["account_key"] for match in matches]
    reused = len(account_keys) - len(set(account_keys))

    by_entity: dict[str, Counter] = defaultdict(Counter)
    for match in matches:
        by_entity[match["entity_type"]][match["archetype"]] += 1

    return {
        "matches": len(matches),
        "accounts_reused": reused,
        "score_distribution": {
            "min": scores[0],
            "p25": scores[len(scores) // 4],
            "median": scores[len(scores) // 2],
            "p75": scores[(3 * len(scores)) // 4],
            "max": scores[-1],
            "mean": sum(scores) / len(scores),
        },
        "archetype_usage": dict(archetypes.most_common()),
        "archetype_by_entity_type": {
            entity_type: dict(counter.most_common()) for entity_type, counter in by_entity.items()
        },
        "verdict": (
            "PASS"
            if reused == 0 and len(archetypes) > 1
            else "FAIL: accounts reused or all entities collapsed onto one archetype"
        ),
    }


def validate_label_leakage(matches: list[dict[str, Any]], flagged_accounts: set[str]) -> dict[str, Any]:
    """Phase 14's test: does any KYC attribute predict the laundering label?

    The label here is a property of the *matched IBM account*, and it reaches the
    KYC side only through the matcher. So a strong association means the matcher
    is routing a KYC attribute towards laundering-heavy behavior — which is
    exactly what has to be caught before transactions are rebuilt on top of it.
    """
    labelled = [(match, match["behavior"]["account_key"] in flagged_accounts) for match in matches]
    positives = sum(1 for _, flag in labelled if flag)
    base_rate = positives / len(labelled) if labelled else 0.0

    attributes = (
        "age_band",
        "gender",
        "education_band",
        "urban_rural",
        "employment_status",
        "income_band",
        "financial_access_segment",
        "digital_usage_segment",
        "occupation_group",
        "customer_tenure_band",
        "industry_group",
        "legal_form",
        "cash_intensity_band",
        "employee_size_band",
        "domestic_international_profile",
    )

    findings = []
    perfect = []
    strong = []
    for attribute in attributes:
        grouped: dict[Any, list[bool]] = defaultdict(list)
        for match, flag in labelled:
            value = match["entity"].get(attribute)
            if value is not None:
                grouped[value].append(flag)
        for value, flags in sorted(grouped.items(), key=lambda item: str(item[0])):
            if len(flags) < MINIMUM_CELL_SIZE:
                continue
            rate = sum(flags) / len(flags)
            lift = rate / base_rate if base_rate else None
            entry = {
                "attribute": attribute,
                "value": str(value),
                "entities": len(flags),
                "flagged_rate": rate,
                "lift": lift,
            }
            findings.append(entry)
            if rate <= PERFECT_PREDICTION_TOLERANCE or rate >= 1 - PERFECT_PREDICTION_TOLERANCE:
                perfect.append(entry)
            elif lift is not None and lift >= STRONG_ASSOCIATION_LIFT:
                strong.append(entry)

    findings.sort(key=lambda entry: -(entry["lift"] or 0))
    return {
        "base_rate": base_rate,
        "flagged_entities": positives,
        "total_entities": len(labelled),
        "minimum_cell_size": MINIMUM_CELL_SIZE,
        "perfect_predictors": perfect,
        "strong_associations": strong,
        "top_associations": findings[:15],
        "mutual_information_bits": _mutual_information(labelled, attributes),
        "verdict": _leakage_verdict(perfect, strong),
    }


def _leakage_verdict(perfect: list[dict[str, Any]], strong: list[dict[str, Any]]) -> str:
    if perfect:
        return (
            "FAIL: a KYC attribute value perfectly separates the label. The dataset "
            "cannot be used to evaluate detection until this is removed."
        )
    if strong:
        return (
            f"WARN: {len(strong)} attribute values concentrate the label above "
            f"{STRONG_ASSOCIATION_LIFT}x. Usable, but downstream evaluation will be "
            "optimistic unless these are controlled for."
        )
    return (
        "PASS: no KYC attribute value perfectly predicts the label, and none "
        f"concentrates it above {STRONG_ASSOCIATION_LIFT}x."
    )


def _mutual_information(labelled: list[tuple[dict[str, Any], bool]], attributes: tuple[str, ...]) -> dict[str, float]:
    """Mutual information between each attribute and the label, in bits.

    Lift catches one category behaving unusually; mutual information catches an
    attribute that carries information spread thinly across many categories,
    which lift would miss entirely.
    """
    total = len(labelled)
    if total == 0:
        return {}
    label_counts = Counter(flag for _, flag in labelled)
    label_entropy = _entropy([count / total for count in label_counts.values()])

    scores = {}
    for attribute in attributes:
        grouped: dict[Any, list[bool]] = defaultdict(list)
        for match, flag in labelled:
            value = match["entity"].get(attribute)
            if value is not None:
                grouped[value].append(flag)
        covered = sum(len(flags) for flags in grouped.values())
        if covered == 0:
            continue
        conditional = 0.0
        for flags in grouped.values():
            weight = len(flags) / covered
            counts = Counter(flags)
            conditional += weight * _entropy([count / len(flags) for count in counts.values()])
        scores[attribute] = round(max(label_entropy - conditional, 0.0), 6)
    return dict(sorted(scores.items(), key=lambda item: -item[1]))


def _entropy(probabilities: list[float]) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0)


def validate_calibration(calibrated: list[dict[str, Any]]) -> dict[str, Any]:
    """Check the calibrated monetary scale lands somewhere plausible."""
    scaled = [row for row in calibrated if row["scale_factor"] is not None]
    if not scaled:
        return {"verdict": "FAIL: nothing was calibrated"}

    inflows = sorted(row["target_monthly_inflow_vnd"] for row in scaled)
    factors = sorted(row["scale_factor"] for row in scaled)

    def quantile(values: list[float], fraction: float) -> float:
        return values[min(len(values) - 1, int(fraction * len(values)))]

    return {
        "accounts_calibrated": len(scaled),
        "accounts_uncalibrated": len(calibrated) - len(scaled),
        "target_monthly_inflow_vnd": {
            "min": inflows[0],
            "median": quantile(inflows, 0.5),
            "p95": quantile(inflows, 0.95),
            "max": inflows[-1],
        },
        "scale_factor": {
            "min": factors[0],
            "median": quantile(factors, 0.5),
            "p95": quantile(factors, 0.95),
            "max": factors[-1],
            "spread_orders_of_magnitude": round(
                math.log10(factors[-1] / factors[0]) if factors[0] > 0 else float("inf"), 2
            ),
        },
        "note": (
            "Scale factors vary by orders of magnitude because IBM denominates "
            "accounts in fifteen currencies. A wide spread is expected and is the "
            "reason absolute IBM amounts are never used directly."
        ),
    }
