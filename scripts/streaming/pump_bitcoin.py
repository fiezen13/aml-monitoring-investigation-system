"""Bơm Bitcoin (Elliptic) TỪNG TIMESTEP theo kiến trúc medallion.

Bitcoin RF chấm ĐỘC LẬP từng giao dịch (stateless) — streaming = batch y hệt. Mỗi
timestep:
  1. đặc trưng thô (166 cột) → BRONZE Parquet (phân vùng theo timestep), KHÔNG vào PG;
  2. RF chấm in-mem (BitcoinScoringContext.build_records);
  3. kết quả (điểm + giải thích) → `bitcoin_scored_tx` (Postgres output) — bảng này
     KHÔNG chứa 166 đặc trưng thô, chỉ output.

Chạy: PYTHONPATH=. python scripts/streaming/pump_bitcoin.py --from-timestep 35
"""
from __future__ import annotations

import argparse
import time

import pandas as pd

from src.bitcoin_aml.scoring import BitcoinScoringContext, DATA, FEATURE_COLUMNS
from src.bitcoin_aml.stream import RELEASE_ID, _ensure_release, _write_batch
from src.db.session import get_engine, get_session
from src.streaming import bronze
from sqlalchemy import text


def main() -> int:
    ap = argparse.ArgumentParser(description="Bơm Bitcoin Elliptic từng timestep (Bronze → RF in-mem → PG output).")
    ap.add_argument("--from-timestep", type=int, default=35, help="Bắt đầu từ timestep (35 = đầu tập test).")
    ap.add_argument("--to-timestep", type=int, default=49)
    ap.add_argument("--rate", type=float, default=0.0)
    args = ap.parse_args()

    ctx = BitcoinScoringContext.load(release_id=RELEASE_ID)
    with get_session() as s:
        _ensure_release(s)
        s.commit()

    feats = pd.read_csv(DATA / "elliptic_txs_features.csv", header=None)
    feats.columns = FEATURE_COLUMNS
    feats["txId"] = feats["txId"].astype(str)

    print(f"{'timestep':>8} {'bronze':>8} {'scored':>8} {'illicit':>8} {'t(s)':>6}")
    total_bronze = total_scored = total_illicit = 0
    for ts in range(args.from_timestep, args.to_timestep + 1):
        batch = feats[feats["timestep"] == ts]
        if batch.empty:
            continue
        rows = batch.to_dict("records")
        t0 = time.time()
        # 1) RAW → Bronze (gắn source_dataset để phân vùng)
        total_bronze += bronze.write_events([{**r, "source_dataset": "bitcoin"} for r in rows])
        # 2+3) chấm in-mem + ghi output
        scored, flagged = _write_batch(ctx, rows)
        total_scored += scored
        total_illicit += flagged
        print(f"{ts:>8} {total_bronze:>8,} {total_scored:>8,} {total_illicit:>8,} {time.time()-t0:>6.1f}")
        if args.rate > 0:
            time.sleep(args.rate)

    with get_engine().connect() as c:
        pg = c.execute(text("SELECT count(*) n, count(*) FILTER (WHERE predicted_label='illicit') ill "
                            "FROM bitcoin_scored_tx")).mappings().first()
    print(f"\nTổng: Bronze {total_bronze:,} giao dịch · bitcoin_scored_tx {pg['n']:,} (illicit {pg['ill']:,})")
    print(f"Bronze Bitcoin: {bronze.count('bitcoin'):,} · Postgres CHỈ giữ điểm/giải thích, KHÔNG giữ 166 đặc trưng thô.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
