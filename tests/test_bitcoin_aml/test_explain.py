"""Giải thích Bitcoin phải đời thường, trung thực, không bịa mẫu hình."""

from __future__ import annotations

from src.bitcoin_aml.explain import build_explanation
from src.bitcoin_aml.schemas import Prediction


def _pred(score: float, label: str) -> Prediction:
    conf = score if label == "illicit" else 1.0 - score
    return Prediction(label=label, risk_score=score, confidence=conf)


def test_gathering_shape_is_described_in_plain_language():
    values = {"num_input_addresses": 8.0, "num_output_addresses": 2.0, "size": 1257.0, "fees": 0.0002}
    imp = {"num_input_addresses": 0.1, "size": 0.05, "fees": 0.04}
    ex = build_explanation(values, imp, _pred(0.61, "illicit"))
    assert "nghi ngờ" in ex.headline and "61" in ex.headline
    assert any("gom tiền từ 8 địa chỉ" in r for r in ex.reasons)
    # Không kết luận, chỉ nghi vấn.
    assert "cần chuyên viên rà soát" in ex.headline


def test_never_invents_laundering_pattern_names():
    values = {"num_input_addresses": 8.0, "num_output_addresses": 2.0, "size": 500.0}
    ex = build_explanation(values, {}, _pred(0.9, "illicit"))
    blob = " ".join([ex.headline, *ex.reasons]).lower()
    # KHÔNG được bịa tên mẫu hình mà Elliptic++ không cung cấp.
    for banned in ("peel", "trộn coin", "mixer", "layering", "chia chuỗi"):
        assert banned not in blob
    # Nhưng caveat NÓI RÕ là không có nhãn mẫu hình.
    assert "mẫu hình" in ex.caveat


def test_only_meaningful_features_are_named_never_anonymous_ones():
    values = {"Local_feature_53": 1.24, "Aggregate_feature_10": -0.3, "fees": 0.0002}
    imp = {"Local_feature_53": 0.9, "Aggregate_feature_10": 0.8, "fees": 0.01}
    ex = build_explanation(values, imp, _pred(0.7, "illicit"))
    blob = " ".join(ex.reasons)
    # Đặc trưng ẩn danh KHÔNG bao giờ lên câu chữ...
    assert "Local_feature" not in blob and "Aggregate_feature" not in blob
    # ...và được đếm gộp trong caveat.
    assert "2 đặc trưng" in ex.caveat


def test_licit_transaction_reads_as_low_suspicion():
    values = {"num_input_addresses": 3.0, "num_output_addresses": 2.0, "size": 853.0}
    ex = build_explanation(values, {}, _pred(0.0, "licit"))
    assert "hợp pháp" in ex.headline
    assert "0/100" in ex.headline
