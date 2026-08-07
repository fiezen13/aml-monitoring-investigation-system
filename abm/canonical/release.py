"""Phase 20 — assemble, validate, and seal the small release end to end."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abm.calibration import monetary
from abm.canonical import build as build_module
from abm.canonical import validate as validate_module
from abm.canonical.build import ReleaseConfig, build_release
from abm.canonical.manifest import build_manifest, write_manifest
from abm.kyc import businesses as business_module
from abm.kyc import individuals as individual_module
from abm.matching import statistical
from abm.sources.vn_distributions import build_all
from abm.sources.worldbank import acquire

# Only the fields the source-alignment report compares are kept in memory; the
# full release has 1.83 million customers and holding every column would cost
# more than the comparison is worth.
COMPARED_CUSTOMER_FIELDS = (
    "age_band",
    "gender",
    "urban_rural",
    "education_band",
    "employment_status",
    "income_band",
    "has_bank_account",
    "uses_digital_payment",
    "has_formal_saving",
    "has_formal_borrowing",
    "has_mobile_money",
)

KNOWN_LIMITATIONS = [
    "IBM's entity population is 99.7% businesses (3,017 individual accounts in "
    "2.08 million). Synthetic Vietnamese retail customers are therefore matched "
    "to behavior that business accounts produced.",
    "The observation window is 27.67 days. Monthly seasonality, 30/60/90-day "
    "rolling baselines, and a four-way chronological split are not supported.",
    "Splits are by entity and network. A chronological split would give windows "
    "of roughly 17/6/3/3 days, too short for rolling-window features, so "
    "transactions carry a `time_partition` marker instead of being cut on time.",
    "IBM's payment format predicts its own laundering label at 7.2x lift, so the "
    "column was redrawn from a Vietnamese taxonomy. The redraw is assumption-"
    "driven and does not reproduce any measured Vietnamese channel mix.",
    "IBM assigns times uniformly at random. Time of day was redrawn from an "
    "assumed diurnal curve; dates and event ordering are preserved exactly.",
    "The flagged-entity rate is an artifact of subgraph selection, which seeds on "
    "laundering patterns. It is not a prevalence estimate.",
    "No sub-national region is modelled. The acquired sources are national only.",
    "Age band is drawn independently of employment and income; no acquired source cross-tabulates them.",
    "Firm size and turnover distributions are assumed (Pareto), not measured for Viet Nam.",
    "The income-to-account-turnover multiple, the hinge of the monetary scale, is "
    "unevidenced and set by assumption with a wide sensitivity range.",
    "One account per entity. Accounts held per customer at a single bank is not published by any acquired source.",
    "Transactions between two internal accounts use the geometric mean of the two "
    "endpoint scale factors, so neither account lands exactly on its inflow target.",
]


def build_and_validate(
    *,
    config: ReleaseConfig | None = None,
    transactions_csv: Path = Path("data/raw/ibm-aml/HI-Medium_Trans.csv"),
    patterns_txt: Path = Path("data/raw/ibm-aml/HI-Medium_Patterns.txt"),
    behavior_csv: Path = Path("artifacts/intermediate/ibm_account_behavior_profiles.csv"),
    archetypes_csv: Path = Path("artifacts/intermediate/ibm_account_archetypes.csv"),
    archetype_report_path: Path = Path("artifacts/source_profiles/ibm_archetypes.json"),
    ibm_profile_path: Path = Path("artifacts/source_profiles/ibm_aml_profile.json"),
    worldbank_cache: Path = Path("data/raw/worldbank"),
) -> dict[str, Any]:
    config = config or ReleaseConfig()

    acquisition = acquire(worldbank_cache)
    distributions = build_all(acquisition["values"])
    archetype_report = json.loads(archetype_report_path.read_text(encoding="utf-8"))
    ibm_profile = json.loads(ibm_profile_path.read_text(encoding="utf-8"))

    result = build_release(
        distributions,
        acquisition["values"],
        archetype_report=archetype_report,
        transactions_csv=transactions_csv,
        patterns_txt=patterns_txt,
        behavior_csv=behavior_csv,
        archetypes_csv=archetypes_csv,
        config=config,
    )

    release = result["release_dir"]
    validation = validate_module.run_all(release)
    (release / "reports" / "quality_report.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    comparisons = distribution_comparisons(release, acquisition["values"], distributions, ibm_profile)
    (release / "reports" / "source_alignment_report.json").write_text(
        json.dumps(comparisons, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (release / "reports" / "behavioral_validation.json").write_text(
        json.dumps(
            {
                "monetary": validation["gates"]["monetary"],
                "temporal": validation["gates"]["temporal"],
                "leakage": validation["gates"]["leakage"],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    (release / "reports" / "graph_validation.json").write_text(
        json.dumps(validation["gates"]["graph"], indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    manifest = build_manifest(
        release,
        dataset_id=build_module.DATASET_ID,
        version=config.version,
        seed=config.seed,
        counts=result["counts"],
        window=result["window"],
        selection_stats=result["selection_stats"],
        ibm_source={
            "transactions_file": ibm_profile["source"]["filename"],
            "transactions_sha256": ibm_profile["source"]["sha256"],
            "transactions_rows": ibm_profile["row_count"],
            "patterns_file": patterns_txt.name,
            "accounts_file": "HI-Medium_accounts.csv",
        },
        public_sources=sorted(
            {
                "WB_WDI_VN_POPULATION",
                "WB_WDI_VN_LABOUR_INCOME",
                "WB_ENTERPRISE_SURVEYS_VN_2023",
                "VN_WB_FINDEX_2024",
            }
        ),
        source_registry_version="0.1.0",
        distributions_version=distributions["distributions_version"],
        assumptions=[
            *build_module.assumption_register(),
            *individual_module.assumption_register(),
            *business_module.assumption_register(),
            *monetary.assumption_register(),
            *statistical.assumption_register(),
        ],
        validation=validation,
        known_limitations=KNOWN_LIMITATIONS,
    )
    write_manifest(manifest, release)

    return {
        "release_dir": str(release),
        "counts": result["counts"],
        "validation_verdict": validation["verdict"],
        "failed_gates": validation["failed_gates"],
        "warned_gates": validation["warned_gates"],
        "manifest": str(release / "manifest.json"),
    }


def distribution_comparisons(
    release: Path,
    values: dict[str, Any],
    distributions: dict[str, Any],
    ibm_profile: dict[str, Any],
) -> dict[str, Any]:
    """Compare the release against both of its sources.

    Vietnamese marginals against the published statistics, and transaction
    behavior against the IBM profile the backbone came from. A release that
    matches neither is not a synthesis of the two, it is a third thing.
    """
    from collections import Counter

    from abm.canonical.validate import iter_table

    customers = [
        {key: row[key] for key in COMPARED_CUSTOMER_FIELDS} for row in iter_table(release / "bank_view/customers.csv")
    ]
    total = len(customers) or 1

    population = distributions["population"]
    kyc_rows = []
    for field, name in (
        ("age_band", "age_band"),
        ("gender", "gender"),
        ("urban_rural", "urban_rural"),
        ("education_band", "education_band"),
        ("employment_status", "employment_status"),
        ("income_band", "income_band"),
    ):
        observed = Counter(row[field] for row in customers)
        for category, expected in population[name]["probabilities"].items():
            generated = observed.get(category, 0) / total
            kyc_rows.append(
                {
                    "attribute": field,
                    "category": category,
                    "source_share": round(expected, 6),
                    "generated_share": round(generated, 6),
                    "absolute_error": round(abs(generated - expected), 6),
                }
            )

    for field, indicator in (
        ("has_bank_account", "account_ownership"),
        ("uses_digital_payment", "digital_payment"),
        ("has_formal_saving", "formal_saving"),
        ("has_formal_borrowing", "borrowed_any"),
        ("has_mobile_money", "mobile_money_account"),
    ):
        generated = sum(1 for row in customers if row[field] == "true") / total
        source = float(values[indicator]["value"]) / 100.0
        kyc_rows.append(
            {
                "attribute": field,
                "category": "true",
                "source_share": round(source, 6),
                "generated_share": round(generated, 6),
                "absolute_error": round(abs(generated - source), 6),
            }
        )

    worst = max(kyc_rows, key=lambda row: row["absolute_error"])

    # Counted in one streaming pass; the full release's transactions table is
    # too large to hold while comparing.
    transaction_count = 0
    self_transfers = 0
    for row in iter_table(release / "bank_view/transactions.csv"):
        transaction_count += 1
        if row["source_account_id"] and row["source_account_id"] == row["destination_account_id"]:
            self_transfers += 1

    return {
        "kyc_vs_vietnam_sources": {
            "checks": kyc_rows,
            "max_absolute_error": worst["absolute_error"],
            "worst_check": worst,
            "verdict": "PASS" if worst["absolute_error"] < 0.03 else "REVIEW",
        },
        "transactions_vs_ibm": {
            "release_transactions": transaction_count,
            "release_self_transfer_share": round(self_transfers / max(transaction_count, 1), 6),
            "ibm_self_transfer_share": round(ibm_profile["structure"]["self_transfer_share"], 6),
            "ibm_row_count": ibm_profile["row_count"],
            "payment_format_note": (
                "Payment format is intentionally NOT comparable: IBM's taxonomy was "
                "replaced because it predicted the laundering label at 7.2x lift."
            ),
            "time_of_day_note": (
                "Hour-of-day is intentionally NOT comparable: IBM's times are "
                "uniform random and were redrawn. Dates and ordering are preserved."
            ),
        },
    }
