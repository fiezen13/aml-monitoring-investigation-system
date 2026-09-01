"""Bản kể đồ thị: đo tất định, rồi mới diễn đạt.

Màn hình đồ thị vẽ đúng nhưng không giải thích gì. Các test này khoá phần đo —
tầng mà mọi con số sinh ra — và bản dự phòng tất định, thứ đảm bảo màn hình
không bao giờ trống dù mô hình có hỏng.
"""

from __future__ import annotations

from src.investigation.graph_narrative import GraphNarrative, fallback_narrative


def _reading(**overrides: object) -> dict:
    base = {
        "account_key": "001:CENTER",
        "window_start": "2022-08-29T00:00:00Z",
        "window_end": "2022-09-28T00:00:00Z",
        "window_days": 30,
        "currency": "Euro",
        "inflow_amount": 19967.46,
        "outflow_amount": 712081.05,
        "incoming_transactions": 9,
        "outgoing_transactions": 30,
        "unique_senders": 3,
        "unique_receivers": 1,
        "top_senders": [
            {"account_key": "002:A", "transactions": 4, "amount": 10000.0, "currency": "Euro"},
            {"account_key": "003:B", "transactions": 3, "amount": 6000.0, "currency": "Euro"},
            {"account_key": "004:C", "transactions": 2, "amount": 3967.46, "currency": "Euro"},
        ],
        "top_receivers": [{"account_key": "099:SINK", "transactions": 30, "amount": 712081.05, "currency": "Euro"}],
        "intermediaries": [],
        "cycles": [],
    }
    base.update(overrides)
    return base


def test_a_funnel_is_named_as_a_collection_point():
    """3 nguồn dồn về 1 đích: đây là câu quan trọng nhất, không được thiếu."""
    narrative = fallback_narrative(_reading())
    assert isinstance(narrative, GraphNarrative)
    joined = " ".join(narrative.why_suspicious)
    assert "phễu" in joined
    assert "điểm gom tiền" in joined


def test_an_intermediary_that_forwards_money_is_called_out():
    reading = _reading(
        intermediaries=[
            {"account_key": "099:SINK", "onward_accounts": 5, "onward_transactions": 12, "onward_amount": 700000.0}
        ]
    )
    narrative = fallback_narrative(reading)
    assert "099:SINK" in narrative.flow_out
    assert "chuyển tiếp" in narrative.flow_out
    assert any("đứng giữa" in line for line in narrative.why_suspicious)


def test_a_detected_cycle_is_read_as_money_coming_back():
    reading = _reading(cycles=[{"length": 4, "accounts": ["001:CENTER", "a", "b", "c"], "duration_hours": 30}])
    narrative = fallback_narrative(reading)
    assert any("chạy vòng" in line for line in narrative.why_suspicious)


def test_the_reading_guide_points_by_account_name_not_screen_position():
    """Đồ thị sắp xếp lại mỗi lần vẽ, nên "cụm bên trái" là câu sai.

    Hướng dẫn phải chỉ đường bằng tên tài khoản — thứ người đọc bấm tìm được.
    """
    narrative = fallback_narrative(_reading())
    guide = " ".join(narrative.how_to_read)
    assert "001:CENTER" in guide
    assert "099:SINK" in guide
    for banned in ("bên trái", "bên phải", "phía trên", "góc"):
        assert banned not in guide


def test_receive_only_account_is_not_described_as_a_funnel():
    reading = _reading(
        outflow_amount=0.0, outgoing_transactions=0, unique_receivers=0, top_receivers=[], intermediaries=[]
    )
    narrative = fallback_narrative(reading)
    assert "giữ lại" in narrative.flow_out
    assert not any("phễu" in line for line in narrative.why_suspicious)


def test_no_unusual_shape_says_so_plainly_instead_of_staying_silent():
    reading = _reading(
        inflow_amount=5000.0,
        outflow_amount=4000.0,
        unique_senders=1,
        unique_receivers=1,
        top_senders=[{"account_key": "002:A", "transactions": 1, "amount": 5000.0, "currency": "Euro"}],
    )
    narrative = fallback_narrative(reading)
    assert narrative.why_suspicious
    assert any("chưa thấy" in line.lower() for line in narrative.why_suspicious)
