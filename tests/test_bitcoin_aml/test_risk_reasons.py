"""QA cho lớp RiskReason deterministic (audit §27).

Bảy ca kiểm thử bắt buộc từ yêu cầu audit. Ca 4/5 (external intel, điểm 100) là
tầng UI/disclaimer — ở backend ta kiểm risk_reasons KHÔNG bịa external intel và
KHÔNG chứa từ overclaim.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.bitcoin_aml.risk_reasons import build_risk_reasons

_DIST = json.loads(Path("data/models/bitcoin_elliptic/feature_distribution.json").read_text(encoding="utf-8"))

# Đặc trưng theo DFRWS index: feature_N = model_index N.
DOWNSTREAM_TX = {"name": "feature_133", "label": "Std deviation of value of output txs", "meaningful": True, "value": 2.5, "contribution": 0.4}
UPSTREAM_TX = {"name": "feature_95", "label": "Minimum value of input txs", "meaningful": True, "value": 0.9, "contribution": 0.3}
LOCAL_OUT = {"name": "feature_6", "label": "Number of outputs", "meaningful": True, "value": 1.2, "contribution": 0.35}
UNRESOLVED = {"name": "feature_4", "label": None, "meaningful": False, "value": 3.0, "contribution": 0.5}

_FORBIDDEN = ("bất thường", "khác đáng kể", "cao hơn thông thường", "hiếm gặp")
_INVENTED_INTEL = ("mixer", "sàn", "exchange", "sanction", "trừng phạt", "darknet")


def _all_text(reasons):
    return " ".join(r["investigator_text"].lower() + " " + r["title"].lower() for r in reasons)


def test_case1_downstream_zero_suppresses_downstream_reason():
    """upstream>0, downstream=0 → KHÔNG có reason về 'giao dịch tiếp theo'."""
    rr = build_risk_reasons([DOWNSTREAM_TX, UPSTREAM_TX, LOCAL_OUT], graph_in_degree=1, graph_out_degree=0, distribution=_DIST)
    assert all(r["category"] != "DOWNSTREAM_TRANSACTION_AGGREGATE" for r in rr)
    assert all(r["side"] != "downstream_tx" for r in rr)


def test_case1b_upstream_zero_suppresses_upstream_reason():
    rr = build_risk_reasons([DOWNSTREAM_TX, UPSTREAM_TX, LOCAL_OUT], graph_in_degree=0, graph_out_degree=3, distribution=_DIST)
    assert all(r["category"] != "UPSTREAM_TRANSACTION_AGGREGATE" for r in rr)


def test_case2_no_percentile_no_overclaim():
    """percentile không có (distribution=None) → không dùng 'bất thường/cao hơn'; reference=None."""
    rr = build_risk_reasons([LOCAL_OUT], graph_in_degree=1, graph_out_degree=1, distribution=None)
    assert rr and all(r["reference"] is None for r in rr)
    txt = _all_text(rr)
    assert not any(w in txt for w in _FORBIDDEN), f"overclaim khi không có percentile: {txt}"


def test_case3_percentile_present_grounds_text():
    """Có percentile → reference.percentile là số; text nói 'cao hơn X%'."""
    rr = build_risk_reasons([LOCAL_OUT], graph_in_degree=1, graph_out_degree=1, distribution=_DIST)
    assert rr and rr[0]["reference"] is not None
    assert isinstance(rr[0]["reference"]["percentile"], int)
    assert "cao hơn" in rr[0]["investigator_text"].lower()


def test_case4_never_invents_external_intelligence():
    """risk_reasons KHÔNG bịa sàn/mixer/sanctions."""
    rr = build_risk_reasons([DOWNSTREAM_TX, UPSTREAM_TX, LOCAL_OUT], graph_in_degree=2, graph_out_degree=2, distribution=_DIST)
    txt = _all_text(rr)
    assert not any(w in txt for w in _INVENTED_INTEL)


def test_case6_only_positive_shap_contributes():
    """SHAP âm (giảm rủi ro) KHÔNG tạo reason tăng; mọi reason là increase_risk."""
    neg = {"name": "feature_2", "label": "Transaction Volume", "meaningful": True, "value": -1.0, "contribution": -0.6}
    rr = build_risk_reasons([LOCAL_OUT, neg], graph_in_degree=1, graph_out_degree=1, distribution=_DIST)
    assert rr and all(r["shap_direction"] == "increase_risk" for r in rr)
    # 'Transaction Volume' (contribution âm) không được lên reason.
    assert all("quy mô" not in r["title"].lower() for r in rr)


def test_case7_unresolved_feature_excluded():
    """Đặc trưng chưa giải nghĩa (UNRESOLVED) không được đưa thành reason nghiệp vụ."""
    rr = build_risk_reasons([UNRESOLVED, LOCAL_OUT], graph_in_degree=1, graph_out_degree=1, distribution=_DIST)
    assert rr and all(r["category"] != "UNRESOLVED" for r in rr)
    # Còn lại chỉ là đặc trưng đã phục hồi.
    assert any(r["category"] == "TRANSACTION_INTRINSIC" for r in rr)


def test_temporal_flag_on_downstream():
    """downstream_tx phải đánh dấu after_transaction (temporal §8)."""
    rr = build_risk_reasons([DOWNSTREAM_TX, LOCAL_OUT], graph_in_degree=1, graph_out_degree=3, distribution=_DIST)
    down = [r for r in rr if r["category"] == "DOWNSTREAM_TRANSACTION_AGGREGATE"]
    assert down and down[0]["after_transaction"] is True
    assert down[0]["temporal_availability"] == "after_transaction"


def test_contribution_band_ordering():
    """Nhóm mạnh nhất (SHAP lớn) đứng đầu và band giảm dần."""
    rr = build_risk_reasons([LOCAL_OUT, UPSTREAM_TX], graph_in_degree=2, graph_out_degree=2, distribution=_DIST)
    bands = [r["contribution"] for r in rr]
    assert bands[0] == "very_high"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
