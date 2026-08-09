"""Feature extraction cấp account — Polars groupby/agg, không for-loop từng account."""

from __future__ import annotations

from pathlib import Path

import polars as pl

PROCESSED_DIR = Path("data/processed")
SPLITS = ("train", "val", "test")


def _to_account_events(tx: pl.DataFrame) -> pl.DataFrame:
    """Vectorized: mỗi giao dịch → 2 sự kiện (credit vào / debit ra)."""
    base = tx.with_columns(
        [
            (pl.col("amount") >= 9000).and_(pl.col("amount") < 10000).cast(pl.Float64).alias("is_near_threshold"),
            pl.col("timestamp").dt.hour().is_in([0, 1, 2, 3, 4, 5]).cast(pl.Float64).alias("is_off_hour"),
            (pl.col("from_bank") != pl.col("to_bank")).cast(pl.Float64).alias("is_interbank"),
        ]
    )

    credit = base.select(
        [
            pl.col("timestamp"),
            pl.col("to_account_key").alias("account_key"),
            pl.col("amount").alias("amount"),
            pl.col("amount").alias("amount_in"),
            pl.lit(0.0).alias("amount_out"),
            pl.col("is_near_threshold"),
            pl.col("is_off_hour"),
            pl.col("is_interbank"),
        ]
    )
    debit = base.select(
        [
            pl.col("timestamp"),
            pl.col("from_account_key").alias("account_key"),
            pl.col("amount").alias("amount"),
            pl.lit(0.0).alias("amount_in"),
            pl.col("amount").alias("amount_out"),
            pl.col("is_near_threshold"),
            pl.col("is_off_hour"),
            pl.col("is_interbank"),
        ]
    )
    return pl.concat([credit, debit], how="vertical")


def extract_split_features(tx: pl.DataFrame) -> pl.DataFrame:
    """Tính toàn bộ feature bằng with_columns + groupby().agg()."""
    events = _to_account_events(tx)
    max_dt = events.select(pl.col("timestamp").max()).item()
    if max_dt is None:
        return pl.DataFrame()

    events = events.with_columns(
        [
            (pl.col("timestamp") >= max_dt - pl.duration(days=1)).alias("in_1d"),
            (pl.col("timestamp") >= max_dt - pl.duration(days=7)).alias("in_7d"),
            (pl.col("timestamp") >= max_dt - pl.duration(days=30)).alias("in_30d"),
        ]
    )

    # Nhân mask thay vì filter-trong-agg — nhanh và tương thích Polars rộng
    events = events.with_columns(
        [
            (pl.col("amount") * pl.col("in_1d").cast(pl.Float64)).alias("amt_1d"),
            (pl.col("amount") * pl.col("in_7d").cast(pl.Float64)).alias("amt_7d"),
            (pl.col("amount") * pl.col("in_30d").cast(pl.Float64)).alias("amt_30d"),
            pl.col("in_1d").cast(pl.Int64).alias("cnt_1d"),
            pl.col("in_7d").cast(pl.Int64).alias("cnt_7d"),
            pl.col("in_30d").cast(pl.Int64).alias("cnt_30d"),
        ]
    )

    feats = events.group_by("account_key").agg(
        [
            # Volume & Count (cửa sổ trượt so với max timestamp của split)
            pl.col("amt_1d").sum().fill_null(0).alias("vol_1d"),
            pl.col("amt_7d").sum().fill_null(0).alias("vol_7d"),
            pl.col("amt_30d").sum().fill_null(0).alias("vol_30d"),
            pl.col("cnt_1d").sum().fill_null(0).alias("tx_cnt_1d"),
            pl.col("cnt_7d").sum().fill_null(0).alias("tx_cnt_7d"),
            pl.col("cnt_30d").sum().fill_null(0).alias("tx_cnt_30d"),
            # Flow & Threshold
            pl.col("is_near_threshold").mean().fill_null(0).alias("near_threshold_ratio"),
            (pl.col("amount_in").sum() / (pl.col("amount_out").sum() + pl.lit(1e-6))).alias(
                "credit_debit_ratio"
            ),
            pl.col("amount").std().fill_null(0).alias("amount_std"),
            # Time & Channel
            pl.col("is_off_hour").mean().fill_null(0).alias("off_hour_ratio"),
            pl.col("is_interbank").mean().fill_null(0).alias("interbank_ratio"),
        ]
    )

    # Làm tròn nhẹ cho ổn định CSV
    float_cols = [
        "vol_1d",
        "vol_7d",
        "vol_30d",
        "near_threshold_ratio",
        "credit_debit_ratio",
        "amount_std",
        "off_hour_ratio",
        "interbank_ratio",
    ]
    feats = feats.with_columns([pl.col(c).round(4) for c in float_cols])
    return feats.sort("account_key")


def extract_features() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for split in SPLITS:
        src = PROCESSED_DIR / f"transactions_{split}.parquet"
        if not src.exists():
            raise FileNotFoundError(
                f"❌ Không tìm thấy {src}. Hãy chạy scripts/ingest_data.py trước!"
            )
        print(f"⏳ [{split}] Đọc {src} và aggregate features (groupby)...")
        tx = pl.read_parquet(src)
        feats = extract_split_features(tx)
        out = PROCESSED_DIR / f"features_{split}.csv"
        feats.write_csv(out)
        print(f"   ✅ {out} | accounts={feats.height:,} | cols={feats.width}")

    print("🎉 FEATURE EXTRACTION XONG → data/processed/features_{train,val,test}.csv")


if __name__ == "__main__":
    extract_features()
