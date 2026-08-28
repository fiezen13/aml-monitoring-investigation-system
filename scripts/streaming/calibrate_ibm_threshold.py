"""Hiệu chỉnh ngưỡng streaming + CHỐT thống kê z-norm cho IBM MEGA-PNA (Pha 2).

IBM MEGA-PNA z-norm đặc trưng từ CHÍNH dữ liệu (`_z_normalize`) → không hợp đồ thị
tăng dần (thêm cạnh sẽ đổi chuẩn hoá). Ở đây CHỐT (mean,std) một lần từ mẫu lớn để
mã hoá CỐ ĐỊNH, rồi replay streaming (incremental graph) và hiệu chỉnh ngưỡng theo
bucket bậc endpoint — như SAML-D.

Ghi: artifacts/streaming/ibm_zstats.json + khoá "ibm" trong thresholds.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, precision_recall_fscore_support

from src.mega_pna.data import PAPER_FEATURES
from src.mega_pna.training import _loader, evaluate
from src.streaming.ibm_score import load_model
from src.streaming.incremental_graph import IncrementalGraph

FMT = Path("data/processed/mega-pna/Medium_HI/formatted_transactions.csv")
FEATURES = list(PAPER_FEATURES)
COLS = ["EdgeID", "from_id", "to_id", *FEATURES, "Is Laundering"]
DTYPE = {"from_id": "int64", "to_id": "int64", "EdgeID": "int64", "Timestamp": "float32",
         "Amount Received": "float32", "Received Currency": "float32",
         "Payment Format": "float32", "Is Laundering": "int64"}
ZSTATS = Path("artifacts/streaming/ibm_zstats.json")
OUT = Path("artifacts/streaming/thresholds.json")


def zstats_from(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """z-norm PHẢI tính trên chính đồ thị đang chấm (model MEGA-PNA train kiểu đó).
    Chốt (mean,std) trên cửa sổ ngữ cảnh để mã hoá nhất quán trong lượt này."""
    mean = frame[FEATURES].to_numpy(np.float64).mean(0)
    std = frame[FEATURES].to_numpy(np.float64).std(0)
    std[std == 0] = 1.0
    ZSTATS.parent.mkdir(parents=True, exist_ok=True)
    ZSTATS.write_text(json.dumps({"features": FEATURES, "mean": mean.tolist(), "std": std.tolist(),
                                  "note": "z-norm theo đồ thị (graph-relative) — tính lại trên cửa sổ hiện tại"}, indent=2), encoding="utf-8")
    return mean.astype(np.float32), std.astype(np.float32)


def pick(y, s):
    cand = np.unique(np.quantile(s, np.linspace(0.3, 0.99999, 300))) if len(s) else np.array([0.5])
    f1best = (-1.0, 0.5, 0.0, 0.0)
    for t in cand:
        p, r, f, _ = precision_recall_fscore_support(y, (s >= t).astype(int), average="binary", zero_division=0)
        if f > f1best[0]:
            f1best = (f, float(t), p, r)
    return f1best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=25_000_000)
    ap.add_argument("--context", type=int, default=500_000)
    ap.add_argument("--measure", type=int, default=100_000)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    ctx = load_model()
    G = IncrementalGraph(feature_dim=len(FEATURES))
    total = args.context + args.measure
    frame = pd.read_csv(FMT, usecols=COLS, dtype=DTYPE, skiprows=range(1, args.offset + 1), nrows=total)
    mean, std = zstats_from(frame)  # z-norm theo đồ thị (graph-relative)
    print(f"Đọc {len(frame):,} cạnh IBM @ offset {args.offset:,} · dương {int(frame['Is Laundering'].sum())}")

    S, Y, MD = [], [], []
    for start in range(0, len(frame), args.batch):
        ch = frame.iloc[start:start + args.batch]
        attr = ((ch[FEATURES].to_numpy(np.float32) - mean) / std).astype(np.float32)
        pos = G.add(ch["EdgeID"].to_numpy(), ch["from_id"].astype(str).tolist(),
                    ch["to_id"].astype(str).tolist(), attr, ch["Is Laundering"].to_numpy(),
                    ch["Timestamp"].to_numpy())
        if len(pos) == 0 or start < args.context:
            continue
        data = G.hetero()
        pt = torch.as_tensor(pos, dtype=torch.long)
        out = evaluate(ctx.model, _loader(data, pt, ctx.config, shuffle=False), pt, ctx.device,
                       ego_ids=ctx.ego_ids, threshold=ctx.threshold)
        id2s = {int(i): float(x) for i, x in zip(out.edge_ids, out.scores)}
        S.append(np.array([id2s.get(int(p), 0.0) for p in pos]))
        Y.append(ch["Is Laundering"].to_numpy())
        MD.append(G.endpoint_min_degree(pos))
    s = np.concatenate(S); y = np.concatenate(Y).astype(int); md = np.concatenate(MD)
    warm = md >= args.k
    print(f"Đo {len(s):,} cạnh · nodes={G.num_nodes:,} · dương {int(y.sum())} · PR-AUC={average_precision_score(y, s):.4f}")
    print(f"warm(≥{args.k})={int(warm.sum()):,} dương={int(y[warm].sum())} · cold={int((~warm).sum()):,} dương={int(y[~warm].sum())}")
    wf, wt, wp, wr = pick(y[warm], s[warm]) if y[warm].sum() else (0, ctx.threshold, 0, 0)
    print(f"WARM F1-best thr={wt:.4f} P={wp:.3f} R={wr:.3f} F1={wf:.3f}")

    payload = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    payload["ibm"] = {"warm_degree": args.k, "stream_threshold": round(float(wt), 5),
                      "batch_threshold": round(float(ctx.threshold), 5),
                      "measured": {"pr_auc": round(float(average_precision_score(y, s)), 4),
                                   "warm_precision": round(float(wp), 3), "warm_recall": round(float(wr), 3),
                                   "n": int(len(s)), "pos": int(y.sum()), "context_edges": args.context}}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✔ Ghi ngưỡng IBM → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
