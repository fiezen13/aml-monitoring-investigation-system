from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from scripts.prepare_ibm_benchmark import build

HEADER = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]


def _source(path: Path) -> Path:
    rows = []
    for day in range(1, 5):
        for index in range(6):
            laundering = "1" if (day == 4 and index == 0) else "0"
            rows.append(
                [
                    f"2022/09/{day:02d} {index:02d}:00",
                    "010",
                    "AAA1000",
                    "020",
                    f"C{index:04d}",
                    "1000.00",
                    "US Dollar",
                    "1000.00",
                    "US Dollar",
                    "Cheque",
                    laundering,
                ]
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def _build(tmp_path: Path) -> tuple[Path, dict]:
    output = tmp_path / "aml.duckdb"
    result = build(
        _source(tmp_path / "src.csv"),
        output,
        limit=100,
        scan_limit=0,
        min_active_days=2,
        min_transactions=2,
        currency_name="US Dollar",
    )
    return output, result


def test_benchmark_db_keeps_the_ground_truth_the_operational_batch_strips(tmp_path: Path) -> None:
    output, result = _build(tmp_path)

    connection = duckdb.connect(str(output), read_only=True)
    try:
        positives = connection.execute("SELECT count(*) FROM transaction WHERE label_laundering = 1").fetchone()[0]
    finally:
        connection.close()

    assert positives == 1
    assert result["labelled_transactions"] == 1
    assert result["labelled_accounts"] == 2


def test_splits_are_chronological_so_evaluation_never_scores_the_past(tmp_path: Path) -> None:
    output, _ = _build(tmp_path)

    connection = duckdb.connect(str(output), read_only=True)
    try:
        bounds = dict(
            (split, (start, end))
            for split, start, end in connection.execute(
                # Cast to text: returning TIMESTAMPTZ to Python needs pytz, which
                # is not a dependency here and adds nothing to this assertion.
                "SELECT split, min(occurred_at)::VARCHAR, max(occurred_at)::VARCHAR FROM transaction GROUP BY split"
            ).fetchall()
        )
    finally:
        connection.close()

    assert bounds["train"][1] <= bounds["val"][0]
    assert bounds["val"][1] <= bounds["test"][0]


def test_the_subject_manifest_is_written_next_to_the_database(tmp_path: Path) -> None:
    output, result = _build(tmp_path)

    manifest = Path(str(result["subject_accounts_manifest"]))
    assert manifest.exists()
    assert "010:AAA1000" in manifest.read_text(encoding="utf-8").split()
