"""IBM batch re-score (production-grade) — dùng ĐẦU RA TOÀN ĐỒ THỊ của MEGA-PNA để
sinh cảnh báo/vụ việc IBM CHẤT LƯỢNG CAO.

IBM chỉ chính xác trên TOÀN đồ thị (per-edge streaming đói ngữ cảnh → im lặng). Batch
re-score định kỳ chấm toàn đồ thị; ở local, chấm 6,9M cạnh với fanout (100,100) là bất
khả thi (hàng giờ). Nên dùng chính đầu ra toàn-đồ-thị đã có (`seed_42_test.parquet` —
đúng thứ batch re-score sinh ra ở production) để đẩy alert/case.

thr=0,99 → P=0,96 R=0,63 (đo trên 6,89M cạnh test). Ánh xạ EdgeID→khoá tài khoản từ
CSV thô (bank bỏ số 0 đầu), rồi bồi tụ vụ việc như mọi nhánh.

Chạy: PYTHONPATH=. python scripts/streaming/rescore_ibm_from_predictions.py --threshold 0.99
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support

from src.db.session import get_session
from src.streaming.case_accumulator import accumulate
from src.streaming.ibm_score import DATASET
from src.streaming.samld_score import ScoredEdge

PRED = Path("models/mega-pna/Medium_HI/paper/seed_42_test.parquet")
RAW = Path("data/raw/ibm-aml/HI-Medium_Trans.csv")


def _bank(b: str) -> str:
    b = str(b).strip()
    return str(int(b)) if b.isdigit() else b


def main() -> int:
    ap = argparse.ArgumentParser(description="IBM batch re-score từ đầu ra toàn đồ thị → alert/case chất lượng cao.")
    ap.add_argument("--threshold", type=float, default=0.99)
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số cảnh báo tạo (0 = tất cả).")
    ap.add_argument("--edgeid-max", type=int, default=0,
                    help="Chỉ lấy cạnh có EdgeID ≤ giá trị này (thu hẹp vùng quét CSV cho nhanh; 0 = hết).")
    args = ap.parse_args()

    preds = pd.read_parquet(PRED)
    y = preds["is_laundering"].to_numpy(); s = preds["score"].to_numpy()
    p, r, f, _ = precision_recall_fscore_support(y, (s >= args.threshold).astype(int), average="binary", zero_division=0)
    print(f"Đầu ra toàn đồ thị (test 6,89M): thr={args.threshold} → P={p:.3f} R={r:.3f} F1={f:.3f} (chất lượng đầy đủ)")

    trig = preds[preds["score"] >= args.threshold].copy()
    if args.edgeid_max:
        trig = trig[trig["source_edge_id"] <= args.edgeid_max]
    if args.limit:
        trig = trig.nlargest(args.limit, "score")
    edgeids = set(int(x) for x in trig["source_edge_id"])
    print(f"Gắn cờ {len(edgeids):,} cạnh · ánh xạ EdgeID→tài khoản từ CSV thô …")

    lo, hi = min(edgeids), max(edgeids)
    keep = {}
    from collections import defaultdict
    ins: dict[str, int] = defaultdict(int)   # bậc VÀO (nhận) per tài khoản trong cửa sổ
    outs: dict[str, int] = defaultdict(int)  # bậc RA (gửi)
    off = lo
    t0 = time.time()
    # Đọc TOÀN cửa sổ [lo..hi] để (1) đếm in/out per tài khoản → typology thật,
    # (2) lấy khoá cho các cạnh gắn cờ.
    for chunk in pd.read_csv(RAW, header=0, usecols=[0, 1, 2, 3, 4],
                             names=["ts", "fb", "fa", "tb", "ta"], skiprows=range(1, lo + 1),
                             chunksize=500_000):
        chunk = chunk[: max(0, hi + 1 - off)] if off + len(chunk) > hi + 1 else chunk
        if len(chunk) == 0:
            break
        fk_all = chunk["fb"].map(_bank).astype(str) + ":" + chunk["fa"].astype(str)
        tk_all = chunk["tb"].map(_bank).astype(str) + ":" + chunk["ta"].astype(str)
        for k, v in fk_all.value_counts().items():
            outs[k] += int(v)
        for k, v in tk_all.value_counts().items():
            ins[k] += int(v)
        idx = np.arange(off, off + len(chunk))
        m = np.isin(idx, list(edgeids))
        for gi, fk, tk, ts in zip(idx[m], fk_all[m], tk_all[m], chunk["ts"][m]):
            keep[int(gi)] = (fk, tk, str(ts).replace("/", "-"))
        off += len(chunk)
        if off > hi:
            break
    print(f"  ánh xạ {len(keep):,}/{len(edgeids):,} cạnh + đếm bậc {len(ins)+len(outs):,} tài khoản trong {time.time()-t0:.1f}s")

    scored = []
    for _, tr in trig.iterrows():
        eid = int(tr["source_edge_id"])
        if eid not in keep:
            continue
        fk, tk, ts = keep[eid]
        scored.append(ScoredEdge(
            source_id=f"IBMB-{eid}", from_account=fk, to_account=tk, amount=0.0,
            payment_currency="", receiving_currency="", payment_format="", occurred_at=ts,
            is_laundering=int(tr["is_laundering"]), score=float(tr["score"]), triggered=True, warm=True,
            from_in=ins.get(fk, 0), from_out=outs.get(fk, 0),   # bậc THẬT → typology đúng
            to_in=ins.get(tk, 0), to_out=outs.get(tk, 0)))
    with get_session() as sess:
        created, touched = accumulate(sess, scored, dataset=DATASET)
        sess.commit()
    print(f"→ IBM batch: {created:,} cảnh báo chất lượng cao · {touched:,} vụ việc (Postgres output).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
