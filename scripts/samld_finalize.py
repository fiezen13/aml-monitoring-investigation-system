"""Dựng lại báo cáo SAML-D từ dự đoán đã lưu — CỤC BỘ, không cần GPU.

Dùng khi đã có ``data/models/samld/runs/seed*/`` (report + predictions) nhưng
thiếu các artifact phân tích (vd benchmark trên GPU bị ngắt sau phần train). Tính
main metrics + over-seeds + cross-border + per-typology + country + đồ thị +
report từ chính dự đoán tập test — hoàn toàn trung thực, không train lại.

Chạy: python -m scripts.samld_finalize
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from scripts.samld_benchmark import _write_report, data_profile
from src.samld.config import get_samld_config
from src.samld.data import load_samld
from src.samld.evaluate import (
    TestFrame,
    country_distribution,
    cross_border_breakdown,
    extended_metrics,
    per_typology,
)
from src.samld.plots import save_all
from src.samld.split import temporal_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("samld_finalize")


def main() -> int:
    cfg = get_samld_config()
    runs = cfg.model_dir / "runs"
    reports = sorted(runs.glob("seed*/seed*_report.json"))
    if not reports:
        log.error("Không thấy seed report ở %s", runs)
        return 1
    pairs = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in reports]
    seed_reports = [r for _, r in pairs]
    log.info("Nạp %d seed report", len(seed_reports))

    best_path, best = max(pairs, key=lambda pr: pr[1]["validation_at_best"]["f1"])
    val_thr = best["test_validation_threshold"]["threshold"]
    # Đường dẫn predictions trong JSON là của MÁY GPU; đọc file cạnh report đã pull.
    preds = pd.read_parquet(best_path.parent / f"predictions_seed{best['seed']}.parquet")
    labels = preds["is_laundering"].to_numpy()
    scores = preds["score"].to_numpy()
    main_metrics = extended_metrics(labels, scores, val_thr)

    def agg(metric: str) -> dict:
        vals = [r["test_validation_threshold"][metric] for r in seed_reports]
        return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "values": [float(v) for v in vals]}

    over_seeds = {m: agg(m) for m in ("f1", "precision", "recall", "pr_auc")}

    log.info("Nạp SAML-D + split để lấy metadata test…")
    df = load_samld(cfg)
    split = temporal_split(df, cfg)
    tf = TestFrame.from_predictions(preds, split.test)

    art = cfg.artifact_dir
    art.mkdir(parents=True, exist_ok=True)
    xb_rows = cross_border_breakdown(tf, val_thr)
    pd.DataFrame(xb_rows).to_csv(art / "cross_border_metrics.csv", index=False)
    typ_rows = per_typology(tf, val_thr)
    pd.DataFrame(typ_rows).to_csv(art / "per_typology_metrics.csv", index=False)
    country_distribution(tf.df).to_csv(art / "country_distribution.csv", index=False)
    save_all(labels, scores, val_thr, art)

    # benchmark.csv (main + baselines) và ablation nếu đã có từ lần chạy GPU.
    bench_rows = []
    if (art / "benchmark.csv").exists():
        bench_rows = pd.read_csv(art / "benchmark.csv").to_dict("records")
    ablation_rows = []
    if (art / "ablation_results.csv").exists():
        ablation_rows = pd.read_csv(art / "ablation_results.csv").to_dict("records")

    import platform as _pf
    from datetime import UTC, datetime

    import torch as _torch

    overall = {
        "schema_version": "fin07.samld.benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "platform": _pf.platform(),
        "torch_version": _torch.__version__,
        "model": "multi_pna_eu",
        "reconstructed_locally": True,
        "seeds": [r["seed"] for r in seed_reports],
        "threshold_strategy": "f1",
        "operational_threshold": val_thr,
        "main_metrics": main_metrics,
        "over_seeds": over_seeds,
        "operating_points": best["operational_budget"],
        "region_rows": int(main_metrics["rows"]),
        "positive_rows": int(main_metrics["positives"]),
        "edge_features": int(json.loads((cfg.model_dir / "feature_schema.json").read_text())["num_features"]),
        "config": best["config"],
        "data_profile": data_profile(df),
    }
    (art / "overall_metrics.json").write_text(json.dumps(overall, ensure_ascii=False, indent=2), "utf-8")
    (art / "benchmark.json").write_text(
        json.dumps(
            {
                "benchmark": bench_rows,
                "ablation": ablation_rows,
                "cross_border": xb_rows,
                "per_typology": typ_rows,
                "over_seeds": over_seeds,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        "utf-8",
    )
    _write_report(art, overall, bench_rows, ablation_rows, xb_rows, typ_rows)
    log.info("Xong. Report + artifacts dựng lại ở %s", art)
    log.info(
        "Main: F1=%.4f PR-AUC=%.4f | over-seeds F1 %.4f±%.4f",
        main_metrics["f1"],
        main_metrics["pr_auc"],
        over_seeds["f1"]["mean"],
        over_seeds["f1"]["std"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
