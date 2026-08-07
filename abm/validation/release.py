"""Deterministic integrity, leakage, behavior, and graph validation."""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from statistics import mean, median
from typing import Any

from abm.models import ReleaseWorld, money
from abm.registry import ParameterRegistry, SimulationConfig


class ValidationError(ValueError):
    """Raised when one or more release gates fail."""


def validate_world(
    world: ReleaseWorld,
    config: SimulationConfig,
    registry: ParameterRegistry,
    *,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def run(name: str, category: str, function: Callable[[], dict[str, Any] | None]) -> None:
        try:
            details = function() or {}
            checks.append({"name": name, "category": category, "status": "PASS", "details": details})
        except (AssertionError, KeyError, ValueError) as exc:
            checks.append({"name": name, "category": category, "status": "FAIL", "details": {"error": str(exc)}})

    run("required_tables_nonempty", "completeness", lambda: _required_tables(world))
    run("primary_keys_unique", "integrity", lambda: _primary_keys(world))
    run("foreign_keys_resolve", "integrity", lambda: _foreign_keys(world))
    run("transaction_endpoints_valid", "integrity", lambda: _transaction_endpoints(world))
    run("transaction_temporal_order", "temporal", lambda: _transaction_time(world, config))
    run("accounting_conservation", "accounting", lambda: _accounting(world))
    run("bank_view_label_leakage", "leakage", lambda: _leakage(world))
    run("entity_and_network_split_isolation", "leakage", lambda: _split_isolation(world))
    run("scenario_ground_truth_consistency", "ground_truth", lambda: _ground_truth(world))
    run("scenario_and_control_coverage", "coverage", lambda: _coverage(world, config, registry))
    run("statistical_calibration", "statistical", lambda: _statistical_calibration(world, registry))
    run("behavioral_field_suitability", "suitability", lambda: _behavioral_suitability(world))
    graph_report: dict[str, Any] = {}

    def graph_check() -> dict[str, Any]:
        nonlocal graph_report
        graph_report = _graph_suitability(world)
        assert graph_report["node_count"] > 0, "transaction graph has no nodes"
        assert graph_report["edge_count"] > 0, "transaction graph has no edges"
        return graph_report

    run("graph_field_suitability", "suitability", graph_check)

    failures = [item for item in checks if item["status"] == "FAIL"]
    report = {
        "dataset_id": config.dataset_id,
        "dataset_version": config.dataset_version,
        "validated_at": datetime.now().astimezone().isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "check_count": len(checks),
        "passed": len(checks) - len(failures),
        "failed": len(failures),
        "checks": checks,
        "behavioral_summary": behavioral_summary(world),
        "graph_summary": graph_report,
    }
    if failures and raise_on_error:
        summary = "; ".join(f"{item['name']}: {item['details']['error']}" for item in failures)
        raise ValidationError(summary)
    return report


def behavioral_summary(world: ReleaseWorld) -> dict[str, Any]:
    amounts = [float(row["amount"]) for row in world.transactions]
    types = Counter(row["transaction_type"] for row in world.transactions)
    channels = Counter(row["channel"] for row in world.transactions)
    splits = Counter(row["dataset_split"] for row in world.transactions)
    observed_devices = sum(row["device_id"] is not None for row in world.transactions)
    observed_purpose = sum(row["purpose_code"] is not None for row in world.transactions)
    return {
        "transaction_count": len(world.transactions),
        "amount_min": min(amounts),
        "amount_median": median(amounts),
        "amount_mean": mean(amounts),
        "amount_max": max(amounts),
        "transaction_type_counts": dict(sorted(types.items())),
        "channel_counts": dict(sorted(channels.items())),
        "split_counts": dict(sorted(splits.items())),
        "device_observation_rate": observed_devices / len(world.transactions),
        "purpose_observation_rate": observed_purpose / len(world.transactions),
    }


def _required_tables(world: ReleaseWorld) -> dict[str, Any]:
    empty = [name for name, count in world.table_counts().items() if count == 0]
    assert not empty, f"empty tables: {empty}"
    return {"table_counts": world.table_counts()}


def _assert_unique(rows: list[dict[str, Any]], columns: tuple[str, ...], table: str) -> None:
    values = [tuple(row[column] for column in columns) for row in rows]
    assert len(values) == len(set(values)), f"duplicate key in {table}: {columns}"


def _primary_keys(world: ReleaseWorld) -> dict[str, Any]:
    specifications = {
        "customers": ("customer_id",),
        "businesses": ("business_id",),
        "accounts": ("account_id",),
        "devices": ("device_id",),
        "merchants": ("merchant_id",),
        "relationships": ("relationship_id",),
        "sessions": ("session_id",),
        "transactions": ("transaction_id",),
        "scenario_instances": ("scenario_instance_id",),
        "networks": ("network_id",),
        "hard_negative_instances": ("hard_negative_instance_id",),
        "hidden_actions": ("hidden_action_id",),
        "hidden_relationships": ("hidden_relationship_id",),
        "entity_labels": ("entity_id", "scenario_instance_id", "role"),
        "transaction_labels": ("transaction_id", "scenario_instance_id", "scenario_stage"),
        "network_members": ("network_id", "entity_id", "role"),
        "split_assignments": ("entity_type", "entity_id"),
        "balance_snapshots": ("account_id", "snapshot_type"),
    }
    for table, columns in specifications.items():
        _assert_unique(getattr(world, table), columns, table)
    return {"tables_checked": len(specifications)}


def _foreign_keys(world: ReleaseWorld) -> dict[str, Any]:
    customers = {row["customer_id"] for row in world.customers}
    businesses = {row["business_id"] for row in world.businesses}
    accounts = {row["account_id"] for row in world.accounts}
    devices = {row["device_id"] for row in world.devices}
    merchants = {row["merchant_id"] for row in world.merchants}
    sessions = {row["session_id"] for row in world.sessions}
    transactions = {row["transaction_id"] for row in world.transactions}
    scenarios = {row["scenario_instance_id"] for row in world.scenario_instances}
    networks = {row["network_id"] for row in world.networks}
    for row in world.accounts:
        assert row["primary_customer_id"] in customers, f"unknown account owner {row['primary_customer_id']}"
    for row in world.businesses:
        assert row["customer_id"] is None or row["customer_id"] in customers
    for row in world.merchants:
        assert row["business_id"] in businesses
    for row in world.sessions:
        assert row["customer_id"] in customers and row["device_id"] in devices
    for row in world.transactions:
        assert row["source_account_id"] is None or row["source_account_id"] in accounts
        assert row["destination_account_id"] is None or row["destination_account_id"] in accounts
        assert row["merchant_id"] is None or row["merchant_id"] in merchants
        assert row["device_id"] is None or row["device_id"] in devices
        assert row["session_id"] is None or row["session_id"] in sessions
    for row in world.transaction_labels:
        assert row["transaction_id"] in transactions
        assert row["scenario_instance_id"] in scenarios and row["network_id"] in networks
    for row in world.entity_labels:
        assert row["scenario_instance_id"] in scenarios and row["network_id"] in networks
    for row in world.scenario_instances:
        assert row["network_id"] in networks
    return {"resolved_reference_types": 10}


def _transaction_endpoints(world: ReleaseWorld) -> dict[str, Any]:
    for row in world.transactions:
        assert bool(row["source_account_id"]) != bool(row["source_counterparty_ref"]), row["transaction_id"]
        assert bool(row["destination_account_id"]) != bool(row["destination_counterparty_ref"]), row["transaction_id"]
        assert row["source_account_id"] != row["destination_account_id"] or row["source_account_id"] is None
        assert row["amount"] > 0 and row["currency"] == "VND"
    return {"transactions_checked": len(world.transactions)}


def _transaction_time(world: ReleaseWorld, config: SimulationConfig) -> dict[str, Any]:
    start = config.simulation_start.astimezone(world.transactions[0]["event_time"].tzinfo)
    end = config.simulation_end.astimezone(world.transactions[0]["event_time"].tzinfo)
    for row in world.transactions:
        assert start <= row["event_time"] <= end, row["transaction_id"]
        assert row["event_time"] <= row["posting_time"] <= row["available_from"], row["transaction_id"]
        assert row["available_from"] <= row["created_at"], row["transaction_id"]
    return {"range_start": start.isoformat(), "range_end": end.isoformat()}


def _accounting(world: ReleaseWorld) -> dict[str, Any]:
    opening = {
        row["account_id"]: row["balance"] for row in world.balance_snapshots if row["snapshot_type"] == "OPENING"
    }
    closing = {
        row["account_id"]: row["balance"] for row in world.balance_snapshots if row["snapshot_type"] == "CLOSING"
    }
    calculated = dict(opening)
    for row in world.transactions:
        if row["source_account_id"]:
            calculated[row["source_account_id"]] -= row["amount"]
        if row["destination_account_id"]:
            calculated[row["destination_account_id"]] += row["amount"]
    mismatches = [account for account, value in calculated.items() if money(value) != closing[account]]
    assert not mismatches, f"balance equation failed for {len(mismatches)} accounts"
    assert all(value >= Decimal("0") for value in closing.values()), "negative closing balance"
    return {"accounts_reconciled": len(calculated), "mismatch_count": 0}


def _leakage(world: ReleaseWorld) -> dict[str, Any]:
    forbidden = {"label", "launder", "scenario_instance", "network_id", "hidden_intent", "true_actor"}
    bank_tables = [
        world.customers,
        world.businesses,
        world.accounts,
        world.devices,
        world.merchants,
        world.relationships,
        world.sessions,
        world.transactions,
        world.balance_snapshots,
    ]
    columns = {column.lower() for rows in bank_tables for column in rows[0]}
    violations = sorted(column for column in columns if any(term in column for term in forbidden))
    assert not violations, f"ground-truth-like Bank View columns: {violations}"
    for row in world.transactions:
        text = " ".join(str(row.get(name) or "").lower() for name in ("purpose_code", "purpose_text"))
        assert "launder" not in text and "synthetic_typology" not in text, row["transaction_id"]
    return {"bank_view_columns_checked": len(columns), "forbidden_columns": []}


def _split_isolation(world: ReleaseWorld) -> dict[str, Any]:
    account_split = {row["account_id"]: row["entity_split"] for row in world.accounts}
    for row in world.transactions:
        for endpoint in (row["source_account_id"], row["destination_account_id"]):
            if endpoint:
                assert account_split[endpoint] == row["dataset_split"], row["transaction_id"]
    scenario_split = {row["scenario_instance_id"]: row["dataset_split"] for row in world.scenario_instances}
    network_split = {row["network_id"]: row["dataset_split"] for row in world.networks}
    for rows in (world.entity_labels, world.transaction_labels, world.network_members):
        for row in rows:
            assert network_split[row["network_id"]] == row["dataset_split"]
            if "scenario_instance_id" in row:
                assert scenario_split[row["scenario_instance_id"]] == row["dataset_split"]
    return {"isolated_splits": sorted(set(account_split.values()))}


def _ground_truth(world: ReleaseWorld) -> dict[str, Any]:
    labels_by_scenario = Counter(row["scenario_instance_id"] for row in world.transaction_labels)
    entities_by_scenario = Counter(
        row["scenario_instance_id"] for row in world.entity_labels if row["entity_type"] == "CUSTOMER"
    )
    for row in world.scenario_instances:
        identifier = row["scenario_instance_id"]
        assert labels_by_scenario[identifier] == row["transaction_count"], identifier
        assert entities_by_scenario[identifier] == row["actor_count"], identifier
        assert row["benchmark_insertion"] is True and row["prevalence_claim"] is False
    return {
        "scenario_instances": len(world.scenario_instances),
        "transaction_labels": len(world.transaction_labels),
        "entity_labels": len(world.entity_labels),
    }


def _coverage(world: ReleaseWorld, config: SimulationConfig, registry: ParameterRegistry) -> dict[str, Any]:
    scenarios = Counter(row["scenario_type"] for row in world.scenario_instances)
    controls = Counter(row["scenario_type"] for row in world.hard_negative_instances)
    expected_scenarios = {
        key: max(1, round(int(value) * config.scenario_scale))
        for key, value in registry.value("AML_SCENARIO_QUOTAS_001").items()
    }
    expected_controls = {
        key: max(1, round(int(value) * config.hard_negative_scale))
        for key, value in registry.value("HARD_NEGATIVE_QUOTAS_001").items()
    }
    assert dict(scenarios) == expected_scenarios, f"scenario quota mismatch: {dict(scenarios)}"
    assert dict(controls) == expected_controls, f"hard-negative quota mismatch: {dict(controls)}"
    return {"scenario_counts": dict(sorted(scenarios.items())), "hard_negative_counts": dict(sorted(controls.items()))}


def _behavioral_suitability(world: ReleaseWorld) -> dict[str, Any]:
    required = {
        "transaction_id",
        "event_time",
        "available_from",
        "source_account_id",
        "source_counterparty_ref",
        "destination_account_id",
        "destination_counterparty_ref",
        "amount",
        "transaction_type",
        "channel",
        "dataset_split",
    }
    missing = required - world.transactions[0].keys()
    assert not missing, f"missing behavioral fields: {sorted(missing)}"
    assert len({row["transaction_type"] for row in world.transactions}) >= 8
    assert len({row["channel"] for row in world.transactions}) >= 5
    return {"required_fields": sorted(required), "summary": behavioral_summary(world)}


def _statistical_calibration(world: ReleaseWorld, registry: ParameterRegistry) -> dict[str, Any]:
    customer_type_target = registry.value("POP_CUSTOMER_TYPE_MIX_001")
    customer_type_actual = Counter(
        "INDIVIDUAL" if row["customer_type"] == "INDIVIDUAL" else "BUSINESS" for row in world.customers
    )
    region_target = registry.value("POP_REGION_MIX_001")
    region_actual = Counter(row["region_code"] for row in world.customers)
    comparisons = {
        "customer_type": _distribution_comparison(
            customer_type_actual,
            customer_type_target,
            ["SRC_WB_GLOBAL_FINDEX_VNM_2024", "SRC_VN_NSO_ENTERPRISES_2024"],
        ),
        "region": _distribution_comparison(
            region_actual,
            region_target,
            ["SRC_VN_NSO_LFS_2024"],
        ),
    }
    tolerance = max(0.03, 3 / math.sqrt(len(world.customers)))
    failed = {
        name: result["total_variation_distance"]
        for name, result in comparisons.items()
        if result["total_variation_distance"] > tolerance
    }
    assert not failed, f"calibration distance above tolerance {tolerance:.4f}: {failed}"
    return {
        "sample_size": len(world.customers),
        "total_variation_tolerance": tolerance,
        "comparisons": comparisons,
        "interpretation": "Targets are registered evidence-linked benchmark marginals, not claims about a specific bank.",
    }


def _distribution_comparison(
    actual_counts: Counter[str],
    expected_weights: dict[str, Any],
    source_ids: list[str],
) -> dict[str, Any]:
    actual_total = sum(actual_counts.values())
    expected_total = sum(float(value) for value in expected_weights.values())
    categories = sorted(set(actual_counts) | set(expected_weights))
    rows: dict[str, Any] = {}
    total_variation = 0.0
    for category in categories:
        actual = actual_counts[category] / actual_total
        expected = float(expected_weights.get(category, 0)) / expected_total
        difference = actual - expected
        total_variation += abs(difference)
        rows[category] = {"actual": actual, "target": expected, "difference": difference}
    return {
        "source_ids": source_ids,
        "categories": rows,
        "total_variation_distance": total_variation / 2,
    }


def _graph_suitability(world: ReleaseWorld) -> dict[str, Any]:
    adjacency: defaultdict[str, set[str]] = defaultdict(set)
    degree = Counter()
    edge_count = 0
    for row in world.transactions:
        source = row["source_account_id"] or row["source_counterparty_ref"]
        target = row["destination_account_id"] or row["destination_counterparty_ref"]
        adjacency[source].add(target)
        adjacency[target].add(source)
        degree[source] += 1
        degree[target] += 1
        edge_count += 1
    remaining = set(adjacency)
    component_sizes: list[int] = []
    while remaining:
        seed = remaining.pop()
        queue = deque([seed])
        size = 0
        while queue:
            node = queue.popleft()
            size += 1
            unseen = adjacency[node] & remaining
            remaining.difference_update(unseen)
            queue.extend(unseen)
        component_sizes.append(size)
    return {
        "node_count": len(adjacency),
        "edge_count": edge_count,
        "unique_undirected_edge_count": sum(len(items) for items in adjacency.values()) // 2,
        "component_count": len(component_sizes),
        "largest_component_nodes": max(component_sizes),
        "mean_event_degree": mean(degree.values()),
        "max_event_degree": max(degree.values()),
        "relationship_edge_count": len(world.relationships),
        "network_count": len(world.networks),
    }
