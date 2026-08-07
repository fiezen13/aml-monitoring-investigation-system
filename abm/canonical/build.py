"""Build the canonical CSV release, phases 10 to 20.

Order matters and is not the order of the phase numbers. The IBM subgraph is
chosen first (see `subgraph.py`), then KYC agents are matched onto the accounts
in it, then money is calibrated, then transactions are rebuilt. Choosing accounts
by behavioral fit and hoping a graph falls out does not work.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from abm.calibration.monetary import CalibrationConfig, target_monthly_inflow_vnd
from abm.canonical import enrichment, hard_negatives, transactions
from abm.canonical.subgraph import (
    SubgraphSelection,
    extract_all_transactions,
    extract_transactions,
    select_full,
    select_subgraph,
)
from abm.kyc.businesses import BusinessConfig, generate_businesses
from abm.kyc.individuals import GenerationConfig, generate_individuals
from abm.matching.statistical import MatchingConfig, match_entities

ACCOUNT_ID_FORMAT = "ACC-{:08d}"
COUNTERPARTY_ID_FORMAT = "CPY-{:08d}"

DATASET_ID = "ABM-BANK"
DATASET_VERSION = "0.1.0-small"

# Accounts too sparse to have been archetyped in Phase 3 form their own group
# rather than being forced into a cluster they were never fitted to.
SPARSE_ARCHETYPE = "SPARSE_ACTIVITY"

# Share of bank customers that are businesses. Not sourced: no acquired statistic
# gives the composition of a Vietnamese bank's book, and IBM's own 99.7% business
# population is exactly the bias the rebuild exists to avoid inheriting.
ASSUME_BUSINESS_CUSTOMER_SHARE = 0.12

# One account per entity for v0.1.0. Accounts-per-customer at a single bank is
# unresolved (Findex gives ownership, not count), so the release takes the
# simplest defensible position rather than inventing a distribution.
ACCOUNTS_PER_ENTITY = 1


@dataclass(slots=True)
class ReleaseConfig:
    output_root: Path = Path("data/releases")
    version: str = DATASET_VERSION
    target_accounts: int = 6000
    target_patterns: int = 150
    seed: int = 20260807
    # "full" keeps every IBM account and every pattern; "subgraph" carves a
    # connected slice around a chosen number of laundering instances.
    mode: str = "subgraph"
    business_share: float = ASSUME_BUSINESS_CUSTOMER_SHARE
    assumptions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def release_dir(self) -> Path:
        return self.output_root / f"{DATASET_ID}-v{self.version}"


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def write_csv(rows: list[dict[str, Any]], path: Path, columns: list[str]) -> int:
    """Write one table with the release's CSV conventions.

    UTF-8, comma-delimited, ISO-8601 timestamps, empty string for null, and a
    leading apostrophe guard on any value a spreadsheet would try to evaluate.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in columns})
    return len(rows)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    # `numpy.bool_` is not a subclass of `bool`, so an isinstance check alone
    # lets numpy-derived flags through to `str()` and writes `True`/`False`
    # instead of the declared `true`/`false`. Customer behavior flags come out of
    # numpy comparisons and business flags out of Python ones, so the same column
    # family serialized two different ways until this was caught.
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        # Formula injection guard: a spreadsheet evaluates these on open.
        return f"'{value}"
    return value


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _load_archetypes(path: Path) -> dict[str, str]:
    import pyarrow.csv as pacsv

    table = pacsv.read_csv(
        str(path),
        convert_options=pacsv.ConvertOptions(include_columns=["account_key", "archetype"]),
    )
    return dict(zip(table.column("account_key").to_pylist(), table.column("archetype").to_pylist(), strict=True))


def _load_behavior(path: Path, keys: set[str]) -> dict[str, dict[str, Any]]:
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv

    table = pacsv.read_csv(
        str(path),
        convert_options=pacsv.ConvertOptions(
            include_columns=[
                "account_key",
                "transaction_count",
                "turnover_amount",
                "total_incoming_amount",
                "total_outgoing_amount",
                "median_incoming_amount",
                "active_days",
                "entity_kind",
            ]
        ),
    )
    import pyarrow as pa

    mask = pc.is_in(table.column("account_key"), value_set=pa.array(sorted(keys), pa.string()))
    return {row["account_key"]: row for row in table.filter(mask).to_pylist()}


def build_release(
    distributions: dict[str, Any],
    source_values: dict[str, Any],
    *,
    archetype_report: dict[str, Any],
    transactions_csv: Path,
    patterns_txt: Path,
    behavior_csv: Path,
    archetypes_csv: Path,
    config: ReleaseConfig,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    release = config.release_dir
    (release / "bank_view").mkdir(parents=True, exist_ok=True)
    (release / "ground_truth").mkdir(parents=True, exist_ok=True)
    (release / "splits").mkdir(parents=True, exist_ok=True)
    (release / "reports").mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- subgraph
    if config.mode == "full":
        selection = select_full(patterns_txt, behavior_csv)
        raw = extract_all_transactions(transactions_csv)
    else:
        selection = select_subgraph(
            transactions_csv,
            patterns_txt,
            behavior_csv,
            target_accounts=config.target_accounts,
            target_patterns=config.target_patterns,
            seed=config.seed,
        )
        raw = extract_transactions(transactions_csv, selection.internal_accounts)

    behavior = _load_behavior(behavior_csv, selection.internal_accounts)
    archetype_by_key = _load_archetypes(archetypes_csv)

    # ------------------------------------------------- entities and matching
    internal = sorted(selection.internal_accounts)
    business_count = int(len(internal) * config.business_share)
    individual_count = len(internal) - business_count

    customers = generate_individuals(distributions, GenerationConfig(population=individual_count, seed=config.seed))
    firms = generate_businesses(
        distributions, source_values, BusinessConfig(population=business_count, seed=config.seed)
    )

    pools: dict[str, list[dict[str, Any]]] = {}
    for key in internal:
        row = behavior.get(key)
        if row is None:
            continue
        name = archetype_by_key.get(key, SPARSE_ARCHETYPE)
        pools.setdefault(name, []).append(row)

    archetypes = list(archetype_report["archetypes"])
    if SPARSE_ARCHETYPE in pools:
        # A neutral centroid: sparse accounts sit at the population mean on every
        # feature, which is the honest position for accounts never fitted.
        archetypes = archetypes + [
            {
                "archetype": SPARSE_ARCHETYPE,
                "centroid_scaled": dict.fromkeys(archetypes[0]["centroid_scaled"], 0.0),
            }
        ]

    entities: list[dict[str, Any]] = [*customers, *firms]
    matches = match_entities(entities, pools, archetypes, MatchingConfig(seed=config.seed))

    # ------------------------------------------------------------- calibration
    calibration = CalibrationConfig()
    account_by_key: dict[str, dict[str, Any]] = {}
    accounts: list[dict[str, Any]] = []
    open_date = "2022-08-01"

    for index, match in enumerate(matches, start=1):
        key = match["behavior"]["account_key"]
        entity = match["entity"]
        target = target_monthly_inflow_vnd(entity, calibration)
        observed = float(match["behavior"].get("total_incoming_amount") or 0.0)
        scale = (
            target / (observed * (30.0 / calibration.observation_days)) if target is not None and observed > 0 else None
        )
        account = {
            "account_id": ACCOUNT_ID_FORMAT.format(index),
            "owner_id": entity.get("customer_id") or entity.get("business_id"),
            "owner_type": "CUSTOMER" if entity.get("customer_type") else "BUSINESS",
            "account_type": (
                "BUSINESS_CURRENT"
                if entity.get("business_id")
                else ("SAVINGS" if entity.get("has_formal_saving") else "CURRENT")
            ),
            "currency": "VND",
            "open_date": open_date,
            "status": "ACTIVE",
            "behavior_archetype": match["archetype"],
            "expected_monthly_turnover_vnd": round(target) if target is not None else None,
            "_key": key,
            "_scale": scale,
            "_entity": entity,
            "target_monthly_inflow_vnd": target,
        }
        accounts.append(account)
        account_by_key[key] = account

    return _materialize(
        release=release,
        started=started,
        config=config,
        selection=selection,
        raw=raw,
        accounts=accounts,
        account_by_key=account_by_key,
        customers=customers,
        firms=firms,
        matches=matches,
        transactions_csv=transactions_csv,
        patterns_txt=patterns_txt,
    )


def _materialize(
    *,
    release: Path,
    started: datetime,
    config: ReleaseConfig,
    selection: SubgraphSelection,
    raw: Any,
    accounts: list[dict[str, Any]],
    account_by_key: dict[str, dict[str, Any]],
    customers: list[dict[str, Any]],
    firms: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    transactions_csv: Path,
    patterns_txt: Path,
) -> dict[str, Any]:
    """Turn the matched world into files. Split out purely for readability."""
    from abm.canonical.materialize import materialize

    return materialize(
        release=release,
        started=started,
        config=config,
        selection=selection,
        raw=raw,
        accounts=accounts,
        account_by_key=account_by_key,
        customers=customers,
        firms=firms,
        matches=matches,
        transactions_csv=transactions_csv,
        patterns_txt=patterns_txt,
    )


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_BUSINESS_CUSTOMER_SHARE",
            "description": "Share of bank customers that are businesses.",
            "value": ASSUME_BUSINESS_CUSTOMER_SHARE,
            "why_not_evidenced": (
                "No acquired statistic gives the composition of a Vietnamese "
                "bank's customer book. IBM's own 99.7% business population is the "
                "bias the rebuild exists to avoid inheriting."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_ACCOUNTS_PER_ENTITY",
            "description": "One account per entity.",
            "value": ACCOUNTS_PER_ENTITY,
            "why_not_evidenced": (
                "Findex gives account ownership, not accounts held at one bank. "
                "The simplest defensible position rather than an invented "
                "distribution."
            ),
            "confidence": "low",
        },
        *transactions.assumption_register(),
        *enrichment.assumption_register(),
        *hard_negatives.assumption_register(),
    ]
