"""Bơm IBM MEGA-PNA (HI-Medium) TỪNG BATCH theo kiến trúc medallion.

Raw → BRONZE Parquet, đồ thị + điểm IN-MEMORY, chỉ cạnh gắn cờ → alert/aml_case (PG).
Nút = TÀI KHOẢN thật (Bank:Account, có trong `account`) nên IBM cũng bồi tụ VỤ VIỆC.

Nguồn: hàng ĐÃ FORMAT (EdgeID + 4 đặc trưng mã hoá đúng encoding checkpoint) căn theo
CSV THÔ (khoá tài khoản). Bank chuẩn hoá bỏ số 0 đầu (012→12) khớp bảng account.
IBM KHÔNG có địa lý (không map quốc gia) nên bỏ qua bước geo.

Chạy: PYTHONPATH=. python scripts/streaming/pump_ibm.py --offset 25000000 --batches 12
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.db.session import get_engine, get_session
from src.mega_pna.data import PAPER_FEATURES
from src.streaming import bronze
from src.streaming.case_accumulator import accumulate
from src.streaming.ibm_score import DATASET, IBMStreamScorer

FMT = Path("data/processed/mega-pna/Medium_HI/formatted_transactions.csv")
RAW = Path("data/raw/ibm-aml/HI-Medium_Trans.csv")
FEATURES = list(PAPER_FEATURES)
FMT_COLS = ["EdgeID", *FEATURES, "Is Laundering"]
RAW_NAMES = ["ts", "fb", "fa", "tb", "ta", "ar", "rc", "ap", "pc", "pf", "il"]


def _bank(b: str) -> str:
    b = str(b).strip()
    return str(int(b)) if b.isdigit() else b


def pg_counts() -> dict:
    with get_engine().connect() as c:
        return c.execute(text("""
            SELECT (SELECT count(*) FROM alert   WHERE detector='mega_pna' AND dataset='ibm_hi_medium'
                      AND alert_id LIKE 'ALT-STREAM-%')                                    AS alerts,
                   (SELECT count(*) FROM aml_case WHERE case_id LIKE 'CASE-STREAM-%')       AS cases
        """)).mappings().first()


def main() -> int:
    ap = argparse.ArgumentParser(description="Bơm IBM MEGA-PNA từng batch (Bronze → in-mem → PG output).")
    ap.add_argument("--offset", type=int, default=25_000_000)
    ap.add_argument("--batches", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--rate", type=float, default=0.0)
    args = ap.parse_args()

    scorer = IBMStreamScorer()
    pos_total = 0
    tp_ids: set[str] = set()
    dt64 = {"from_id": "int64", "to_id": "int64", "EdgeID": "int64", "Timestamp": "float32",
            "Amount Received": "float32", "Received Currency": "float32",
            "Payment Format": "float32", "Is Laundering": "int64"}

    print(f"{'batch':>5} {'bronze':>8} {'graph':>8} {'flag':>6} {'prov':>7} {'reμ':>5} {'TP':>4} {'rec':>6} "
          f"| {'cases':>5}  {'t(s)':>5}")
    read = 0
    for b in range(args.batches):
        fmt = pd.read_csv(FMT, usecols=[c for c in FMT_COLS], dtype={k: dt64[k] for k in FMT_COLS if k in dt64},
                          skiprows=range(1, args.offset + read + 1), nrows=args.batch_size)
        if len(fmt) == 0:
            print("(hết dữ liệu)")
            break
        raw = pd.read_csv(RAW, header=None, names=RAW_NAMES,
                          skiprows=args.offset + read + 1, nrows=len(fmt))
        read += len(fmt)
        fmt = fmt.reset_index(drop=True); raw = raw.reset_index(drop=True)
        events = []
        for i in range(len(fmt)):
            events.append({
                "source_id": int(fmt["EdgeID"].iloc[i]),
                "source_dataset": DATASET,
                "from_account_key": f"{_bank(raw['fb'].iloc[i])}:{raw['fa'].iloc[i]}",
                "to_account_key": f"{_bank(raw['tb'].iloc[i])}:{raw['ta'].iloc[i]}",
                "occurred_at": str(raw["ts"].iloc[i]).replace("/", "-"),
                "f_timestamp": float(fmt["Timestamp"].iloc[i]),
                "f_amount_received": float(fmt["Amount Received"].iloc[i]),
                "f_received_currency": float(fmt["Received Currency"].iloc[i]),
                "f_payment_format": float(fmt["Payment Format"].iloc[i]),
                "is_laundering": int(fmt["Is Laundering"].iloc[i]),
            })
        t0 = time.time()
        bronze.write_events(events)                       # 1) RAW → Bronze
        scored = scorer.process_events(events)            # 2) chấm in-mem
        rescored = scorer.rescore_warmed()
        pos_total += sum(e.is_laundering for e in scored)
        for e in scored + rescored:
            if e.triggered and e.is_laundering:
                tp_ids.add(e.source_id)
        with get_session() as s:                          # 3) chỉ cạnh gắn cờ → PG
            accumulate(s, scored + rescored, dataset=DATASET)
            s.commit()
        c = pg_counts()
        rec = len(tp_ids) / pos_total if pos_total else 0.0
        print(f"{b+1:>5} {scorer.num_edges:>8,} {scorer.num_nodes:>8,} {c['alerts']:>6,} "
              f"{len(scorer._provisional):>7,} {len(rescored):>5,} {len(tp_ids):>4} {rec:>6.3f} | "
              f"{c['cases']:>5,}  {time.time()-t0:>5.1f}")
        if args.rate > 0:
            time.sleep(args.rate)

    c = pg_counts()
    print(f"\nTổng: Bronze {scorer.num_edges:,} cạnh · {c['alerts']} cảnh báo IBM · {c['cases']} vụ (chung queue) "
          f"· bắt {len(tp_ids)}/{pos_total} dương")
    print(f"Bronze IBM: {bronze.count(DATASET):,} · Postgres CHỈ giữ alert/case, KHÔNG giữ giao dịch thô.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
