"""Phase 6 — generate the synthetic individual KYC population.

Attributes are generated **conditionally**, in dependency order, never as
independent draws. The chain is:

    education, employment, residence, income   (jointly, via IPF)
        -> age band and sex                    (independent; no source links them)
        -> occupation                          (conditional on being employed)
        -> account access                      (conditional on all of the above)
        -> digital use, saving, borrowing      (conditional on access)

The joint block at the top is fitted with iterative proportional fitting so each
dimension's published margin is reproduced exactly while their association comes
from one declared parameter. The financial-behavior tail is conditional through
Findex's own published breakdowns.

## No real people, and no realistic identifiers

There is no name, no national ID number, no phone number, no address, and no
date of birth — not hashed, not masked, absent. Every attribute is a band. A
synthetic CCCD number is worse than useless: it looks like a real identifier, so
it invites being treated as one, while carrying no information a band does not.

## What is assumed rather than evidenced

Three things, each registered with an ID and a sensitivity range:

- `ASSUME_INCOME_ASSOCIATION` — the strength of the association between
  education, employment, residence, and income. Sources publish the margins only.
- `ASSUME_ECONOMIC_RANK` — the ordering of employment statuses from least to
  most economically secure.
- `ASSUME_TENURE_DISTRIBUTION` — banking tenure, which no acquired source covers.

Nothing here reads or references an AML label. Customer risk attributes are not
generated, because a KYC field that implies AML would make Phase 14 unfalsifiable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from abm.kyc.ipf import joint_from_margins
from abm.sources.vn_distributions import calibrate_intercept, shift_for

CUSTOMER_ID_FORMAT = "CUS-{:08d}"

# How strongly education, employment, residence, and income move together. The
# margins are evidenced; this number is not. 0.0 would mean independence.
ASSUME_INCOME_ASSOCIATION = 0.45
ASSUME_INCOME_ASSOCIATION_SENSITIVITY = (0.0, 0.9)

# Where each employment status sits on a shared economic-security ordering.
# Ordinal only: the spacing carries no claim, just the order.
ASSUME_ECONOMIC_RANK: dict[str, float] = {
    "EMPLOYER": 2.0,
    "WAGE_WORKER": 1.0,
    "OWN_ACCOUNT": 0.0,
    "UNPAID_FAMILY": -1.0,
    "UNEMPLOYED": -1.5,
    "NOT_IN_LABOUR_FORCE": -1.0,
}

_EDUCATION_RANK = {"SECONDARY_OR_MORE": 1.0, "PRIMARY_OR_LESS": -1.0}
_RESIDENCE_RANK = {"URBAN": 1.0, "RURAL": -1.0}
_INCOME_RANK = {"Q1": -2.0, "Q2": -1.0, "Q3": 0.0, "Q4": 1.0, "Q5": 2.0}

# Banking tenure. No acquired source covers it; the shape is a declared guess.
ASSUME_TENURE_DISTRIBUTION = {"<1Y": 0.18, "1-3Y": 0.29, "3-5Y": 0.24, "5Y+": 0.29}

# Findex breaks digital payment into a single yes/no. Segmenting further needs a
# rule, so the rule is stated: a customer who transacts digitally and saves
# formally is a heavier user than one who only transacts digitally.
DIGITAL_SEGMENTS = ("NONE", "LOW", "MEDIUM", "HIGH")


@dataclass(slots=True)
class GenerationConfig:
    population: int = 5000
    seed: int = 20260807
    income_association: float = ASSUME_INCOME_ASSOCIATION
    assumptions: dict[str, Any] = field(default_factory=dict)


def _rng(seed: int, stream: str) -> np.random.Generator:
    """A named random stream.

    Deriving each component's seed from the release seed plus a name means adding
    a draw in one component cannot shift every later component's output — the
    thing that makes "deterministic" releases quietly stop reproducing.
    """
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _choose(rng: np.random.Generator, probabilities: dict[str, float], size: int) -> np.ndarray:
    keys = list(probabilities)
    weights = np.array([probabilities[key] for key in keys], dtype=float)
    weights = weights / weights.sum()
    return np.array(keys, dtype=object)[rng.choice(len(keys), size=size, p=weights)]


def build_socioeconomic_joint(
    distributions: dict[str, Any], strength: float
) -> tuple[np.ndarray, dict[str, list[str]]]:
    """Fit the joint over education, employment, residence, and income."""
    population = distributions["population"]
    margins = {
        "education_band": population["education_band"]["probabilities"],
        "employment_status": population["employment_status"]["probabilities"],
        "urban_rural": population["urban_rural"]["probabilities"],
        "income_band": population["income_band"]["probabilities"],
    }
    ranks = {
        "education_band": _EDUCATION_RANK,
        "employment_status": ASSUME_ECONOMIC_RANK,
        "urban_rural": _RESIDENCE_RANK,
        "income_band": _INCOME_RANK,
    }
    return joint_from_margins(margins, ranks, strength)


def generate_individuals(distributions: dict[str, Any], config: GenerationConfig) -> list[dict[str, Any]]:
    joint, order = build_socioeconomic_joint(distributions, config.income_association)
    population = distributions["population"]
    behaviors = distributions["financial_behavior"]["behaviors"]

    rng = _rng(config.seed, "individual.socioeconomic")
    flat = joint.ravel() / joint.sum()
    picks = rng.choice(len(flat), size=config.population, p=flat)
    indices = np.unravel_index(picks, joint.shape)
    dimensions = list(order)
    drawn = {
        dimension: np.array(order[dimension], dtype=object)[indices[axis]] for axis, dimension in enumerate(dimensions)
    }

    age_rng = _rng(config.seed, "individual.age")
    gender_rng = _rng(config.seed, "individual.gender")
    ages = _choose(age_rng, population["age_band"]["probabilities"], config.population)
    genders = _choose(gender_rng, population["gender"]["probabilities"], config.population)

    occupation_rng = _rng(config.seed, "individual.occupation")
    occupations = _choose(occupation_rng, population["occupation_group"]["probabilities"], config.population)

    tenure_rng = _rng(config.seed, "individual.tenure")
    tenures = _choose(tenure_rng, ASSUME_TENURE_DISTRIBUTION, config.population)

    behavior_rng = _rng(config.seed, "individual.behavior")
    income_means = population["income_band"]["mean_monthly_income_vnd"]

    # Every customer's Findex category vector, built before any behavior is drawn
    # so intercepts can be calibrated against the population that actually exists
    # rather than the one the margins imply.
    profiles = []
    for index in range(config.population):
        employment = drawn["employment_status"][index]
        income_band = drawn["income_band"][index]
        profiles.append(
            {
                "gender": genders[index],
                "age_band": "15-24" if ages[index] == "15-24" else "25+",
                "education": drawn["education_band"][index],
                "income_group": "POOREST_40" if income_band in ("Q1", "Q2") else "RICHEST_60",
                "urban_rural": drawn["urban_rural"][index],
                "labour_force": ("IN_LABOUR_FORCE" if employment != "NOT_IN_LABOUR_FORCE" else "OUT_OF_LABOUR_FORCE"),
            }
        )

    wage_worker = [drawn["employment_status"][index] == "WAGE_WORKER" for index in range(config.population)]
    account = _draw_behavior(behaviors["account_ownership"], profiles, behavior_rng)
    digital = _draw_behavior(behaviors["digital_payment"], profiles, behavior_rng, gate=account)
    saves = _draw_behavior(behaviors["formal_saving"], profiles, behavior_rng, gate=account)
    mobile_money = _draw_behavior(behaviors["mobile_money_account"], profiles, behavior_rng, gate=account)
    borrows = _draw_behavior(behaviors["borrowed_any"], profiles, behavior_rng)
    # Asked only of wage workers, so the source used is the one whose denominator
    # is wage recipients rather than all adults.
    salary_gate = [held and is_wage for held, is_wage in zip(account, wage_worker, strict=True)]
    salary_into_account = _draw_behavior(
        behaviors["wages_into_account_given_wages"],
        profiles,
        behavior_rng,
        gate=salary_gate,
        denominator=wage_worker,
    )

    customers = []
    for index in range(config.population):
        education = drawn["education_band"][index]
        employment = drawn["employment_status"][index]
        residence = drawn["urban_rural"][index]
        income_band = drawn["income_band"][index]
        age_band = ages[index]
        employed = employment in ("WAGE_WORKER", "OWN_ACCOUNT", "EMPLOYER", "UNPAID_FAMILY")

        has_account = account[index]
        customers.append(
            {
                "customer_id": CUSTOMER_ID_FORMAT.format(index + 1),
                "customer_type": "INDIVIDUAL",
                "age_band": age_band,
                "gender": genders[index],
                "education_band": education,
                "urban_rural": residence,
                "occupation_group": occupations[index] if employed else None,
                "employment_status": employment,
                "income_band": income_band,
                # Assigned to everyone, including people outside the labour
                # force. The quintiles are per-capita *household* income, so a
                # retired parent or a student has one; it is money accruing to
                # them, not wages they earn. Withholding it here would leave a
                # quarter of the population with no basis for calibration, and
                # Findex shows 41% of adults outside the labour force hold an
                # account — those accounts are funded by something.
                "expected_monthly_income_vnd": income_means[income_band],
                "income_is_own_earnings": employed,
                "financial_access_segment": _access_segment(has_account, saves[index], borrows[index]),
                "digital_usage_segment": _digital_segment(has_account, digital[index], mobile_money[index]),
                "has_bank_account": has_account,
                "uses_digital_payment": digital[index],
                "has_formal_saving": saves[index],
                "has_formal_borrowing": borrows[index],
                "has_mobile_money": mobile_money[index],
                "salary_paid_into_account": salary_into_account[index],
                "customer_tenure_band": tenures[index],
                "residency_status": "RESIDENT",
            }
        )
    return customers


def _draw_behavior(
    behavior: dict[str, Any],
    profiles: list[dict[str, str]],
    rng: np.random.Generator,
    *,
    gate: list[bool] | None = None,
    denominator: list[bool] | None = None,
) -> list[bool]:
    """Draw one behavior for the whole population, hitting its published rate.

    `gate` is who *can* be true — you cannot make a digital payment without an
    account. `denominator` is who the published rate is a share *of*. They are
    usually the same, and then the target is used as-is.

    They come apart for salary into an account. Findex reports 80.9% of private
    wage recipients are paid into an account, and its denominator is all wage
    recipients — including those with no account, who are paid in cash and are
    part of why the figure is not higher. The gate is narrower than the
    denominator, so the rate has to be scaled up over the gated subset for the
    share of the denominator to come out right. Skipping this leaves the
    generated rate at 74.5% against a published 80.9%.
    """
    eligible = list(range(len(profiles))) if gate is None else [i for i, open_ in enumerate(gate) if open_]
    if not eligible:
        return [False] * len(profiles)

    target = behavior["overall_rate"]
    if denominator is not None:
        base_count = sum(denominator)
        target = min(target * base_count / len(eligible), 0.999) if len(eligible) else 0.0

    shifts = [shift_for(behavior, profiles[index]) for index in eligible]
    intercept = calibrate_intercept(shifts, target)

    outcome = [False] * len(profiles)
    for index, shift in zip(eligible, shifts, strict=True):
        outcome[index] = rng.random() < 1.0 / (1.0 + np.exp(-(intercept + shift)))
    return outcome


def _access_segment(has_account: bool, saves: bool, borrows: bool) -> str:
    if not has_account:
        return "UNBANKED"
    if saves and borrows:
        return "FULL"
    if saves or borrows:
        return "BASIC"
    return "TRANSACTIONAL"


def _digital_segment(has_account: bool, digital: bool, mobile_money: bool) -> str:
    if not has_account or not digital:
        return "NONE" if not digital else "LOW"
    return "HIGH" if mobile_money else "MEDIUM"


def assumption_register() -> list[dict[str, Any]]:
    """Every non-evidenced choice this module makes, in one place."""
    return [
        {
            "assumption_id": "ASSUME_INCOME_ASSOCIATION",
            "description": (
                "Strength of association between education, employment status, residence, and income quintile."
            ),
            "value": ASSUME_INCOME_ASSOCIATION,
            "sensitivity_range": list(ASSUME_INCOME_ASSOCIATION_SENSITIVITY),
            "why_not_evidenced": (
                "Sources publish each margin separately and never the joint. "
                "IPF keeps all four margins exact regardless of this value."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_ECONOMIC_RANK",
            "description": "Ordering of employment statuses by economic security.",
            "value": ASSUME_ECONOMIC_RANK,
            "why_not_evidenced": "No acquired source cross-tabulates employment status with income.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_TENURE_DISTRIBUTION",
            "description": "Distribution of banking relationship tenure.",
            "value": ASSUME_TENURE_DISTRIBUTION,
            "why_not_evidenced": "No acquired source covers tenure at a single bank.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_LOGIT_ADDITIVITY",
            "description": ("Findex demographic breakdowns combine as independent additive shifts in log-odds."),
            "why_not_evidenced": "Findex publishes one-dimension breakdowns, never the joint.",
            "confidence": "medium",
        },
        {
            "assumption_id": "ASSUME_EDUCATION_MAPPING",
            "description": (
                "WDI 'at least lower secondary attainment' is treated as Findex's 'secondary education or more'."
            ),
            "why_not_evidenced": "The two classifications are close but not defined identically.",
            "confidence": "medium",
        },
        {
            "assumption_id": "ASSUME_AGE_INDEPENDENCE",
            "description": ("Age band is drawn independently of employment, income, and education."),
            "why_not_evidenced": (
                "No acquired source cross-tabulates age with these. Known to be "
                "wrong in reality; recorded as a bias in the validation report."
            ),
            "confidence": "low",
        },
    ]
