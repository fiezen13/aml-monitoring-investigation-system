"""Derive Vietnamese conditional distributions from acquired indicators.

Turns the raw World Bank responses into the probability tables the KYC generator
consumes. Nothing here contains a hard-coded percentage: every number is
computed from a cached API response, and every table records which indicators
and which reference years produced it.

## The one assumption that matters

Findex publishes each behavior broken down **one dimension at a time**. There is
a rate for women, a rate for rural adults, a rate for the poorest 40% — but no
rate for *rural women in the poorest 40%*. The joint distribution is not
published and cannot be recovered from the margins.

So combining dimensions requires an assumption, and it is made explicitly here
rather than buried: each dimension contributes an independent additive shift in
log-odds. Under this model a category that doubles the odds of holding an account
does so regardless of the other categories.

This is the standard way to combine marginal rates and it is transparently
falsifiable, but it is still an assumption, not evidence. It is registered as
`ASSUME_LOGIT_ADDITIVITY` and every distribution built through it is flagged
`derivation: logit_additive`. Where a relationship needs no combination, the
published rate is used directly and flagged `derivation: direct`.

Interaction effects are the known casualty. Real financial exclusion concentrates
where disadvantages compound, and an additive-in-log-odds model understates that
by construction.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from abm.sources.worldbank import FINDEX_INDICATORS, findex_breakdown

DISTRIBUTIONS_VERSION = "0.1.0"

# KYC age bands. Coarser than the five-year source bands so that each band holds
# enough synthetic customers to be checkable, and aligned to how banks segment.
AGE_BANDS = ("15-24", "25-34", "35-44", "45-54", "55-64", "65+")

_AGE_BAND_SOURCES = {
    "15-24": ("1519", "2024"),
    "25-34": ("2529", "3034"),
    "35-44": ("3539", "4044"),
    "45-54": ("4549", "5054"),
    "55-64": ("5559", "6064"),
    "65+": ("6569", "7074", "7579", "80UP"),
}

INCOME_BANDS = ("Q1", "Q2", "Q3", "Q4", "Q5")

EMPLOYMENT_STATUSES = (
    "WAGE_WORKER",
    "OWN_ACCOUNT",
    "EMPLOYER",
    "UNPAID_FAMILY",
    "UNEMPLOYED",
    "NOT_IN_LABOUR_FORCE",
)

OCCUPATION_GROUPS = ("AGRICULTURE", "INDUSTRY", "SERVICES")


def _value(values: dict[str, Any], alias: str) -> float:
    entry = values.get(alias)
    if entry is None:
        raise KeyError(f"indicator {alias} was not acquired; cannot derive a distribution from it")
    return float(entry["value"])


def _year(values: dict[str, Any], alias: str) -> int:
    return int(values[alias]["year"])


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("cannot normalize a distribution whose weights sum to zero")
    return {key: value / total for key, value in weights.items()}


def age_band_distribution(values: dict[str, Any]) -> dict[str, Any]:
    """P(age_band) for adults 15+, from five-year UN population bands.

    Source bands are a share of *that sex's* population, so male and female
    shares are weighted by the male and female population counts before being
    combined, then renormalized over 15+ only.
    """
    male_population = _value(values, "population_male")
    female_population = _value(values, "population_female")

    weights: dict[str, float] = {}
    for band, sources in _AGE_BAND_SOURCES.items():
        total = 0.0
        for source in sources:
            total += _value(values, f"population_age_{source}_ma") / 100.0 * male_population
            total += _value(values, f"population_age_{source}_fe") / 100.0 * female_population
        weights[band] = total

    return {
        "distribution": "P(age_band)",
        "derivation": "direct",
        "source_indicators": ["SP.POP.<band>.{MA,FE}.5Y", "SP.POP.TOTL.{MA,FE}.IN"],
        "reference_year": _year(values, "population_male"),
        "note": "Restricted to ages 15 and over, then renormalized.",
        "probabilities": _normalize(weights),
    }


def gender_distribution(values: dict[str, Any]) -> dict[str, Any]:
    male = _value(values, "population_male")
    female = _value(values, "population_female")
    return {
        "distribution": "P(gender)",
        "derivation": "direct",
        "source_indicators": ["SP.POP.TOTL.MA.IN", "SP.POP.TOTL.FE.IN"],
        "reference_year": _year(values, "population_male"),
        "note": "Whole-population sex ratio, not restricted to adults.",
        "probabilities": _normalize({"M": male, "F": female}),
    }


def urban_rural_distribution(values: dict[str, Any]) -> dict[str, Any]:
    urban = _value(values, "urban_population_share")
    return {
        "distribution": "P(urban_rural)",
        "derivation": "direct",
        "source_indicators": ["SP.URB.TOTL.IN.ZS"],
        "reference_year": _year(values, "urban_population_share"),
        "note": (
            "National split only. Sub-national region is NOT available from this "
            "source; P(urban_rural | region) is unresolved."
        ),
        "probabilities": {"URBAN": urban / 100.0, "RURAL": 1.0 - urban / 100.0},
    }


def employment_status_distribution(values: dict[str, Any]) -> dict[str, Any]:
    """P(employment_status) over all adults 15+.

    Built in two stages because the sources measure different denominators.
    Participation and unemployment are shares of the 15+ population and of the
    labour force respectively; the status split is a share of *employment*. Each
    is applied to its own correct base.
    """
    participation = _value(values, "labour_force_participation") / 100.0
    unemployment = _value(values, "unemployment_rate") / 100.0

    in_labour_force = participation
    unemployed = in_labour_force * unemployment
    employed = in_labour_force - unemployed

    wage = _value(values, "employment_wage_salaried") / 100.0
    employers = _value(values, "employment_employers") / 100.0
    family = _value(values, "employment_family_workers") / 100.0
    # Own-account workers are self-employment minus employers and family workers.
    self_employed = _value(values, "employment_self_employed") / 100.0
    own_account = max(self_employed - employers - family, 0.0)

    within_employment = _normalize(
        {
            "WAGE_WORKER": wage,
            "OWN_ACCOUNT": own_account,
            "EMPLOYER": employers,
            "UNPAID_FAMILY": family,
        }
    )

    probabilities = {status: share * employed for status, share in within_employment.items()}
    probabilities["UNEMPLOYED"] = unemployed
    probabilities["NOT_IN_LABOUR_FORCE"] = 1.0 - in_labour_force

    return {
        "distribution": "P(employment_status)",
        "derivation": "direct",
        "source_indicators": [
            "SL.TLF.CACT.ZS",
            "SL.UEM.TOTL.ZS",
            "SL.EMP.WORK.ZS",
            "SL.EMP.SELF.ZS",
            "SL.EMP.MPYR.ZS",
            "SL.FAM.WORK.ZS",
        ],
        "reference_year": _year(values, "labour_force_participation"),
        "note": (
            "Unconditional. P(employment_status | age_band) is NOT supported by these indicators and is unresolved."
        ),
        "probabilities": _normalize(probabilities),
    }


def occupation_distribution(values: dict[str, Any]) -> dict[str, Any]:
    """P(occupation_group | employed), at the only granularity ILO publishes here."""
    return {
        "distribution": "P(occupation_group | employed)",
        "derivation": "direct",
        "source_indicators": ["SL.AGR.EMPL.ZS", "SL.IND.EMPL.ZS", "SL.SRV.EMPL.ZS"],
        "reference_year": _year(values, "employment_agriculture"),
        "note": (
            "Three broad sectors, which is what the source publishes. Finer "
            "occupation groups would need the National Statistics Office."
        ),
        "probabilities": _normalize(
            {
                "AGRICULTURE": _value(values, "employment_agriculture"),
                "INDUSTRY": _value(values, "employment_industry"),
                "SERVICES": _value(values, "employment_services"),
            }
        ),
    }


def education_distribution(values: dict[str, Any]) -> dict[str, Any]:
    """P(education_band), using Findex's own two-way split.

    Findex reports every behavior for "primary education or less" against
    "secondary education or more", and that contrast is its strongest conditional
    — holding an account shifts by -1.56 in log-odds for the lower group, far
    beyond the effect of sex, age, or residence. Modelling education is therefore
    the difference between using that signal and discarding it.
    """
    secondary_or_more = _value(values, "education_lower_secondary_or_more") / 100.0
    return {
        "distribution": "P(education_band)",
        "derivation": "direct",
        "source_indicators": ["SE.SEC.CUAT.LO.ZS"],
        "reference_year": _year(values, "education_lower_secondary_or_more"),
        "note": (
            "Share with at least lower secondary attainment, mapped onto Findex's "
            "SECONDARY_OR_MORE category. The two definitions are close but not "
            "identical; the mapping is an assumption."
        ),
        "probabilities": {
            "SECONDARY_OR_MORE": secondary_or_more,
            "PRIMARY_OR_LESS": 1.0 - secondary_or_more,
        },
    }


def income_band_distribution(values: dict[str, Any]) -> dict[str, Any]:
    """Income quintiles with a mean income for each, in VND per month.

    Quintiles hold 20% of people each by construction; what the source adds is
    how much of total income each holds. Mean income within a quintile is
    therefore (income share / population share) x mean income.

    The anchor is GDP per capita in current VND, which avoids an exchange-rate
    assumption but introduces a different one: GDP per capita is not household
    income. It includes corporate and government value added and counts every
    resident, not just earners. The published ratio of household income to GDP
    per capita is not in this source, so the anchor is recorded with a scale
    factor of 1.0 and flagged for calibration in Phase 8 rather than silently
    adjusted here.
    """
    shares = {band: _value(values, f"income_share_q{index}") for index, band in enumerate(INCOME_BANDS, start=1)}
    annual_per_capita = _value(values, "gdp_per_capita_vnd")
    monthly_per_capita = annual_per_capita / 12.0

    means = {band: (share / 100.0) / 0.20 * monthly_per_capita for band, share in shares.items()}
    return {
        "distribution": "P(income_band) with band means",
        "derivation": "direct",
        "source_indicators": [
            "SI.DST.FRST.20",
            "SI.DST.02ND.20",
            "SI.DST.03RD.20",
            "SI.DST.04TH.20",
            "SI.DST.05TH.20",
            "NY.GDP.PCAP.CN",
        ],
        "reference_year": _year(values, "income_share_q1"),
        "anchor_year": _year(values, "gdp_per_capita_vnd"),
        "note": (
            "Quintiles are equal by construction. Band means come from income "
            "shares anchored on GDP per capita in VND, which overstates household "
            "income by an unmeasured factor."
        ),
        "probabilities": {band: 0.20 for band in INCOME_BANDS},
        "income_share_percent": shares,
        "mean_monthly_income_vnd": {band: round(value) for band, value in means.items()},
        "gini": _value(values, "gini"),
    }


def behavior_conditionals(values: dict[str, Any]) -> dict[str, Any]:
    """Findex behaviors as log-odds shifts per category.

    A shift is the log-odds of the category minus the log-odds of the population
    overall. Zero means the category behaves like the population; positive means
    more likely. Storing shifts rather than raw rates is what makes the additive
    combination in `conditional_probability` well defined.
    """
    behaviors = {}
    for behavior in FINDEX_INDICATORS:
        breakdown = findex_breakdown(values, behavior)
        overall = breakdown["overall_rate_percent"]
        if overall is None:
            continue
        base_logit = _logit(overall / 100.0)
        dimensions = {}
        for dimension, categories in breakdown["by_dimension"].items():
            dimensions[dimension] = {
                category: {
                    "rate": entry["rate_percent"] / 100.0,
                    "logit_shift": _logit(entry["rate_percent"] / 100.0) - base_logit,
                }
                for category, entry in categories.items()
            }
        behaviors[behavior] = {
            "overall_rate": overall / 100.0,
            "base_logit": base_logit,
            "reference_year": breakdown["year"],
            "dimensions": dimensions,
        }
    return {
        "distribution": "P(behavior | demographic category)",
        "derivation": "logit_additive",
        "assumption_id": "ASSUME_LOGIT_ADDITIVITY",
        "note": (
            "Findex publishes one-dimension-at-a-time breakdowns only. Combining "
            "dimensions assumes independent additive shifts in log-odds and "
            "cannot represent interaction effects."
        ),
        "behaviors": behaviors,
    }


def _logit(probability: float) -> float:
    clipped = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(clipped / (1 - clipped))


def _sigmoid(logit: float) -> float:
    return 1.0 / (1.0 + math.exp(-logit))


def center_shifts(behaviors: dict[str, Any], dimension_margins: dict[str, dict[str, float]]) -> None:
    """Re-center each dimension's shifts on the population, in place.

    Without this the model is biased and the bias is not small. Because the logit
    is non-linear, the log-odds of the overall rate is *not* the population
    average of the per-category log-odds. Education makes the point: 34% of
    adults are in the lower group at a shift of -1.56 and 66% in the higher group
    at +0.24, so the population-weighted mean shift is -0.37, not zero. Adding
    six such dimensions subtracts about a full unit of log-odds from the average
    customer, and the generated account-ownership rate lands near 62% against a
    published 70.6%.

    Subtracting each dimension's population-weighted mean shift makes the average
    customer sit at the base rate, so the generated marginal reproduces the
    published one while the *relative* gradients — the part Findex actually
    measured — are untouched.
    """
    for behavior in behaviors.values():
        for dimension, categories in behavior["dimensions"].items():
            margins = dimension_margins.get(dimension)
            if not margins:
                continue
            weighted_mean = sum(
                margins.get(category, 0.0) * entry["logit_shift"] for category, entry in categories.items()
            )
            for entry in categories.values():
                entry["logit_shift"] -= weighted_mean
            behavior.setdefault("centering", {})[dimension] = weighted_mean


def residual_behavior(behavior: dict[str, Any], gate: dict[str, Any], gate_rate: float) -> dict[str, Any]:
    """Express a behavior as a conditional on its gating behavior.

    Making a digital payment requires an account, so the generator draws account
    ownership first and digital payment only for account holders. But Findex
    publishes digital payment as a share of *all* adults. Feeding the published
    rate into a gated draw would multiply the two together and undershoot.

    So the base becomes P(behavior | gate) = P(behavior) / P(gate), and the
    gradients become the residual after the gate has already applied its own —
    otherwise the same demographic effect is counted twice, once through account
    ownership and again through the behavior.
    """
    conditional_rate = min(behavior["overall_rate"] / gate_rate, 0.999) if gate_rate > 0 else 0.0
    dimensions = {}
    for dimension, categories in behavior["dimensions"].items():
        gate_categories = gate["dimensions"].get(dimension, {})
        dimensions[dimension] = {
            category: {
                "rate": entry["rate"],
                "logit_shift": entry["logit_shift"] - gate_categories.get(category, {}).get("logit_shift", 0.0),
            }
            for category, entry in categories.items()
        }
    return {
        "overall_rate": conditional_rate,
        "base_logit": _logit(conditional_rate),
        "dimensions": dimensions,
        "conditional_on": "account_ownership",
    }


def conditional_probability(behavior: dict[str, Any], categories: dict[str, str]) -> float:
    """P(behavior | categories) under the additive log-odds assumption.

    Categories the source does not break down by are ignored rather than guessed.
    """
    logit = behavior["base_logit"]
    for dimension, category in categories.items():
        entry = behavior["dimensions"].get(dimension, {}).get(category)
        if entry is not None:
            logit += entry["logit_shift"]
    return _sigmoid(logit)


def calibrate_intercept(shifts: list[float], target_rate: float, *, tolerance: float = 1e-9) -> float:
    """Find the intercept that makes the population's mean probability hit target.

    Centering the shifts is necessary but not sufficient. Even with a mean shift
    of zero, the mean *probability* is not the probability at the mean shift,
    because the logistic curve is concave above 0.5 and convex below it. The
    correlations that IPF deliberately introduces widen the spread of shifts and
    push the two further apart. Left alone the generated account-ownership rate
    settles near 64% against a published 70.6% — a six-point error that no amount
    of sampling would reveal as a bug rather than noise.

    Solving for the intercept fixes the marginal exactly while leaving every
    relative gradient — the part Findex actually measured — untouched. Bisection
    is used because the mean probability is monotone in the intercept, so it
    always converges and cannot overshoot.

    Vectorised with numpy because the population can be large. A pure-Python mean
    over the shift list costs 200 bisection steps times one sigmoid per customer
    per behavior; at the full release's 1.83 million customers and six behaviors
    that is over two billion interpreter-level operations, and the build does not
    finish. The same arithmetic in numpy takes a few seconds.
    """
    if len(shifts) == 0:
        return _logit(target_rate)
    values = np.asarray(shifts, dtype=float)

    def mean_probability(intercept: float) -> float:
        # Computed as expit via tanh, which is numerically stable for large
        # magnitudes where a naive exp() would overflow.
        return float(np.mean(0.5 * (1.0 + np.tanh(0.5 * (intercept + values)))))

    low, high = -40.0, 40.0
    for _ in range(200):
        middle = (low + high) / 2
        if mean_probability(middle) < target_rate:
            low = middle
        else:
            high = middle
        if high - low < tolerance:
            break
    return (low + high) / 2


def shift_for(behavior: dict[str, Any], categories: dict[str, str]) -> float:
    """The summed log-odds shift for one customer, excluding the intercept."""
    total = 0.0
    for dimension, category in categories.items():
        entry = behavior["dimensions"].get(dimension, {}).get(category)
        if entry is not None:
            total += entry["logit_shift"]
    return total


def findex_dimension_margins(population: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Population shares for each dimension Findex breaks results down by.

    These are what `center_shifts` weights by, so they have to be expressed in
    Findex's own categories rather than the finer ones the KYC schema uses.
    """
    age = population["age_band"]["probabilities"]
    young = age.get("15-24", 0.0)
    employment = population["employment_status"]["probabilities"]
    in_labour_force = 1.0 - employment.get("NOT_IN_LABOUR_FORCE", 0.0)
    return {
        "gender": population["gender"]["probabilities"],
        "age_band": {"15-24": young, "25+": 1.0 - young},
        "education": population["education_band"]["probabilities"],
        # Quintiles are equal by construction, so the Findex split is exact.
        "income_group": {"POOREST_40": 0.40, "RICHEST_60": 0.60},
        "urban_rural": population["urban_rural"]["probabilities"],
        "labour_force": {
            "IN_LABOUR_FORCE": in_labour_force,
            "OUT_OF_LABOUR_FORCE": 1.0 - in_labour_force,
        },
    }


def build_all(values: dict[str, Any]) -> dict[str, Any]:
    population = {
        "age_band": age_band_distribution(values),
        "gender": gender_distribution(values),
        "urban_rural": urban_rural_distribution(values),
        "employment_status": employment_status_distribution(values),
        "occupation_group": occupation_distribution(values),
        "education_band": education_distribution(values),
        "income_band": income_band_distribution(values),
    }
    financial = behavior_conditionals(values)
    center_shifts(financial["behaviors"], findex_dimension_margins(population))

    # Behaviors that logically require an account are re-expressed as conditionals
    # on holding one, so the generator can gate them without undershooting.
    account = financial["behaviors"]["account_ownership"]
    for name in ("digital_payment", "formal_saving", "mobile_money_account"):
        if name in financial["behaviors"]:
            financial["behaviors"][name] = residual_behavior(
                financial["behaviors"][name], account, account["overall_rate"]
            )

    return {
        "distributions_version": DISTRIBUTIONS_VERSION,
        "derived_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "World Bank open data API (Global Findex source 28, WDI source 2)",
        "population": population,
        "financial_behavior": financial,
        "unresolved": [
            "P(region) and P(urban_rural | region): sub-national data not in this source.",
            "P(employment_status | age_band): not published at this granularity.",
            "P(occupation_group | age_band, region): not published.",
            "Declared KYC income versus survey income: no source links the two.",
            "Household income relative to GDP per capita: anchor is unadjusted.",
            "Enterprise size and turnover distributions: needs the National Statistics Office.",
        ],
    }


def write_distributions(distributions: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(distributions, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return output
