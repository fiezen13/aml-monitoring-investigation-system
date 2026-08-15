#!/usr/bin/env python3
"""Train and evaluate the reviewed 7-day Behaviour detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_model import evaluate_model  # noqa: E402
from scripts.extract_features import extract_features  # noqa: E402
from scripts.generate_scores import generate_scores  # noqa: E402
from scripts.train_isolation_forest import train  # noqa: E402
from src.data.schemas import (  # noqa: E402
    LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS,
    LI_SMALL_TRANSACTION_TOLERANCE,
)

WINDOW = "7d"
WINDOW_DAYS = 7
FULL_LI_SMALL_MIN_TRANSACTIONS = int(LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS * (1 - LI_SMALL_TRANSACTION_TOLERANCE))
FULL_LI_SMALL_MAX_TRANSACTIONS = int(LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS * (1 + LI_SMALL_TRANSACTION_TOLERANCE))
FULL_LI_SMALL_MIN_CALENDAR_DAYS = 17


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data/processed/aml.duckdb")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/processed/behavior-7d",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=ROOT / "reports/behavior-7d",
    )
    parser.add_argument("--target-recall", type=float, default=0.80)
    parser.add_argument("--precision-at-k", default="50,100,500,1000")
    parser.add_argument(
        "--require-full-li-small",
        action="store_true",
        help="Refuse non-canonical DuckDB inputs (post-filter LI-Small count and >=17 calendar days)",
    )
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _db_metadata(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = duckdb.connect(str(path), read_only=True)
    try:
        rows = connection.execute(
            """SELECT split, count(*), min(occurred_at), max(occurred_at)
                 FROM transaction
                GROUP BY split"""
        ).fetchall()
        total, start, end = connection.execute(
            "SELECT count(*), min(occurred_at), max(occurred_at) FROM transaction"
        ).fetchone()
    finally:
        connection.close()
    splits = {str(split): int(count) for split, count, _, _ in rows}
    if set(splits) != {"train", "val", "test"}:
        raise RuntimeError(f"DuckDB phai co du train/val/test, nhan duoc {splits}")
    return {
        "transactions": int(total),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "calendar_span_days": int((end.date() - start.date()).days + 1),
        "transactions_by_split": splits,
    }


def _artifact_metadata(path: Path) -> dict[str, object]:
    connection = duckdb.connect()
    try:
        count, start, end = connection.execute(
            "SELECT count(*), min(as_of_ts), max(as_of_ts) FROM read_parquet(?)",
            [str(path)],
        ).fetchone()
    finally:
        connection.close()
    return {
        "path": _display_path(path),
        "sha256": sha256(path),
        "rows": int(count),
        "as_of_min": start.isoformat(),
        "as_of_max": end.isoformat(),
    }


def _require_full_li_small(metadata: dict[str, object]) -> None:
    transactions = int(metadata["transactions"])
    calendar_days = int(metadata["calendar_span_days"])
    if (
        not FULL_LI_SMALL_MIN_TRANSACTIONS <= transactions <= FULL_LI_SMALL_MAX_TRANSACTIONS
        or calendar_days < FULL_LI_SMALL_MIN_CALENDAR_DAYS
    ):
        raise RuntimeError(
            "DuckDB khong phai LI-Small day du: "
            f"transactions={transactions:,}, calendar_days={calendar_days}; "
            f"can {FULL_LI_SMALL_MIN_TRANSACTIONS:,}..{FULL_LI_SMALL_MAX_TRANSACTIONS:,} "
            "post-filter transactions va "
            f">= {FULL_LI_SMALL_MIN_CALENDAR_DAYS} ngay. Hay chay lai scripts/run_task1_etl.py."
        )


def run(args: argparse.Namespace) -> dict[str, object]:
    if not 0 < args.target_recall <= 1:
        raise ValueError("--target-recall phai trong (0, 1]")
    precision_at_k = tuple(int(item.strip()) for item in args.precision_at_k.split(",") if item.strip())
    if not precision_at_k or any(item <= 0 for item in precision_at_k):
        raise ValueError("--precision-at-k phai gom cac so nguyen duong")

    db_path = args.db.resolve()
    output_dir = args.output_dir.resolve()
    reports_dir = args.reports_dir.resolve()
    db_metadata = _db_metadata(db_path)
    if args.require_full_li_small:
        _require_full_li_small(db_metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    extract_features(WINDOW, db_path, output_dir)
    model = train(WINDOW, output_dir, "if_behavior_7d_v2")
    scores = generate_scores(
        WINDOW,
        model,
        output_dir / "if_scores_7d.parquet",
        output_dir,
    )
    report = reports_dir / "evaluation_7d.txt"
    threshold = reports_dir / "best_threshold_7d.txt"
    evaluate_model(
        scores_path=scores,
        db_path=db_path,
        window=WINDOW,
        report_path=report,
        target_recall=args.target_recall,
        precision_at_k=precision_at_k,
        features_dir=output_dir,
        threshold_out=threshold,
    )

    features = {
        split: _artifact_metadata(output_dir / f"features_{split}_7d.parquet") for split in ("train", "val", "test")
    }
    mature_after = datetime.fromisoformat(str(db_metadata["start"])) + timedelta(days=WINDOW_DAYS)
    train_as_of_max = datetime.fromisoformat(str(features["train"]["as_of_max"]))
    train_has_mature_snapshot = train_as_of_max >= mature_after
    warnings = []
    if not train_has_mature_snapshot:
        warnings.append("train has no fully mature 7-day snapshot; this release remains a research baseline")

    manifest = {
        "schema_version": "fin07.behavior.7d.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": {
            "window": WINDOW,
            "features": "continuous point-in-time rolling history",
            "fit": "train only",
            "threshold_selection": "validation only",
            "test": "one final pass",
        },
        "dataset": db_metadata,
        "warnings": warnings,
        "first_fully_mature_as_of": mature_after.astimezone(UTC).isoformat(),
        "train_has_fully_mature_snapshot": train_has_mature_snapshot,
        "features": features,
        "model": {"path": _display_path(model), "sha256": sha256(model)},
        "scores": _artifact_metadata(scores),
        "evaluation_report": _display_path(report),
        "threshold": float(threshold.read_text(encoding="utf-8").strip()),
    }
    manifest_path = reports_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
