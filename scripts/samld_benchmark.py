"""Benchmark toàn diện nhánh SAML-D (Multi-PNA+EU) — sinh mọi artifact + report.

Chạy:
    python -m scripts.samld_benchmark --config src/samld/config/benchmark.yaml

Sinh trong artifacts/samld/: benchmark.csv/json, overall_metrics.json,
per_typology_metrics.csv, cross_border_metrics.csv, country_distribution.csv,
ablation_results.csv, các đường cong .png, data_profile.json, benchmark_report.md.

Kết quả reproduction là của CHÍNH pipeline này — không phải số tham chiếu TransXion.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from src.samld.ablation import ARMS, apply_arm
from src.samld.baselines import run_tabular_baselines
from src.samld.config import get_samld_config
from src.samld.data import load_samld
from src.samld.evaluate import (
    TestFrame,
    country_distribution,
    cross_border_breakdown,
    extended_metrics,
    per_typology,
    select_threshold,
)
from src.samld.graph_builder import FORWARD, build_graph
from src.samld.plots import save_all
from src.samld.split import temporal_split
from src.samld.training import build_mega_config, load_yaml_config, train_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("samld_benchmark")


def data_profile(df: pd.DataFrame) -> dict[str, Any]:
    xb = df["cross_border"] > 0.5
    return {
        "rows": int(len(df)),
        "unique_senders": int(df["sender_account"].nunique()),
        "unique_receivers": int(df["receiver_account"].nunique()),
        "unique_accounts": int(pd.concat([df["sender_account"], df["receiver_account"]]).nunique()),
        "date_range": [str(df["timestamp"].min()), str(df["timestamp"].max())],
        "positive_labels": int(df["label"].sum()),
        "negative_labels": int((df["label"] == 0).sum()),
        "positive_ratio": float(df["label"].mean()),
        "cross_border_count": int(xb.sum()),
        "domestic_count": int((~xb).sum()),
        "currency_mismatch_count": int((df["currency_mismatch"] > 0.5).sum()),
        "countries": int(df["sender_country"].nunique()),
        "payment_types": int(df["payment_type"].nunique()),
        "currencies": int(df["payment_currency"].nunique()),
        "suspicious_typologies": int(df.loc[df["label"] == 1, "typology"].nunique()),
    }


def _tabular_arrays(bundle):
    """(X_train, y_train, X_val, y_val, X_test, y_test) từ đặc trưng cạnh đã encode."""
    train_attr = bundle.mega_bundle.train[FORWARD].edge_attr.numpy()
    train_y = bundle.mega_bundle.train[FORWARD].y.numpy()
    val_attr = bundle.mega_bundle.validation[FORWARD].edge_attr.numpy()
    val_y = bundle.mega_bundle.validation[FORWARD].y.numpy()
    test_attr = bundle.mega_bundle.test[FORWARD].edge_attr.numpy()
    test_y = bundle.mega_bundle.test[FORWARD].y.numpy()
    return (
        train_attr,
        train_y,
        val_attr[bundle.train_end : bundle.val_end],
        val_y[bundle.train_end : bundle.val_end],
        test_attr[bundle.val_end :],
        test_y[bundle.val_end :],
    )


def _seed_test_scores(report: dict) -> tuple[np.ndarray, np.ndarray]:
    """Lấy nhãn + điểm test từ predictions parquet của một seed."""
    preds = pd.read_parquet(report["predictions_path"])
    return preds["is_laundering"].to_numpy(), preds["score"].to_numpy()


def run_ablation_only(
    config_path: Path,
    *,
    arms: list[str],
    base_f1: float,
    base_pr_auc: float,
    epochs: int | None,
    device: str,
) -> None:
    """Chỉ chạy ablation địa lý, dùng lại kết quả main đã có (base_f1/base_pr_auc).

    Tránh train lại các seed đã có; mỗi arm dựng bundle riêng (giải phóng ngay).
    """
    samld_cfg = get_samld_config()
    yaml_cfg = load_yaml_config(config_path)
    overrides: dict[str, Any] = {} if epochs is None else {"epochs": epochs}
    mega_cfg = build_mega_config(yaml_cfg, **overrides)
    neg_ratio = int(yaml_cfg.get("training", {}).get("train_neg_ratio", 0))
    seed0 = int(yaml_cfg.get("seeds", [42])[0])
    runs_dir = samld_cfg.model_dir / "runs"

    df = load_samld(samld_cfg)
    split_full = temporal_split(df, samld_cfg)
    rows: list[dict] = [
        {"arm": "full", "pr_auc": base_pr_auc, "f1": base_f1, "recall": None, "delta_pr_auc": 0.0, "delta_f1": 0.0}
    ]
    for arm in [a for a in arms if a != "full"]:
        ab_bundle = build_graph(apply_arm(split_full, arm, seed=seed0), encoder=None)
        rep = train_seed(
            ab_bundle,
            mega_cfg,
            seed=seed0,
            out_dir=runs_dir / f"ablation_{arm}",
            device=device,
            train_neg_ratio=neg_ratio,
        )
        albl, ascr = _seed_test_scores(rep)
        m = extended_metrics(albl, ascr, rep["test_validation_threshold"]["threshold"])
        rows.append(
            {
                "arm": arm,
                "pr_auc": m["pr_auc"],
                "f1": m["f1"],
                "recall": m["recall"],
                "delta_pr_auc": m["pr_auc"] - base_pr_auc,
                "delta_f1": m["f1"] - base_f1,
            }
        )
        del ab_bundle
        gc.collect()
        log.info("ablation %s: PR-AUC=%.4f F1=%.4f (ΔF1=%+.4f)", arm, m["pr_auc"], m["f1"], m["f1"] - base_f1)
    pd.DataFrame(rows).to_csv(samld_cfg.artifact_dir / "ablation_results.csv", index=False)
    log.info("Ablation xong. Ghi %s", samld_cfg.artifact_dir / "ablation_results.csv")


def run(
    config_path: Path,
    *,
    seeds: list[int] | None,
    epochs: int | None,
    device: str,
    xgboost: bool = True,
    arms: list[str] | None = None,
) -> None:
    samld_cfg = get_samld_config()
    yaml_cfg = load_yaml_config(config_path)
    seeds = seeds or list(yaml_cfg.get("seeds", [42]))
    overrides: dict[str, Any] = {}
    if epochs is not None:
        overrides["epochs"] = epochs
    mega_cfg = build_mega_config(yaml_cfg, **overrides)
    threshold_strategy = yaml_cfg.get("threshold", {}).get("strategy", "f1")
    recall_target = yaml_cfg.get("threshold", {}).get("recall_target", 0.90)
    # Lấy mẫu cạnh giám sát train theo lớp (0 = tắt). Giúp epoch rẻ đi nhiều lần
    # trên đồ thị 6,6 triệu cạnh mà không đụng val/test.
    neg_ratio = int(yaml_cfg.get("training", {}).get("train_neg_ratio", 0))

    art = samld_cfg.artifact_dir
    art.mkdir(parents=True, exist_ok=True)
    runs_dir = samld_cfg.model_dir / "runs"

    log.info("Nạp + chia + dựng đồ thị (full features)…")
    df = load_samld(samld_cfg)
    (art / "data_profile.json").write_text(json.dumps(data_profile(df), ensure_ascii=False, indent=2), "utf-8")
    split_full = temporal_split(df, samld_cfg)
    bundle = build_graph(split_full)
    # Lưu encoder + lược đồ đặc trưng để inference tự chứa, không cần fit lại.
    bundle.encoder.save(samld_cfg.model_dir / "encoder")
    (samld_cfg.model_dir / "feature_schema.json").write_text(
        json.dumps(
            {"edge_features": bundle.feature_names, "num_features": bundle.edge_features}, ensure_ascii=False, indent=2
        ),
        "utf-8",
    )

    # --- Model chính: Multi-PNA+EU, nhiều seed ---
    log.info("Huấn luyện Multi-PNA+EU trên %d seed…", len(seeds))
    seed_reports = [
        train_seed(bundle, mega_cfg, seed=s, out_dir=runs_dir / f"seed{s}", device=device, train_neg_ratio=neg_ratio)
        for s in seeds
    ]

    # Ngưỡng chọn trên validation của seed tốt nhất (theo val F1), áp cho test.
    best = max(seed_reports, key=lambda r: r["validation_at_best"]["f1"])
    val_thr = best["test_validation_threshold"]["threshold"]
    labels, scores = _seed_test_scores(best)
    main_metrics = extended_metrics(labels, scores, val_thr)

    # Tổng hợp nhiều seed (mean ± std).
    def agg(metric: str) -> dict[str, float]:
        vals = [r["test_validation_threshold"][metric] for r in seed_reports]
        return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "values": [float(v) for v in vals]}

    over_seeds = {m: agg(m) for m in ("f1", "precision", "recall", "pr_auc")}

    # --- Baselines tabular ---
    # PR-AUC là chỉ số so sánh CHÍNH (không phụ ngưỡng). F1 báo cáo ở ngưỡng chọn
    # trên VALIDATION của chính baseline đó (đúng §13, không tune trên test).
    log.info("Baselines tabular (LogReg + XGBoost)…")
    x_tr, y_tr, x_va, y_va, x_te, y_te = _tabular_arrays(bundle)
    baseline_rows: list[dict] = []
    for res in run_tabular_baselines(x_tr, y_tr, np.concatenate([x_va, x_te]), include_xgboost=xgboost):
        val_scores = res.test_scores[: len(x_va)]
        test_scores = res.test_scores[len(x_va) :]
        bthr = select_threshold(y_va, val_scores, strategy=threshold_strategy, recall_target=recall_target)
        m = extended_metrics(y_te, test_scores, bthr)
        m["model"] = res.name
        m["train_seconds"] = res.train_seconds
        baseline_rows.append(m)

    # --- Bảng benchmark (model chính + baselines) ---
    bench_rows = [
        {"model": "multi_pna_eu", "train_seconds": sum(r["seconds"] for r in seed_reports), **main_metrics},
        *baseline_rows,
    ]
    bench_df = pd.DataFrame(bench_rows)
    bench_df.to_csv(art / "benchmark.csv", index=False)

    # --- Ablation địa lý (single seed mỗi nhánh) ---
    run_arms = arms or list(ARMS)
    log.info("Ablation địa lý (%s)…", ", ".join(run_arms))
    ablation_rows: list[dict] = []
    base_pr = main_metrics["pr_auc"]
    base_f1 = main_metrics["f1"]
    # Giải phóng bundle chính (đồ thị ~15GB) trước khi dựng bundle ablation —
    # nếu không, hai bundle cùng lúc vượt 30GB RAM và OOM. Đã trích xong mọi thứ
    # cần từ bundle (predictions đã lưu, tabular arrays đã dùng).
    del bundle
    gc.collect()
    for arm in run_arms:
        if arm == "full":
            m = main_metrics
        else:
            ab_split = apply_arm(split_full, arm, seed=seeds[0])
            ab_bundle = build_graph(ab_split, encoder=None)
            rep = train_seed(
                ab_bundle,
                mega_cfg,
                seed=seeds[0],
                out_dir=runs_dir / f"ablation_{arm}",
                device=device,
                train_neg_ratio=neg_ratio,
            )
            albl, ascr = _seed_test_scores(rep)
            m = extended_metrics(albl, ascr, rep["test_validation_threshold"]["threshold"])
            del ab_bundle  # một bundle tại một thời điểm
            gc.collect()
        ablation_rows.append(
            {
                "arm": arm,
                "pr_auc": m["pr_auc"],
                "f1": m["f1"],
                "recall": m["recall"],
                "delta_pr_auc": m["pr_auc"] - base_pr,
                "delta_f1": m["f1"] - base_f1,
            }
        )
    pd.DataFrame(ablation_rows).to_csv(art / "ablation_results.csv", index=False)

    # --- Phân tích trên dự đoán của model chính ---
    preds = pd.read_parquet(best["predictions_path"])
    tf = TestFrame.from_predictions(preds, split_full.test)
    xb_rows = cross_border_breakdown(tf, val_thr)
    pd.DataFrame(xb_rows).to_csv(art / "cross_border_metrics.csv", index=False)
    typ_rows = per_typology(tf, val_thr)
    pd.DataFrame(typ_rows).to_csv(art / "per_typology_metrics.csv", index=False)
    country_distribution(tf.df).to_csv(art / "country_distribution.csv", index=False)

    # --- Đồ thị ---
    save_all(labels, scores, val_thr, art)

    overall = {
        "schema_version": "fin07.samld.benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "model": "multi_pna_eu",
        "device": device,
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "seeds": seeds,
        "threshold_strategy": threshold_strategy,
        "recall_target": recall_target,
        "operational_threshold": val_thr,
        "main_metrics": main_metrics,
        "over_seeds": over_seeds,
        # Đường vận hành theo ngân sách cảnh báo (từ seed tốt nhất) — cho
        # /fc/model-branches và trang Đánh giá chuẩn đọc.
        "operating_points": best["operational_budget"],
        "region_rows": int(main_metrics["rows"]),
        "positive_rows": int(main_metrics["positives"]),
        "edge_features": int(bundle.edge_features),
        "config": mega_cfg.to_dict(),
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
    log.info("Xong. Artifacts trong %s", art)


def _write_report(
    art: Path, overall: dict, bench: list[dict], ablation: list[dict], xb: list[dict], typ: list[dict]
) -> None:
    m = overall["main_metrics"]
    os_ = overall["over_seeds"]
    lines = [
        "# SAML-D Benchmark — Multi-PNA + Edge Updates",
        "",
        f"_Sinh tự động {overall['created_at']} · {overall['platform']} · torch {overall['torch_version']}_",
        "",
        "## Dataset",
        f"- Giao dịch: {overall['data_profile']['rows']:,} · tài khoản: {overall['data_profile']['unique_accounts']:,}",
        f"- Nhãn dương: {overall['data_profile']['positive_labels']:,} ({100 * overall['data_profile']['positive_ratio']:.3f}%)",
        f"- Xuyên biên giới: {overall['data_profile']['cross_border_count']:,} · typology nghi ngờ: {overall['data_profile']['suspicious_typologies']}",
        f"- Khoảng thời gian: {overall['data_profile']['date_range'][0]} → {overall['data_profile']['date_range'][1]}",
        "",
        "## Kết quả chính (FIN-07 reproduction — KHÔNG phải số TransXion)",
        f"- Ngưỡng chọn trên validation: {overall['operational_threshold']:.4f} (chiến lược {overall['threshold_strategy']})",
        f"- F1 {m['f1']:.4f} · Precision {m['precision']:.4f} · Recall {m['recall']:.4f}",
        f"- PR-AUC {m['pr_auc']:.4f} · ROC-AUC {m['roc_auc']:.4f} · F2 {m['f2']:.4f} · MCC {m['mcc']:.4f}",
        f"- FPR {m['fpr']:.5f} · FNR {m['fnr']:.4f} · Brier {m['brier']:.5f}",
        f"- Confusion: TP {m['confusion_matrix']['tp']} · FP {m['confusion_matrix']['fp']} · FN {m['confusion_matrix']['fn']} · TN {m['confusion_matrix']['tn']}",
        f"- Nhiều seed {overall['seeds']}: F1 {os_['f1']['mean']:.4f} ± {os_['f1']['std']:.4f} · PR-AUC {os_['pr_auc']['mean']:.4f} ± {os_['pr_auc']['std']:.4f}",
        "",
        "## Baseline comparison",
        "| Model | PR-AUC | F1 | Recall | FPR |",
        "|---|---|---|---|---|",
    ]
    for row in bench:
        lines.append(
            f"| {row['model']} | {row['pr_auc']:.4f} | {row['f1']:.4f} | {row['recall']:.4f} | {row['fpr']:.5f} |"
        )
    lines += [
        "",
        "## Geography ablation (§18)",
        "| Arm | PR-AUC | F1 | Recall | ΔPR-AUC | ΔF1 |",
        "|---|---|---|---|---|---|",
    ]
    for row in ablation:
        lines.append(
            f"| {row['arm']} | {row['pr_auc']:.4f} | {row['f1']:.4f} | {row['recall']:.4f} | {row['delta_pr_auc']:+.4f} | {row['delta_f1']:+.4f} |"
        )
    lines += [
        "",
        "## Cross-border vs domestic (§19)",
        "| Subset | N | AML rate | PR-AUC | Recall | F1 | FPR |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in xb:
        lines.append(
            f"| {row['subset']} | {row['count']:,} | {100 * row['laundering_prevalence']:.3f}% | {row['pr_auc']:.4f} | {row['recall']:.4f} | {row['f1']:.4f} | {row['fpr']:.5f} |"
        )
    lines += ["", "## Per-typology recall (§21)", "| Typology | Support | Recall | Mean prob |", "|---|---|---|---|"]
    for row in typ:
        lines.append(
            f"| {row['typology']} | {row['support']} | {row['recall']:.4f} | {row['mean_predicted_prob']:.4f} |"
        )
    lines += [
        "",
        "## Limitations",
        "- SAML-D là dataset **tổng hợp**; hiệu năng rất cao có thể một phần đến từ artifacts/correlations của bộ sinh.",
        "- Trường địa lý **không** được diễn giải như rủi ro FATF hiện hành; cross-border chỉ là ngữ cảnh giao dịch.",
        "- Kết quả trên SAML-D **không** trực tiếp đại diện cho hiệu năng AML thực tế.",
        "- Số tham chiếu TransXion (ROC-AUC≈0.999984, AP≈0.994835, F1≈0.976988) là để so sánh, KHÔNG phải kết quả repo này.",
    ]
    (art / "benchmark_report.md").write_text("\n".join(lines), "utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark SAML-D Multi-PNA+EU.")
    p.add_argument("--config", type=Path, default=Path("src/samld/config/benchmark.yaml"))
    p.add_argument("--seeds", type=int, nargs="*", default=None)
    p.add_argument("--epochs", type=int, default=None, help="Ghi đè epochs (dùng cho smoke test).")
    p.add_argument("--device", default="auto")
    p.add_argument("--no-xgboost", action="store_true", help="Bỏ XGBoost (né segfault libomp cục bộ).")
    p.add_argument("--arms", nargs="*", default=None, help="Chọn nhánh ablation (mặc định tất cả).")
    p.add_argument("--ablation-only", action="store_true", help="Chỉ chạy ablation, dùng lại main đã có.")
    p.add_argument("--base-f1", type=float, default=None)
    p.add_argument("--base-pr-auc", type=float, default=None)
    args = p.parse_args()
    if args.ablation_only:
        run_ablation_only(
            args.config,
            arms=args.arms or ["no_country", "no_geography", "country_shuffle"],
            base_f1=args.base_f1,
            base_pr_auc=args.base_pr_auc,
            epochs=args.epochs,
            device=args.device,
        )
        return 0
    run(
        args.config,
        seeds=args.seeds,
        epochs=args.epochs,
        device=args.device,
        xgboost=not args.no_xgboost,
        arms=args.arms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
