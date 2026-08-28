"""Fixtures cho test nhánh SAML-D — dữ liệu TỔNG HỢP hình dạng giống SAML-D.

Không nạp 9,5 triệu dòng thật trong test: dựng một CSV nhỏ đúng cột thô của
SAML-D để kiểm loader/split/leakage nhanh và tất định.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def raw_samld_csv(tmp_path: Path) -> Path:
    """Một CSV nhỏ đúng lược đồ THÔ của SAML-D (tên cột gốc)."""
    rng = np.random.default_rng(0)
    n = 400
    countries = ["UK", "UAE", "Turkey", "Mexico", "India", "Germany"]
    currencies = ["UK pounds", "Dirham", "Turkish lira", "Mexican Peso", "Euro"]
    ptypes = ["Cash Deposit", "Cross-border", "Cheque", "ACH", "Credit card"]
    # Ngày tăng dần để có trục thời gian cho chronological split.
    days = pd.date_range("2022-10-07", periods=n, freq="6h")
    sc = rng.integers(0, len(countries), n)
    rc = rng.integers(0, len(countries), n)
    frame = pd.DataFrame(
        {
            "Time": [d.strftime("%H:%M:%S") for d in days],
            "Date": [d.strftime("%Y-%m-%d") for d in days],
            "Sender_account": rng.integers(10**9, 10**10, n).astype(str),
            "Receiver_account": rng.integers(10**9, 10**10, n).astype(str),
            "Amount": np.round(rng.uniform(10, 50000, n), 2),
            "Payment_currency": [currencies[i % len(currencies)] for i in sc],
            "Received_currency": [currencies[i % len(currencies)] for i in rc],
            "Sender_bank_location": [countries[i] for i in sc],
            "Receiver_bank_location": [countries[i] for i in rc],
            "Payment_type": rng.choice(ptypes, n),
            "Is_laundering": (rng.uniform(0, 1, n) < 0.05).astype(int),
            "Laundering_type": "Normal",
        }
    )
    # Gán vài typology thật cho các dòng dương, để test per-typology.
    pos = frame["Is_laundering"] == 1
    frame.loc[pos, "Laundering_type"] = rng.choice(["Structuring", "Fan_In", "Smurfing"], pos.sum())
    path = tmp_path / "SAML-D.csv"
    frame.to_csv(path, index=False)
    return path
