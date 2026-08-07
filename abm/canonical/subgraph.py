"""Select a connected slice of the IBM transaction graph.

## Why selection has to come before matching

Phase 9 matched synthetic KYC agents to IBM accounts chosen independently, one
per agent, by archetype compatibility. That is the right way to pick *behavior*
and the wrong way to pick a *graph*: 5,800 accounts drawn from 2.08 million share
almost no edges, so the induced subgraph would be nearly empty and every network
property IBM supplies — fan-in structure, cycles, laundering topology — would be
lost. The release would preserve IBM's amounts and none of its shape.

So the subgraph is chosen first, and the KYC agents are matched onto the accounts
in it.

## How the slice is chosen

Seed with complete laundering patterns, then expand one hop to their
counterparties. This is deliberately not a random sample:

- **Complete patterns.** Taking whole instances keeps criminal networks intact.
  Half a cycle is not a cycle, and a fan-in missing its collectors is not a
  fan-in.
- **One-hop expansion.** The accounts a laundering network transacts with are
  overwhelmingly ordinary, and they are what makes the release realistic — a
  bank's book is suspicious accounts embedded in normal ones, not a directory of
  suspects. It also guarantees connectivity, which random sampling cannot.

Accounts outside the selection are not discarded. Transactions crossing the
boundary are kept with a tokenised external counterparty, which is exactly what a
real bank sees: its own accounts on one side, an external party on the other.

## Hub exclusion

IBM's busiest account carries 1,083,821 transactions and bank `070` alone appears
on 2.98 million transaction legs — clearing infrastructure rather than a customer.
Admitting one would make a single account dominate the release. Accounts beyond
`MAX_ACCOUNT_TRANSACTIONS` are excluded from selection but remain reachable as
external counterparties, which is the honest representation of a correspondent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from abm.profiling.ibm_behavior import account_key
from abm.profiling.ibm_patterns import PatternInstance, parse_patterns
from abm.profiling.ibm_reader import COLUMN_NAMES, convert_column, iter_batches

# An account busier than this is infrastructure, not a customer.
MAX_ACCOUNT_TRANSACTIONS = 1_000

# Below this there is too little behavior to calibrate or characterise, so an
# account is not worth admitting on behavioral grounds alone.
MIN_ACCOUNT_TRANSACTIONS = 5

# Pattern accounts are admitted on *network* grounds, not behavioral ones, so
# they use a lower floor. A mule that receives once and forwards once has two
# transactions and is exactly the actor the typology needs; applying the
# behavioral floor to it drops 145 of 493 instances and biases the surviving
# criminal networks toward unusually busy mules.
MIN_SEED_TRANSACTIONS = 1


@dataclass(slots=True)
class SubgraphSelection:
    internal_accounts: set[str]
    seed_accounts: set[str]
    pattern_instances: list[PatternInstance]
    selected_pattern_indices: set[int]
    stats: dict[str, Any]


def _account_counts(behavior_csv: Path) -> dict[str, int]:
    table = pacsv.read_csv(
        str(behavior_csv),
        convert_options=pacsv.ConvertOptions(include_columns=["account_key", "transaction_count"]),
    )
    counts = table.column("transaction_count").to_numpy(zero_copy_only=False)
    return dict(zip(table.column("account_key").to_pylist(), (int(c) for c in counts), strict=True))


def _within(counts: dict[str, int], minimum: int) -> dict[str, int]:
    return {key: count for key, count in counts.items() if minimum <= count <= MAX_ACCOUNT_TRANSACTIONS}


def _stable_order(keys: set[str], seed: int) -> list[str]:
    """Deterministic shuffle keyed on the release seed.

    Sorting alone would bias selection toward whatever the account-key ordering
    correlates with — and IBM's keys start with the bank id, so sorted order is
    bank order. Hashing with the seed removes that without giving up determinism.
    """
    return sorted(keys, key=lambda key: hashlib.sha256(f"{seed}:{key}".encode()).hexdigest())


def select_pattern_seeds(
    instances: list[PatternInstance],
    eligible: dict[str, int],
    *,
    target_patterns: int,
    seed: int,
) -> tuple[set[str], set[int]]:
    """Take whole laundering instances whose accounts are all usable.

    An instance is taken only if every one of its accounts passes the activity
    band. Taking a partial instance would leave a network in the ground truth
    whose members are not all in the release, and every graph validation would
    then be checking a broken structure.
    """
    ordered = sorted(
        instances,
        key=lambda instance: hashlib.sha256(f"{seed}:{instance.index}".encode()).hexdigest(),
    )
    accounts: set[str] = set()
    chosen: set[int] = set()
    for instance in ordered:
        if len(chosen) >= target_patterns:
            break
        keys = instance.accounts
        if not keys or any(key not in eligible for key in keys):
            continue
        accounts |= keys
        chosen.add(instance.index)
    return accounts, chosen


def find_counterparties(transactions_csv: Path, seeds: set[str], *, max_rows: int | None = None) -> dict[str, int]:
    """One streaming pass collecting every account the seeds transact with.

    Returns each counterparty with the number of times it met a seed, so the
    caller can prefer accounts that are genuinely connected over ones that
    brushed the seed set once.
    """
    counts: dict[str, int] = {}
    for batch in iter_batches(transactions_csv, max_rows=max_rows):
        columns = {name: batch.column(index) for index, name in enumerate(COLUMN_NAMES)}
        from_key = account_key(
            convert_column(columns["from_bank"], "from_bank"),
            convert_column(columns["from_account"], "from_account"),
        )
        to_key = account_key(
            convert_column(columns["to_bank"], "to_bank"),
            convert_column(columns["to_account"], "to_account"),
        )
        sources = from_key.to_pylist()
        targets = to_key.to_pylist()
        for source, target in zip(sources, targets, strict=True):
            if source == target:
                continue
            if source in seeds and target not in seeds:
                counts[target] = counts.get(target, 0) + 1
            elif target in seeds and source not in seeds:
                counts[source] = counts.get(source, 0) + 1
    return counts


def select_subgraph(
    transactions_csv: Path,
    patterns_txt: Path,
    behavior_csv: Path,
    *,
    target_accounts: int,
    target_patterns: int,
    seed: int,
    max_rows: int | None = None,
) -> SubgraphSelection:
    counts = _account_counts(behavior_csv)
    eligible = _within(counts, MIN_ACCOUNT_TRANSACTIONS)
    seed_eligible = _within(counts, MIN_SEED_TRANSACTIONS)
    instances = parse_patterns(patterns_txt)

    seeds, chosen_patterns = select_pattern_seeds(instances, seed_eligible, target_patterns=target_patterns, seed=seed)
    counterparties = find_counterparties(transactions_csv, seeds, max_rows=max_rows)

    # Prefer well-connected, eligible counterparties, then fill deterministically.
    ranked = sorted(
        (key for key in counterparties if key in eligible and key not in seeds),
        key=lambda key: (-counterparties[key], key),
    )
    selected = set(seeds)
    for key in ranked:
        if len(selected) >= target_accounts:
            break
        selected.add(key)

    if len(selected) < target_accounts:
        # One hop did not reach the target. Fill from the eligible pool so the
        # release still has the requested size; these accounts join without an
        # internal edge and the stats record how many.
        for key in _stable_order(set(eligible) - selected, seed):
            if len(selected) >= target_accounts:
                break
            selected.add(key)

    return SubgraphSelection(
        internal_accounts=selected,
        seed_accounts=seeds,
        pattern_instances=instances,
        selected_pattern_indices=chosen_patterns,
        stats={
            "eligible_accounts": len(eligible),
            "seed_eligible_accounts": len(seed_eligible),
            "activity_band": [MIN_ACCOUNT_TRANSACTIONS, MAX_ACCOUNT_TRANSACTIONS],
            "pattern_instances_total": len(instances),
            "pattern_instances_selected": len(chosen_patterns),
            "seed_accounts": len(seeds),
            "one_hop_counterparties_found": len(counterparties),
            "counterparties_eligible": len(ranked),
            "internal_accounts": len(selected),
            "filled_without_internal_edge": max(
                0, len(selected) - len(seeds) - min(len(ranked), target_accounts - len(seeds))
            ),
        },
    )


def select_full(
    patterns_txt: Path,
    behavior_csv: Path,
) -> SubgraphSelection:
    """Take the entire IBM world: every account, every pattern.

    The seed-and-expand selection exists to carve a *connected* slice out of two
    million accounts. When the release keeps all of them the question does not
    arise — the graph is IBM's graph, every edge is internal, and there are no
    external counterparties because there is no outside.

    The hub ceiling is also dropped. In a slice, admitting an account with a
    million transactions would let one node dominate; in the full release that
    account is simply the correspondent bank it always was, and excluding it
    would delete 2.98 million transaction legs from the middle of the network.
    """
    counts = _account_counts(behavior_csv)
    instances = parse_patterns(patterns_txt)
    accounts = set(counts)
    return SubgraphSelection(
        internal_accounts=accounts,
        seed_accounts=set(),
        pattern_instances=instances,
        selected_pattern_indices={instance.index for instance in instances},
        stats={
            "mode": "full",
            "eligible_accounts": len(accounts),
            "activity_band": None,
            "hub_ceiling_applied": False,
            "pattern_instances_total": len(instances),
            "pattern_instances_selected": len(instances),
            "internal_accounts": len(accounts),
            "external_counterparties_expected": 0,
        },
    )


def extract_all_transactions(transactions_csv: Path, *, max_rows: int | None = None) -> pa.Table:
    """Every transaction, with no membership test.

    `extract_transactions` checks each endpoint against the internal set, which
    for the full release is a two-million-value `is_in` against every one of 63.8
    million endpoints — real work to compute an answer that is always true.
    """
    chunks: list[pa.RecordBatch] = []
    for batch in iter_batches(transactions_csv, max_rows=max_rows):
        columns = {name: convert_column(batch.column(index), name) for index, name in enumerate(COLUMN_NAMES)}
        rows = batch.num_rows
        chunks.append(
            pa.RecordBatch.from_arrays(
                [
                    account_key(columns["from_bank"], columns["from_account"]),
                    account_key(columns["to_bank"], columns["to_account"]),
                    pc.cast(columns["timestamp"], pa.int64()),
                    columns["amount_paid"],
                    columns["payment_currency"],
                    columns["payment_format"],
                    columns["is_laundering"],
                    pa.array([True] * rows, pa.bool_()),
                    pa.array([True] * rows, pa.bool_()),
                ],
                names=[
                    "from_key",
                    "to_key",
                    "timestamp_epoch",
                    "amount",
                    "currency",
                    "payment_format",
                    "is_laundering",
                    "from_internal",
                    "to_internal",
                ],
            )
        )
    if not chunks:
        raise ValueError("no transactions were read")
    return pa.Table.from_batches(chunks)


def extract_transactions(transactions_csv: Path, internal: set[str], *, max_rows: int | None = None) -> pa.Table:
    """Every transaction touching an internal account, with both keys retained.

    A transaction is kept when either endpoint is internal. The `direction`
    column records whether it is internal-to-internal, inbound from outside, or
    outbound to outside — which is what decides whether an endpoint becomes an
    account reference or an external counterparty token.
    """
    chunks: list[pa.RecordBatch] = []
    for batch in iter_batches(transactions_csv, max_rows=max_rows):
        columns = {name: convert_column(batch.column(index), name) for index, name in enumerate(COLUMN_NAMES)}
        from_key = account_key(columns["from_bank"], columns["from_account"])
        to_key = account_key(columns["to_bank"], columns["to_account"])

        internal_array = pa.array(sorted(internal), pa.string())
        from_internal = pc.is_in(from_key, value_set=internal_array)
        to_internal = pc.is_in(to_key, value_set=internal_array)
        keep = pc.or_(from_internal, to_internal)
        if not pc.any(keep).as_py():
            continue

        # Epoch seconds are produced here by a vectorised cast. Handing the
        # caller `timestamp[s]` instead would force 31.9 million Python datetime
        # objects through `to_pylist()`, which costs more than the entire rest of
        # the extraction.
        epoch = pc.cast(pc.cast(columns["timestamp"], pa.int64()), pa.int64())

        chunks.append(
            pa.RecordBatch.from_arrays(
                [
                    pc.filter(from_key, keep),
                    pc.filter(to_key, keep),
                    pc.filter(epoch, keep),
                    pc.filter(columns["amount_paid"], keep),
                    pc.filter(columns["payment_currency"], keep),
                    pc.filter(columns["payment_format"], keep),
                    pc.filter(columns["is_laundering"], keep),
                    pc.filter(from_internal, keep),
                    pc.filter(to_internal, keep),
                ],
                names=[
                    "from_key",
                    "to_key",
                    "timestamp_epoch",
                    "amount",
                    "currency",
                    "payment_format",
                    "is_laundering",
                    "from_internal",
                    "to_internal",
                ],
            )
        )
    if not chunks:
        raise ValueError("no transactions touch the selected accounts")
    return pa.Table.from_batches(chunks)


def summarize_extraction(table: pa.Table) -> dict[str, Any]:
    from_internal = table.column("from_internal").to_numpy(zero_copy_only=False)
    to_internal = table.column("to_internal").to_numpy(zero_copy_only=False)
    both = int(np.sum(from_internal & to_internal))
    labels = table.column("is_laundering").to_numpy(zero_copy_only=False)
    return {
        "transactions": table.num_rows,
        "internal_to_internal": both,
        "inbound_from_external": int(np.sum(~from_internal & to_internal)),
        "outbound_to_external": int(np.sum(from_internal & ~to_internal)),
        "internal_edge_share": both / table.num_rows if table.num_rows else 0.0,
        "laundering_rows": int(np.sum(labels == 1)),
    }
