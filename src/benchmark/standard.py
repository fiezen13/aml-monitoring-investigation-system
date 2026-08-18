"""Một chuẩn báo cáo benchmark cho mọi nhánh phát hiện.

Vì sao cần
----------
Kiểm kê ``reports/`` ngày 18/08 tìm thấy **19 báo cáo, 4 đơn vị đánh giá khác
nhau**, F1 trải từ 0,0007 tới 0,1870, và không cái nào so được với cái nào:

* nhánh edge đo trên **giao dịch**, ngưỡng chốt trên validation;
* MEGA-PNA đo trên **giao dịch**, quyết định bằng **argmax hai logit**;
* hợp nhất đo trên **tài khoản-mốc**;
* bộ dò đồ thị đo trên **tài khoản-mốc**, tất định;
* luật đo trên **tài khoản**, cả kỳ 28 ngày.

Tệ hơn: một file duy nhất chứa **chín** giá trị ``f1`` ở các độ sâu khác nhau
(``selection.trials[0].validation.f1``, ``test_primary_seed.f1``,
``test_over_seeds.runs[2].f1`` …) mà không quy ước nào nói cái nào là chính
thức. Script đọc tự động sẽ lấy nhầm — và đã lấy nhầm.

Bốn quy tắc
-----------
1. **Đơn vị chung là tài khoản-cửa sổ.** Đó là đơn vị của bảng ``alert``. Mô hình
   chấm cạnh phải chiếu lên tài khoản rồi mới đo. Được phép báo cáo thêm ở đơn vị
   gốc, nhưng con số đem so sánh luôn là đơn vị chung.
2. **Đúng một khoá chứa con số chính thức:** ``headline``. Mọi giá trị khác phải
   nằm dưới ``diagnostics`` và bị cấm trích dẫn. Bộ kiểm tra từ chối báo cáo có
   ``f1`` nằm ngoài hai chỗ đó.
3. **Báo cáo tự khai đủ ngữ cảnh** — bộ dữ liệu, mã băm, mốc chia tập, quy tắc
   quyết định, ngưỡng và nơi chọn ngưỡng. Thiếu một trường là không hợp lệ.
4. **Điểm vận hành cố định.** Mọi mô hình báo cáo trên cùng dãy ngân sách, vì đó
   mới là câu hỏi so sánh được: *rà N cảnh báo thì bắt được bao nhiêu?*
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

UTC = timezone.utc  # noqa: UP017 — container CUDA chạy Python 3.10

SCHEMA_VERSION = "fin07.benchmark.v1"

#: Đơn vị chung. ``account_window`` là đơn vị của ``alert`` nên mọi so sánh phải
#: quy về nó; ``transaction`` chỉ để đối chiếu với bảng của các bài báo.
Unit = Literal["account_window", "transaction"]
UNITS: tuple[str, ...] = ("account_window", "transaction")

#: Cách biến điểm thành quyết định. Ghi rõ vì ba cách cho ba con số khác nhau
#: trên cùng một mô hình, và trước đây ta đã đặt chúng cạnh nhau.
DecisionRule = Literal["argmax", "threshold_from_validation", "top_k_budget", "deterministic"]
DECISION_RULES: tuple[str, ...] = ("argmax", "threshold_from_validation", "top_k_budget", "deterministic")

#: Dãy ngân sách cố định, giữ nguyên dãy đã dùng trong
#: ``scripts/evaluate_mega_pna_operations.py`` để báo cáo cũ còn đối chiếu được.
CANONICAL_BUDGETS: tuple[int, ...] = (100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000)

#: Bộ số đo bắt buộc trong ``headline``. Không thừa, không thiếu.
HEADLINE_METRICS: tuple[str, ...] = ("f1", "precision", "recall", "pr_auc")

_REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "schema_version",
    "created_at",
    "component",
    "unit",
    "dataset",
    "split",
    "decision_rule",
    "threshold",
    "headline",
    "operating_points",
    "provenance",
)
_REQUIRED_DATASET: tuple[str, ...] = ("name", "sha256", "rows", "positives")
_REQUIRED_SPLIT: tuple[str, ...] = ("protocol", "train", "validation", "test")
_REQUIRED_SPLIT_PART: tuple[str, ...] = ("rows", "positives")
_REQUIRED_THRESHOLD: tuple[str, ...] = ("value", "selected_on")
_REQUIRED_PROVENANCE: tuple[str, ...] = ("model_sha256", "git_commit")

#: Ba chỗ được phép chứa số đo. Xem ``_stray_metric_paths``.
_METRIC_EXEMPT_KEYS: tuple[str, ...] = ("headline", "diagnostics", "operating_points")


def metrics_at_threshold(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    """Bộ số đo chuẩn tại một ngưỡng."""
    labels = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    if labels.shape != scores.shape:
        raise ValueError("labels và scores phải cùng kích thước")
    if labels.size == 0:
        raise ValueError("không đo được trên tập rỗng")

    predictions = (scores >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        # PR-AUC không phụ thuộc ngưỡng: nó đo chất lượng xếp hạng. Giữ trong bộ
        # bắt buộc vì hai mô hình cùng F1 vẫn có thể xếp hạng khác hẳn nhau.
        "pr_auc": float(average_precision_score(labels, scores)) if labels.sum() else 0.0,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "rows": int(labels.size),
        "positives": int(labels.sum()),
    }


def operating_points(
    labels: np.ndarray,
    scores: np.ndarray,
    budgets: tuple[int, ...] = CANONICAL_BUDGETS,
) -> list[dict[str, Any]]:
    """Bắt được bao nhiêu nếu chuyên viên chỉ rà N mục xếp đầu.

    Đây là con số so sánh được giữa các mô hình, kể cả khi chúng dùng quy tắc
    quyết định khác nhau — vì nó bỏ ngưỡng ra khỏi phép so.
    """
    labels = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    order = np.argsort(-scores, kind="stable")
    cumulative = np.cumsum(labels[order])
    positives = int(labels.sum())

    rows: list[dict[str, Any]] = []
    for budget in budgets:
        if budget <= 0 or budget > labels.size:
            # Ghi rõ là không áp dụng được, thay vì lặng lẽ bỏ qua: người đọc cần
            # phân biệt "không đo" với "đo ra 0".
            rows.append({"budget": int(budget), "applicable": False})
            continue
        caught = int(cumulative[budget - 1])
        rows.append(
            {
                "budget": int(budget),
                "applicable": True,
                "caught": caught,
                "precision": caught / budget,
                "recall": caught / positives if positives else None,
            }
        )
    return rows


def build_report(
    *,
    component: str,
    unit: Unit,
    dataset: dict[str, Any],
    split: dict[str, Any],
    decision_rule: DecisionRule,
    threshold_value: float | None,
    threshold_selected_on: str,
    labels: np.ndarray,
    scores: np.ndarray,
    provenance: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
    budgets: tuple[int, ...] = CANONICAL_BUDGETS,
) -> dict[str, Any]:
    """Dựng một báo cáo đúng chuẩn. Đây là đường duy nhất nên dùng."""
    if unit not in UNITS:
        raise ValueError(f"unit phải thuộc {UNITS}, nhận {unit!r}")
    if decision_rule not in DECISION_RULES:
        raise ValueError(f"decision_rule phải thuộc {DECISION_RULES}, nhận {decision_rule!r}")
    if decision_rule == "threshold_from_validation" and threshold_selected_on != "validation":
        raise ValueError("threshold_from_validation bắt buộc threshold_selected_on='validation'")

    headline = metrics_at_threshold(labels, scores, threshold_value if threshold_value is not None else 0.5)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "component": component,
        "unit": unit,
        "dataset": dataset,
        "split": split,
        "decision_rule": decision_rule,
        "threshold": {"value": threshold_value, "selected_on": threshold_selected_on},
        "headline": headline,
        "operating_points": operating_points(labels, scores, budgets),
        "provenance": provenance,
        "diagnostics": diagnostics or {},
    }
    problems = validate_report(report)
    if problems:
        raise ValueError("báo cáo vừa dựng đã sai chuẩn: " + "; ".join(problems))
    return report


def _stray_metric_paths(node: Any, path: str = "") -> list[str]:
    """Tìm ``f1`` nằm ngoài ``headline`` và ``diagnostics``.

    Đây là quy tắc đắt giá nhất của cả chuẩn. Nó tồn tại vì một báo cáo cũ chứa
    chín giá trị ``f1`` ở chín đường dẫn khác nhau, và bộ đọc tự động lấy nhầm
    ``selection.trials[0].validation.f1`` = 0,1273 thay vì ``test_primary_seed.f1``
    = 0,3022.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key in HEADLINE_METRICS and isinstance(value, int | float):
                found.append(here)
            else:
                found.extend(_stray_metric_paths(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_stray_metric_paths(value, f"{path}[{index}]"))
    return found


def validate_report(report: dict[str, Any]) -> list[str]:
    """Liệt kê mọi vi phạm. Rỗng nghĩa là hợp lệ."""
    problems: list[str] = []

    if report.get("schema_version") != SCHEMA_VERSION:
        return [f"schema_version phải là {SCHEMA_VERSION!r}, nhận {report.get('schema_version')!r}"]

    for key in _REQUIRED_TOP_LEVEL:
        if key not in report:
            problems.append(f"thiếu trường bắt buộc {key!r}")
    if problems:
        return problems

    if report["unit"] not in UNITS:
        problems.append(f"unit không hợp lệ: {report['unit']!r}")
    if report["decision_rule"] not in DECISION_RULES:
        problems.append(f"decision_rule không hợp lệ: {report['decision_rule']!r}")

    for key in _REQUIRED_DATASET:
        if key not in report["dataset"]:
            problems.append(f"dataset thiếu {key!r}")
    for key in _REQUIRED_SPLIT:
        if key not in report["split"]:
            problems.append(f"split thiếu {key!r}")
    for part in ("train", "validation", "test"):
        block = report["split"].get(part)
        if isinstance(block, dict):
            for key in _REQUIRED_SPLIT_PART:
                if key not in block:
                    problems.append(f"split.{part} thiếu {key!r}")
    for key in _REQUIRED_THRESHOLD:
        if key not in report["threshold"]:
            problems.append(f"threshold thiếu {key!r}")
    for key in _REQUIRED_PROVENANCE:
        if key not in report["provenance"]:
            problems.append(f"provenance thiếu {key!r}")

    headline = report["headline"]
    for metric in HEADLINE_METRICS:
        if metric not in headline:
            problems.append(f"headline thiếu {metric!r}")
        elif not isinstance(headline[metric], int | float):
            problems.append(f"headline.{metric} phải là số")

    budgets = [row.get("budget") for row in report["operating_points"]]
    if budgets != list(CANONICAL_BUDGETS):
        problems.append(f"operating_points phải dùng đúng dãy ngân sách chuẩn {list(CANONICAL_BUDGETS)}")

    # Ba chỗ được phép chứa số đo:
    #   headline         — con số chính thức, đúng một bộ
    #   diagnostics      — mọi thứ khác, đã bị cấm trích dẫn
    #   operating_points — precision/recall theo từng ngân sách là CẤU TRÚC của
    #                      chuẩn này, không phải số đo lạc chỗ. Hình dạng của nó
    #                      đã bị khoá bởi phép kiểm dãy ngân sách ở trên, nên
    #                      không giấu được gì vào đây.
    outside = {key: value for key, value in report.items() if key not in _METRIC_EXEMPT_KEYS}
    for stray in _stray_metric_paths(outside):
        problems.append(f"số đo nằm ngoài headline: {stray!r} — chuyển xuống diagnostics")

    return problems
