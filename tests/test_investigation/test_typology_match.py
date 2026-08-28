"""Ánh xạ nhóm hành vi phải đọc luật từ danh mục, không tự chế ra luật."""

from src.investigation.typology_match import (
    BEHAVIOR_SIGNAL_THRESHOLDS,
    FALLBACK_TYPOLOGY,
    match_typology,
    signals_from_behavior,
    signals_from_graph_motifs,
)


def test_no_signal_gives_an_explicit_fallback_not_a_silent_t02():
    """Đây là trạng thái của toàn bộ 6.541 cảnh báo hiện có.

    Trước đây chúng mang T02 mà không có chỗ nào nói mã ấy từ đâu ra. Giá trị
    không đổi — nhưng giờ phải tự khai là mặc định.
    """
    match = match_typology(set())

    assert match.typology_code == FALLBACK_TYPOLOGY
    assert match.is_fallback is True
    assert match.matched_required == ()
    assert "mặc định" in match.rationale


def test_a_full_required_signal_set_wins():
    match = match_typology({"fan_in", "fan_out", "short_dwell_time"})

    assert match.typology_code == "T04"
    assert match.is_fallback is False
    assert set(match.matched_required) == {"fan_in", "fan_out"}
    assert match.matched_supporting == ("short_dwell_time",)


def test_a_partial_required_signal_set_does_not_win():
    """Thiếu một tín hiệu bắt buộc là loại — không có 'gần đúng'."""
    match = match_typology({"fan_in"})

    assert match.typology_code != "T04"
    assert match.is_fallback is True


def test_more_required_signals_beat_fewer():
    """T04 cần hai tín hiệu, T05 cần một; có đủ cả thì T04 mô tả sát hơn."""
    match = match_typology({"fan_in", "fan_out", "rapid_outflow"})

    assert match.typology_code == "T04"


def test_the_ranking_is_deterministic_across_runs():
    signals = {"fan_in", "fan_out", "rapid_outflow", "directed_cycle", "network_flow"}
    codes = {match_typology(set(signals)).typology_code for _ in range(20)}

    assert len(codes) == 1


def test_t02_chung_minh_bang_phep_do_tien_di_qua_tai_khoan():
    """T02 chứng minh được bằng chính sổ giao dịch của tài khoản.

    Trước đây T02 đòi ``network_flow`` — tín hiệu của bộ phát hiện ĐỒ THỊ. Nhãn
    thì gắn cho MỘT tài khoản, nên phép đo cấp tài khoản (tiền vào rồi phần lớn
    đi tiếp) mới là thứ chứng minh được nó; mẫu hình đồ thị lùi về vai trò hỗ trợ.
    """
    match = match_typology({"pass_through", "network_flow", "rapid_outflow"})

    assert match.typology_code == "T02"
    assert match.is_fallback is False
    assert match.matched_required == ("pass_through",)
    assert "network_flow" in match.matched_supporting


def test_khong_chung_minh_duoc_nhom_nao_thi_khong_gan_bua_mot_nhom_co_that():
    """Mặc định vào T02 là gán cho tài khoản một hành vi chưa ai đo được.

    Đó chính là nguồn của mâu thuẫn trên màn hình: nhãn nói "Tài khoản trung
    chuyển" còn bản giải thích đo lại rồi nói "chưa khớp dấu hiệu nào".
    """
    match = match_typology({"new_counterparties"})

    assert match.typology_code == "T00"
    assert match.is_fallback is True


def test_behavior_signals_respect_the_configured_thresholds():
    above = BEHAVIOR_SIGNAL_THRESHOLDS["rapid_outflow_ratio"]
    assert signals_from_behavior({"rapid_outflow_ratio": above}) == {"rapid_outflow"}
    assert signals_from_behavior({"rapid_outflow_ratio": above - 0.01}) == set()


def test_a_missing_feature_produces_no_signal():
    """Đặc trưng vắng mặt không được suy thành 0 rồi thành tín hiệu."""
    assert signals_from_behavior({}) == set()
    assert signals_from_behavior({"rapid_outflow_ratio": None}) == set()


def test_graph_motifs_only_fire_when_the_detector_actually_hit():
    assert signals_from_graph_motifs({"cycle_hit": 0}) == set()
    assert signals_from_graph_motifs({"cycle_hit": 2}) == {"directed_cycle"}
    assert signals_from_graph_motifs({"gather_scatter_hit": 1}) == {"network_flow"}
    assert signals_from_graph_motifs({}) == set()


def test_booleans_are_not_read_as_numeric_signals():
    """``True`` lọt qua thành 1.0 sẽ tạo ra tín hiệu từ một cờ không liên quan."""
    assert signals_from_behavior({"rapid_outflow_ratio": True}) == set()
