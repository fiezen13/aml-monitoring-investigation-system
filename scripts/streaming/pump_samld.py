"""Bơm SAML-D TỪNG BATCH theo kiến trúc medallion (Bronze Parquet → graph in-mem → PG output).

Mỗi batch:
  1. CSV → sự kiện canonical → ghi BRONZE (Parquet, KHÔNG vào Postgres);
  2. scorer in-mem nạp cạnh + chấm (neighbor-loader) + chấm lại cạnh warm;
  3. CHỈ cạnh gắn cờ → alert + aml_case (Postgres) qua union-find;
  4. bản đồ hành lang gộp từ Bronze → edge_country_hub/flow;
  5. cập nhật release 'sống' cho trang Tổng quan.

Postgres KHÔNG giữ giao dịch thô — đúng nguyên tắc (raw ở lake, PG chỉ output).

Chạy: PYTHONPATH=. python scripts/streaming/pump_samld.py --batches 24 --batch-size 5000
"""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.db.session import get_engine, get_session
from src.streaming import bronze
from src.streaming.case_accumulator import accumulate
from src.streaming.geo_rollup import refresh as refresh_geo
from src.streaming.samld_producer import _to_canonical
from src.streaming.samld_score import BronzeStreamScorer

CSV = Path("data/raw/saml-d/SAML-D.csv")
COLS = [
    "Time",
    "Date",
    "Sender_account",
    "Receiver_account",
    "Amount",
    "Payment_currency",
    "Received_currency",
    "Sender_bank_location",
    "Receiver_bank_location",
    "Payment_type",
    "Is_laundering",
]
STREAM_RELEASE_ID = "REL-STREAM-SAMLD"
_SHA = hashlib.sha256(b"samld-stream-live").hexdigest()


def upsert_release(
    session, tx_rows: int, pos_rows: int, triggered_rows: int, feature_count: int, threshold: float
) -> None:
    """Release 'sống' cho Tổng quan (headline). transaction_rows = số giao dịch ở Bronze."""
    session.execute(
        text("""
        INSERT INTO edge_model_release (release_id, model_version, dataset, split, model_sha256,
            scores_sha256, source_database_sha256, threshold, transaction_rows, positive_rows,
            triggered_rows, feature_count, benchmark, policy, status, trained_at)
        VALUES (:rid,'samld-stream-v1','SAML-D (streaming)','test',:sha,:sha,:sha,:thr,:tx,:pos,:trig,
                :fc,'{}'::jsonb,'{}'::jsonb,'active',now())
        ON CONFLICT (release_id) DO UPDATE SET transaction_rows=EXCLUDED.transaction_rows,
            positive_rows=EXCLUDED.positive_rows, triggered_rows=EXCLUDED.triggered_rows, threshold=EXCLUDED.threshold
    """),
        {
            "rid": STREAM_RELEASE_ID,
            "sha": _SHA,
            "thr": threshold,
            "tx": tx_rows,
            "pos": pos_rows,
            "trig": triggered_rows,
            "fc": feature_count,
        },
    )


def pg_counts() -> dict:
    with get_engine().connect() as c:
        return (
            c.execute(
                text("""
            SELECT (SELECT count(*) FROM alert   WHERE alert_id LIKE 'ALT-STREAM-%')  AS alerts,
                   (SELECT count(*) FROM aml_case WHERE case_id LIKE 'CASE-STREAM-%')  AS cases,
                   (SELECT COALESCE(max(n),0) FROM (SELECT count(*) n FROM alert
                      WHERE alert_id LIKE 'ALT-STREAM-%' GROUP BY case_id) q)          AS biggest
        """)
            )
            .mappings()
            .first()
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Bơm SAML-D từng batch (Bronze → in-mem → PG output).")
    ap.add_argument("--offset", type=int, default=8_600_000)
    ap.add_argument("--batches", type=int, default=24)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--rate", type=float, default=0.0)
    args = ap.parse_args()

    scorer = BronzeStreamScorer()
    fc = scorer.ctx.encoder.num_features
    pos_total = 0
    tp_ids: set[str] = set()

    print(
        f"{'batch':>5} {'bronze':>8} {'graph':>8} {'flag':>6} {'prov':>7} {'reμ':>5} {'TP':>4} "
        f"{'rec':>6} | {'cases':>5} {'big':>4}  {'t(s)':>5}"
    )
    total_read = 0
    for b in range(args.batches):
        raw = pd.read_csv(
            CSV, usecols=lambda c: c in COLS, skiprows=range(1, args.offset + total_read + 1), nrows=args.batch_size
        )
        if len(raw) == 0:
            print("(hết dữ liệu)")
            break
        events = [_to_canonical(r.to_dict(), args.offset + total_read + i) for i, (_, r) in enumerate(raw.iterrows())]
        total_read += len(raw)
        t0 = time.time()

        bronze.write_events(events)  # 1) RAW → Bronze Parquet
        scored = scorer.process_events(events)  # 2) chấm in-mem
        rescored = scorer.rescore_warmed()
        pos_total += sum(e.is_laundering for e in scored)
        for e in scored + rescored:
            if e.triggered and e.is_laundering:
                tp_ids.add(e.source_id)

        with get_session() as s:  # 3) CHỈ cạnh gắn cờ → PG
            accumulate(s, scored + rescored)
            refresh_geo(s)  # 4) bản đồ từ Bronze
            triggered = s.execute(text("SELECT count(*) FROM alert WHERE alert_id LIKE 'ALT-STREAM-%'")).scalar()
            upsert_release(
                s, scorer.G.num_edges, pos_total, int(triggered), fc, scorer.stream_threshold
            )  # 5) Tổng quan
            s.commit()

        dt = time.time() - t0
        c = pg_counts()
        rec = len(tp_ids) / pos_total if pos_total else 0.0
        print(
            f"{b + 1:>5} {scorer.G.num_edges:>8,} {scorer.G.num_nodes:>8,} {c['alerts']:>6,} "
            f"{len(scorer._provisional):>7,} {len(rescored):>5,} {len(tp_ids):>4} {rec:>6.3f} | "
            f"{c['cases']:>5,} {c['biggest']:>4}  {dt:>5.1f}"
        )
        if args.rate > 0:
            time.sleep(args.rate)

    c = pg_counts()
    print(
        f"\nTổng: Bronze {scorer.G.num_edges:,} cạnh · {c['alerts']} cảnh báo · {c['cases']} vụ "
        f"· bắt {len(tp_ids)}/{pos_total} dương (recall {len(tp_ids) / max(pos_total, 1):.3f})"
    )
    print("Postgres CHỈ giữ output (alert/case/geo); giao dịch thô nằm ở Bronze Parquet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
