"""Run phases 6 to 9 and write small intermediate outputs for validation.

This is not the canonical release. It produces enough of the pipeline to check
that the distributions hold, the matching behaves, and the calibration does what
it claims — before any transaction is rebuilt.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from abm.calibration import monetary
from abm.calibration.monetary import CalibrationConfig, calibrate_accounts, verify_ratio_preservation
from abm.kyc import businesses as business_module
from abm.kyc import individuals as individual_module
from abm.kyc.businesses import BusinessConfig, generate_businesses
from abm.kyc.individuals import GenerationConfig, generate_individuals
from abm.matching import statistical
from abm.matching.statistical import MatchingConfig, match_entities

# Accounts below this transaction count were excluded from archetype derivation
# and must stay excluded here, or the matcher would draw on behavior too sparse
# to have produced a reliable archetype in the first place.
MIN_CANDIDATE_TRANSACTIONS = 10


def load_candidate_accounts(
    archetypes_csv: Path, behavior_csv: Path, *, limit_per_archetype: int = 20_000
) -> dict[str, list[dict[str, Any]]]:
    """Candidate IBM accounts grouped by archetype, with their behavior joined.

    Only the columns matching and calibration need are carried, because the full
    behavior frame is 470 MB and none of the rest is used here.
    """
    assignments = pacsv.read_csv(
        str(archetypes_csv),
        convert_options=pacsv.ConvertOptions(include_columns=["account_key", "archetype", "entity_kind"]),
    )
    behavior = pacsv.read_csv(
        str(behavior_csv),
        convert_options=pacsv.ConvertOptions(
            include_columns=[
                "account_key",
                "transaction_count",
                "turnover_amount",
                "total_incoming_amount",
                "total_outgoing_amount",
                "median_incoming_amount",
                "unique_inbound_counterparties",
                "unique_outbound_counterparties",
                "active_days",
            ]
        ),
    )
    joined = assignments.join(behavior, keys="account_key", join_type="inner")
    joined = joined.filter(pc.greater_equal(joined.column("transaction_count"), MIN_CANDIDATE_TRANSACTIONS))

    pools: dict[str, list[dict[str, Any]]] = {}
    for row in joined.to_pylist():
        pools.setdefault(row["archetype"], []).append(row)
    for name, rows in pools.items():
        # Deterministic order, then a bounded slice: matching only ever needs a
        # few thousand candidates and holding a million costs memory for nothing.
        rows.sort(key=lambda item: item["account_key"])
        pools[name] = rows[:limit_per_archetype]
    return pools


def run(
    distributions: dict[str, Any],
    values: dict[str, Any],
    *,
    archetypes: list[dict[str, Any]],
    candidate_accounts: dict[str, list[dict[str, Any]]],
    output_dir: Path,
    individuals: int = 5000,
    business_count: int = 800,
    seed: int = 20260807,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)

    customers = generate_individuals(distributions, GenerationConfig(population=individuals, seed=seed))
    firms = generate_businesses(distributions, values, BusinessConfig(population=business_count, seed=seed))

    entities: list[dict[str, Any]] = [*customers, *firms]
    matches = match_entities(entities, candidate_accounts, archetypes, MatchingConfig(seed=seed))
    calibrated = calibrate_accounts(matches, CalibrationConfig())

    _write_csv(customers, output_dir / "customers.csv")
    _write_csv(firms, output_dir / "businesses.csv")
    _write_csv(
        [
            {
                "account_id": row["account_id"],
                "owner_id": row["entity_id"],
                "owner_type": row["entity_type"],
                "archetype": row["archetype"],
                "matching_method": row["matching_method"],
                "matching_score": row["matching_score"],
                "archetype_propensity": round(row["archetype_propensity"], 4),
                "target_monthly_inflow_vnd": (
                    round(row["target_monthly_inflow_vnd"]) if row["target_monthly_inflow_vnd"] is not None else None
                ),
                "scale_factor": (round(row["scale_factor"], 8) if row["scale_factor"] is not None else None),
                "uncalibrated_reason": row["uncalibrated_reason"],
            }
            for row in calibrated
        ],
        output_dir / "matched_accounts.csv",
    )
    # Lineage stays out of the release directory and keeps only a hash.
    _write_csv(
        [
            {
                "account_id": row["account_id"],
                "ibm_behavior_source_account_hash": row["ibm_behavior_source_account_hash"],
                "archetype": row["archetype"],
            }
            for row in calibrated
        ],
        output_dir / "account_lineage.csv",
    )

    summary = {
        "generated_at": started.isoformat(timespec="seconds"),
        "seed": seed,
        "counts": {
            "individuals": len(customers),
            "businesses": len(firms),
            "matched_accounts": len(calibrated),
        },
        "assumptions": [
            *individual_module.assumption_register(),
            *business_module.assumption_register(),
            *monetary.assumption_register(),
            *statistical.assumption_register(),
        ],
        "calibration_check": _calibration_check(calibrated),
    }
    (output_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return summary


def _calibration_check(calibrated: list[dict[str, Any]]) -> dict[str, Any]:
    scaled = [row for row in calibrated if row["scale_factor"] is not None]
    preserved = [verify_ratio_preservation(row["behavior"], row["scale_factor"])["preserved"] for row in scaled[:500]]
    return {
        "accounts_calibrated": len(scaled),
        "accounts_uncalibrated": len(calibrated) - len(scaled),
        "uncalibrated_reasons": sorted(
            {row["uncalibrated_reason"] for row in calibrated if row["uncalibrated_reason"]}
        ),
        "ratio_preservation_sampled": len(preserved),
        "ratio_preservation_all_passed": all(preserved),
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    columns = list(rows[0])
    table = pa.table({name: [row.get(name) for row in rows] for name in columns})
    pacsv.write_csv(table, str(path))
