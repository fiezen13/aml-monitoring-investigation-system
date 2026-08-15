"""Data quality checks for FIN-07 Task 1 (DAT §10)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data.schemas import (
    LI_SMALL_ACCOUNT_TOLERANCE,
    LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS,
    LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS,
    LI_SMALL_EXPECTED_RAW_TRANSACTIONS,
    LI_SMALL_LAUNDERING_RATE_MAX,
    LI_SMALL_LAUNDERING_RATE_MIN,
    LI_SMALL_TRANSACTION_TOLERANCE,
)
from src.data.split import assert_time_split_valid


class DataQualityError(Exception):
    pass


def sums_close(
    a: float,
    b: float,
    *,
    rel_tol: float = 1e-6,
    abs_tol: float = 1.0,
) -> bool:
    """Relative tolerance for large float64 sums (~7M rows); abs floor for tiny totals."""
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b), 1.0), abs_tol)


def run_dq(
    transactions: pd.DataFrame,
    accounts: pd.DataFrame,
    etl_stats: dict,
    *,
    strict_li_small_stats: bool = False,
    rel_tol: float = 1e-6,
    abs_tol: float = 1.0,
) -> dict:
    """
    Return a DQ report. Raises DataQualityError on hard failures.
    Soft checks (post-filter active account count, laundering rate) warn unless
    strict_li_small_stats.
    """
    report: dict = {"ok": True, "hard_failures": [], "warnings": [], "metrics": {}}

    n_raw = etl_stats["n_raw"]
    n_self = etl_stats["n_self_loops"]
    n_loaded = etl_stats["n_loaded"]
    report["metrics"]["n_raw"] = n_raw
    report["metrics"]["n_self_loops"] = n_self
    report["metrics"]["n_loaded"] = n_loaded

    # Row identity: no parse loss
    if n_loaded + n_self != n_raw:
        report["hard_failures"].append(
            f"Row identity failed: n_loaded({n_loaded}) + n_self_loops({n_self}) != n_raw({n_raw})"
        )

    # Strict source identity uses the raw row population; downstream model
    # completeness uses the post-self-loop population. Checking both catches a
    # truncated source as well as a broken filtering step.
    transaction_populations = (
        ("Raw transaction", n_raw, LI_SMALL_EXPECTED_RAW_TRANSACTIONS),
        ("Active transaction", n_loaded, LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS),
    )
    for label, observed, expected in transaction_populations:
        lo = expected * (1 - LI_SMALL_TRANSACTION_TOLERANCE)
        hi = expected * (1 + LI_SMALL_TRANSACTION_TOLERANCE)
        if observed and not (lo <= observed <= hi):
            msg = f"{label} count {observed} outside expected ~{expected} ±{LI_SMALL_TRANSACTION_TOLERANCE:.0%}"
            if strict_li_small_stats:
                report["hard_failures"].append(msg)
            else:
                report["warnings"].append(msg)

    # Sum of originals: loaded + self_loops == raw file totals (relative float tolerance)
    paid_recon = etl_stats["sum_amount_paid_orig"] + etl_stats["sum_amount_paid_self_loops"]
    recv_recon = etl_stats["sum_amount_received_orig"] + etl_stats["sum_amount_received_self_loops"]
    paid_raw = etl_stats["sum_amount_paid_raw_all"]
    recv_raw = etl_stats["sum_amount_received_raw_all"]
    if not sums_close(paid_recon, paid_raw, rel_tol=rel_tol, abs_tol=abs_tol):
        report["hard_failures"].append(f"Amount Paid sum mismatch: recon={paid_recon} raw={paid_raw}")
    if not sums_close(recv_recon, recv_raw, rel_tol=rel_tol, abs_tol=abs_tol):
        report["hard_failures"].append(f"Amount Received sum mismatch: recon={recv_recon} raw={recv_raw}")

    # No remaining self-loops
    if len(transactions) and (transactions["from_account_key"] == transactions["to_account_key"]).any():
        report["hard_failures"].append("Self-loops remain in loaded transactions")

    # Unique transaction_id
    if len(transactions) and transactions["transaction_id"].nunique() != len(transactions):
        report["hard_failures"].append("Duplicate transaction_id values")

    # Time split
    try:
        assert_time_split_valid(transactions)
        report["metrics"]["time_split_ok"] = True
    except AssertionError as exc:
        report["hard_failures"].append(str(exc))
        report["metrics"]["time_split_ok"] = False

    # Laundering rate
    if len(transactions):
        rate = float(transactions["label_laundering"].mean())
        report["metrics"]["laundering_rate"] = rate
        if not (LI_SMALL_LAUNDERING_RATE_MIN <= rate <= LI_SMALL_LAUNDERING_RATE_MAX):
            msg = f"Laundering rate {rate:.6f} outside LI-Small band; wrong dataset?"
            if strict_li_small_stats:
                report["hard_failures"].append(msg)
            else:
                report["warnings"].append(msg)

    # Active account count after the canonical self-loop filter. The published
    # 705,907 figure is the raw endpoint population and is not comparable to
    # this post-filter account dimension.
    n_accounts = len(accounts)
    report["metrics"]["n_accounts"] = n_accounts
    report["metrics"]["account_population"] = "active_endpoints_after_self_loop_filter"
    lo = LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS * (1 - LI_SMALL_ACCOUNT_TOLERANCE)
    hi = LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS * (1 + LI_SMALL_ACCOUNT_TOLERANCE)
    if n_accounts and not (lo <= n_accounts <= hi):
        msg = (
            f"Active account count {n_accounts} outside expected post-filter "
            f"~{LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS} ±{LI_SMALL_ACCOUNT_TOLERANCE:.0%}"
        )
        if strict_li_small_stats:
            report["hard_failures"].append(msg)
        else:
            report["warnings"].append(msg)

    # Time gaps (soft): flag if any gap > 2 days for LI-Small (~10 day span)
    if len(transactions) >= 2:
        ts = transactions["occurred_at"].sort_values()
        max_gap = (ts.diff().max()).total_seconds() / 86400.0
        report["metrics"]["max_day_gap"] = max_gap
        if max_gap > 2.0:
            report["warnings"].append(f"Unusual time gap of {max_gap:.2f} days")

    # Raw account collision diagnostic (same account_raw, different banks → keys differ)
    if len(accounts):
        collision_groups = accounts.groupby("account_raw")["bank_id"].nunique()
        multi_bank = int((collision_groups > 1).sum())
        report["metrics"]["raw_account_multi_bank"] = multi_bank

    report["ok"] = len(report["hard_failures"]) == 0
    if not report["ok"]:
        raise DataQualityError("; ".join(report["hard_failures"]))
    return report


def write_dq_report(report: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
