#!/usr/bin/env python3
"""Huấn luyện bản hợp nhất ba nhánh — Rule + Isolation Forest + Graph.

Đầu vào:

* ``data/processed/fusion-v2/fusion_scores.parquet`` — phân vị đã hiệu chỉnh của
  hai nhánh Isolation Forest và Graph, kèm nhãn và phân chia train/val/test.
* ``data/processed/fusion-v2/rule_scores.parquet`` — điểm nhánh Rule trên cùng
  lưới, do ``scripts/compute_rule_grid.py`` sinh ra.

Giao thức, giữ đúng như bản hai nhánh:

1. Trọng số và ngưỡng **chỉ chọn trên tập kiểm định**.
2. Tập kiểm tra chỉ được chạm đúng một lần, ở ngưỡng đã đóng băng.
3. So với hai nhánh đơn để biết hợp nhất có thật sự hơn không — nếu không hơn
   thì phải nói ra, đừng công bố hợp nhất chỉ vì nó phức tạp hơn.

Đầu ra: bundle JSON + parquet điểm hợp nhất cho toàn bộ lưới.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fusion.tri import (  # noqa: E402
    average_precision,
    best_threshold,
    build_bundle,
    evaluate_at,
    fuse,
    rank_percentile,
    select_weights,
)

DEFAULT_FUSION = ROOT / "data/processed/fusion-v2/fusion_scores.parquet"
DEFAULT_RULES = ROOT / "data/processed/fusion-v2/rule_scores.parquet"
DEFAULT_BUNDLE = ROOT / "models/fin07_rule_if_graph_fusion_v1.json"
DEFAULT_REPORT = ROOT / "reports/fusion-tri/li_small_tri_fusion_v1.json"
DEFAULT_SCORES = ROOT / "data/processed/fusion-tri/tri_fusion_scores.parquet"

_JOIN_SQL = """
SELECT f.account_key, f.as_of_ts, f.sample_split, f.target_laundering,
       f.isolation_forest_percentile AS if_pct,
       f.graph_percentile           AS graph_pct,
       -- Không có dòng nào trong lưới rule nghĩa là **đã kiểm và không luật nào
       -- kích hoạt** — đó là điểm 0 có thật, không phải thiếu dữ liệu.
       coalesce(r.rule_score, 0.0)  AS rule_raw,
       f.fan_in_hit, f.fan_out_hit, f.gather_scatter_hit, f.cycle_hit
  FROM read_parquet(?) f
  LEFT JOIN read_parquet(?) r
    ON r.account_key = f.account_key AND r.as_of_ts = f.as_of_ts
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fusion-scores", type=Path, default=DEFAULT_FUSION)
    parser.add_argument("--rule-scores", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--bundle-out", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scores-out", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--weight-step", type=float, default=0.05)
    parser.add_argument("--fusion-version", default="rule_if_graph_fusion_v1")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for path in (args.bundle_out, args.report_out, args.scores_out):
        path.parent.mkdir(parents=True, exist_ok=True)

    print("[1/5] Nối phân vị ba nhánh trên cùng một lưới", flush=True)
    con = duckdb.connect()
    # `.arrow()` trả về RecordBatchReader ở bản DuckDB này; gom lại thành Table.
    table = pa.Table.from_batches(
        list(con.execute(_JOIN_SQL, [str(args.fusion_scores), str(args.rule_scores)]).arrow())
    )
    con.close()

    split = np.asarray(table["sample_split"])
    labels = np.asarray(table["target_laundering"]).astype(np.int8)
    if_pct = np.asarray(table["if_pct"], dtype=np.float64)
    graph_pct = np.asarray(table["graph_pct"], dtype=np.float64)
    rule_raw = np.asarray(table["rule_raw"], dtype=np.float64)

    # Điểm luật là thang do người đặt, không cùng đơn vị với phân vị đã hiệu
    # chỉnh của hai nhánh kia. Đưa về thứ hạng trên **tập train** rồi áp cho cả
    # ba tập — chuẩn hoá bằng dữ liệu kiểm định hay kiểm tra là rò rỉ.
    is_train = split == "train"
    rule_pct = np.zeros_like(rule_raw)
    train_ranked = rank_percentile(rule_raw[is_train])
    order = np.argsort(rule_raw[is_train], kind="stable")
    train_sorted = rule_raw[is_train][order]
    train_pct_sorted = train_ranked[order]
    rule_pct = np.interp(rule_raw, train_sorted, train_pct_sorted, left=0.0, right=1.0)

    print(
        f"      {len(labels):,} dòng | train={int(is_train.sum()):,} "
        f"val={int((split == 'val').sum()):,} test={int((split == 'test').sum()):,} "
        f"| nhãn dương={int(labels.sum()):,}",
        flush=True,
    )

    is_val = split == "val"
    is_test = split == "test"

    print(f"[2/5] Quét đơn hình trọng số trên tập kiểm định (bước {args.weight_step})", flush=True)
    weights, threshold, val_f1, grid = select_weights(
        rule_percentile=rule_pct[is_val],
        if_percentile=if_pct[is_val],
        graph_percentile=graph_pct[is_val],
        labels=labels[is_val],
        step=args.weight_step,
    )
    print(
        f"      trọng số rule={weights.rule:.2f} if={weights.isolation_forest:.2f} "
        f"graph={weights.graph:.2f} | ngưỡng={threshold:.6f} | val F1={val_f1:.4f}",
        flush=True,
    )

    print("[3/5] So với từng nhánh đơn trên tập kiểm định", flush=True)
    singles: dict[str, dict[str, float]] = {}
    for name, values in (("rule", rule_pct), ("isolation_forest", if_pct), ("graph", graph_pct)):
        single_threshold, single_f1 = best_threshold(values[is_val], labels[is_val])
        singles[name] = {"threshold": float(single_threshold), "f1": float(single_f1)}
        print(f"      {name:17} val F1={single_f1:.4f}", flush=True)

    champion = (
        "fusion"
        if val_f1 >= max(item["f1"] for item in singles.values())
        else max(singles, key=lambda k: singles[k]["f1"])
    )
    print(f"      champion = {champion}", flush=True)

    print("[4/5] Chấm toàn bộ lưới và đánh giá tập kiểm tra một lần duy nhất", flush=True)
    fused = fuse(rule_percentile=rule_pct, if_percentile=if_pct, graph_percentile=graph_pct, weights=weights)
    test_metrics = evaluate_at(scores=fused["fusion_score"][is_test], labels=labels[is_test], threshold=threshold)
    print(
        f"      test F1={test_metrics['f1']:.4f} PR-AUC={test_metrics['pr_auc']:.4f} "
        f"precision={test_metrics['precision']:.4f} recall={test_metrics['recall']:.4f} "
        f"alerts={test_metrics['alerts']:,}",
        flush=True,
    )
    single_test = {
        name: {
            "f1": round(
                evaluate_at(scores=values[is_test], labels=labels[is_test], threshold=singles[name]["threshold"])["f1"],
                6,
            ),
            "pr_auc": round(average_precision(values[is_test], labels[is_test]), 6),
        }
        for name, values in (("rule", rule_pct), ("isolation_forest", if_pct), ("graph", graph_pct))
    }

    print("[5/5] Ghi bundle, báo cáo và điểm hợp nhất", flush=True)
    bundle = build_bundle(
        fusion_version=args.fusion_version,
        weights=weights,
        threshold=threshold,
        validation={"f1": round(val_f1, 6), "singles": singles},
        test={**test_metrics, "singles": single_test},
        provenance={
            "fusion_scores": str(args.fusion_scores.relative_to(ROOT)),
            "rule_scores": str(args.rule_scores.relative_to(ROOT)),
            "rule_percentile_fit": "train split only",
            "trained_at": datetime.now(tz=UTC).isoformat(),
            "champion": champion,
        },
        grid=grid,
    )
    args.bundle_out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report_out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    triggered = fused["fusion_score"] >= threshold
    pq.write_table(
        pa.table(
            {
                "account_key": table["account_key"],
                "as_of_ts": table["as_of_ts"],
                "sample_split": table["sample_split"],
                "target_laundering": table["target_laundering"],
                "rule_percentile": pa.array(rule_pct),
                "isolation_forest_percentile": pa.array(if_pct),
                "graph_percentile": pa.array(graph_pct),
                "rule_contribution": pa.array(fused["rule_contribution"]),
                "isolation_forest_contribution": pa.array(fused["isolation_forest_contribution"]),
                "graph_contribution": pa.array(fused["graph_contribution"]),
                "fusion_score": pa.array(fused["fusion_score"]),
                "fusion_threshold": pa.array(np.full(len(labels), threshold)),
                "triggered": pa.array(triggered),
                "fan_in_hit": table["fan_in_hit"],
                "fan_out_hit": table["fan_out_hit"],
                "gather_scatter_hit": table["gather_scatter_hit"],
                "cycle_hit": table["cycle_hit"],
            }
        ),
        args.scores_out,
        compression="zstd",
    )
    print(f"      {int(triggered.sum()):,} dòng vượt ngưỡng -> {args.scores_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
