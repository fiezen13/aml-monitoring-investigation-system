"""Turn the matched world into the release's CSV files.

Split from `build.py` because assembling the world and writing it out are
different concerns, and the write step is where every schema decision lives.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from abm.canonical import enrichment, ground_truth, hard_negatives, splits
from abm.canonical.stream import AccountColumns, append_hard_negative_transactions, stream_transactions
from abm.canonical.transactions import (
    ASSUME_DIURNAL_PROFILE,
    RebuildConfig,
    to_epoch,
)
from abm.profiling.ibm_patterns import normalize_account_key, parse_patterns

SECONDS_PER_DAY = 86_400

BANK_VIEW_COLUMNS: dict[str, list[str]] = {
    "customers": [
        "customer_id",
        "customer_type",
        "age_band",
        "gender",
        "education_band",
        "urban_rural",
        "occupation_group",
        "employment_status",
        "income_band",
        "expected_monthly_income_vnd",
        "income_is_own_earnings",
        "financial_access_segment",
        "digital_usage_segment",
        "has_bank_account",
        "uses_digital_payment",
        "has_formal_saving",
        "has_formal_borrowing",
        "has_mobile_money",
        "salary_paid_into_account",
        "customer_tenure_band",
        "residency_status",
    ],
    "businesses": [
        "business_id",
        "business_kind",
        "legal_form",
        "industry_group",
        "urban_rural",
        "business_age_band",
        "employee_size_band",
        "employee_count",
        "revenue_band",
        "expected_monthly_turnover_vnd",
        "cash_intensity_band",
        "digital_payment_intensity",
        "domestic_international_profile",
        "has_bank_credit",
        "uses_bank_working_capital",
        "has_female_ownership",
    ],
    "accounts": [
        "account_id",
        "owner_id",
        "owner_type",
        "account_type",
        "currency",
        "open_date",
        "status",
        "behavior_archetype",
        "expected_monthly_turnover_vnd",
    ],
    "transactions": [
        "transaction_id",
        "event_id",
        "schema_version",
        "timestamp",
        "source_account_id",
        "destination_account_id",
        "source_counterparty_token",
        "destination_counterparty_token",
        "amount",
        "currency",
        "payment_format",
        "channel",
        "transaction_type",
        "merchant_id",
        "time_partition",
    ],
    "devices": ["device_id", "customer_id", "device_type", "first_seen", "last_seen"],
    "merchants": ["merchant_id", "merchant_category", "urban_rural", "operated_by_business_id"],
    "relationships": [
        "relationship_id",
        "source_entity_id",
        "source_entity_type",
        "destination_entity_id",
        "destination_entity_type",
        "relationship_type",
        "valid_from",
        "valid_to",
    ],
}

GROUND_TRUTH_COLUMNS: dict[str, list[str]] = {
    "entity_labels": [
        "entity_id",
        "entity_type",
        "label_type",
        "label_value",
        "active_from",
        "active_to",
        "source",
    ],
    "transaction_labels": [
        "transaction_id",
        "is_laundering",
        "scenario_id",
        "scenario_stage",
        "source",
    ],
    "scenario_instances": [
        "scenario_id",
        "network_id",
        "typology",
        "typology_parameter",
        "transaction_count",
        "account_count",
        "first_event",
        "last_event",
        "split",
        "benchmark_quota",
        "prevalence_claim",
        "source",
    ],
    "criminal_networks": [
        "network_id",
        "scenario_id",
        "member_entity_id",
        "member_entity_type",
        "owner_entity_id",
        "owner_entity_type",
        "true_role",
        "source",
    ],
    "hard_negative_instances": [
        "hard_negative_id",
        "family",
        "entity_id",
        "entity_type",
        "account_id",
        "transaction_count",
        "legitimate_explanation",
        "observable_collision",
        "ground_truth",
        "split",
        "source",
    ],
}

SPLIT_COLUMNS = ["entity_id", "entity_type", "split"]

# Columns that must never appear in Bank View. Checked by the leakage gate.
FORBIDDEN_IN_BANK_VIEW = (
    "is_laundering",
    "scenario_id",
    "true_role",
    "criminal_network_id",
    "network_id",
    "label_value",
    "typology",
    "hard_negative_id",
    "account_key",
)


def materialize(
    *,
    release: Path,
    started: datetime,
    config: Any,
    selection: Any,
    raw: Any,
    accounts: list[dict[str, Any]],
    account_by_key: dict[str, dict[str, Any]],
    customers: list[dict[str, Any]],
    firms: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    transactions_csv: Path,
    patterns_txt: Path,
) -> dict[str, Any]:
    from abm.canonical.build import write_csv

    rebuild = RebuildConfig(seed=config.seed)
    # One stream drives every per-transaction draw. The streaming writer pulls
    # format, channel, merchant, and salary decisions from it in a fixed order,
    # so the sequence is reproducible without four separate generators.
    rng_time = _rng(config.seed, "transactions.stream")

    # ------------------------------------------------------------- transactions
    #
    # Written straight to CSV rather than assembled in memory. At 31.9 million
    # rows a list of dicts costs tens of gigabytes to produce a six-gigabyte
    # file; streaming makes the full release cost about what the small one does.
    merchant_rows, merchant_links = enrichment.build_merchants(firms, config.seed)
    merchant_ids = [row["merchant_id"] for row in merchant_rows]

    columns = AccountColumns(accounts)

    # Index only the pattern transactions — 4,086 of them — and let each row test
    # itself, instead of indexing all 31.9 million so the patterns can find theirs.
    instances = parse_patterns(patterns_txt)
    selected_instances: list[dict[str, Any]] = []
    pattern_lookup: dict[tuple[int, int, int], tuple[str, str]] = {}
    sorted_keys = columns.keys.to_pylist()
    position_of = {key: index for index, key in enumerate(sorted_keys)}

    for instance in instances:
        if instance.index not in selection.selected_pattern_indices:
            continue
        scenario_id = ground_truth.SCENARIO_ID_FORMAT.format(len(selected_instances) + 1)
        network_id = ground_truth.NETWORK_ID_FORMAT.format(len(selected_instances) + 1)
        edges: list[tuple[str, str]] = []
        stage = _stage(instance.typology)
        expected = 0
        for row in instance.transactions:
            source = normalize_account_key(row["from_bank"], row["from_account"])
            destination = normalize_account_key(row["to_bank"], row["to_account"])
            edges.append((source, destination))
            epoch = to_epoch(datetime.strptime(row["timestamp"], "%Y/%m/%d %H:%M"))
            source_position = position_of.get(source, -1)
            target_position = position_of.get(destination, -1)
            pattern_lookup[(source_position, target_position, epoch)] = (scenario_id, stage)
            expected += 1
        timestamps = sorted(row["timestamp"] for row in instance.transactions)
        selected_instances.append(
            {
                "scenario_id": scenario_id,
                "network_id": network_id,
                "typology": instance.typology,
                "typology_parameter": instance.typology_parameter,
                "transaction_count": expected,
                "account_count": len(instance.accounts),
                "first_event": timestamps[0] if timestamps else None,
                "last_event": timestamps[-1] if timestamps else None,
                "edges": edges,
                "members": sorted(instance.accounts),
            }
        )

    stream_stats = stream_transactions(
        raw=raw,
        columns=columns,
        pattern_lookup=pattern_lookup,
        transactions_path=release / "bank_view" / "transactions.csv",
        labels_path=release / "ground_truth" / "transaction_labels.csv",
        transaction_columns=BANK_VIEW_COLUMNS["transactions"],
        label_columns=GROUND_TRUTH_COLUMNS["transaction_labels"],
        merchant_ids=merchant_ids,
        diurnal_profile=ASSUME_DIURNAL_PROFILE,
        international_wire_share=rebuild.international_wire_share,
        rng=rng_time,
        time_partition=splits.time_partition,
    )
    first_day = stream_stats["first_day"]
    last_day = stream_stats["last_day"]
    window_start = stream_stats["window_start"]
    window_end = stream_stats["window_end"]
    flagged_account_ids = stream_stats["flagged_accounts"]

    # ------------------------------------------------------------------ splits
    networks_for_splits = [
        {
            "network_id": entry["network_id"],
            "members": [account_by_key[key]["owner_id"] for key in entry["members"] if key in account_by_key],
        }
        for entry in selected_instances
    ]
    components = splits.network_components([network for network in networks_for_splits if network["members"]])
    entity_ids = [customer["customer_id"] for customer in customers] + [firm["business_id"] for firm in firms]
    assignment = splits.assign_entity_splits(entity_ids, components, config.seed)

    # --------------------------------------------------------- hard negatives
    laundering_entities = {member for network in networks_for_splits for member in network["members"]}
    episodes = hard_negatives.generate_episodes(
        accounts, laundering_entities, day_range=(first_day, last_day), seed=config.seed
    )
    hard_negative_count = append_hard_negative_transactions(
        episodes=episodes,
        account_lookup={account["account_id"]: account for account in accounts},
        transactions_path=release / "bank_view" / "transactions.csv",
        labels_path=release / "ground_truth" / "transaction_labels.csv",
        offset=stream_stats["written"],
        first_day=first_day,
        last_day=last_day,
        rng=_rng(config.seed, "hard_negatives.transactions"),
        time_partition=splits.time_partition,
    )

    # ------------------------------------------------------------- enrichment
    devices, device_links = enrichment.build_devices(customers, window_start, window_end, config.seed)
    ownership = enrichment.build_ownership_relationships(accounts, window_start)
    business_owner = enrichment.build_business_owner_relationships(customers, firms, config.seed)
    relationships = enrichment.finalize_relationships(
        [ownership, device_links, merchant_links, business_owner], window_start
    )

    # ----------------------------------------------------------------- writing
    # Flagged accounts were collected during the streaming pass; the rows are no
    # longer in memory to scan afterwards.
    flagged_accounts = set(flagged_account_ids)
    flagged_accounts.discard(None)

    counts: dict[str, int] = {}
    bank_view = release / "bank_view"
    counts["customers"] = write_csv(customers, bank_view / "customers.csv", BANK_VIEW_COLUMNS["customers"])
    counts["businesses"] = write_csv(firms, bank_view / "businesses.csv", BANK_VIEW_COLUMNS["businesses"])
    counts["accounts"] = write_csv(accounts, bank_view / "accounts.csv", BANK_VIEW_COLUMNS["accounts"])
    counts["transactions"] = stream_stats["written"] + hard_negative_count
    counts["devices"] = write_csv(devices, bank_view / "devices.csv", BANK_VIEW_COLUMNS["devices"])
    counts["merchants"] = write_csv(merchant_rows, bank_view / "merchants.csv", BANK_VIEW_COLUMNS["merchants"])
    counts["relationships"] = write_csv(
        relationships, bank_view / "relationships.csv", BANK_VIEW_COLUMNS["relationships"]
    )

    truth = release / "ground_truth"
    counts["entity_labels"] = write_csv(
        ground_truth.build_entity_labels(accounts, flagged_accounts, window_start, window_end),
        truth / "entity_labels.csv",
        GROUND_TRUTH_COLUMNS["entity_labels"],
    )
    counts["transaction_labels"] = counts["transactions"]
    scenario_splits = {
        entry["scenario_id"]: assignment.get(
            networks_for_splits[index]["members"][0] if networks_for_splits[index]["members"] else "",
            "TRAIN",
        )
        for index, entry in enumerate(selected_instances)
    }
    counts["scenario_instances"] = write_csv(
        ground_truth.build_scenario_instances(selected_instances, scenario_splits),
        truth / "scenario_instances.csv",
        GROUND_TRUTH_COLUMNS["scenario_instances"],
    )
    counts["criminal_networks"] = write_csv(
        ground_truth.build_criminal_networks(selected_instances, account_by_key),
        truth / "criminal_networks.csv",
        GROUND_TRUTH_COLUMNS["criminal_networks"],
    )
    counts["hard_negative_instances"] = write_csv(
        ground_truth.build_hard_negative_instances(episodes, assignment),
        truth / "hard_negative_instances.csv",
        GROUND_TRUTH_COLUMNS["hard_negative_instances"],
    )

    split_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in splits.SPLITS}
    for customer in customers:
        split = assignment[customer["customer_id"]]
        split_rows[split].append({"entity_id": customer["customer_id"], "entity_type": "CUSTOMER", "split": split})
    for firm in firms:
        split = assignment[firm["business_id"]]
        split_rows[split].append({"entity_id": firm["business_id"], "entity_type": "BUSINESS", "split": split})
    for name, rows in split_rows.items():
        counts[f"split_{name.lower()}"] = write_csv(
            rows, release / "splits" / f"{name.lower()}_entities.csv", SPLIT_COLUMNS
        )

    return {
        "release_dir": release,
        "counts": counts,
        "window": {"start": window_start, "end": window_end, "days": last_day - first_day + 1},
        "selection_stats": selection.stats,
        "split_assignment": assignment,
        "networks": networks_for_splits,
        "scenario_instances": selected_instances,
        "accounts": accounts,
        "customers": customers,
        "businesses": firms,
        "transaction_stats": stream_stats,
        "hard_negative_transactions": hard_negative_count,
        "devices": devices,
        "relationships": relationships,
        "merchants": merchant_rows,
        "episodes": episodes,
        "external_counterparties": stream_stats["external_counterparties"],
        "started": started,
    }


def _stage(typology: str) -> str:
    """Coarse laundering stage implied by the typology's shape."""
    if typology in ("FAN-IN", "GATHER-SCATTER"):
        return "PLACEMENT"
    if typology in ("CYCLE", "STACK", "RANDOM", "BIPARTITE", "SCATTER-GATHER"):
        return "LAYERING"
    return "INTEGRATION"


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))
