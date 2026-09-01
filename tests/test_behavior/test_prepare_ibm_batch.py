from __future__ import annotations

import csv
from pathlib import Path

from scripts.prepare_ibm_behavior_batch import prepare, select_accounts
from src.behavior.batch import parse_batch_csv

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/aml/HI-Sample_Trans.csv"
MULTI_DAY = ROOT / "tests/fixtures/aml/Multi-Day_Trans.csv"


def test_prepare_ibm_batch_removes_labels_and_emits_canonical_rows(tmp_path: Path) -> None:
    output = tmp_path / "batch.csv"

    result = prepare(
        FIXTURE,
        output,
        limit=5,
        scan_limit=200,
        min_active_days=1,
        min_transactions=1,
        currency_name="US Dollar",
        currency_code="USD",
    )

    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert "Is Laundering" not in (reader.fieldnames or [])
        assert "label_laundering" not in (reader.fieldnames or [])
    parsed = parse_batch_csv(output)
    assert len(parsed.transactions) == 5
    assert result["labels_written"] == 0


def _rows(output: Path) -> list[dict[str, str]]:
    with output.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_selected_accounts_keep_their_whole_history_across_the_file_span(tmp_path: Path) -> None:
    output = tmp_path / "batch.csv"

    result = prepare(
        MULTI_DAY,
        output,
        limit=200,
        scan_limit=0,
        min_active_days=2,
        min_transactions=2,
        currency_name="US Dollar",
        currency_code="USD",
    )

    rows = _rows(output)
    days = {row["occurred_at"][:10] for row in rows}
    # Taking a prefix of this time-ordered file yields one day; selecting whole
    # accounts must span every day they transact on.
    assert len(days) == 4
    assert result["accounts_selected"] >= 1
    assert result["max_active_days"] == 4


def _rows_touching(path: Path, account: str) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))[1:]
    return sum(1 for row in rows if account in (f"{row[1]}:{row[2]}", f"{row[3]}:{row[4]}"))


def test_a_selected_account_keeps_every_row_it_appears_in(tmp_path: Path) -> None:
    output = tmp_path / "capped.csv"
    settings = dict(
        scan_limit=0,
        min_active_days=2,
        min_transactions=2,
        currency_name="US Dollar",
    )
    selected, _ = select_accounts(MULTI_DAY, limit=20, **settings)
    prepare(MULTI_DAY, output, limit=20, currency_code="USD", **settings)

    written: dict[str, int] = {}
    for row in _rows(output):
        for key in (f"{row['from_bank']}:{row['from_account']}", f"{row['to_bank']}:{row['to_account']}"):
            written[key] = written.get(key, 0) + 1

    assert selected
    for account in selected:
        # A tighter ceiling may drop a selected account entirely, but never keep
        # a clipped slice of one — that is the artefact this selection removes.
        # Unselected accounts legitimately appear in part, as counterparties.
        assert written.get(account) == _rows_touching(MULTI_DAY, account), account
