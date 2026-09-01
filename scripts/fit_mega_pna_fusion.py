#!/usr/bin/env python3
"""Khớp trọng số hợp nhất Rule + MEGA-PNA ở mức tài khoản.

    python scripts/fit_mega_pna_fusion.py

Giao thức, giữ đúng như bản hợp nhất cũ:

1. Phân vị và trọng số **chỉ chọn trên validation**.
2. Test chỉ chạm **đúng một lần**, ở trọng số và ngưỡng đã đóng băng.
3. So với từng nhánh đơn. Nếu hợp nhất không hơn thì nói ra, đừng công bố nó chỉ
   vì nó phức tạp hơn — đó là bài học từ bản hợp nhất trước, nơi Isolation Forest
   nhận trọng số 0,00 và hợp nhất chỉ hơn nhánh graph 0,0027 F1.

Hợp nhất trên **phân vị**, không trên điểm thô: hai nhánh có thang khác hẳn nhau
(MEGA-PNA cho softmax 0..1 lệch mạnh về 0; rule cho điểm 0..1 rời rạc). Cộng
thẳng thì nhánh có phương sai lớn hơn nuốt nhánh kia bất kể trọng số.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

UTC = timezone.utc  # noqa: UP017

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data/processed/mega-pna-accounts"
DEFAULT_OUT = ROOT / "reports/mega-pna/fusion_account_v1.json"

#: Lưới trọng số. Bước 0,05 là đủ mịn: chênh lệch F1 giữa hai bước liền nhau nhỏ
#: hơn dao động giữa các seed, nên mịn hơn chỉ tạo cảm giác chính xác giả.
WEIGHT_STEP = 0.05


def load(directory: Path, split: str) -> Any:
    con = duckdb.connect()
    try:
        return con.execute(
            """
            SELECT a.account_key, a.as_of, a.label,
                   a.score_max, a.score_top5_mean, a.edges_over_threshold,
                   a.flagged_amount, a.edge_count,
                   coalesce(r.rule_score, 0.0) AS rule_score
              FROM read_parquet(?) a
              LEFT JOIN read_parquet(?) r
                ON r.account_key = a.account_key AND r.as_of_ts = a.as_of
             ORDER BY a.account_key, a.as_of
            """,
            [str(directory / f"{split}.parquet"), str(directory / f"{split}_rule.parquet")],
        ).fetchdf()
    finally:
        con.close()


def rank_percentile(values: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
    """Đưa điểm về phân vị 0..1 theo phân bố của tập THAM CHIẾU.

    Tham chiếu luôn là train/validation. Dùng phân bố của chính tập test là rò
    rỉ: thứ hạng của một ô khi ấy phụ thuộc vào những ô khác trong test.
    """
    base = np.sort(reference if reference is not None else values)
    if base.size == 0:
        return np.zeros_like(values, dtype=float)
    return np.searchsorted(base, values, side="right") / base.size


def metrics(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float]:
    pred = (scores >= threshold).astype(int)
    return {
        "f1": float(f1_score(labels, pred, zero_division=0)),
        "precision": float(precision_score(labels, pred, zero_division=0)),
        "recall": float(recall_score(labels, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(labels, scores)) if labels.sum() else 0.0,
    }


def best_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """Ngưỡng cho F1 cao nhất, và giá trị F1 tại đó.

    Vector hoá thay vì dò từng ngưỡng: sắp một lần rồi tính F1 tại **mọi** điểm
    cắt bằng tổng luỹ kế. Bản dò tuần tự gọi ``f1_score`` 400 lần cho mỗi tổ hợp
    trọng số — 8.400 lượt quét toàn bộ 3 triệu dòng, không chạy nổi.

    Cách này còn xét đủ mọi điểm cắt chứ không chỉ 400 phân vị, nên ngưỡng chọn
    ra chính xác hơn chứ không chỉ nhanh hơn.
    """
    order = np.argsort(-scores, kind="stable")
    sorted_labels = labels[order]
    tp = np.cumsum(sorted_labels)
    k = np.arange(1, labels.size + 1)
    total_positive = int(labels.sum())
    if total_positive == 0:
        return 0.5, 0.0
    f1 = 2 * tp / (k + total_positive)
    index = int(np.argmax(f1))
    # Ngưỡng là điểm ngay tại vị trí cắt; dùng giá trị điểm ở đó để so >=.
    return float(scores[order][index]), float(f1[index])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("[1/4] Nạp lưới validation và test ...", flush=True)
    val = load(args.dir, "validation")
    test = load(args.dir, "test")

    y_val = val["label"].to_numpy(dtype=int)
    y_test = test["label"].to_numpy(dtype=int)

    # Phân vị chốt trên validation, áp cho cả hai tập.
    mega_val_raw = val["score_max"].to_numpy(dtype=float)
    rule_val_raw = val["rule_score"].to_numpy(dtype=float)
    mega_val = rank_percentile(mega_val_raw, mega_val_raw)
    rule_val = rank_percentile(rule_val_raw, rule_val_raw)
    mega_test = rank_percentile(test["score_max"].to_numpy(dtype=float), mega_val_raw)
    rule_test = rank_percentile(test["rule_score"].to_numpy(dtype=float), rule_val_raw)

    print(f"      validation {len(y_val):,} ô · dương {y_val.sum():,}", flush=True)
    print(f"      test       {len(y_test):,} ô · dương {y_test.sum():,}", flush=True)

    print("[2/4] Quét lưới trọng số trên validation ...", flush=True)
    trials: list[dict[str, Any]] = []
    for w_rule in np.arange(0.0, 1.0 + WEIGHT_STEP / 2, WEIGHT_STEP):
        w_mega = 1.0 - w_rule
        fused = w_rule * rule_val + w_mega * mega_val
        t, _ = best_threshold(y_val, fused)
        m = metrics(y_val, fused, t)
        trials.append({"w_rule": round(float(w_rule), 3), "w_mega_pna": round(float(w_mega), 3), "threshold": t, **m})
    best = max(trials, key=lambda r: r["f1"])
    print(
        f"      tốt nhất: rule {best['w_rule']} · mega_pna {best['w_mega_pna']} · F1(val) {best['f1']:.4f}", flush=True
    )

    print("[3/4] Chạm test một lần, ngưỡng đã đóng băng ...", flush=True)
    fused_test = best["w_rule"] * rule_test + best["w_mega_pna"] * mega_test
    test_fused = metrics(y_test, fused_test, best["threshold"])
    # Nhánh đơn, cùng giao thức: ngưỡng chốt trên validation rồi áp cho test.
    t_mega, _ = best_threshold(y_val, mega_val)
    t_rule, _ = best_threshold(y_val, rule_val)
    test_mega = metrics(y_test, mega_test, t_mega)
    test_rule = metrics(y_test, rule_test, t_rule)

    gain = test_fused["f1"] - max(test_mega["f1"], test_rule["f1"])
    verdict = (
        "Hợp nhất KHÔNG hơn nhánh đơn tốt nhất; dùng nhánh đơn." if gain < 0.005 else "Hợp nhất hơn nhánh đơn tốt nhất."
    )
    print(
        f"      fused {test_fused['f1']:.4f} · mega_pna {test_mega['f1']:.4f} "
        f"· rule {test_rule['f1']:.4f} → chênh {gain:+.4f}",
        flush=True,
    )
    print(f"      {verdict}", flush=True)

    print("[4/4] Ghi báo cáo ...", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "fin07.mega_pna.fusion_account.v1",
                "created_at": datetime.now(UTC).isoformat(),
                "unit": "account_window",
                "window_days": 7,
                "weights": {"rule": best["w_rule"], "mega_pna": best["w_mega_pna"]},
                "threshold": best["threshold"],
                "threshold_selected_on": "validation",
                "validation": {
                    "cells": int(len(y_val)),
                    "positives": int(y_val.sum()),
                    **{k: best[k] for k in ("f1", "precision", "recall", "pr_auc")},
                },
                "test_fused": {"cells": int(len(y_test)), "positives": int(y_test.sum()), **test_fused},
                "test_mega_pna_only": {"threshold": t_mega, **test_mega},
                "test_rule_only": {"threshold": t_rule, **test_rule},
                "fusion_gain_over_best_single": gain,
                "verdict": verdict,
                "weight_grid": trials,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"đã ghi {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
