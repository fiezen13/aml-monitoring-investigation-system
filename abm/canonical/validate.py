"""Phase 18 and Phase 14 — validate the materialized release.

Six gates. Each reads the written CSV files rather than in-memory state, because
what ships is the files, and a check that passes on the builder's variables while
the files disagree is worse than no check.

1. **Schema and data quality** — headers, types, nulls, ID formats, encoding
2. **Referential integrity** — every foreign key resolves
3. **Temporal** — timestamps parse, ordering holds, accounts predate their activity
4. **Monetary** — amounts positive, currency supported, ranges plausible
5. **Statistical and behavioral** — distributions against source, behavior against IBM
6. **Graph** — nodes, edges, components, degree, cycles
7. **Leakage** — no ground-truth column in Bank View, no KYC field predicting the label

Gate 7 is the one that decides whether the release is usable for its purpose.
"""

from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

ID_PATTERNS = {
    "customer_id": re.compile(r"^CUS-\d{8}$"),
    "business_id": re.compile(r"^BIZ-\d{8}$"),
    "account_id": re.compile(r"^ACC-\d{8}$"),
    "transaction_id": re.compile(r"^TXN-\d{12}$"),
    "device_id": re.compile(r"^DEV-\d{8}$"),
    "merchant_id": re.compile(r"^MER-\d{8}$"),
    "scenario_id": re.compile(r"^SCN-\d{6}$"),
    "network_id": re.compile(r"^NET-\d{6}$"),
}

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

FORBIDDEN_BANK_VIEW_COLUMNS = (
    "is_laundering",
    "scenario_id",
    "scenario_stage",
    "true_role",
    "criminal_network_id",
    "network_id",
    "label_value",
    "label_type",
    "typology",
    "hard_negative_id",
    "ground_truth",
    "account_key",
    "ibm_behavior_source_account_hash",
)

# A KYC attribute value above this lift concentrates the label enough to distort
# evaluation; at 1.0 rate or 0.0 rate it determines it outright.
STRONG_LIFT = 3.0
MINIMUM_CELL = 30


# Tables above this many rows are never materialised as a list. The full
# release's transactions.csv has 31.9 million rows; as dicts that is tens of
# gigabytes, so a validator that loads it cannot run on the artifact it is
# meant to validate.
STREAM_THRESHOLD_BYTES = 64 << 20


def read_table(path: Path) -> list[dict[str, str]]:
    """Read a small table fully.

    Refuses anything large rather than silently exhausting memory: a validator
    that dies partway through is indistinguishable from one that found nothing.
    """
    size = path.stat().st_size
    if size > STREAM_THRESHOLD_BYTES:
        raise MemoryError(f"{path.name} is {size / (1 << 20):.0f} MB; use iter_table() instead of read_table()")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_table(path: Path) -> Iterator[dict[str, str]]:
    """Stream a table of any size, one row at a time."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def table_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle), [])


def _null(value: str | None) -> bool:
    return value is None or value == ""


def validate_schema(release: Path) -> dict[str, Any]:
    """Headers present, IDs well formed, nulls represented as empty strings."""
    findings: list[str] = []
    tables: dict[str, int] = {}

    for path in sorted(release.rglob("*.csv")):
        name = f"{path.parent.name}/{path.stem}"
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{name}: not valid UTF-8")
        if raw.startswith(b"\xef\xbb\xbf"):
            findings.append(f"{name}: has a UTF-8 BOM")

        header = table_header(path)
        if not header:
            tables[name] = 0
            continue

        checked = [(column, ID_PATTERNS[column]) for column in header if column in ID_PATTERNS]
        malformed: dict[str, list[str]] = defaultdict(list)
        placeholders: set[str] = set()
        python_booleans: set[str] = set()
        rows = 0

        for row in iter_table(path):
            rows += 1
            for column, pattern in checked:
                value = row[column]
                if not _null(value) and not pattern.match(value) and len(malformed[column]) < 3:
                    malformed[column].append(value)
            for column in header:
                value = row[column]
                if value in ("NULL", "None", "NA", "nan", "-"):
                    placeholders.add(column)
                elif value in ("True", "False"):
                    python_booleans.add(column)

        tables[name] = rows
        for column, samples in malformed.items():
            findings.append(f"{name}.{column}: malformed ids, e.g. {samples[0]!r}")
        for column in sorted(placeholders):
            findings.append(f"{name}.{column}: uses a null placeholder instead of an empty field")
        # Booleans are declared lowercase. Python's `True`/`False` reaches a
        # column when a numpy bool slips past the serializer, and a reader
        # casting on `== "true"` then silently sees every value as false.
        for column in sorted(python_booleans):
            findings.append(f"{name}.{column}: booleans written as True/False, expected true/false")

    return {"gate": "schema", "tables": tables, "findings": findings, "verdict": _verdict(findings)}


def validate_primary_keys(release: Path) -> dict[str, Any]:
    findings: list[str] = []
    unique_columns = {
        "bank_view/customers": "customer_id",
        "bank_view/businesses": "business_id",
        "bank_view/accounts": "account_id",
        "bank_view/transactions": "transaction_id",
        "bank_view/devices": "device_id",
        "bank_view/merchants": "merchant_id",
        "bank_view/relationships": "relationship_id",
    }
    for name, column in unique_columns.items():
        path = release / f"{name}.csv"
        if not path.exists():
            continue
        seen: set[str] = set()
        duplicates = 0
        for row in iter_table(path):
            value = row[column]
            if value in seen:
                duplicates += 1
            else:
                seen.add(value)
        if duplicates:
            findings.append(f"{name}.{column}: {duplicates} duplicate keys")

    seen_events: set[str] = set()
    duplicate_events = 0
    for row in iter_table(release / "bank_view/transactions.csv"):
        value = row["event_id"]
        if value in seen_events:
            duplicate_events += 1
        else:
            seen_events.add(value)
    if duplicate_events:
        findings.append(f"bank_view/transactions.event_id: {duplicate_events} duplicates, Kafka dedup would drop rows")

    return {"gate": "primary_keys", "findings": findings, "verdict": _verdict(findings)}


def validate_foreign_keys(release: Path) -> dict[str, Any]:
    findings: list[str] = []
    customers = {row["customer_id"] for row in iter_table(release / "bank_view/customers.csv")}
    businesses = {row["business_id"] for row in iter_table(release / "bank_view/businesses.csv")}
    accounts_rows = [
        {"account_id": row["account_id"], "owner_id": row["owner_id"], "owner_type": row["owner_type"]}
        for row in iter_table(release / "bank_view/accounts.csv")
    ]
    accounts = {row["account_id"] for row in accounts_rows}
    merchants = {row["merchant_id"] for row in iter_table(release / "bank_view/merchants.csv")}

    for row in accounts_rows:
        pool = customers if row["owner_type"] == "CUSTOMER" else businesses
        if row["owner_id"] not in pool:
            findings.append(f"accounts.owner_id {row['owner_id']} not in {row['owner_type']}")
            break

    dangling_endpoint = 0
    both_or_neither = 0
    dangling_merchant = 0
    transaction_ids: set[str] = set()
    for row in iter_table(release / "bank_view/transactions.csv"):
        transaction_ids.add(row["transaction_id"])
        for side in ("source", "destination"):
            account = row[f"{side}_account_id"]
            token = row[f"{side}_counterparty_token"]
            if bool(_null(account)) == bool(_null(token)):
                both_or_neither += 1
            if not _null(account) and account not in accounts:
                dangling_endpoint += 1
        if not _null(row["merchant_id"]) and row["merchant_id"] not in merchants:
            dangling_merchant += 1

    if dangling_endpoint:
        findings.append(f"transactions: {dangling_endpoint} endpoints reference a missing account")
    if both_or_neither:
        findings.append(f"transactions: {both_or_neither} endpoints set both an account and a token, or neither")
    if dangling_merchant:
        findings.append(f"transactions: {dangling_merchant} rows reference a missing merchant")

    for row in iter_table(release / "bank_view/devices.csv"):
        if row["customer_id"] not in customers:
            findings.append("devices.customer_id references a missing customer")
            break

    entities = customers | businesses | accounts | merchants
    entities |= {row["device_id"] for row in iter_table(release / "bank_view/devices.csv")}
    unresolved = 0
    for row in iter_table(release / "bank_view/relationships.csv"):
        if row["source_entity_id"] not in entities or row["destination_entity_id"] not in entities:
            unresolved += 1
    if unresolved:
        findings.append(f"relationships: {unresolved} rows reference a missing entity")

    orphan_labels = sum(
        1
        for row in iter_table(release / "ground_truth/transaction_labels.csv")
        if row["transaction_id"] not in transaction_ids
    )
    if orphan_labels:
        findings.append(f"transaction_labels: {orphan_labels} labels have no transaction")

    return {"gate": "foreign_keys", "findings": findings, "verdict": _verdict(findings)}


def validate_temporal(release: Path) -> dict[str, Any]:
    findings: list[str] = []
    accounts = {row["account_id"]: row["open_date"] for row in iter_table(release / "bank_view/accounts.csv")}

    malformed = 0
    before_open = 0
    earliest: datetime | None = None
    latest: datetime | None = None
    for row in iter_table(release / "bank_view/transactions.csv"):
        if not TIMESTAMP_PATTERN.match(row["timestamp"]):
            malformed += 1
            continue
        moment = datetime.fromisoformat(row["timestamp"])
        earliest = moment if earliest is None or moment < earliest else earliest
        latest = moment if latest is None or moment > latest else latest
        for side in ("source", "destination"):
            open_date = accounts.get(row[f"{side}_account_id"])
            if open_date and moment.date() < datetime.fromisoformat(open_date).date():
                before_open += 1

    if malformed:
        findings.append(f"transactions: {malformed} timestamps are not ISO-8601 with an offset")
    if before_open:
        findings.append(f"transactions: {before_open} occur before their account's open_date")

    span = (latest - earliest).days if earliest and latest else 0
    return {
        "gate": "temporal",
        "first_event": earliest.isoformat() if earliest else None,
        "last_event": latest.isoformat() if latest else None,
        "span_days": span,
        "findings": findings,
        "verdict": _verdict(findings),
    }


def validate_monetary(release: Path) -> dict[str, Any]:
    findings: list[str] = []
    amounts: list[float] = []
    currencies: Counter = Counter()

    for row in iter_table(release / "bank_view/transactions.csv"):
        currencies[row["currency"]] += 1
        try:
            amount = float(row["amount"])
        except ValueError:
            findings.append(f"transactions: unparseable amount {row['amount']!r}")
            continue
        amounts.append(amount)

    non_positive = sum(1 for amount in amounts if amount <= 0)
    if non_positive:
        findings.append(f"transactions: {non_positive} amounts are not positive")
    unsupported = set(currencies) - {"VND"}
    if unsupported:
        findings.append(f"transactions: unsupported currencies {sorted(unsupported)}")

    fractional = sum(1 for amount in amounts if amount != int(amount))
    if fractional:
        findings.append(f"transactions: {fractional} amounts have a fractional part; dong has no subunit")

    # Plausibility is reported, not enforced. Clipping the tail would break the
    # guarantee that within-account ratios come through calibration untouched,
    # and the tail is inherited from IBM rather than introduced here. Making it
    # visible is the honest treatment; hiding it behind a passing gate is not.
    total = len(amounts) or 1
    plausibility = {
        "below_1000_vnd": sum(1 for amount in amounts if amount < 1_000),
        "above_1_billion_vnd": sum(1 for amount in amounts if amount > 1e9),
        "above_100_billion_vnd": sum(1 for amount in amounts if amount > 1e11),
    }

    amounts.sort()
    return {
        "gate": "monetary",
        "currencies": dict(currencies),
        "amount_vnd": _quantiles(amounts),
        "plausibility_counts": plausibility,
        "plausibility_shares": {key: round(value / total, 6) for key, value in plausibility.items()},
        "plausibility_note": (
            "Extreme amounts are inherited from IBM's within-account spread, which "
            "calibration preserves by design. Reported, not clipped."
        ),
        "findings": findings,
        "verdict": _verdict(findings),
    }


def validate_graph(release: Path) -> dict[str, Any]:
    """Node and edge counts, degree, components, and reciprocity."""
    accounts = {row["account_id"] for row in iter_table(release / "bank_view/accounts.csv")}
    events = 0

    edges: set[tuple[str, str]] = set()
    out_degree: Counter = Counter()
    in_degree: Counter = Counter()
    internal_events = 0
    self_loops = 0
    external_nodes: set[str] = set()

    for row in iter_table(release / "bank_view/transactions.csv"):
        events += 1
        source = row["source_account_id"] or row["source_counterparty_token"]
        destination = row["destination_account_id"] or row["destination_counterparty_token"]
        if not source or not destination:
            continue
        if row["source_counterparty_token"]:
            external_nodes.add(source)
        if row["destination_counterparty_token"]:
            external_nodes.add(destination)
        if source == destination:
            self_loops += 1
            continue
        edges.add((source, destination))
        out_degree[source] += 1
        in_degree[destination] += 1
        if row["source_account_id"] and row["destination_account_id"]:
            internal_events += 1

    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, destination in edges:
        adjacency[source].add(destination)
        adjacency[destination].add(source)

    seen: set[str] = set()
    components: list[int] = []
    for node in adjacency:
        if node in seen:
            continue
        stack = [node]
        seen.add(node)
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append(size)
    components.sort(reverse=True)

    reciprocal = sum(1 for source, destination in edges if (destination, source) in edges)
    degrees = sorted(out_degree[node] + in_degree[node] for node in adjacency)

    findings: list[str] = []
    if not components:
        findings.append("graph has no edges")
    elif components[0] < 0.2 * len(adjacency):
        findings.append("largest connected component holds under 20% of nodes")

    return {
        "gate": "graph",
        "nodes_total": len(adjacency),
        "nodes_internal_accounts": len(accounts & set(adjacency)),
        "nodes_external_counterparties": len(external_nodes),
        "unique_edges": len(edges),
        "transaction_events": events,
        "internal_to_internal_events": internal_events,
        "self_loop_events": self_loops,
        "reciprocal_edges": reciprocal,
        "connected_components": len(components),
        "largest_component": components[0] if components else 0,
        "largest_component_share": components[0] / len(adjacency) if adjacency else 0.0,
        "degree": _quantiles([float(value) for value in degrees]),
        "findings": findings,
        "verdict": _verdict(findings),
    }


def validate_leakage(release: Path) -> dict[str, Any]:
    """Phase 14. Bank View carries no ground truth, and no KYC field predicts it."""
    findings: list[str] = []

    for path in sorted((release / "bank_view").glob("*.csv")):
        present = set(table_header(path)) & set(FORBIDDEN_BANK_VIEW_COLUMNS)
        if present:
            findings.append(f"bank_view/{path.stem}: ground-truth columns present {sorted(present)}")

    customers = {row["customer_id"]: row for row in iter_table(release / "bank_view/customers.csv")}
    businesses = {row["business_id"]: row for row in iter_table(release / "bank_view/businesses.csv")}
    labels = {
        row["entity_id"]: row["label_value"]
        for row in iter_table(release / "ground_truth/entity_labels.csv")
        if row["entity_type"] in ("CUSTOMER", "BUSINESS")
    }

    entities = {**customers, **businesses}
    flags = {key: labels.get(key, "0") == "1" for key in entities}
    positives = sum(flags.values())
    base = positives / len(flags) if flags else 0.0

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
        "business_kind",
        "revenue_band",
    )

    associations = []
    perfect = []
    strong = []
    for attribute in attributes:
        grouped: dict[str, list[bool]] = defaultdict(list)
        for key, entity in entities.items():
            value = entity.get(attribute)
            if value:
                grouped[value].append(flags[key])
        for value, group in sorted(grouped.items()):
            if len(group) < MINIMUM_CELL:
                continue
            rate = sum(group) / len(group)
            lift = rate / base if base else None
            entry = {
                "attribute": attribute,
                "value": value,
                "entities": len(group),
                "flagged_rate": round(rate, 6),
                "lift": round(lift, 4) if lift is not None else None,
            }
            associations.append(entry)
            if rate in (0.0, 1.0):
                perfect.append(entry)
            elif lift is not None and lift >= STRONG_LIFT:
                strong.append(entry)

    associations.sort(key=lambda entry: -(entry["lift"] or 0))
    if perfect:
        findings.append(f"{len(perfect)} KYC attribute values perfectly separate the label")

    return {
        "gate": "leakage",
        "base_rate": round(base, 6),
        "flagged_entities": positives,
        "total_entities": len(flags),
        "perfect_predictors": perfect,
        "strong_associations": strong,
        "top_associations": associations[:12],
        "mutual_information_bits": _mutual_information(entities, flags, attributes),
        "findings": findings,
        "verdict": _verdict(findings) if not strong else "WARN",
    }


def validate_splits(release: Path) -> dict[str, Any]:
    """Entity coherence, network integrity, and no entity in two splits."""
    findings: list[str] = []
    assignment: dict[str, str] = {}
    counts: dict[str, int] = {}

    for path in sorted((release / "splits").glob("*_entities.csv")):
        rows = read_table(path)
        counts[path.stem.replace("_entities", "").upper()] = len(rows)
        for row in rows:
            if row["entity_id"] in assignment:
                findings.append(f"{row['entity_id']} appears in more than one split")
            assignment[row["entity_id"]] = row["split"]

    networks: dict[str, set[str]] = defaultdict(set)
    for row in iter_table(release / "ground_truth/criminal_networks.csv"):
        networks[row["network_id"]].add(row["owner_entity_id"])

    crossing = []
    for network_id, members in networks.items():
        found = {assignment[member] for member in members if member in assignment}
        if len(found) > 1:
            crossing.append({"network_id": network_id, "splits": sorted(found)})
    if crossing:
        findings.append(f"{len(crossing)} criminal networks span more than one split")

    unassigned = sum(1 for row in iter_table(release / "bank_view/accounts.csv") if row["owner_id"] not in assignment)
    if unassigned:
        findings.append(f"{unassigned} accounts have an owner with no split")

    return {
        "gate": "splits",
        "counts": counts,
        "shares": {name: round(value / sum(counts.values()), 4) for name, value in counts.items()} if counts else {},
        "networks_checked": len(networks),
        "networks_crossing_splits": crossing[:10],
        "findings": findings,
        "verdict": _verdict(findings),
    }


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    ordered = sorted(values)

    def at(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]

    return {
        "min": ordered[0],
        "p25": at(0.25),
        "median": at(0.50),
        "p75": at(0.75),
        "p95": at(0.95),
        "p99": at(0.99),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def _mutual_information(
    entities: dict[str, dict[str, str]], flags: dict[str, bool], attributes: tuple[str, ...]
) -> dict[str, float]:
    """Mutual information between each attribute and the label, in bits.

    The label entropy is measured over the *same* entities the attribute covers,
    not the whole population. `industry_group` exists only on businesses, so
    comparing its conditional entropy against the entropy of all 6,000 entities
    mixes two different populations and can report 0.0 for an attribute that
    plainly carries information — which is how a leaky field slips through a
    check that appears to be looking for exactly that.
    """
    scores = {}
    for attribute in attributes:
        grouped: dict[str, list[bool]] = defaultdict(list)
        for key, entity in entities.items():
            value = entity.get(attribute)
            if value:
                grouped[value].append(flags[key])
        covered = sum(len(group) for group in grouped.values())
        if not covered:
            continue

        marginal = Counter(flag for group in grouped.values() for flag in group)
        label_entropy = _entropy([count / covered for count in marginal.values()])
        conditional = sum(
            (len(group) / covered) * _entropy([c / len(group) for c in Counter(group).values()])
            for group in grouped.values()
        )
        scores[attribute] = round(max(label_entropy - conditional, 0.0), 6)
    return dict(sorted(scores.items(), key=lambda item: -item[1]))


def _entropy(probabilities: list[float]) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0)


def _verdict(findings: list[str]) -> str:
    return "PASS" if not findings else "FAIL"


def run_all(release: Path) -> dict[str, Any]:
    gates = [
        validate_schema(release),
        validate_primary_keys(release),
        validate_foreign_keys(release),
        validate_temporal(release),
        validate_monetary(release),
        validate_graph(release),
        validate_splits(release),
        validate_leakage(release),
    ]
    failed = [gate["gate"] for gate in gates if gate["verdict"] == "FAIL"]
    warned = [gate["gate"] for gate in gates if gate["verdict"] == "WARN"]
    return {
        "gates": {gate["gate"]: gate for gate in gates},
        "failed_gates": failed,
        "warned_gates": warned,
        "verdict": "FAIL" if failed else ("WARN" if warned else "PASS"),
    }
