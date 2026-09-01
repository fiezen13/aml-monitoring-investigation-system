"""Migrate Original Elliptic: artifact hợp lệ + KHÔNG rò nhãn vào RF (§27, §45)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

OUT = Path(__file__).resolve().parents[2] / "data/models/bitcoin_elliptic"

pytestmark = pytest.mark.skipif(
    not (OUT / "selected_features.json").exists(),
    reason="Chưa train Elliptic gốc (chạy scripts/train_elliptic_rf.py).",
)


def _load(name):
    return json.loads((OUT / name).read_text())


def test_dac_trung_rf_khong_chua_nhan_hay_do_thi():
    """Đầu vào RF chỉ là đặc trưng Elliptic — không nhãn/láng giềng/đồ thị (chống rò)."""
    feats = _load("selected_features.json")
    assert len(feats) == 166
    for f in feats:
        low = f.lower()
        for banned in ("label", "class", "illicit", "neighbor", "known", "graph"):
            assert banned not in low, f"nghi rò nhãn: {f}"


def test_registry_khop_do_dai_dau_vao_model():
    reg = _load("feature_registry.json")
    feats = _load("selected_features.json")
    assert reg["n_features"] == len(feats) == 166
    assert sum(1 for f in reg["features"] if f["semantic_status"] == "RECOVERED_AND_VALIDATED") == 151


def test_metrics_uu_tien_illicit_hop_ly():
    m = _load("evaluation_metrics.json")
    for k in ("precision_illicit", "recall_illicit", "f1_illicit", "roc_auc", "pr_auc"):
        assert 0.0 <= m[k] <= 1.0
    # Split theo thời gian, không random.
    assert m["train_last_timestep"] == 34 and m["n_test"] > 0


def test_percentile_dist_tinh_tu_train_khong_ro_test():
    """feature_distribution phải phủ đúng 166 đặc trưng (tính từ train)."""
    dist = _load("feature_distribution.json")
    feats = _load("selected_features.json")
    assert set(dist.keys()) == set(feats)
    for stats in dist.values():
        assert "median_illicit" in stats and "median_licit" in stats and "percentiles" in stats
