"""Ingestion IBM AML LI-Small — Polars vectorized, ND1 labels tách riêng, ND2 time-split 60/20/20."""

from __future__ import annotations

from pathlib import Path

import polars as pl

RAW_PATH = Path("data/raw/ibm-aml/LI-Small_Trans.csv")
PROCESSED_DIR = Path("data/processed")

SCHEMA_NAMES = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account.1",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]

TX_COLS = [
    "transaction_id",
    "timestamp",
    "from_account_key",
    "to_account_key",
    "from_bank",
    "to_bank",
    "amount",
]


def _read_ibm_csv(path: Path) -> pl.DataFrame:
    """Đọc 1 pass (vectorized). Đặt tên cột tường minh vì CSV có 2 cột Account trùng."""
    print(f"⏳ Đọc {path} (Polars, 1 pass)...")
    df = pl.read_csv(
        path,
        has_header=False,
        skip_rows=1,
        new_columns=SCHEMA_NAMES,
        truncate_ragged_lines=True,
        ignore_errors=True,
        infer_schema_length=50_000,
        n_threads=0,  # dùng hết CPU
        low_memory=True,
    )
    print(f"   raw rows={df.height:,}. Chuẩn hóa khóa / datetime UTC...")

    df = (
        df.with_columns(
            [
                pl.col("Timestamp")
                .str.strptime(pl.Datetime, format="%Y/%m/%d %H:%M", strict=False)
                .dt.replace_time_zone("UTC")
                .alias("timestamp"),
                (pl.col("From Bank").cast(pl.Utf8) + pl.lit(":") + pl.col("Account").cast(pl.Utf8)).alias(
                    "from_account_key"
                ),
                (pl.col("To Bank").cast(pl.Utf8) + pl.lit(":") + pl.col("Account.1").cast(pl.Utf8)).alias(
                    "to_account_key"
                ),
                pl.col("From Bank").cast(pl.Utf8).alias("from_bank"),
                pl.col("To Bank").cast(pl.Utf8).alias("to_bank"),
                pl.col("Amount Paid").cast(pl.Float64, strict=False).alias("amount"),
                pl.col("Is Laundering").cast(pl.Int8, strict=False).fill_null(0).alias("is_laundering"),
            ]
        )
        .select(
            [
                "timestamp",
                "from_account_key",
                "to_account_key",
                "from_bank",
                "to_bank",
                "amount",
                "is_laundering",
            ]
        )
        .drop_nulls(subset=["timestamp", "from_account_key", "to_account_key", "amount"])
    )

    print(f"✅ Hợp lệ={df.height:,}. Sort tăng dần theo timestamp...")
    df = df.sort("timestamp", maintain_order=True)
    df = df.with_columns(pl.arange(0, df.height).cast(pl.Int64).alias("transaction_id"))
    return df


def ingest_data() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"❌ Không tìm thấy {RAW_PATH}. Hãy giải nén LI-Small_Trans.csv vào data/raw/ibm-aml/"
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = _read_ibm_csv(RAW_PATH)

    # ND1: tách nhãn khỏi đặc trưng
    labels = df.select(
        [
            "transaction_id",
            "timestamp",
            "from_account_key",
            "to_account_key",
            pl.col("is_laundering").alias("Is Laundering"),
        ]
    )
    labels_path = PROCESSED_DIR / "labels.csv"
    labels.write_csv(labels_path)
    print(f"📁 Labels (ND1): {labels_path} ({labels.height:,} dòng)")

    tx = df.select(TX_COLS)
    n = tx.height
    train_end = int(n * 0.60)
    val_end = int(n * 0.80)

    splits = {
        "train": tx.slice(0, train_end),
        "val": tx.slice(train_end, val_end - train_end),
        "test": tx.slice(val_end, n - val_end),
    }

    print("⏳ ND2 — tách theo mốc thời gian 60/20/20 → Parquet...")
    for name, part in splits.items():
        out = PROCESSED_DIR / f"transactions_{name}.parquet"
        part.write_parquet(out, compression="zstd")
        t_min = part.select(pl.col("timestamp").min()).item()
        t_max = part.select(pl.col("timestamp").max()).item()
        print(f"   {name:5s}: {part.height:>10,} tx | {t_min} → {t_max} | {out}")

    n_lau = int(labels.select(pl.col("Is Laundering").sum()).item())
    print(
        f"🎉 INGEST XONG | total={n:,} train={splits['train'].height:,} "
        f"val={splits['val'].height:,} test={splits['test'].height:,} laundering_tx={n_lau:,}"
    )


if __name__ == "__main__":
    ingest_data()
