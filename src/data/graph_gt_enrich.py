"""Enrich IBM Patterns.txt blocks for Graph detector eval.

Task 2 JSON lacks timestamps and historically kept leading-zero bank IDs.
Eval reads Patterns.txt directly: normalize account_key via make_account_key,
derive center/cycle signature + [t_min, t_max].
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.data.pattern_parser import (
    BEGIN_RE,
    END_RE,
    _stable_instance_id,
    file_sha256,
)
from src.data.schemas import make_account_key
from src.data.snapshot_split import assign_snapshot_split, parse_utc
from src.data.typology_schema import canonicalize_pattern_type

# IBM hyphen → Graph underscore (eval scope only)
IBM_TO_GRAPH = {
    "FAN-IN": "FAN_IN",
    "FAN-OUT": "FAN_OUT",
    "GATHER-SCATTER": "GATHER_SCATTER",
}
GRAPH_TO_IBM = {v: k for k, v in IBM_TO_GRAPH.items()}

_TX_TS = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}),")


def canonicalize_directed_cycle(accounts: list[str]) -> tuple[str, ...]:
    """Canonical rotation for a directed, closed account cycle.

    Direction is preserved; reversing the cycle is a different motif.
    """
    if len(accounts) < 2 or accounts[0] != accounts[-1]:
        raise ValueError("cycle must be closed and contain at least two hops")
    nodes = accounts[:-1]
    if len(set(nodes)) != len(nodes):
        raise ValueError("cycle must not repeat an intermediate account")
    rotations = [tuple(nodes[i:] + nodes[:i]) for i in range(len(nodes))]
    return min(rotations)


def _parse_tx_line(line: str) -> dict[str, Any] | None:
    parts = line.split(",")
    if len(parts) < 5:
        return None
    m = _TX_TS.match(line)
    if not m:
        return None
    ts = datetime.strptime(m.group(1), "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
    return {
        "occurred_at": ts,
        "from_account_key": make_account_key(parts[1].strip(), parts[2].strip()),
        "to_account_key": make_account_key(parts[3].strip(), parts[4].strip()),
    }


def derive_center(pattern_type: str, txs: list[dict[str, Any]]) -> str:
    """Center account for FAN_IN / FAN_OUT / GATHER_SCATTER blocks."""
    if not txs:
        raise ValueError("empty tx list")
    if pattern_type == "FAN-IN":
        counts: dict[str, int] = {}
        for t in txs:
            counts[t["to_account_key"]] = counts.get(t["to_account_key"], 0) + 1
        return max(counts, key=lambda k: (counts[k], k))
    if pattern_type == "FAN-OUT":
        counts = {}
        for t in txs:
            counts[t["from_account_key"]] = counts.get(t["from_account_key"], 0) + 1
        return max(counts, key=lambda k: (counts[k], k))
    if pattern_type == "GATHER-SCATTER":
        recv: dict[str, int] = {}
        send: dict[str, int] = {}
        for t in txs:
            recv[t["to_account_key"]] = recv.get(t["to_account_key"], 0) + 1
            send[t["from_account_key"]] = send.get(t["from_account_key"], 0) + 1
        both = set(recv) & set(send)
        pool = both if both else (set(recv) | set(send))
        return max(pool, key=lambda a: (recv.get(a, 0) + send.get(a, 0), a))
    raise ValueError(f"unsupported pattern_type for center: {pattern_type}")


def enrich_ibm_gt_for_graph_eval(
    patterns_path: str | Path,
    *,
    split_cutoffs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Return enriched GT rows for FAN-IN / FAN-OUT / GATHER-SCATTER only.

    Each row: instance_id, pattern_type (IBM), detected_pattern (Graph),
    center_account_key, t_min, t_max, sample_split (optional), n_tx.
    """
    path = Path(patterns_path)
    checksum = file_sha256(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        begin_m = BEGIN_RE.match(stripped)
        if not begin_m:
            i += 1
            continue
        raw_type = begin_m.group(1)
        canonical = canonicalize_pattern_type(raw_type)
        start_line = i + 1
        tx_lines: list[str] = []
        j = i + 1
        end_m = None
        while j < len(lines):
            s = lines[j].strip()
            end_m = END_RE.match(s)
            if end_m:
                break
            if s and not s.startswith("END "):
                tx_lines.append(s)
            j += 1
        if end_m is None:
            break
        end_line = j + 1
        i = j + 1

        if canonical not in IBM_TO_GRAPH:
            continue
        txs = [t for line in tx_lines if (t := _parse_tx_line(line)) is not None]
        if not txs:
            continue
        t_min = min(t["occurred_at"] for t in txs)
        t_max = max(t["occurred_at"] for t in txs)
        center = derive_center(canonical, txs)
        # Split by as_of of snapshot_date = date(t_max) → end of that calendar day
        as_of = datetime(
            t_max.year, t_max.month, t_max.day, tzinfo=timezone.utc
        )
        # as_of_ts for snapshot_date D is (D+1) 00:00
        from datetime import timedelta

        as_of = as_of + timedelta(days=1)
        row: dict[str, Any] = {
            "instance_id": _stable_instance_id(
                checksum, start_line, end_line, canonical
            ),
            "pattern_type": canonical,
            "detected_pattern": IBM_TO_GRAPH[canonical],
            "center_account_key": center,
            "t_min": parse_utc(t_min).isoformat(),
            "t_max": parse_utc(t_max).isoformat(),
            "n_tx": len(txs),
            "source_start_line": start_line,
            "source_end_line": end_line,
        }
        if split_cutoffs is not None:
            row["sample_split"] = assign_snapshot_split(as_of, split_cutoffs)
            row["as_of_ts"] = parse_utc(as_of).isoformat()
        out.append(row)
    return out


def enrich_cycle_gt_for_graph_eval(
    patterns_path: str | Path,
    *,
    split_cutoffs: dict[str, Any] | None = None,
    max_cycle_len: int = 6,
    max_window_days: int = 7,
) -> dict[str, Any]:
    """Extract CYCLE GT and explicitly classify unsupported blocks.

    CYCLE GT has no transaction IDs, so matching is structural (directed
    account-cycle signature) plus temporal snapshot-window overlap. Blocks
    outside the detector's supported length/window are reported as excluded,
    never counted as false negatives.
    """
    path = Path(patterns_path)
    checksum = file_sha256(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        begin_m = BEGIN_RE.match(lines[i].strip())
        if not begin_m:
            i += 1
            continue
        raw_type = begin_m.group(1)
        canonical = canonicalize_pattern_type(raw_type)
        start_line = i + 1
        tx_lines: list[str] = []
        j = i + 1
        end_m = None
        while j < len(lines):
            s = lines[j].strip()
            end_m = END_RE.match(s)
            if end_m:
                break
            if s and not s.startswith("END "):
                tx_lines.append(s)
            j += 1
        if end_m is None:
            break
        end_line = j + 1
        i = j + 1
        if canonical != "CYCLE":
            continue

        txs = [t for line in tx_lines if (t := _parse_tx_line(line)) is not None]
        instance_id = _stable_instance_id(checksum, start_line, end_line, canonical)
        if not txs:
            excluded.append({"instance_id": instance_id, "reason": "no_parseable_transactions"})
            continue
        accounts = [txs[0]["from_account_key"]] + [tx["to_account_key"] for tx in txs]
        t_min = min(t["occurred_at"] for t in txs)
        t_max = max(t["occurred_at"] for t in txs)
        span_days = (t_max - t_min).total_seconds() / 86400.0
        try:
            signature = canonicalize_directed_cycle(accounts)
        except ValueError as exc:
            excluded.append({"instance_id": instance_id, "reason": str(exc), "n_tx": len(txs)})
            continue
        as_of = datetime(t_max.year, t_max.month, t_max.day, tzinfo=timezone.utc) + timedelta(days=1)
        row: dict[str, Any] = {
            "instance_id": instance_id,
            "pattern_type": "CYCLE",
            "detected_pattern": "CYCLE",
            "cycle_signature": list(signature),
            "t_min": parse_utc(t_min).isoformat(),
            "t_max": parse_utc(t_max).isoformat(),
            "n_tx": len(txs),
            "span_days": span_days,
            "source_start_line": start_line,
            "source_end_line": end_line,
        }
        if split_cutoffs is not None:
            row["sample_split"] = assign_snapshot_split(as_of, split_cutoffs)
            row["as_of_ts"] = parse_utc(as_of).isoformat()
        if len(signature) > max_cycle_len:
            excluded.append({"instance_id": instance_id, "reason": "cycle_length_exceeds_detector", "n_tx": len(txs), "cycle_length": len(signature)})
        elif span_days > max_window_days:
            excluded.append({"instance_id": instance_id, "reason": "span_exceeds_detector_window", "n_tx": len(txs), "span_days": span_days})
        else:
            rows.append(row)
    return {
        "status": "OK" if rows else "NOT_EVALUATED",
        "rows": rows,
        "excluded": excluded,
        "total_cycle_blocks": len(rows) + len(excluded),
        "eligible_count": len(rows),
    }
