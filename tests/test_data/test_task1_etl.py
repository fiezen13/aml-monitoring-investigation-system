"""Tests for FIN-07 Task 1 ETL / DQ / split."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.data.build_accounts import build_accounts
from src.data.currency import UnknownCurrencyError, to_usd
from src.data.dq import DataQualityError, run_dq, sums_close
from src.data.etl_transactions import read_raw_transactions, transform_transactions
from src.data.pipeline import run_task1_etl
from src.data.schemas import (
    LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS,
    LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS,
    LI_SMALL_EXPECTED_RAW_ENDPOINT_ACCOUNTS,
    LI_SMALL_EXPECTED_RAW_TRANSACTIONS,
    TRANSACTION_ALL_COLUMNS,
    TRANSACTION_FEATURE_COLUMNS,
    assert_no_label_leakage,
    feature_columns,
    make_account_key,
)
from src.data.split import assert_time_split_valid, assign_time_split

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_li_sample.csv"

# All currency names observed in IBM LI-Small
IBM_LI_SMALL_CURRENCIES = [
    "Australian Dollar",
    "Bitcoin",
    "Brazil Real",
    "Canadian Dollar",
    "Euro",
    "Mexican Peso",
    "Ruble",
    "Rupee",
    "Saudi Riyal",
    "Shekel",
    "Swiss Franc",
    "UK Pound",
    "US Dollar",
    "Yen",
    "Yuan",
]


@pytest.fixture
def raw_df() -> pd.DataFrame:
    return read_raw_transactions(FIXTURE)


def test_sums_close_relative_tolerance() -> None:
    # LI-Small-scale float noise must pass
    assert sums_close(32377102200535.16, 32377102200535.1)
    assert sums_close(43788147053548.17, 43788147053548.266)
    # Real data loss must fail
    assert not sums_close(1000.0, 900.0)


def test_ibm_currency_names_convert_to_usd() -> None:
    for name in IBM_LI_SMALL_CURRENCIES:
        assert to_usd(1.0, name) > 0
    assert to_usd(100.0, "US Dollar") == to_usd(100.0, "USD")
    assert to_usd(1.0, "Euro") == to_usd(1.0, "EUR")
    with pytest.raises(UnknownCurrencyError):
        to_usd(1.0, "NotACurrency")


def test_etl_mapping_and_self_loops(raw_df: pd.DataFrame) -> None:
    tx, stats = transform_transactions(raw_df)
    assert stats["n_raw"] == 12
    assert stats["n_self_loops"] == 1
    assert stats["n_loaded"] == 11
    assert stats["n_loaded"] + stats["n_self_loops"] == stats["n_raw"]

    assert "label_laundering" in tx.columns
    assert set(TRANSACTION_FEATURE_COLUMNS) - {"split"} <= set(tx.columns)

    # Bank+Account keys: same raw ACC001 at banks 1 and 4 must differ
    keys = set(tx["from_account_key"]) | set(tx["to_account_key"])
    assert make_account_key(1, "ACC001") in keys
    assert make_account_key(4, "ACC001") in keys
    assert make_account_key(1, "ACC001") != make_account_key(4, "ACC001")

    assert (tx["from_account_key"] != tx["to_account_key"]).all()
    assert (
        tx["channel"].isin({"ACH", "WIRE", "CHEQUE", "CREDIT_CARD", "CASH", "BITCOIN", "REINVESTMENT", "OTHER"}).all()
    )
    assert tx["currency"].eq("USD").all()
    assert tx["transaction_id"].is_unique


def test_no_label_leakage_helper() -> None:
    cols = feature_columns(TRANSACTION_ALL_COLUMNS)
    assert_no_label_leakage(cols)
    assert "label_laundering" not in cols
    with pytest.raises(AssertionError, match="Label leakage"):
        assert_no_label_leakage(list(TRANSACTION_ALL_COLUMNS))


def test_time_split_no_future_leak(raw_df: pd.DataFrame) -> None:
    tx, _ = transform_transactions(raw_df)
    tx, cutoffs = assign_time_split(tx)
    assert_time_split_valid(tx)
    assert set(tx["split"]) <= {"train", "val", "test"}
    assert cutoffs["n"] == len(tx)


def test_accounts_built(raw_df: pd.DataFrame) -> None:
    tx, _ = transform_transactions(raw_df)
    tx, _ = assign_time_split(tx)
    accounts = build_accounts(tx)
    assert accounts["account_key"].is_unique
    assert accounts["tx_count_out"].ge(0).all()
    assert accounts["tx_count_in"].ge(0).all()


def test_li_small_account_populations_match_etl_contract() -> None:
    """Do not compare post-filter graph nodes with raw endpoint population."""
    assert LI_SMALL_EXPECTED_RAW_TRANSACTIONS == 6_924_049
    assert LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS == 6_119_572
    assert LI_SMALL_EXPECTED_RAW_ENDPOINT_ACCOUNTS == 705_907
    assert LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS == 576_781
    assert LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS < LI_SMALL_EXPECTED_RAW_TRANSACTIONS
    assert LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS < LI_SMALL_EXPECTED_RAW_ENDPOINT_ACCOUNTS


def test_dq_passes_on_fixture(raw_df: pd.DataFrame) -> None:
    tx, stats = transform_transactions(raw_df)
    tx, _ = assign_time_split(tx)
    accounts = build_accounts(tx)
    report = run_dq(tx, accounts, stats, strict_li_small_stats=False)
    assert report["ok"]
    # fixture is tiny → expect soft warnings on LI-Small bands
    assert report["warnings"]


def test_reproducibility(tmp_path: Path) -> None:
    db1 = tmp_path / "a.duckdb"
    db2 = tmp_path / "b.duckdb"
    r1 = run_task1_etl(FIXTURE, db1, seed=42, report_dir=tmp_path / "r1")
    r2 = run_task1_etl(FIXTURE, db2, seed=42, report_dir=tmp_path / "r2")
    assert r1["dq_report"]["checksums"] == r2["dq_report"]["checksums"]
    assert len(r1["dq_report"]["checksums"]["transaction"]) == 64


def test_duckdb_load_and_indexes(tmp_path: Path) -> None:
    db = tmp_path / "aml.duckdb"
    run_task1_etl(FIXTURE, db, seed=42, report_dir=tmp_path)
    con = duckdb.connect(str(db))
    n_tx = con.execute("SELECT COUNT(*) FROM transaction").fetchone()[0]
    n_acct = con.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    assert n_tx == 11
    assert n_acct >= 1
    indexes = con.execute("SELECT index_name FROM duckdb_indexes()").fetchall()
    names = {r[0] for r in indexes}
    assert "idx_tx_from" in names
    assert "idx_acct_pk" in names
    con.close()


def test_dq_fails_on_row_loss(raw_df: pd.DataFrame) -> None:
    tx, stats = transform_transactions(raw_df)
    tx, _ = assign_time_split(tx)
    accounts = build_accounts(tx)
    bad_stats = {**stats, "n_raw": stats["n_raw"] + 1}
    with pytest.raises(DataQualityError, match="Row identity"):
        run_dq(tx, accounts, bad_stats)
