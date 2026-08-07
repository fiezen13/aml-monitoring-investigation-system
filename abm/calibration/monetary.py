"""Phase 8 — map IBM's monetary scale onto Vietnamese income and revenue.

The wrong way to do this is an FX multiplication. IBM's amounts are denominated
in fifteen currencies across eighteen orders of magnitude, in a synthetic world
with no Vietnamese content; multiplying by a dong rate would produce numbers that
look Vietnamese and mean nothing.

What IBM actually supplies is **relative structure**: how large a payment is
against that account's own typical payment, how much flows in against how much
flows out, how turnover compares to a single transaction. Those ratios are the
part worth keeping, and they are dimensionless.

So calibration is a single multiplicative scale per account:

    scale = target monthly inflow in VND / observed IBM monthly inflow

Every transaction on that account is multiplied by its account's scale. Because
the scale is constant within an account, **every ratio is preserved exactly** —
fan patterns, inflow-to-outflow balance, turnover multiple, the ordering and
relative size of individual payments. Only the unit changes.

## The assumption at the centre of this

The target inflow is the customer's expected monthly income times a turnover
multiple, and *no acquired source publishes that multiple*. Nothing links
declared income to money crossing an account. It is registered as
`ASSUME_INCOME_TO_TURNOVER` with a wide sensitivity range, and the release is
expected to be generated at several settings so the sensitivity is measured
rather than asserted.

A second, quieter assumption: the income anchor is GDP per capita in VND, which
is not household income. It counts corporate and government value added and
divides by everyone rather than by earners, so it overstates. The correction
factor is `ASSUME_HOUSEHOLD_INCOME_RATIO`, and it is applied openly here rather
than folded silently into the income bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Money crossing an account each month, as a multiple of monthly income. Wages
# arrive, transfers and repayments pass through, so inflow exceeds income — but
# by how much is not published anywhere in the acquired sources.
ASSUME_INCOME_TO_TURNOVER = 1.6
ASSUME_INCOME_TO_TURNOVER_SENSITIVITY = (1.0, 3.0)

# Household income per capita as a fraction of GDP per capita. Vietnamese
# household survey income runs well below GDP per capita for the structural
# reasons above.
ASSUME_HOUSEHOLD_INCOME_RATIO = 0.62
ASSUME_HOUSEHOLD_INCOME_RATIO_SENSITIVITY = (0.45, 0.80)

# Businesses run far more money through an account relative to their margin than
# individuals do relative to income, because turnover is gross.
ASSUME_BUSINESS_TURNOVER_TO_INFLOW = 0.85
ASSUME_BUSINESS_TURNOVER_TO_INFLOW_SENSITIVITY = (0.6, 1.2)

# Below this, an account's observed inflow is too small to divide by safely.
MINIMUM_OBSERVED_INFLOW = 1e-6


@dataclass(slots=True)
class CalibrationConfig:
    income_to_turnover: float = ASSUME_INCOME_TO_TURNOVER
    household_income_ratio: float = ASSUME_HOUSEHOLD_INCOME_RATIO
    business_turnover_to_inflow: float = ASSUME_BUSINESS_TURNOVER_TO_INFLOW
    observation_days: float = 27.67


def target_monthly_inflow_vnd(entity: dict[str, Any], config: CalibrationConfig) -> float | None:
    """What this customer's account should see in a month, in VND.

    Returns None when the entity has no income basis at all — an unemployed
    customer outside the labour force with no expected income. Those accounts
    are handled by the caller rather than given a fabricated floor.
    """
    if "expected_monthly_turnover_vnd" in entity:
        return float(entity["expected_monthly_turnover_vnd"]) * config.business_turnover_to_inflow

    income = entity.get("expected_monthly_income_vnd")
    if income is None:
        return None
    household_income = float(income) * config.household_income_ratio
    return household_income * config.income_to_turnover


def account_scale_factor(
    observed_inflow: float,
    target_inflow: float,
    *,
    observation_days: float,
) -> float:
    """The multiplier that maps one IBM account's amounts into VND.

    The observed inflow covers the source's 27.67-day window, so it is converted
    to a 30-day month before the comparison. Getting this wrong would bias every
    amount in the release by about 8 percent — small enough to pass a glance and
    large enough to matter.
    """
    if observed_inflow <= MINIMUM_OBSERVED_INFLOW:
        raise ValueError("observed inflow is too small to calibrate against")
    monthly_observed = observed_inflow * (30.0 / observation_days)
    return target_inflow / monthly_observed


def calibrate_accounts(matches: list[dict[str, Any]], config: CalibrationConfig) -> list[dict[str, Any]]:
    """Attach a scale factor to every matched account.

    Each match must carry the entity's expected income or turnover and the IBM
    account's observed inflow. Accounts with no income basis, or with no observed
    inflow to scale, are returned with `scale_factor` of None and a stated reason
    rather than a substituted default.
    """
    calibrated = []
    for match in matches:
        target = target_monthly_inflow_vnd(match["entity"], config)
        observed = float(match["behavior"].get("total_incoming_amount") or 0.0)

        if target is None:
            reason = "entity has no expected income or turnover"
            scale = None
        elif observed <= MINIMUM_OBSERVED_INFLOW:
            reason = "IBM account has no observed inflow to scale"
            scale = None
        else:
            reason = None
            scale = account_scale_factor(observed, target, observation_days=config.observation_days)

        calibrated.append(
            {
                **match,
                "target_monthly_inflow_vnd": target,
                "observed_inflow_source_units": observed,
                "scale_factor": scale,
                "uncalibrated_reason": reason,
            }
        )
    return calibrated


def verify_ratio_preservation(behavior: dict[str, Any], scale: float) -> dict[str, Any]:
    """Confirm a scale factor changes units without changing shape.

    A multiplicative scale cannot alter a ratio of two amounts from the same
    account, so this is closer to an assertion than a computation — which is the
    point. It gives the validation report something to check rather than a claim
    to trust.
    """
    incoming = float(behavior.get("total_incoming_amount") or 0.0)
    outgoing = float(behavior.get("total_outgoing_amount") or 0.0)
    median = float(behavior.get("median_incoming_amount") or 0.0)

    def ratio(numerator: float, denominator: float) -> float | None:
        return numerator / denominator if denominator else None

    before = {
        "inflow_outflow": ratio(incoming, outgoing),
        "turnover_multiple": ratio(incoming + outgoing, median),
    }
    after = {
        "inflow_outflow": ratio(incoming * scale, outgoing * scale),
        "turnover_multiple": ratio((incoming + outgoing) * scale, median * scale),
    }
    return {
        "before": before,
        "after": after,
        "preserved": all(
            before[key] is None
            or after[key] is None
            or abs(before[key] - after[key]) < 1e-9 * max(1.0, abs(before[key]))
            for key in before
        ),
    }


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_INCOME_TO_TURNOVER",
            "description": "Monthly account inflow as a multiple of monthly income.",
            "value": ASSUME_INCOME_TO_TURNOVER,
            "sensitivity_range": list(ASSUME_INCOME_TO_TURNOVER_SENSITIVITY),
            "why_not_evidenced": (
                "No acquired source links declared income to money crossing an "
                "account. This is the hinge of the entire monetary scale."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_HOUSEHOLD_INCOME_RATIO",
            "description": "Household income per capita as a fraction of GDP per capita.",
            "value": ASSUME_HOUSEHOLD_INCOME_RATIO,
            "sensitivity_range": list(ASSUME_HOUSEHOLD_INCOME_RATIO_SENSITIVITY),
            "why_not_evidenced": (
                "GDP per capita is the only VND-denominated income anchor acquired. "
                "It includes corporate and government value added."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_BUSINESS_TURNOVER_TO_INFLOW",
            "description": "Share of business turnover that crosses the bank account.",
            "value": ASSUME_BUSINESS_TURNOVER_TO_INFLOW,
            "sensitivity_range": list(ASSUME_BUSINESS_TURNOVER_TO_INFLOW_SENSITIVITY),
            "why_not_evidenced": "Not published; cash-intensive firms bank less of their turnover.",
            "confidence": "low",
        },
    ]
