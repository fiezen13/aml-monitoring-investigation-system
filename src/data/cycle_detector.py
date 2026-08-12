"""CYCLE detector — docs/graph_cycle_detector_spec.md / graph_branch_plan.md §4.1."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.schemas import assert_no_label_leakage
from src.data.snapshot_split import (
    WINDOW_7D,
    assign_snapshot_split,
    candidate_snapshot_dates,
    load_split_cutoffs,
    parse_utc,
    snapshot_window_bounds,
)

DETECTED_PATTERN = "CYCLE"
DETECTOR_VERSION = "graph_cycle_v1"
MIN_CYCLE_LEN = 2
MAX_CYCLE_LEN = 6

REQUIRED_TX_COLUMNS = (
    "transaction_id",
    "occurred_at",
    "from_account_key",
    "to_account_key",
)

DETECTION_COLUMNS = (
    "detection_id",
    "pattern_instance_id",
    "evidence_id",
    "account_key",
    "as_of_ts",
    "snapshot_date",
    "window",
    "sample_split",
    "detected_pattern",
    "detector_version",
    "cycle_length",
)


@dataclass(frozen=True)
class TxEdge:
    transaction_id: str
    occurred_at: pd.Timestamp
    amount: float | None
    from_account_key: str
    to_account_key: str


def _sha1_16(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def canonicalize_accounts(nodes: list[str]) -> list[str]:
    """Lex-smallest cyclic rotation of the node sequence."""
    if not nodes:
        return []
    rotations = [tuple(nodes[i:] + nodes[:i]) for i in range(len(nodes))]
    return list(min(rotations))


def pattern_instance_id(
    *,
    as_of_ts: pd.Timestamp,
    accounts: list[str],
    detector_version: str = DETECTOR_VERSION,
    window: str = WINDOW_7D,
) -> str:
    as_of = parse_utc(as_of_ts).isoformat()
    motif_key = "|".join(
        [as_of, window, detector_version, DETECTED_PATTERN, ",".join(accounts)]
    )
    return f"PI_CYCLE_{_sha1_16(motif_key)}"


def evidence_id_for(pi: str, transaction_ids: list[str]) -> str:
    witness_key = pi + "|" + ",".join(transaction_ids)
    return f"EV_CYCLE_{_sha1_16(witness_key)}"


def detection_id_for(pi: str, account_key: str) -> str:
    return f"DET_CYCLE_{_sha1_16(pi + '|' + account_key)}"


def _ensure_tx_frame(transactions: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_TX_COLUMNS if c not in transactions.columns]
    if missing:
        raise ValueError(f"transactions missing columns: {missing}")
    cols = list(REQUIRED_TX_COLUMNS)
    if "amount" in transactions.columns:
        cols.append("amount")
    df = transactions.loc[:, cols].copy()
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df["transaction_id"] = df["transaction_id"].astype(str)
    df["from_account_key"] = df["from_account_key"].astype(str)
    df["to_account_key"] = df["to_account_key"].astype(str)
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def _build_topology(w: pd.DataFrame) -> dict[str, set[str]]:
    """Build unique directed topology without materializing transaction edges."""
    pairs = w.loc[
        w["from_account_key"] != w["to_account_key"],
        ["from_account_key", "to_account_key"],
    ].drop_duplicates()
    adj: dict[str, set[str]] = {}
    for frm, to in pairs.itertuples(index=False, name=None):
        frm = str(frm)
        to = str(to)
        adj.setdefault(frm, set()).add(to)
        adj.setdefault(to, set())
    return adj


def _build_multi_for_pairs(
    w: pd.DataFrame,
    pairs: set[tuple[str, str]],
) -> dict[tuple[str, str], list[TxEdge]]:
    """Materialize TxEdge objects only for topology pairs in candidate cycles."""
    multi: dict[tuple[str, str], list[TxEdge]] = {}
    if not pairs:
        return multi
    pair_frame = pd.DataFrame(
        sorted(pairs), columns=["from_account_key", "to_account_key"]
    )
    selected = w.merge(
        pair_frame,
        on=["from_account_key", "to_account_key"],
        how="inner",
        sort=False,
    )
    for row in selected.itertuples(index=False):
        frm = str(row.from_account_key)
        to = str(row.to_account_key)
        amt = float(row.amount) if hasattr(row, "amount") and pd.notna(row.amount) else None
        edge = TxEdge(
            transaction_id=str(row.transaction_id),
            occurred_at=pd.Timestamp(row.occurred_at),
            amount=amt,
            from_account_key=frm,
            to_account_key=to,
        )
        multi.setdefault((frm, to), []).append(edge)
    return multi


def _build_adjacency(
    w: pd.DataFrame,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], list[TxEdge]]]:
    """Compatibility helper returning full topology and all transaction edges."""
    adj = _build_topology(w)
    pairs = set(zip(w["from_account_key"].astype(str), w["to_account_key"].astype(str)))
    pairs = {(frm, to) for frm, to in pairs if frm != to}
    return adj, _build_multi_for_pairs(w, pairs)


def _iterative_cycle_core(adj: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """Remove only nodes that provably cannot belong to a directed cycle."""
    core = {node: set(neighbors) for node, neighbors in adj.items()}
    changed = True
    while changed:
        changed = False
        incoming: dict[str, int] = {node: 0 for node in core}
        for node, neighbors in core.items():
            for neighbor in neighbors:
                if neighbor in incoming:
                    incoming[neighbor] += 1
        remove = {
            node
            for node, neighbors in core.items()
            if not neighbors or incoming[node] == 0
        }
        if remove:
            changed = True
            for node in remove:
                core.pop(node, None)
            for neighbors in core.values():
                neighbors.difference_update(remove)
    return core


def _strongly_connected_components(
    adj: Mapping[str, set[str]],
) -> list[set[str]]:
    """Deterministic iterative Kosaraju SCC decomposition."""
    nodes = sorted(adj)
    reverse: dict[str, set[str]] = {node: set() for node in nodes}
    for node in nodes:
        for neighbor in adj.get(node, ()):
            reverse.setdefault(neighbor, set()).add(node)

    visited: set[str] = set()
    order: list[str] = []
    for root in nodes:
        if root in visited:
            continue
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                order.append(node)
                continue
            if node in visited:
                continue
            visited.add(node)
            stack.append((node, True))
            for neighbor in sorted(adj.get(node, ()), reverse=True):
                if neighbor not in visited:
                    stack.append((neighbor, False))

    components: list[set[str]] = []
    visited.clear()
    for root in reversed(order):
        if root in visited:
            continue
        component: set[str] = set()
        stack = [root]
        visited.add(root)
        while stack:
            node = stack.pop()
            component.add(node)
            for neighbor in sorted(reverse.get(node, ()), reverse=True):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return sorted(components, key=lambda component: min(component))


def enumerate_simple_cycles(
    adj: Mapping[str, set[str]],
    *,
    min_len: int = MIN_CYCLE_LEN,
    max_len: int = MAX_CYCLE_LEN,
) -> list[list[str]]:
    """Directed simple cycles; exact SCC/canonical-start enumeration.

    The pruning here is structural only: every removed node is proven unable to
    participate in a directed cycle. Hubs are retained; no degree threshold is
    used. Each cycle is searched from its lexicographically smallest node, so
    rotations are never enumerated repeatedly.
    """
    core = _iterative_cycle_core(adj)
    if not core:
        return []
    components = _strongly_connected_components(core)
    seen: set[tuple[str, ...]] = set()
    out: list[list[str]] = []

    for component in components:
        if len(component) < min_len:
            continue
        component_nodes = set(component)
        for start in sorted(component):
            def dfs(path: list[str], visited: set[str]) -> None:
                if len(path) > max_len:
                    return
                node = path[-1]
                for neighbor in sorted(adj.get(node, ())):
                    if neighbor not in component_nodes:
                        continue
                    # The minimum node is the sole legal start for a motif.
                    if neighbor < start:
                        continue
                    if neighbor == start and min_len <= len(path) <= max_len:
                        canonical = tuple(path)
                        if canonical not in seen:
                            seen.add(canonical)
                            out.append(path[:])
                    elif neighbor not in visited and len(path) < max_len:
                        visited.add(neighbor)
                        path.append(neighbor)
                        dfs(path, visited)
                        path.pop()
                        visited.remove(neighbor)

            dfs([start], {start})
    return out


def select_temporal_witness(
    nodes: list[str],
    multi: Mapping[tuple[str, str], list[TxEdge]],
) -> list[TxEdge] | None:
    """
    Pick one TX per hop such that some cyclic shift is time-non-decreasing.
    Minimize (t1..tk, id1..idk) in the shifted (witness) order.
    """
    k = len(nodes)
    hop_lists: list[list[TxEdge]] = []
    for i in range(k):
        a, b = nodes[i], nodes[(i + 1) % k]
        edges = multi.get((a, b), [])
        if not edges:
            return None
        # The search below assumes timestamp/id order; callers may provide
        # unsorted multi-edge lists, so normalize them here deterministically.
        hop_lists.append(sorted(edges, key=lambda edge: (edge.occurred_at, edge.transaction_id)))

    best_key: tuple[Any, ...] | None = None
    best_hops: list[TxEdge] | None = None

    # For a fixed rotation, choosing the earliest valid edge at every hop is
    # exact: a later choice can never make a non-decreasing suffix possible
    # when an earlier valid choice already exists. Evaluate every rotation and
    # retain the same global lexicographic tie-break as the product oracle.
    for shift in range(k):
        rotated = hop_lists[shift:] + hop_lists[:shift]
        chosen: list[TxEdge] = []
        previous: pd.Timestamp | None = None
        for edges in rotated:
            timestamps = [edge.occurred_at for edge in edges]
            index = 0 if previous is None else bisect_left(timestamps, previous)
            if index >= len(edges):
                chosen = []
                break
            edge = edges[index]
            chosen.append(edge)
            previous = edge.occurred_at
        if len(chosen) != k:
            continue
        times = [edge.occurred_at for edge in chosen]
        ids = [edge.transaction_id for edge in chosen]
        key = tuple(times) + tuple(ids)
        if best_key is None or key < best_key:
            best_key = key
            best_hops = chosen
    return best_hops


def _hop_dict(edge: TxEdge) -> dict[str, Any]:
    return {
        "from_account_key": edge.from_account_key,
        "to_account_key": edge.to_account_key,
        "transaction_id": edge.transaction_id,
        "occurred_at": parse_utc(edge.occurred_at).isoformat(),
        "amount": edge.amount,
    }


def detect_cycles_for_snapshot(
    transactions: pd.DataFrame,
    snapshot_date: date,
    split_cutoffs: Mapping[str, Any],
    *,
    detector_version: str = DETECTOR_VERSION,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Return (detections_df, evidence_records) for one snapshot date."""
    tx = _ensure_tx_frame(transactions)
    start_ts, end_ts = snapshot_window_bounds(snapshot_date)
    as_of_ts = end_ts
    sample_split = assign_snapshot_split(as_of_ts, split_cutoffs)

    w = tx.loc[(tx["occurred_at"] >= start_ts) & (tx["occurred_at"] < end_ts)]
    if w.empty:
        return pd.DataFrame(columns=list(DETECTION_COLUMNS)), []

    adj = _build_topology(w)
    cycles = enumerate_simple_cycles(adj)
    candidate_pairs = {
        (path[i], path[(i + 1) % len(path)])
        for path in cycles
        for i in range(len(path))
    }
    multi = _build_multi_for_pairs(w, candidate_pairs)

    det_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    emitted_pi: set[str] = set()

    for path in cycles:
        hops = select_temporal_witness(path, multi)
        if hops is None:
            continue
        accounts = canonicalize_accounts(path)
        pi = pattern_instance_id(
            as_of_ts=as_of_ts,
            accounts=accounts,
            detector_version=detector_version,
        )
        if pi in emitted_pi:
            continue
        emitted_pi.add(pi)

        tx_ids = [h.transaction_id for h in hops]
        ev = evidence_id_for(pi, tx_ids)
        duration_hours = (
            (hops[-1].occurred_at - hops[0].occurred_at).total_seconds() / 3600.0
        )
        cycle_length = len(accounts)

        evidence.append(
            {
                "evidence_id": ev,
                "pattern_instance_id": pi,
                "as_of_ts": parse_utc(as_of_ts).isoformat(),
                "snapshot_date": snapshot_date.isoformat(),
                "window": WINDOW_7D,
                "sample_split": sample_split,
                "detected_pattern": DETECTED_PATTERN,
                "detector_version": detector_version,
                "cycle_length": cycle_length,
                "accounts": accounts,
                "hops": [_hop_dict(h) for h in hops],
                "transaction_ids": tx_ids,
                "duration_hours": float(duration_hours),
            }
        )

        for account in accounts:
            det_rows.append(
                {
                    "detection_id": detection_id_for(pi, account),
                    "pattern_instance_id": pi,
                    "evidence_id": ev,
                    "account_key": account,
                    "as_of_ts": as_of_ts,
                    "snapshot_date": snapshot_date,
                    "window": WINDOW_7D,
                    "sample_split": sample_split,
                    "detected_pattern": DETECTED_PATTERN,
                    "detector_version": detector_version,
                    "cycle_length": cycle_length,
                }
            )

    detections = pd.DataFrame(det_rows, columns=list(DETECTION_COLUMNS))
    if not detections.empty:
        detections = detections.sort_values(
            ["as_of_ts", "pattern_instance_id", "account_key"], kind="mergesort"
        ).reset_index(drop=True)
    assert_no_label_leakage(list(detections.columns))
    return detections, evidence


def detect_cycles(
    transactions: pd.DataFrame,
    split_cutoffs: Mapping[str, Any],
    *,
    snapshot_dates: list[date] | None = None,
    detector_version: str = DETECTOR_VERSION,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    tx = _ensure_tx_frame(transactions)
    dates = (
        snapshot_dates
        if snapshot_dates is not None
        else candidate_snapshot_dates(tx["occurred_at"])
    )
    all_det: list[pd.DataFrame] = []
    all_ev: list[dict[str, Any]] = []
    for d in dates:
        det, ev = detect_cycles_for_snapshot(
            tx, d, split_cutoffs, detector_version=detector_version
        )
        if not det.empty:
            all_det.append(det)
        all_ev.extend(ev)
    if not all_det:
        return pd.DataFrame(columns=list(DETECTION_COLUMNS)), all_ev
    out = pd.concat(all_det, ignore_index=True)
    out = out.sort_values(
        ["as_of_ts", "pattern_instance_id", "account_key"], kind="mergesort"
    ).reset_index(drop=True)
    return out, all_ev


def write_cycle_artifacts(
    detections: pd.DataFrame,
    evidence: list[dict[str, Any]],
    *,
    detection_path: str | Path,
    evidence_path: str | Path,
) -> None:
    detection_path = Path(detection_path)
    evidence_path = Path(evidence_path)
    detection_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    detections.to_parquet(detection_path, index=False)
    with evidence_path.open("w", encoding="utf-8") as f:
        for rec in evidence:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def run_cycle_detector(
    *,
    transactions: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
    cutoffs_path: str | Path | None = None,
    split_cutoffs: Mapping[str, Any] | None = None,
    snapshot_dates: list[date] | None = None,
    detection_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
    range_start: datetime | pd.Timestamp | None = None,
    range_end_exclusive: datetime | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Run CYCLE detector; optionally write artifacts."""
    if split_cutoffs is None:
        if cutoffs_path is None:
            raise ValueError("Provide cutoffs_path or split_cutoffs")
        split_cutoffs = load_split_cutoffs(cutoffs_path)

    if transactions is None:
        if db_path is None:
            raise ValueError("Provide db_path or transactions")
        import duckdb

        con = duckdb.connect(str(Path(db_path).resolve()), read_only=True)
        try:
            if range_start is not None or range_end_exclusive is not None:
                start = range_start or datetime(1970, 1, 1, tzinfo=timezone.utc)
                end = range_end_exclusive or datetime(2100, 1, 1, tzinfo=timezone.utc)
                transactions = con.execute(
                    """
                    SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount
                    FROM transaction
                    WHERE occurred_at >= ? AND occurred_at < ?
                    """,
                    [
                        pd.Timestamp(start).to_pydatetime(),
                        pd.Timestamp(end).to_pydatetime(),
                    ],
                ).df()
            else:
                transactions = con.execute(
                    """
                    SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount
                    FROM transaction
                    """
                ).df()
        finally:
            con.close()

    detections, evidence = detect_cycles(
        transactions, split_cutoffs, snapshot_dates=snapshot_dates
    )
    if detection_path is not None and evidence_path is not None:
        write_cycle_artifacts(
            detections,
            evidence,
            detection_path=detection_path,
            evidence_path=evidence_path,
        )
    return detections, evidence
