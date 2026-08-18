"""Chuẩn báo cáo benchmark.

Bộ test này khoá bốn quy tắc, và quy tắc thứ tư là quy tắc đắt giá nhất: cấm số
đo nằm ngoài ``headline``. Nó tồn tại vì một báo cáo cũ chứa chín giá trị ``f1``
ở chín đường dẫn khác nhau, và bộ đọc tự động lấy nhầm 0,1273 thay vì 0,3022.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmark.standard import (  # noqa: E402
    CANONICAL_BUDGETS,
    SCHEMA_VERSION,
    build_report,
    metrics_at_threshold,
    operating_points,
    validate_report,
)

RNG = np.random.default_rng(42)


def _labels_and_scores(n: int = 4000, positives: int = 40) -> tuple[np.ndarray, np.ndarray]:
    labels = np.zeros(n, dtype=np.int64)
    labels[:positives] = 1
    RNG.shuffle(labels)
    scores = RNG.random(n) * 0.5 + labels * 0.4
    return labels, scores


def _report(**overrides: Any) -> dict[str, Any]:
    labels, scores = _labels_and_scores()
    base = dict(
        component="mega_pna",
        unit="account_window",
        dataset={"name": "HI-Medium", "sha256": "a" * 64, "rows": 4000, "positives": 40},
        split={
            "protocol": "60/20/20 theo thời gian",
            "train": {"rows": 2400, "positives": 24},
            "validation": {"rows": 800, "positives": 8},
            "test": {"rows": 800, "positives": 8},
        },
        decision_rule="threshold_from_validation",
        threshold_value=0.6,
        threshold_selected_on="validation",
        labels=labels,
        scores=scores,
        provenance={"model_sha256": "b" * 64, "git_commit": "c" * 40},
    )
    base.update(overrides)
    return build_report(**base)


# ── Quy tắc 1: đơn vị phải khai và phải hợp lệ ─────────────────────────────


def test_unit_must_be_declared_and_valid() -> None:
    assert _report()["unit"] == "account_window"
    with pytest.raises(ValueError, match="unit phải thuộc"):
        _report(unit="ring")


def test_transaction_unit_is_allowed_for_paper_comparison() -> None:
    assert _report(unit="transaction")["unit"] == "transaction"


# ── Quy tắc 2: đúng một chỗ chứa con số chính thức ─────────────────────────


def test_headline_carries_the_full_metric_set() -> None:
    headline = _report()["headline"]
    for metric in ("f1", "precision", "recall", "pr_auc"):
        assert isinstance(headline[metric], float)
    assert set(headline["confusion_matrix"]) == {"tn", "fp", "fn", "tp"}


def test_stray_metric_outside_headline_is_rejected() -> None:
    """Đây là lỗi đã thực sự xảy ra, không phải giả định."""
    report = _report()
    report["selection"] = {"trials": [{"validation": {"f1": 0.1273}}]}
    problems = validate_report(report)
    assert any("selection.trials[0].validation.f1" in p for p in problems)


def test_stray_metric_is_allowed_inside_diagnostics() -> None:
    report = _report()
    report["diagnostics"] = {"per_seed": [{"f1": 0.30}, {"f1": 0.28}]}
    assert validate_report(report) == []


def test_all_four_metric_names_are_guarded_not_just_f1() -> None:
    for metric in ("f1", "precision", "recall", "pr_auc"):
        report = _report()
        report["scratch"] = {metric: 0.5}
        assert any(f"scratch.{metric}" in p for p in validate_report(report))


# ── Quy tắc 3: đủ ngữ cảnh ─────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["dataset", "split", "threshold", "provenance", "unit", "decision_rule"])
def test_missing_required_field_is_rejected(field: str) -> None:
    report = _report()
    del report[field]
    assert any(field in p for p in validate_report(report))


@pytest.mark.parametrize("part", ["train", "validation", "test"])
def test_split_must_state_rows_and_positives(part: str) -> None:
    report = _report()
    del report["split"][part]["positives"]
    assert any(f"split.{part}" in p for p in validate_report(report))


def test_dataset_must_carry_a_checksum() -> None:
    report = _report()
    del report["dataset"]["sha256"]
    assert any("sha256" in p for p in validate_report(report))


def test_validation_threshold_rule_requires_validation_source() -> None:
    """Không được khai 'chốt trên validation' rồi chốt ở chỗ khác."""
    with pytest.raises(ValueError, match="threshold_selected_on='validation'"):
        _report(decision_rule="threshold_from_validation", threshold_selected_on="test")


# ── Quy tắc 4: điểm vận hành cố định ───────────────────────────────────────


def test_operating_points_use_the_canonical_ladder() -> None:
    assert [row["budget"] for row in _report()["operating_points"]] == list(CANONICAL_BUDGETS)


def test_altered_ladder_is_rejected() -> None:
    report = _report()
    report["operating_points"] = [{"budget": 42}]
    assert any("dãy ngân sách chuẩn" in p for p in validate_report(report))


def test_budget_larger_than_dataset_is_marked_not_applicable() -> None:
    """Phải phân biệt 'không đo được' với 'đo ra 0'."""
    labels, scores = _labels_and_scores(n=300, positives=5)
    rows = {row["budget"]: row for row in operating_points(labels, scores)}
    assert rows[100]["applicable"] is True
    assert rows[5000]["applicable"] is False
    assert "precision" not in rows[5000]


def test_operating_points_are_monotonic_in_caught() -> None:
    labels, scores = _labels_and_scores()
    caught = [r["caught"] for r in operating_points(labels, scores) if r["applicable"]]
    assert caught == sorted(caught)


# ── Số đo ──────────────────────────────────────────────────────────────────


def test_metrics_match_a_hand_computed_case() -> None:
    labels = np.array([1, 1, 0, 0])
    scores = np.array([0.9, 0.4, 0.8, 0.1])
    m = metrics_at_threshold(labels, scores, 0.5)
    # dự đoán dương: 0.9 và 0.8 → tp=1, fp=1, fn=1, tn=1
    assert m["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert m["precision"] == pytest.approx(0.5)
    assert m["recall"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(0.5)


def test_empty_input_is_refused_not_silently_zero() -> None:
    with pytest.raises(ValueError, match="tập rỗng"):
        metrics_at_threshold(np.array([]), np.array([]), 0.5)


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(ValueError, match="cùng kích thước"):
        metrics_at_threshold(np.array([1, 0]), np.array([0.5]), 0.5)


# ── Dựng báo cáo ───────────────────────────────────────────────────────────


def test_built_report_is_valid_and_versioned() -> None:
    report = _report()
    assert report["schema_version"] == SCHEMA_VERSION
    assert validate_report(report) == []


def test_wrong_schema_version_short_circuits() -> None:
    report = _report()
    report["schema_version"] = "fin07.benchmark.v0"
    problems = validate_report(report)
    assert len(problems) == 1
    assert "schema_version" in problems[0]
