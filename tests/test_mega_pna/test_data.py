from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from src.mega_pna.data import format_kaggle_file, temporal_split

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


def test_formatter_preserves_official_contract_and_first_seen_ids(tmp_path: Path) -> None:
    raw = tmp_path / "HI-Small_Trans.csv"
    with raw.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        writer.writerows(
            [
                ["2022/09/01 00:20", "010", "A", "001", "B", "4", "Euro", "5", "US Dollar", "ACH", "1"],
                ["2022/09/01 00:10", "001", "B", "001", "B", "2", "US Dollar", "2", "US Dollar", "Cheque", "0"],
                ["2022/09/02 00:10", "010", "A", "001", "B", "3", "Euro", "3", "Euro", "ACH", "0"],
            ]
        )
    output = tmp_path / "formatted_transactions.csv"
    manifest = format_kaggle_file(raw, output)
    frame = pd.read_csv(output)

    assert frame.columns.tolist() == [
        "EdgeID",
        "from_id",
        "to_id",
        "Timestamp",
        "Amount Sent",
        "Sent Currency",
        "Amount Received",
        "Received Currency",
        "Payment Format",
        "Is Laundering",
    ]
    assert frame.EdgeID.tolist() == [1, 0, 2]
    assert frame.Timestamp.tolist() == [610, 1210, 87010]
    # Account IDs are based on first source occurrence, not sorted output order.
    assert frame.from_id.tolist() == [1, 0, 0]
    assert frame.to_id.tolist() == [1, 1, 1]
    assert frame["Sent Currency"].tolist() == [1, 1, 0]
    assert frame["Received Currency"].tolist() == [1, 0, 0]
    assert frame["Payment Format"].tolist() == [1, 0, 0]
    assert manifest["rows"] == 3
    assert manifest["self_transfers"] == 1
    assert manifest["positives"] == 1


def test_temporal_split_uses_whole_days_nearest_to_60_20_20() -> None:
    timestamps = np.concatenate(
        [
            np.full(60, 10.0),
            np.full(20, 86_410.0),
            np.full(20, 172_810.0),
        ]
    )
    split = temporal_split(timestamps)
    assert (split.train_end, split.validation_end, split.total) == (60, 80, 100)
    assert split.train_days == (0,)
    assert split.validation_days == (1,)
    assert split.test_days == (2,)
