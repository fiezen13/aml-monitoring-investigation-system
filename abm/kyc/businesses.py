"""Phase 7 — generate the synthetic business KYC population.

Businesses are modelled separately from individuals throughout. Individual income
distributions are never reused for business revenue: a household trader turning
over thirty million dong a month and a wage worker earning thirty million are
different animals, and giving them the same distribution would make every
turnover-based AML feature meaningless.

## What is evidenced here

The split between household businesses and registered enterprises is *derived*,
not assumed. ILO reports own-account workers and employers as separate shares of
employment; a business entity in a bank's book is operated by one or the other,
so their ratio gives the population split directly.

Firm banking behavior comes from the World Bank Enterprise Surveys for Viet Nam
2023 — the share of firms with bank credit, and the share financing working
capital through banks.

Industry mix is derived from employment by sector, with a caveat recorded on the
distribution: sector shares of *employment* are not sector shares of
*establishments*, because a factory employs more people than a shop. Using it
over-weights industry and under-weights services.

## What is assumed

Firm size and turnover distributions are not published by any acquired source.
They use a Pareto shape, which is a well-established regularity for firm sizes
rather than a Vietnamese measurement, and it is registered as such with a
sensitivity range. Legal form within registered enterprises is likewise assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from abm.kyc.individuals import _choose, _rng

BUSINESS_ID_FORMAT = "BIZ-{:08d}"

# Firm sizes follow a heavy right tail across every economy where they have been
# measured. The shape parameter is the assumption; smaller means a heavier tail.
ASSUME_FIRM_SIZE_PARETO_SHAPE = 1.06
ASSUME_FIRM_SIZE_PARETO_SENSITIVITY = (0.9, 1.4)

EMPLOYEE_SIZE_BANDS = ("0", "1-9", "10-49", "50-199", "200+")
_SIZE_BAND_UPPER = {"0": 1, "1-9": 10, "10-49": 50, "50-199": 200, "200+": float("inf")}

# Revenue per employee, in VND per month. Anchored on GDP per worker rather than
# invented, but the ratio of firm turnover to value added is an assumption.
ASSUME_TURNOVER_TO_VALUE_ADDED = 2.5
ASSUME_TURNOVER_TO_VALUE_ADDED_SENSITIVITY = (1.5, 4.0)

# Legal form within registered enterprises. Not published by any acquired source.
ASSUME_REGISTERED_LEGAL_FORM = {"LLC": 0.68, "JSC": 0.24, "PARTNERSHIP": 0.08}

ASSUME_CASH_INTENSITY_BY_INDUSTRY = {
    "AGRICULTURE": {"HIGH": 0.62, "MEDIUM": 0.30, "LOW": 0.08},
    "INDUSTRY": {"HIGH": 0.18, "MEDIUM": 0.47, "LOW": 0.35},
    "SERVICES": {"HIGH": 0.41, "MEDIUM": 0.39, "LOW": 0.20},
}

ASSUME_BUSINESS_AGE = {"<1Y": 0.09, "1-3Y": 0.22, "3-10Y": 0.41, "10Y+": 0.28}


@dataclass(slots=True)
class BusinessConfig:
    population: int = 800
    seed: int = 20260807
    pareto_shape: float = ASSUME_FIRM_SIZE_PARETO_SHAPE
    turnover_multiple: float = ASSUME_TURNOVER_TO_VALUE_ADDED


def household_vs_registered(values: dict[str, Any]) -> dict[str, float]:
    """Split derived from the own-account to employer ratio in employment.

    An own-account worker runs a business with no employees; an employer runs one
    with them. Both appear in a bank's book as a business customer, so their
    relative frequency in the labour force is the relative frequency of the two
    kinds of business entity.
    """
    employers = float(values["employment_employers"]["value"])
    self_employed = float(values["employment_self_employed"]["value"])
    family = float(values["employment_family_workers"]["value"])
    own_account = max(self_employed - employers - family, 0.0)
    total = own_account + employers
    return {
        "HOUSEHOLD_BUSINESS": own_account / total,
        "REGISTERED_ENTERPRISE": employers / total,
    }


def _draw_employee_counts(rng: np.random.Generator, size: int, shape: float) -> np.ndarray:
    """Pareto-distributed employee counts, at least one employee."""
    return np.floor(rng.pareto(shape, size=size) + 1).astype(int)


def _size_band(count: int) -> str:
    for band in EMPLOYEE_SIZE_BANDS:
        if count < _SIZE_BAND_UPPER[band]:
            return band
    return "200+"


def _revenue_band(monthly_turnover: float) -> str:
    """Bands in VND per month, on a roughly half-order-of-magnitude ladder."""
    thresholds = [
        (50_000_000, "<50M"),
        (200_000_000, "50M-200M"),
        (1_000_000_000, "200M-1B"),
        (5_000_000_000, "1B-5B"),
        (20_000_000_000, "5B-20B"),
    ]
    for limit, label in thresholds:
        if monthly_turnover < limit:
            return label
    return "20B+"


def generate_businesses(
    distributions: dict[str, Any], values: dict[str, Any], config: BusinessConfig
) -> list[dict[str, Any]]:
    population = distributions["population"]
    kind_split = household_vs_registered(values)

    kind_rng = _rng(config.seed, "business.kind")
    industry_rng = _rng(config.seed, "business.industry")
    size_rng = _rng(config.seed, "business.size")
    region_rng = _rng(config.seed, "business.region")
    age_rng = _rng(config.seed, "business.age")
    form_rng = _rng(config.seed, "business.legal_form")
    cash_rng = _rng(config.seed, "business.cash")
    bank_rng = _rng(config.seed, "business.banking")

    kinds = _choose(kind_rng, kind_split, config.population)
    industries = _choose(industry_rng, population["occupation_group"]["probabilities"], config.population)
    regions = _choose(region_rng, population["urban_rural"]["probabilities"], config.population)
    ages = _choose(age_rng, ASSUME_BUSINESS_AGE, config.population)
    forms = _choose(form_rng, ASSUME_REGISTERED_LEGAL_FORM, config.population)
    employees = _draw_employee_counts(size_rng, config.population, config.pareto_shape)

    # GDP per worker per month, as the anchor for value added per employee.
    annual_per_capita = float(values["gdp_per_capita_vnd"]["value"])
    participation = float(values["labour_force_participation"]["value"]) / 100.0
    monthly_value_added_per_worker = annual_per_capita / 12.0 / max(participation, 0.01)

    credit_rate = float(values["firms_with_bank_credit"]["value"]) / 100.0
    working_capital_rate = float(values["firms_using_banks_for_working_capital"]["value"]) / 100.0
    female_owned_rate = float(values["firms_with_female_ownership"]["value"]) / 100.0
    female_rng = _rng(config.seed, "business.female_ownership")

    businesses = []
    for index in range(config.population):
        household = kinds[index] == "HOUSEHOLD_BUSINESS"
        headcount = 0 if household else int(employees[index])
        industry = industries[index]

        # Own-account businesses are one working owner; registered firms scale
        # with headcount. Turnover is value added times the assumed multiple.
        workers = 1 if household else max(headcount, 1)
        monthly_turnover = workers * monthly_value_added_per_worker * config.turnover_multiple
        cash_intensity = _choose(cash_rng, ASSUME_CASH_INTENSITY_BY_INDUSTRY[industry], 1)[0]

        businesses.append(
            {
                "business_id": BUSINESS_ID_FORMAT.format(index + 1),
                "business_kind": kinds[index],
                "legal_form": "SOLE_PROPRIETOR" if household else forms[index],
                "industry_group": industry,
                "urban_rural": regions[index],
                "business_age_band": ages[index],
                "employee_size_band": _size_band(headcount),
                "employee_count": headcount,
                "revenue_band": _revenue_band(monthly_turnover),
                "expected_monthly_turnover_vnd": round(monthly_turnover),
                "cash_intensity_band": cash_intensity,
                "digital_payment_intensity": _digital_intensity(household, headcount),
                "domestic_international_profile": _international_profile(industry, headcount),
                "has_bank_credit": bank_rng.random() < credit_rate,
                "uses_bank_working_capital": bank_rng.random() < working_capital_rate,
                "has_female_ownership": female_rng.random() < female_owned_rate,
            }
        )
    return businesses


def _digital_intensity(household: bool, headcount: int) -> str:
    if household:
        return "LOW"
    if headcount >= 50:
        return "HIGH"
    return "MEDIUM"


def _international_profile(industry: str, headcount: int) -> str:
    """Only larger industrial firms are treated as internationally active.

    Vietnam's exports concentrate in manufacturing, so agriculture and services
    at household scale are domestic. The thresholds are assumptions.
    """
    if industry == "INDUSTRY" and headcount >= 50:
        return "INTERNATIONAL_HEAVY"
    if headcount >= 10:
        return "MIXED"
    return "DOMESTIC_ONLY"


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_FIRM_SIZE_PARETO",
            "description": "Employee counts follow a Pareto distribution.",
            "value": ASSUME_FIRM_SIZE_PARETO_SHAPE,
            "sensitivity_range": list(ASSUME_FIRM_SIZE_PARETO_SENSITIVITY),
            "why_not_evidenced": (
                "No acquired source publishes Vietnamese firm size bands. The "
                "Pareto shape is a cross-country regularity, not a measurement of "
                "Viet Nam."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_TURNOVER_TO_VALUE_ADDED",
            "description": "Firm turnover as a multiple of value added.",
            "value": ASSUME_TURNOVER_TO_VALUE_ADDED,
            "sensitivity_range": list(ASSUME_TURNOVER_TO_VALUE_ADDED_SENSITIVITY),
            "why_not_evidenced": "Turnover is not published; only value added is.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_REGISTERED_LEGAL_FORM",
            "description": "Legal form mix within registered enterprises.",
            "value": ASSUME_REGISTERED_LEGAL_FORM,
            "why_not_evidenced": "Needs the National Statistics Office enterprise tables.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_CASH_INTENSITY_BY_INDUSTRY",
            "description": "Cash intensity conditional on industry group.",
            "value": ASSUME_CASH_INTENSITY_BY_INDUSTRY,
            "why_not_evidenced": ("SBV publishes system-wide payment aggregates, not cash intensity by industry."),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_INDUSTRY_FROM_EMPLOYMENT",
            "description": ("Sector shares of employment are used as sector shares of business establishments."),
            "why_not_evidenced": (
                "Establishment counts by sector are not in the acquired sources. "
                "This over-weights industry, which employs more people per firm."
            ),
            "confidence": "low",
        },
    ]
