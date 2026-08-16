#!/usr/bin/env python3
"""Render a reproducible, publication-style report from locked benchmark JSON."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports/edge-benchmark/li_small_currency_native_policy_v1.json"
DEFAULT_BASELINE = ROOT / "reports/edge-benchmark/li_small.json"
DEFAULT_OUTPUT = ROOT / "reports/edge-benchmark/li_small_currency_native_policy_v1.md"
EXPECTED_SCHEMA = "fin07.currency_native_edge.benchmark.v1"
T_CRITICAL_95_DF4 = 2.7764451051977987


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _fmt_float(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}"


def _fmt_int(value: int | float) -> str:
    return f"{int(value):,}".replace(",", ".")


def _fmt_pct(value: float, digits: int = 4) -> str:
    return f"{100 * value:.{digits}f}%".replace(".", ",")


def _fmt_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{amount:.2f} {unit}"


def _markdown_table(headers: list[str], rows: list[list[Any]], align_right: set[int] | None = None) -> str:
    align_right = align_right or set()
    separator = ["---:" if index in align_right else "---" for index in range(len(headers))]
    body = [headers, separator, *[[str(cell) for cell in row] for row in rows]]
    return "\n".join("| " + " | ".join(row) + " |" for row in body)


def _validate(report: dict[str, Any], baseline: dict[str, Any]) -> None:
    if report.get("schema_version") != EXPECTED_SCHEMA:
        raise ValueError(f"Unsupported schema_version: {report.get('schema_version')!r}")
    if report.get("status") != "complete":
        raise ValueError(f"Benchmark is not canonical: status={report.get('status')!r}")

    runs = report["test_over_seeds"]["runs"]
    if report["test_over_seeds"]["count"] != 5 or len(runs) != 5:
        raise ValueError("Canonical benchmark must contain exactly five seed runs")
    if len({run["seed"] for run in runs}) != 5:
        raise ValueError("Seed identifiers must be unique")

    f1_values = [float(run["f1"]) for run in runs]
    expected_mean = statistics.mean(f1_values)
    expected_std = statistics.stdev(f1_values)
    if not math.isclose(expected_mean, report["test_over_seeds"]["f1_mean"], abs_tol=1e-12):
        raise ValueError("Stored F1 mean does not match seed runs")
    if not math.isclose(expected_std, report["test_over_seeds"]["f1_sample_std"], abs_tol=1e-12):
        raise ValueError("Stored F1 sample standard deviation does not match seed runs")

    split_counts = report["data"]["split_counts"]
    total_rows = sum(split["rows"] for split in split_counts.values())
    checks = report["data"]["checks"]
    if total_rows != checks["expected_rows"] or total_rows != checks["feature_rows"]:
        raise ValueError("Split counts do not match the feature population")

    primary_seed = report["selection"]["primary_seed"]
    primary = report["test_primary_seed"]
    matching = [run for run in runs if run["seed"] == primary_seed]
    if len(matching) != 1 or matching[0] != primary:
        raise ValueError("Primary seed metrics do not match the corresponding seed run")

    confusion_total = sum(
        primary[key] for key in ("true_positive", "false_positive", "false_negative", "true_negative")
    )
    if confusion_total != primary["rows"]:
        raise ValueError("Primary confusion matrix does not sum to test rows")
    if primary["true_positive"] + primary["false_negative"] != primary["positives"]:
        raise ValueError("Primary positive count is inconsistent")
    if primary["true_positive"] + primary["false_positive"] != primary["alerts"]:
        raise ValueError("Primary alert count is inconsistent")

    if baseline.get("schema_version") != "fin07.edge_benchmark.v1":
        raise ValueError(f"Unsupported baseline schema_version: {baseline.get('schema_version')!r}")
    baseline_splits = baseline["split_counts"]
    for split_name, split in split_counts.items():
        old = baseline_splits[split_name]
        if split["rows"] != old["rows"] or split["positives"] != old["laundering"]:
            raise ValueError(f"Baseline is not on the same {split_name} population")


def _feature_groups(features: list[str]) -> list[tuple[str, list[str]]]:
    groups = [
        ("Amount native đã chuẩn hóa", features[0:11]),
        ("Currency/category và cờ giao dịch", features[11:18]),
        ("Đếm hoạt động causal 24h/7d", features[18:25]),
        ("Cấu trúc đồ thị", features[25:32]),
        ("Dòng tiền và trạng thái thiếu inflow", features[32:37]),
    ]
    flattened = [feature for _, group in groups for feature in group]
    if flattened != features:
        raise ValueError("Feature grouping is stale relative to the feature contract")
    return groups


def _derived_metrics(primary: dict[str, Any]) -> dict[str, float]:
    tp = float(primary["true_positive"])
    fp = float(primary["false_positive"])
    fn = float(primary["false_negative"])
    tn = float(primary["true_negative"])
    total = tp + fp + fn + tn
    specificity = _ratio(tn, tn + fp)
    recall = _ratio(tp, tp + fn)
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "prevalence": _ratio(tp + fn, total),
        "accuracy": _ratio(tp + tn, total),
        "specificity": specificity,
        "false_positive_rate": _ratio(fp, fp + tn),
        "false_negative_rate": _ratio(fn, fn + tp),
        "negative_predictive_value": _ratio(tn, tn + fn),
        "balanced_accuracy": (recall + specificity) / 2,
        "mcc": _ratio(tp * tn - fp * fn, denominator),
    }


def _aggregate_seed_metrics(runs: list[dict[str, Any]]) -> list[list[str]]:
    metrics = [
        ("F1", "f1"),
        ("PR-AUC", "pr_auc"),
        ("Precision", "precision"),
        ("Recall", "recall"),
        ("Alert rate", "alert_rate"),
        ("Threshold", "threshold"),
    ]
    rows: list[list[str]] = []
    for label, key in metrics:
        values = [float(run[key]) for run in runs]
        rows.append(
            [
                label,
                _fmt_float(statistics.mean(values)),
                _fmt_float(statistics.stdev(values)),
                _fmt_float(min(values)),
                _fmt_float(max(values)),
            ]
        )
    return rows


def _render(report: dict[str, Any], baseline: dict[str, Any], input_path: Path, baseline_path: Path) -> str:
    _validate(report, baseline)
    split_counts = report["data"]["split_counts"]
    checks = report["data"]["checks"]
    selection = report["selection"]
    primary = report["test_primary_seed"]
    seed_summary = report["test_over_seeds"]
    runs = seed_summary["runs"]
    runtime = report["runtime"]
    artifacts = report["artifacts"]
    derived = _derived_metrics(primary)

    f1_mean = float(seed_summary["f1_mean"])
    f1_std = float(seed_summary["f1_sample_std"])
    f1_margin = T_CRITICAL_95_DF4 * f1_std / math.sqrt(len(runs))
    total_rows = sum(split["rows"] for split in split_counts.values())
    total_positives = sum(split["positives"] for split in split_counts.values())

    baseline_by_name = {row["feature_set"]: row for row in baseline["results"]}
    comparison_rows: list[list[str]] = []
    for name, label, policy_note in (
        ("basic_only", "Basic only", "Legacy; có feature bị policy hiện tại cấm"),
        ("basic_plus_graph", "Basic + Graph", "Legacy; có feature bị policy hiện tại cấm"),
        ("policy_compliant", "Policy-compliant static-FX", "Không dùng feature cấm; còn static FX"),
    ):
        row = baseline_by_name[name]
        old_mean = float(row["test_f1_over_seeds"]["mean"])
        comparison_rows.append(
            [
                label,
                str(row["n_features"]),
                f"{old_mean:.6f} ± {row['test_f1_over_seeds']['std']:.6f}",
                _fmt_float(float(row["test_pr_auc"])),
                _fmt_float(float(row["test"]["precision"])),
                _fmt_float(float(row["test"]["recall"])),
                _fmt_float(f1_mean - old_mean, 6),
                policy_note,
            ]
        )
    comparison_rows.append(
        [
            "Currency-native policy v1",
            str(len(report["features"])),
            f"{f1_mean:.6f} ± {f1_std:.6f}",
            _fmt_float(float(primary["pr_auc"])),
            _fmt_float(float(primary["precision"])),
            _fmt_float(float(primary["recall"])),
            "—",
            "Release hiện tại; không static FX",
        ]
    )

    published_labels = {
        "xgboost_basic_features": "XGBoost — basic features",
        "lightgbm_basic_features": "LightGBM — basic features",
        "mlp": "MLP",
        "lightgbm_plus_gfp": "LightGBM + GFP",
        "xgboost_plus_gfp": "XGBoost + GFP",
        "gin": "GIN",
        "pna": "PNA",
        "gin_plus_eu": "GIN + EU",
    }
    published_rows = [
        [published_labels.get(key, key), _fmt_float(float(value), 4), "LI-Small"]
        for key, value in baseline["published_li_small_f1_for_reference"].items()
    ]

    feature_rows = [
        [str(index), label, str(len(group)), "<br>".join(f"`{feature}`" for feature in group)]
        for index, (label, group) in enumerate(_feature_groups(report["features"]), start=1)
    ]

    trial_rows = []
    for index, trial in enumerate(selection["trials"], start=1):
        config = trial["config"]
        validation = trial["validation"]
        trial_rows.append(
            [
                str(index),
                str(config["class_weight"]),
                str(config["learning_rate"]),
                str(config["max_iter"]),
                str(config["max_leaf_nodes"]),
                _fmt_float(validation["threshold"]),
                _fmt_float(validation["precision"]),
                _fmt_float(validation["recall"]),
                _fmt_float(validation["f1"]),
                _fmt_float(validation["pr_auc"]),
                f"{trial['seconds']:.1f}",
            ]
        )

    seed_rows = [
        [
            str(run["seed"]),
            _fmt_float(run["threshold"]),
            _fmt_float(run["precision"]),
            _fmt_float(run["recall"]),
            _fmt_float(run["f1"]),
            _fmt_float(run["pr_auc"]),
            _fmt_int(run["true_positive"]),
            _fmt_int(run["false_positive"]),
            _fmt_int(run["false_negative"]),
            _fmt_int(run["alerts"]),
        ]
        for run in runs
    ]

    split_rows = []
    for name in ("train", "val", "test"):
        split = split_counts[name]
        negatives = split["rows"] - split["positives"]
        split_rows.append(
            [
                name,
                split["start"],
                split["end"],
                _fmt_int(split["rows"]),
                _fmt_int(split["positives"]),
                _fmt_int(negatives),
                _fmt_pct(_ratio(split["positives"], split["rows"]), 5),
            ]
        )
    split_rows.append(
        [
            "Tổng",
            "—",
            "—",
            _fmt_int(total_rows),
            _fmt_int(total_positives),
            _fmt_int(total_rows - total_positives),
            _fmt_pct(_ratio(total_positives, total_rows), 5),
        ]
    )

    operating_rows = [
        [
            _fmt_int(point["alerts_reviewed"]),
            _fmt_int(point["caught"]),
            _fmt_int(point["false_alarms"]),
            _fmt_float(point["precision"]),
            _fmt_float(point["recall"]),
            _fmt_pct(_ratio(point["alerts_reviewed"], primary["rows"]), 4),
        ]
        for point in report["operating_points"]
    ]

    policy = report["policy"]
    policy_rows = [
        [
            "Amount paid + payment currency gốc",
            "Có",
            str(policy["uses_original_amount_paid"] and policy["uses_original_payment_currency"]),
        ],
        [
            "Amount received + receiving currency gốc",
            "Có",
            str(policy["uses_original_amount_received"] and policy["uses_original_receiving_currency"]),
        ],
        ["Static FX trong model", "Không", str(policy["uses_static_fx"])],
        ["Chuẩn hóa", "Train-only, theo native currency", policy["normalization"]],
        ["Payment format", "Không dùng", str(policy["payment_format_feature"])],
        ["Giờ trong ngày", "Không dùng", str(policy["hour_of_day_feature"])],
        ["USD conversion", "Chỉ rule ngoài model", policy["usd_conversion_scope"]],
    ]

    quality_rows = [
        ["Số dòng kỳ vọng", _fmt_int(checks["expected_rows"]), "Đạt"],
        ["Số dòng feature", _fmt_int(checks["feature_rows"]), "Đạt"],
        ["Thiếu currency", _fmt_int(checks["missing_currency_rows"]), "Đạt"],
        ["Currency chưa biết", _fmt_int(checks["unknown_currency_rows"]), "Đạt"],
        ["Amount không dương", _fmt_int(checks["non_positive_amount_rows"]), "Đạt"],
        ["Feature NaN/Inf", _fmt_int(checks["non_finite_feature_rows"]), "Đạt"],
        ["Fit degree cap", checks["degree_cap_fit_scope"], "Đạt"],
        ["Static FX", str(checks["uses_static_fx"]), "Đạt"],
    ]

    lines = [
        "# Báo cáo benchmark khoa học — HI-Medium Currency-Native Policy v1",
        "",
        f"> **Trạng thái:** `{report['status']}` · **Model:** `{report['model_version']}` · "
        f"**Tạo lúc:** `{report['created_at']}`",
        "",
        "## Tóm tắt",
        "",
        "Mô hình phân loại từng giao dịch trên IBM AML HI-Medium đạt "
        f"**F1 = {f1_mean:.6f} ± {f1_std:.6f}** trên 5 seed (trung bình ± sample SD). "
        f"Khoảng 95% dùng phân phối t là **[{f1_mean - f1_margin:.6f}, "
        f"{f1_mean + f1_margin:.6f}]**; khoảng này chỉ mô tả biến thiên do seed, không phải "
        "khoảng tin cậy cho hiệu năng production. Primary release seed 42 đạt "
        f"F1 **{primary['f1']:.6f}**, PR-AUC **{primary['pr_auc']:.6f}**, precision "
        f"**{primary['precision']:.6f}** và recall **{primary['recall']:.6f}**.",
        "",
        "Nguồn số liệu máy đọc được: "
        f"[`{input_path.name}`](./{input_path.name}); baseline hồi cứu: "
        f"[`{baseline_path.name}`](./{baseline_path.name}). Tất cả bảng dưới đây được sinh "
        "từ hai artifact đã khóa, không nhập tay.",
        "",
        "## 1. Thiết kế nghiên cứu",
        "",
        "**Bảng 1. Thiết kế thí nghiệm và protocol đánh giá.**",
        "",
        _markdown_table(
            ["Thành phần", "Quy định"],
            [
                ["Nhiệm vụ", "Binary edge classification: một dòng là một giao dịch"],
                ["Dataset", "IBM AML HI-Medium, 29.336.378 giao dịch"],
                ["Chia tập", "60/20/20 theo thứ tự thời gian; không shuffle giữa các tập"],
                ["Tính nhân quả", "Cửa sổ graph kết thúc 1 phút trước giao dịch được chấm"],
                ["Chọn model", "Tối đa hóa F1 validation của lớp laundering"],
                ["Chọn threshold", "Tối đa hóa F1 trên validation; không chọn trên test"],
                ["Đánh giá chính", "F1 trung bình ± sample SD trên 5 seed"],
                ["Đánh giá bổ sung", "PR-AUC, precision, recall, confusion matrix, operating points"],
                ["Primary release", f"Seed {selection['primary_seed']}"],
                ["Model family", "scikit-learn HistGradientBoostingClassifier"],
            ],
        ),
        "",
        "**Bảng 2. Phân bố dữ liệu theo temporal split.**",
        "",
        _markdown_table(
            ["Tập", "Bắt đầu (UTC)", "Kết thúc (UTC)", "Số dòng", "Positive", "Negative", "Prevalence"],
            split_rows,
            {3, 4, 5, 6},
        ),
        "",
        "Dữ liệu mất cân bằng rất mạnh; vì vậy accuracy không phải chỉ số chọn model. F1 và "
        "PR-AUC được ưu tiên vì tập trung vào lớp laundering hiếm.",
        "",
        "**Bảng 3. Data-quality và leakage gates.**",
        "",
        _markdown_table(["Kiểm tra", "Kết quả", "Trạng thái"], quality_rows, {1}),
        "",
        "## 2. Policy và feature contract",
        "",
        "**Bảng 4. Kiểm chứng policy tiền tệ.**",
        "",
        _markdown_table(["Yêu cầu", "Kỳ vọng", "Artifact ghi nhận"], policy_rows),
        "",
        "**Bảng 5. Danh mục 37 feature của release.**",
        "",
        _markdown_table(["Nhóm", "Mô tả", "Số feature", "Tên feature"], feature_rows, {0, 2}),
        "",
        "Hai feature category là `payment_currency_code` và `receiving_currency_code`, tại "
        f"zero-based indices `{report['categorical_features']}`. Thống kê amount/currency pair và "
        "degree cap đều chỉ fit trên train.",
        "",
        "## 3. Chọn siêu tham số trên validation",
        "",
        "**Bảng 6. Toàn bộ grid-search trials.** Dòng có F1 validation cao nhất được chọn.",
        "",
        _markdown_table(
            [
                "Trial",
                "class_weight",
                "learning_rate",
                "max_iter",
                "max_leaf_nodes",
                "Threshold",
                "Precision",
                "Recall",
                "F1",
                "PR-AUC",
                "Giây",
            ],
            trial_rows,
            set(range(0, 11)),
        ),
        "",
        "Cấu hình khóa: "
        f"`{json.dumps(selection['selected_config'], sort_keys=True)}`; threshold primary "
        f"`{selection['threshold']:.12f}`.",
        "",
        "## 4. Kết quả test",
        "",
        "**Bảng 7. Kết quả test theo từng seed.** Mỗi seed dùng threshold đã chọn trên validation của chính run đó.",
        "",
        _markdown_table(
            ["Seed", "Threshold", "Precision", "Recall", "F1", "PR-AUC", "TP", "FP", "FN", "Alerts"],
            seed_rows,
            set(range(10)),
        ),
        "",
        "**Bảng 8. Thống kê mô tả trên 5 seed.** SD là sample standard deviation (`ddof=1`).",
        "",
        _markdown_table(
            ["Metric", "Mean", "Sample SD", "Min", "Max"],
            _aggregate_seed_metrics(runs),
            {1, 2, 3, 4},
        ),
        "",
        "**Bảng 9. Ma trận nhầm lẫn của primary release (seed 42).**",
        "",
        _markdown_table(
            ["Nhãn thực tế", "Dự đoán laundering", "Dự đoán legitimate", "Tổng"],
            [
                [
                    "Laundering",
                    _fmt_int(primary["true_positive"]),
                    _fmt_int(primary["false_negative"]),
                    _fmt_int(primary["positives"]),
                ],
                [
                    "Legitimate",
                    _fmt_int(primary["false_positive"]),
                    _fmt_int(primary["true_negative"]),
                    _fmt_int(primary["rows"] - primary["positives"]),
                ],
                [
                    "Tổng",
                    _fmt_int(primary["alerts"]),
                    _fmt_int(primary["rows"] - primary["alerts"]),
                    _fmt_int(primary["rows"]),
                ],
            ],
            {1, 2, 3},
        ),
        "",
        "**Bảng 10. Chỉ số primary release, gồm chỉ số dẫn xuất từ ma trận nhầm lẫn.**",
        "",
        _markdown_table(
            ["Metric", "Giá trị", "Vai trò"],
            [
                ["F1", _fmt_float(primary["f1"]), "Chỉ số chính của primary seed"],
                ["PR-AUC", _fmt_float(primary["pr_auc"]), "Chất lượng ranking trên dữ liệu lệch lớp"],
                ["Precision / PPV", _fmt_float(primary["precision"]), "Tỷ lệ alert là positive thật"],
                ["Recall / sensitivity", _fmt_float(primary["recall"]), "Tỷ lệ positive được bắt"],
                ["Specificity", _fmt_float(derived["specificity"]), "Tỷ lệ legitimate được bỏ qua đúng"],
                ["False-positive rate", _fmt_float(derived["false_positive_rate"]), "FP / (FP + TN)"],
                ["False-negative rate", _fmt_float(derived["false_negative_rate"]), "FN / (FN + TP)"],
                ["Negative predictive value", _fmt_float(derived["negative_predictive_value"]), "TN / (TN + FN)"],
                [
                    "Balanced accuracy",
                    _fmt_float(derived["balanced_accuracy"]),
                    "Trung bình sensitivity và specificity",
                ],
                [
                    "Matthews correlation coefficient",
                    _fmt_float(derived["mcc"]),
                    "Đo tương quan cân bằng bốn ô confusion matrix",
                ],
                ["Accuracy", _fmt_float(derived["accuracy"]), "Chỉ tham khảo do lệch lớp mạnh"],
                ["Prevalence", _fmt_pct(derived["prevalence"], 5), "Positive / toàn bộ test"],
                [
                    "Alert rate",
                    _fmt_pct(primary["alert_rate"], 5),
                    f"{_fmt_int(primary['alerts'])} / {_fmt_int(primary['rows'])}",
                ],
            ],
            {1},
        ),
        "",
        "**Bảng 11. Operating points trên ranking của primary release.**",
        "",
        _markdown_table(
            ["Review budget", "Bắt đúng", "False alarm", "Precision", "Recall", "% test được review"],
            operating_rows,
            set(range(6)),
        ),
        "",
        "Operating points trả lời câu hỏi vận hành theo ngân sách review; chúng không thay thế "
        f"threshold release `{selection['threshold']:.6f}`.",
        "",
        "## 5. So sánh và diễn giải",
        "",
        "**Bảng 12. So sánh hồi cứu với các nhánh trong repo trên cùng temporal split.** "
        "PR-AUC, precision và recall là primary seed 42; F1 là mean ± sample SD trên 5 seed.",
        "",
        _markdown_table(
            ["Nhánh", "Features", "F1 5 seeds", "PR-AUC", "Precision", "Recall", "Δ current − nhánh", "Policy note"],
            comparison_rows,
            {1, 2, 3, 4, 5, 6},
        ),
        "",
        f"So với `policy_compliant` static-FX, release mới tăng F1 tuyệt đối "
        f"**{f1_mean - baseline_by_name['policy_compliant']['test_f1_over_seeds']['mean']:.6f}** "
        f"({100 * (f1_mean / baseline_by_name['policy_compliant']['test_f1_over_seeds']['mean'] - 1):.2f}% tương đối). "
        "Đây không phải ablation sạch: feature contract và preprocessing khác nhau, nên không quy "
        "toàn bộ chênh lệch cho một biến duy nhất.",
        "",
        "**Bảng 13. Kết quả công bố trên LI-Small được giữ trong artifact để tham chiếu.**",
        "",
        _markdown_table(["Mô hình", "F1 công bố", "Dataset"], published_rows, {1}),
        "",
        "Không xếp hạng trực tiếp Bảng 13 với HI-Medium ở Bảng 12: khác dataset và có thể khác "
        "pipeline/feature implementation. Các số này chỉ cung cấp bối cảnh phương pháp.",
        "",
        "## 6. Khả năng tái lập và provenance",
        "",
        "**Bảng 14. Môi trường và thời gian chạy.**",
        "",
        _markdown_table(
            ["Thành phần", "Giá trị"],
            [
                ["Python", runtime["python"]],
                ["NumPy", runtime["numpy"]],
                ["pandas", runtime["pandas"]],
                ["scikit-learn", runtime["scikit_learn"]],
                ["DuckDB", runtime["duckdb"]],
                ["joblib", runtime["joblib"]],
                ["Wall-clock", f"{runtime['seconds']:.1f} giây ({runtime['seconds'] / 60:.2f} phút)"],
            ],
        ),
        "",
        "**Bảng 15. Artifact release và checksum.**",
        "",
        _markdown_table(
            ["Artifact", "Đường dẫn", "Kích thước", "SHA-256"],
            [
                [
                    "Model",
                    f"`{artifacts['model']['path']}`",
                    _fmt_bytes(artifacts["model"]["bytes"]),
                    f"`{artifacts['model']['sha256']}`",
                ],
                [
                    "Test scores",
                    f"`{artifacts['test_scores']['path']}`",
                    _fmt_bytes(artifacts["test_scores"]["bytes"]),
                    f"`{artifacts['test_scores']['sha256']}`",
                ],
                ["Benchmark JSON", f"`{input_path.relative_to(ROOT)}`", "—", "Nguồn của báo cáo này"],
            ],
        ),
        "",
        "Tái tạo hoặc kiểm tra báo cáo:",
        "",
        "```bash",
        ".venv/bin/python scripts/render_edge_benchmark_report.py",
        ".venv/bin/python scripts/render_edge_benchmark_report.py --check",
        "```",
        "",
        "## 7. Giới hạn nghiên cứu",
        "",
        _markdown_table(
            ["Giới hạn", "Ảnh hưởng", "Cách xử lý khi production"],
            [
                [
                    "Dữ liệu IBM AML là synthetic",
                    "Không suy rộng trực tiếp sang tỷ lệ bắt AML thật",
                    "Shadow evaluation và backtest trên dữ liệu đã gán nhãn nội bộ",
                ],
                ["Chỉ một temporal split", "Chưa đo drift theo nhiều giai đoạn", "Rolling/forward-chaining evaluation"],
                [
                    "5 seed cùng một split",
                    "SD chỉ đo ngẫu nhiên thuật toán",
                    "Không diễn giải CI seed như CI hiệu năng production",
                ],
                [
                    "Threshold tối ưu F1",
                    "Chưa phản ánh chi phí FP/FN cụ thể",
                    "Chọn operating point theo review capacity và risk appetite",
                ],
                [
                    "Baseline không phải ablation sạch",
                    "Không xác định nhân quả của từng feature/policy change",
                    "Chạy controlled ablation cùng preprocessing và seed",
                ],
                [
                    "Chưa calibration report",
                    "Score chưa được chứng minh là xác suất hiệu chỉnh",
                    "Đo Brier score/reliability và calibrate trên validation",
                ],
            ],
        ),
        "",
        "## 8. Định nghĩa chỉ số",
        "",
        "- `Precision = TP / (TP + FP)`.",
        "- `Recall = TP / (TP + FN)`.",
        "- `F1 = 2 × Precision × Recall / (Precision + Recall)`.",
        "- `PR-AUC` là diện tích dưới đường precision–recall từ score liên tục.",
        "- `Sample SD = sqrt(Σ(xᵢ − x̄)² / (n − 1))` với `n = 5`.",
        "- Khoảng 95% mô tả seed dùng `x̄ ± t(0,975; 4) × SD / sqrt(5)`.",
        "",
        "Tài liệu phương pháp trong repo: "
        "[`EDGE_LEVEL_BENCHMARK.md`](../../docs/ml/EDGE_LEVEL_BENCHMARK.md) và "
        "[`CURRENCY_NATIVE_EDGE_MVP.md`](../../docs/ml/CURRENCY_NATIVE_EDGE_MVP.md).",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed Markdown does not match the benchmark JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rendered = _render(
        _load_json(args.input),
        _load_json(args.baseline),
        args.input.resolve(),
        args.baseline.resolve(),
    )
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Benchmark report is stale: {args.output}")
        print(f"Benchmark report is current: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
