"""IBM batch re-score — chấm TOÀN đồ thị tích luỹ ở Bronze (nơi MEGA-PNA đạt
P=0,999) rồi đẩy cảnh báo/vụ việc chất lượng cao xuống Postgres.

Vì sao cần: IBM per-edge streaming đói ngữ cảnh (precision ~0) → để streaming IM
LẶNG. Phát hiện IBM tin cậy chạy ĐỊNH KỲ ở đây: đọc mọi cạnh IBM từ Bronze, dựng
đồ thị đầy đủ, chấm bằng ngưỡng batch, gắn cờ (score ≥ ngưỡng) → bồi tụ vụ việc.

Chạy: PYTHONPATH=. python scripts/streaming/rescore_ibm_batch.py --threshold 0.5
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import precision_recall_fscore_support

from src.db.session import get_session
from src.mega_pna.data import _graph
from src.mega_pna.training import _loader, evaluate
from src.streaming import bronze
from src.streaming.case_accumulator import accumulate
from src.streaming.ibm_score import DATASET, load_model
from src.streaming.samld_score import ScoredEdge


def main() -> int:
    ap = argparse.ArgumentParser(description="IBM batch re-score toàn đồ thị (Bronze → alert/case chất lượng cao).")
    ap.add_argument("--threshold", type=float, default=0.5, help="Ngưỡng batch (đồ thị đầy, điểm tách bạch).")
    ap.add_argument("--chunk", type=int, default=5000, help="Số vị trí chấm mỗi chunk (tránh OOM).")
    ap.add_argument(
        "--max-positions",
        type=int,
        default=0,
        help="0 = chấm hết; >0 = chỉ chấm N cạnh CUỐI (ngữ cảnh dày nhất) cho nhanh.",
    )
    args = ap.parse_args()

    model, cfg, ego = load_model()
    from src.mega_pna.training import resolve_device

    device = resolve_device("cpu")

    df = bronze.read_frame(DATASET)
    df = df[df["from_account_key"] != df["to_account_key"]].reset_index(drop=True)
    if len(df) == 0:
        print("Bronze IBM rỗng — chưa có gì để chấm.")
        return 0
    print(f"Đọc {len(df):,} cạnh IBM từ Bronze · dựng đồ thị đầy đủ …")

    # reindex node
    nodes = pd.unique(pd.concat([df["from_account_key"], df["to_account_key"]], ignore_index=True))
    idx = {v: i for i, v in enumerate(nodes)}
    src = df["from_account_key"].map(idx).to_numpy(np.int64)
    dst = df["to_account_key"].map(idx).to_numpy(np.int64)
    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_attr = torch.tensor(
        df[["f_timestamp", "f_amount_received", "f_received_currency", "f_payment_format"]].to_numpy(np.float32)
    )
    labels = torch.tensor(df["is_laundering"].to_numpy(np.int64))
    n = len(df)
    data = _graph(edge_index, edge_attr, labels, edge_attr[:, 0].clone(), end=n, num_nodes=len(nodes))
    print(f"Đồ thị {n:,} cạnh / {len(nodes):,} node · bắt đầu chấm theo chunk …", flush=True)

    # bậc in/out (cho typology)
    in_deg = np.bincount(dst, minlength=len(nodes))
    out_deg = np.bincount(src, minlength=len(nodes))

    t0 = time.time()
    # Tập vị trí cần chấm: hết, hoặc N cạnh CUỐI (ngữ cảnh dày nhất) cho nhanh.
    to_score = np.arange(max(0, n - args.max_positions) if args.max_positions else 0, n, dtype=np.int64)
    # Chấm theo từng lô (mỗi lô lấy mẫu láng giềng trên TOÀN đồ thị) để tránh OOM.
    chunk_size = args.chunk
    id2s: dict[int, float] = {}
    for start in range(0, len(to_score), chunk_size):
        pos = torch.as_tensor(to_score[start : start + chunk_size], dtype=torch.long)
        out = evaluate(
            model, _loader(data, pos, cfg, shuffle=False), pos, device, ego_ids=ego, threshold=args.threshold
        )
        id2s.update({int(i): float(s) for i, s in zip(out.edge_ids, out.scores)})
        print(f"  chấm {min(start + chunk_size, len(to_score)):,}/{len(to_score):,}", flush=True)
    scores = np.array([id2s.get(i, 0.0) for i in range(n)])
    flagged = int(sum(1 for i in to_score if scores[i] >= args.threshold))
    print(f"Chấm {len(to_score):,} cạnh trong {time.time() - t0:.1f}s · gắn cờ (≥{args.threshold}) = {flagged:,}")

    y = df["is_laundering"].to_numpy()
    ys = y[to_score]
    ss = scores[to_score]
    if ys.sum():
        p, r, f, _ = precision_recall_fscore_support(
            ys, (ss >= args.threshold).astype(int), average="binary", zero_division=0
        )
        print(f"Chất lượng batch (đồ thị đầy): P={p:.3f} R={r:.3f} F1={f:.3f} · dương thật {int(ys.sum())}/{len(ys):,}")

    # ScoredEdge cho cạnh gắn cờ → bồi tụ vụ việc
    scored = []
    for i in to_score:
        i = int(i)
        if scores[i] < args.threshold:
            continue
        s, d = int(src[i]), int(dst[i])
        scored.append(
            ScoredEdge(
                source_id=str(df["source_id"].iloc[i]),
                from_account=df["from_account_key"].iloc[i],
                to_account=df["to_account_key"].iloc[i],
                amount=float(df["f_amount_received"].iloc[i]),
                payment_currency="",
                receiving_currency="",
                payment_format="",
                occurred_at=str(df["event_time"].iloc[i]) if "event_time" in df else str(df["occurred_at"].iloc[i]),
                is_laundering=int(y[i]),
                score=scores[i],
                triggered=True,
                warm=True,
                from_in=int(in_deg[s]),
                from_out=int(out_deg[s]),
                to_in=int(in_deg[d]),
                to_out=int(out_deg[d]),
            )
        )
    with get_session() as sess:
        created, touched = accumulate(sess, scored, dataset=DATASET)
        sess.commit()
    print(f"→ Bồi tụ: {created} cảnh báo mới · {touched} vụ chạm (Postgres output).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
