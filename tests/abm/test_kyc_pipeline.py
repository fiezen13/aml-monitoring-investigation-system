"""Tests for phases 3 to 9: archetypes, sources, KYC, calibration, matching.

These use small hand-built inputs rather than the real 470 MB behavior frame, so
they run in a second and fail for one reason at a time.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from abm.calibration.monetary import (
    CalibrationConfig,
    account_scale_factor,
    calibrate_accounts,
    target_monthly_inflow_vnd,
    verify_ratio_preservation,
)
from abm.kyc.businesses import BusinessConfig, generate_businesses, household_vs_registered
from abm.kyc.individuals import GenerationConfig, generate_individuals
from abm.kyc.ipf import fit, joint_from_margins, ordinal_seed
from abm.matching.statistical import (
    MatchingConfig,
    archetype_propensity,
    expected_behavior_vector,
    match_entities,
)
from abm.sources.vn_distributions import (
    calibrate_intercept,
    center_shifts,
    conditional_probability,
)
from abm.validation import kyc_validation

# --------------------------------------------------------------------------- IPF


def test_ipf_reproduces_both_margins_exactly() -> None:
    """The whole point: the assumption shapes the association, not the margins."""
    rows = np.array([0.3, 0.7])
    columns = np.array([0.4, 0.35, 0.25])
    seed = np.array([[1.0, 2.0, 3.0], [4.0, 1.0, 1.0]])
    fitted = fit(seed, [rows, columns])
    assert fitted.sum(axis=1) == pytest.approx(rows, abs=1e-9)
    assert fitted.sum(axis=0) == pytest.approx(columns, abs=1e-9)


def test_ipf_rejects_margins_describing_different_totals() -> None:
    with pytest.raises(ValueError, match="different totals"):
        fit(np.ones((2, 2)), [np.array([0.5, 0.5]), np.array([0.3, 0.3])])


def test_zero_strength_seed_gives_independence() -> None:
    """Strength 0 must be exactly the independent joint, so the null is reachable."""
    margins = {
        "a": {"low": 0.3, "high": 0.7},
        "b": {"x": 0.6, "y": 0.4},
    }
    ranks = {"a": {"low": -1.0, "high": 1.0}, "b": {"x": -1.0, "y": 1.0}}
    joint, order = joint_from_margins(margins, ranks, strength=0.0)
    assert joint[0, 0] == pytest.approx(0.3 * 0.6, abs=1e-9)
    assert order["a"] == ["low", "high"]


def test_positive_strength_creates_association() -> None:
    margins = {"a": {"low": 0.5, "high": 0.5}, "b": {"x": 0.5, "y": 0.5}}
    ranks = {"a": {"low": -1.0, "high": 1.0}, "b": {"x": -1.0, "y": 1.0}}
    joint, _ = joint_from_margins(margins, ranks, strength=0.8)
    # High-with-high must exceed high-with-low once the ranks agree.
    assert joint[1, 1] > joint[1, 0]
    assert joint.sum() == pytest.approx(1.0)


def test_ordinal_seed_is_symmetric_under_rank_reversal() -> None:
    forward = ordinal_seed([np.array([-1.0, 1.0]), np.array([-1.0, 1.0])], 0.5)
    reversed_ranks = ordinal_seed([np.array([1.0, -1.0]), np.array([1.0, -1.0])], 0.5)
    assert forward == pytest.approx(reversed_ranks[::-1, ::-1])


# ------------------------------------------------------------------ calibration


def test_intercept_calibration_hits_the_target_rate() -> None:
    shifts = [-2.0, -0.5, 0.0, 0.5, 2.0, 1.3, -1.1]
    intercept = calibrate_intercept(shifts, 0.706)
    mean = sum(1 / (1 + math.exp(-(intercept + shift))) for shift in shifts) / len(shifts)
    assert mean == pytest.approx(0.706, abs=1e-6)


def test_uncentered_shifts_would_miss_the_target() -> None:
    """Documents why centering exists: the mean logit is not the logit of the mean."""
    behaviors = {
        "b": {
            "overall_rate": 0.7,
            "base_logit": math.log(0.7 / 0.3),
            "dimensions": {
                "education": {
                    "LOW": {"rate": 0.33, "logit_shift": -1.56},
                    "HIGH": {"rate": 0.75, "logit_shift": 0.24},
                }
            },
        }
    }
    margins = {"education": {"LOW": 0.34, "HIGH": 0.66}}
    before = 0.34 * conditional_probability(behaviors["b"], {"education": "LOW"}) + 0.66 * conditional_probability(
        behaviors["b"], {"education": "HIGH"}
    )
    center_shifts(behaviors, margins)
    after = 0.34 * conditional_probability(behaviors["b"], {"education": "LOW"}) + 0.66 * conditional_probability(
        behaviors["b"], {"education": "HIGH"}
    )
    assert abs(after - 0.7) < abs(before - 0.7)


def test_scale_factor_converts_the_observation_window_to_a_month() -> None:
    """27.67 days of inflow is not a month; ignoring that biases every amount ~8%."""
    scale = account_scale_factor(1000.0, 1000.0, observation_days=27.67)
    assert scale == pytest.approx(27.67 / 30.0)


def test_scale_factor_refuses_a_zero_inflow_account() -> None:
    with pytest.raises(ValueError, match="too small"):
        account_scale_factor(0.0, 1_000_000.0, observation_days=27.67)


def test_calibration_preserves_every_within_account_ratio() -> None:
    behavior = {
        "total_incoming_amount": 5000.0,
        "total_outgoing_amount": 3000.0,
        "median_incoming_amount": 250.0,
    }
    result = verify_ratio_preservation(behavior, scale=12345.678)
    assert result["preserved"]
    assert result["before"]["inflow_outflow"] == pytest.approx(result["after"]["inflow_outflow"])


def test_business_and_individual_use_different_income_bases() -> None:
    config = CalibrationConfig()
    individual = target_monthly_inflow_vnd({"expected_monthly_income_vnd": 10_000_000}, config)
    business = target_monthly_inflow_vnd({"expected_monthly_turnover_vnd": 10_000_000}, config)
    assert individual != business


def test_uncalibratable_accounts_are_flagged_not_defaulted() -> None:
    """A missing scale must stay missing; a fabricated default would be invisible."""
    matches = [
        {"entity": {"expected_monthly_income_vnd": 8_000_000}, "behavior": {"total_incoming_amount": 0.0}},
        {"entity": {}, "behavior": {"total_incoming_amount": 500.0}},
    ]
    calibrated = calibrate_accounts(matches, CalibrationConfig())
    assert all(row["scale_factor"] is None for row in calibrated)
    assert all(row["uncalibrated_reason"] for row in calibrated)


# ---------------------------------------------------------------------- matching


def _archetypes() -> list[dict]:
    def make(name: str, flow: float, fan: float, rhythm: float, currency: float) -> dict:
        return {
            "archetype": name,
            "centroid_scaled": {
                "flow_direction_balance": flow,
                "fan_in_ratio": fan,
                "fan_out_ratio": fan,
                "log_transactions_per_active_day": rhythm,
                "activity_density": rhythm,
                "log_distinct_currencies": currency,
                "dominant_format_share": 0.0,
            },
        }

    return [
        make("INBOUND", 1.0, -0.4, 0.0, -0.2),
        make("OUTBOUND_BURSTY", -0.9, -0.3, 0.8, -0.2),
        make("WIDE_FAN_IN", -1.5, 2.5, -0.5, -0.2),
        make("MULTI_CURRENCY", -0.3, 0.0, 0.7, 4.5),
    ]


def _accounts(count: int) -> dict[str, list[dict]]:
    return {
        archetype["archetype"]: [
            {
                "account_key": f"{archetype['archetype']}:{index}",
                "turnover_amount": 1000.0 * (index + 1),
                "transaction_count": 10 + index,
            }
            for index in range(count)
        ]
        for archetype in _archetypes()
    }


def test_propensity_is_a_distribution_favouring_the_closest_archetype() -> None:
    centroids = np.array([[1.0, 0.0], [-1.0, 0.0]])
    weights = archetype_propensity(np.array([0.9, 0.0]), centroids, temperature=1.0)
    assert weights.sum() == pytest.approx(1.0)
    assert weights[0] > weights[1]


def test_expected_behavior_never_reads_a_risk_or_label_field() -> None:
    """Guards the matcher's core rule at the level of its inputs."""
    entity = {
        "customer_type": "INDIVIDUAL",
        "employment_status": "WAGE_WORKER",
        "digital_usage_segment": "HIGH",
        "income_band": "Q4",
        "is_laundering": 1,
        "risk_rating": "HIGH",
    }
    baseline = expected_behavior_vector(entity)
    without = expected_behavior_vector(
        {key: value for key, value in entity.items() if key not in ("is_laundering", "risk_rating")}
    )
    assert baseline == pytest.approx(without)


def test_matching_never_reuses_an_account() -> None:
    entities = [
        {
            "customer_id": f"CUS-{i:08d}",
            "customer_type": "INDIVIDUAL",
            "employment_status": "WAGE_WORKER",
            "digital_usage_segment": "MEDIUM",
            "income_band": "Q3",
        }
        for i in range(40)
    ]
    matches = match_entities(entities, _accounts(30), _archetypes(), MatchingConfig())
    keys = [match["behavior"]["account_key"] for match in matches]
    assert len(keys) == len(set(keys)) == 40


def test_matching_raises_rather_than_reusing_when_capacity_runs_out() -> None:
    entities = [
        {
            "customer_id": f"CUS-{i:08d}",
            "customer_type": "INDIVIDUAL",
            "employment_status": "WAGE_WORKER",
            "digital_usage_segment": "MEDIUM",
            "income_band": "Q3",
        }
        for i in range(50)
    ]
    with pytest.raises(RuntimeError, match="capacity"):
        match_entities(entities, _accounts(10), _archetypes(), MatchingConfig())


def test_matching_exposes_a_hash_not_the_ibm_account_id() -> None:
    entities = [
        {
            "customer_id": "CUS-00000001",
            "customer_type": "INDIVIDUAL",
            "employment_status": "WAGE_WORKER",
            "digital_usage_segment": "LOW",
            "income_band": "Q2",
        }
    ]
    match = match_entities(entities, _accounts(5), _archetypes(), MatchingConfig())[0]
    source_key = match["behavior"]["account_key"]
    assert match["ibm_behavior_source_account_hash"] != source_key
    assert source_key not in match["ibm_behavior_source_account_hash"]


def test_matching_spreads_identical_entities_across_accounts() -> None:
    """Identical inputs must not collapse onto one archetype or one account."""
    entities = [
        {
            "customer_id": f"CUS-{i:08d}",
            "customer_type": "INDIVIDUAL",
            "employment_status": "WAGE_WORKER",
            "digital_usage_segment": "MEDIUM",
            "income_band": "Q3",
        }
        for i in range(120)
    ]
    matches = match_entities(entities, _accounts(60), _archetypes(), MatchingConfig())
    assert len({match["archetype"] for match in matches}) > 1


# --------------------------------------------------------------- KYC generation


def _distributions() -> dict:
    return {
        "population": {
            "age_band": {
                "probabilities": {"15-24": 0.2, "25-34": 0.3, "35-44": 0.2, "45-54": 0.15, "55-64": 0.1, "65+": 0.05}
            },
            "gender": {"probabilities": {"M": 0.49, "F": 0.51}},
            "urban_rural": {"probabilities": {"URBAN": 0.4, "RURAL": 0.6}},
            "education_band": {"probabilities": {"SECONDARY_OR_MORE": 0.66, "PRIMARY_OR_LESS": 0.34}},
            "employment_status": {
                "probabilities": {
                    "WAGE_WORKER": 0.33,
                    "OWN_ACCOUNT": 0.28,
                    "EMPLOYER": 0.02,
                    "UNPAID_FAMILY": 0.09,
                    "UNEMPLOYED": 0.01,
                    "NOT_IN_LABOUR_FORCE": 0.27,
                }
            },
            "occupation_group": {"probabilities": {"AGRICULTURE": 0.25, "INDUSTRY": 0.35, "SERVICES": 0.40}},
            "income_band": {
                "probabilities": {"Q1": 0.2, "Q2": 0.2, "Q3": 0.2, "Q4": 0.2, "Q5": 0.2},
                "mean_monthly_income_vnd": {
                    "Q1": 3_500_000,
                    "Q2": 6_200_000,
                    "Q3": 8_400_000,
                    "Q4": 11_500_000,
                    "Q5": 22_700_000,
                },
            },
        },
        "financial_behavior": {
            "behaviors": {
                name: {"overall_rate": rate, "base_logit": math.log(rate / (1 - rate)), "dimensions": {}}
                for name, rate in (
                    ("account_ownership", 0.706),
                    ("digital_payment", 0.884),
                    ("formal_saving", 0.63),
                    ("borrowed_any", 0.432),
                    ("mobile_money_account", 0.55),
                    ("wages_into_account_given_wages", 0.809),
                )
            }
        },
    }


def test_generation_is_deterministic_for_a_seed() -> None:
    config = GenerationConfig(population=300, seed=99)
    assert generate_individuals(_distributions(), config) == generate_individuals(_distributions(), config)


def test_different_seeds_give_different_populations() -> None:
    first = generate_individuals(_distributions(), GenerationConfig(population=300, seed=1))
    second = generate_individuals(_distributions(), GenerationConfig(population=300, seed=2))
    assert first != second


def test_no_customer_carries_a_real_world_identifier() -> None:
    """PII absence is a property worth asserting, not just documenting."""
    customers = generate_individuals(_distributions(), GenerationConfig(population=100))
    forbidden = {
        "name",
        "full_name",
        "national_id",
        "cccd",
        "cmnd",
        "phone",
        "phone_number",
        "address",
        "email",
        "date_of_birth",
        "dob",
        "tax_id",
    }
    for customer in customers:
        assert not forbidden & set(customer)


def test_no_customer_carries_an_aml_field() -> None:
    customers = generate_individuals(_distributions(), GenerationConfig(population=100))
    for customer in customers:
        assert not any(
            token in key.lower()
            for key in customer
            for token in ("launder", "suspicious", "scenario", "risk_rating", "typology")
        )


def test_behaviors_respect_their_logical_gates() -> None:
    customers = generate_individuals(_distributions(), GenerationConfig(population=2000))
    for customer in customers:
        if not customer["has_bank_account"]:
            assert not customer["uses_digital_payment"]
            assert not customer["has_formal_saving"]
            assert not customer["salary_paid_into_account"]
        if customer["employment_status"] != "WAGE_WORKER":
            assert not customer["salary_paid_into_account"]


def test_generated_marginals_track_their_sources() -> None:
    distributions = _distributions()
    customers = generate_individuals(distributions, GenerationConfig(population=6000))
    rate = sum(c["has_bank_account"] for c in customers) / len(customers)
    assert rate == pytest.approx(0.706, abs=0.02)


# ------------------------------------------------------------------- businesses


def test_household_share_is_derived_from_the_employment_split() -> None:
    values = {
        "employment_employers": {"value": 1.9},
        "employment_self_employed": {"value": 53.3},
        "employment_family_workers": {"value": 12.0},
    }
    split = household_vs_registered(values)
    assert split["HOUSEHOLD_BUSINESS"] + split["REGISTERED_ENTERPRISE"] == pytest.approx(1.0)
    assert split["HOUSEHOLD_BUSINESS"] > split["REGISTERED_ENTERPRISE"]


def test_businesses_do_not_reuse_individual_income_bands() -> None:
    values = {
        "employment_employers": {"value": 1.9},
        "employment_self_employed": {"value": 53.3},
        "employment_family_workers": {"value": 12.0},
        "gdp_per_capita_vnd": {"value": 126_000_000.0},
        "labour_force_participation": {"value": 72.8},
        "firms_with_bank_credit": {"value": 29.2},
        "firms_using_banks_for_working_capital": {"value": 38.7},
        "firms_with_female_ownership": {"value": 24.8},
    }
    firms = generate_businesses(_distributions(), values, BusinessConfig(population=200))
    assert all("income_band" not in firm for firm in firms)
    assert all(firm["expected_monthly_turnover_vnd"] > 0 for firm in firms)


# ------------------------------------------------------------------- validation


def test_leakage_check_fails_on_a_perfect_predictor() -> None:
    """The test that protects the dataset's purpose must itself be tested."""
    matches = [
        {
            "entity": {"income_band": "Q5" if index < 60 else "Q1"},
            "entity_type": "CUSTOMER",
            "behavior": {"account_key": f"acct-{index}"},
        }
        for index in range(120)
    ]
    flagged = {f"acct-{index}" for index in range(60)}
    result = kyc_validation.validate_label_leakage(matches, flagged)
    assert result["verdict"].startswith("FAIL")
    assert result["perfect_predictors"]


def test_leakage_check_passes_when_the_label_is_unrelated() -> None:
    """The strides must be coprime.

    An earlier version of this test used income `index % 5` with every tenth
    account flagged. Ten and five share a factor, so every flagged account landed
    in Q1 and the checker correctly reported a perfect predictor — in test data
    that was meant to be unrelated. Eleven and five are coprime, so the label
    spreads evenly across the bands.
    """
    matches = [
        {
            "entity": {"income_band": ["Q1", "Q2", "Q3", "Q4", "Q5"][index % 5]},
            "entity_type": "CUSTOMER",
            "behavior": {"account_key": f"acct-{index}"},
        }
        for index in range(1000)
    ]
    flagged = {f"acct-{index}" for index in range(0, 1000, 11)}
    result = kyc_validation.validate_label_leakage(matches, flagged)
    assert result["verdict"].startswith("PASS")
