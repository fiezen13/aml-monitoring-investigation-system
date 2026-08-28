"""Hiệu chỉnh NGƯỠNG STREAMING theo NGỮ CẢNH cho SAML-D (Pha 2, cold-start).

Vì sao cần: điểm GNN streaming bị NÉN vì đồ thị quanh cạnh còn thưa. Ngưỡng batch
(0,503) chỉ hợp đồ thị đầy đủ → streaming gần như không bắt gì (R≈0,06). Đo lại
trên REPLAY streaming thật (đồ thị in-memory tăng dần) và tách bucket theo bậc
endpoint:
  * warm (min_deg ≥ K): chấm bằng model + ngưỡng streaming (đo được R≈0,69),
  * cold (min_deg < K): tài khoản quá mới → provisional, chấm lại khi warm.

Chạy: PYTHONPATH=. python scripts/streaming/calibrate_samld_threshold.py \
        --offset 8600000 --context 500000 --measure 100000 --k 2
Ghi: artifacts/streaming/thresholds.json (khoá "samld").
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, precision_recall_fscore_support

from src.mega_pna.training import _loader, evaluate
from src.streaming.incremental_graph import IncrementalGraph
from src.streaming.samld_score import load_model, reconstruct_samld_df

CSV = Path("data/raw/saml-d/SAML-D.csv")
ORIGIN = datetime.fromisoformat("2022-10-07T10:35:19")
COLS = ["Time", "Date", "Sender_account", "Receiver_account", "Amount", "Payment_currency",
        "Received_currency", "Sender_bank_location", "Receiver_bank_location", "Payment_type", "Is_laundering"]
OUT = Path("artifacts/streaming/thresholds.json")


def to_stream_rows(df: pd.DataFrame, base: int) -> pd.DataFrame:
    out = pd.DataFrame()
    out["stream_txn_id"] = np.arange(base, base + len(df))
    out["from_account_key"] = df["Sender_bank_location"].astype(str) + ":" + df["Sender_account"].astype(str)
    out["to_account_key"] = df["Receiver_bank_location"].astype(str) + ":" + df["Receiver_account"].astype(str)
    dt = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"].astype(str), errors="coerce", utc=True)
    out["occurred_at"] = dt
    out["amount_paid"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    out["payment_currency"] = df["Payment_currency"].astype(str)
    out["amount_received"] = out["amount_paid"]
    out["receiving_currency"] = df["Received_currency"].astype(str)
    out["payment_format"] = df["Payment_type"].astype(str)
    out["is_laundering"] = pd.to_numeric(df["Is_laundering"], errors="coerce").fillna(0).astype(int)
    return out[out["from_account_key"] != out["to_account_key"]].reset_index(drop=True)


def pick(y, s):
    """(F1-best, ngưỡng đạt P≥0.5). Trả dict điểm vận hành."""
    cand = np.unique(np.quantile(s, np.linspace(0.3, 0.99999, 300))) if len(s) else np.array([0.5])
    f1best = (-1.0, 0.5, 0.0, 0.0)
    hi_p = None
    for t in cand:
        p, r, f, _ = precision_recall_fscore_support(y, (s >= t).astype(int), average="binary", zero_division=0)
        if f > f1best[0]:
            f1best = (f, float(t), p, r)
        if p >= 0.5 and hi_p is None:
            hi_p = (float(t), p, r)
    return f1best, hi_p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=8_600_000)
    ap.add_argument("--context", type=int, default=500_000, help="Số cạnh tích luỹ làm ngữ cảnh trước khi đo.")
    ap.add_argument("--measure", type=int, default=100_000, help="Số cạnh đo (sau ngữ cảnh).")
    ap.add_argument("--k", type=int, default=2, help="Bậc endpoint tối thiểu để coi là WARM.")
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    ctx = load_model()
    G = IncrementalGraph(feature_dim=ctx.encoder.num_features)
    total = args.context + args.measure
    raw = pd.read_csv(CSV, usecols=lambda c: c in COLS, skiprows=range(1, args.offset + 1), nrows=total)
    rows = to_stream_rows(raw, args.offset)
    print(f"Đọc {len(rows):,} cạnh @ offset {args.offset:,} · dương {int(rows['is_laundering'].sum())}")

    S, Y, MD = [], [], []
    for start in range(0, len(rows), args.batch):
        ch = rows.iloc[start:start + args.batch].reset_index(drop=True)
        df = reconstruct_samld_df(ch, ORIGIN)
        attr = ctx.encoder.transform(df).astype(np.float32)
        pos = G.add(ch["stream_txn_id"].to_numpy(), ch["from_account_key"].tolist(),
                    ch["to_account_key"].tolist(), attr, ch["is_laundering"].to_numpy(),
                    df["elapsed_days"].to_numpy())
        if len(pos) == 0 or start < args.context:  # phần đầu chỉ tích ngữ cảnh
            continue
        data = G.hetero()
        pt = torch.as_tensor(pos, dtype=torch.long)
        out = evaluate(ctx.model, _loader(data, pt, ctx.config, shuffle=False), pt, ctx.device,
                       ego_ids=ctx.ego_ids, threshold=ctx.threshold)
        id2s = {int(i): float(x) for i, x in zip(out.edge_ids, out.scores)}
        S.append(np.array([id2s.get(int(p), 0.0) for p in pos]))
        Y.append(ch["is_laundering"].to_numpy())
        MD.append(G.endpoint_min_degree(pos))
    s = np.concatenate(S); y = np.concatenate(Y).astype(int); md = np.concatenate(MD)
    warm = md >= args.k
    print(f"Đo {len(s):,} cạnh · nodes={G.num_nodes:,} edges={G.num_edges:,} · dương {int(y.sum())} "
          f"· PR-AUC={average_precision_score(y, s):.4f}")
    print(f"warm(min_deg≥{args.k})={int(warm.sum()):,} dương={int(y[warm].sum())} · "
          f"cold={int((~warm).sum()):,} dương={int(y[~warm].sum())}")

    (wf, wt, wp, wr), whip = pick(y[warm], s[warm])
    print(f"WARM  F1-best thr={wt:.4f} P={wp:.3f} R={wr:.3f} F1={wf:.3f}"
          + (f" · P≥0.5 thr={whip[0]:.4f} P={whip[1]:.3f} R={whip[2]:.3f}" if whip else ""))

    payload = {}
    if OUT.exists():
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    payload["samld"] = {
        "warm_degree": args.k,
        "stream_threshold": round(wt, 5),           # ngưỡng cho cạnh WARM (F1-best)
        "high_precision_threshold": round(whip[0], 5) if whip else round(wt, 5),
        "batch_threshold": round(ctx.threshold, 5),
        "measured": {"pr_auc": round(float(average_precision_score(y, s)), 4),
                     "warm_precision": round(wp, 3), "warm_recall": round(wr, 3),
                     "n": int(len(s)), "pos": int(y.sum()),
                     "context_edges": args.context, "offset": args.offset},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✔ Ghi ngưỡng SAML-D → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
