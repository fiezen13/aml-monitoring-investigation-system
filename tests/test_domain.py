"""Từ vựng nghiệp vụ dùng chung — src/domain.py.

Máy trạng thái ở đây là thứ API và worker cùng dựa vào để đồng ý với nhau về
"bước tiếp theo là gì". Sai ở một chỗ thì giao diện vẽ một tiến trình còn
worker chạy một tiến trình khác, và không có bài kiểm thử nào ở hai đầu phát
hiện được.
"""

from src.domain import (
    CASE_STATE_LABELS,
    INVESTIGATION_CHAIN,
    TERMINAL_STATES,
    TYPOLOGY_LABELS,
    next_state,
    state_label,
    typology_label,
)


def test_chain_starts_at_intake_and_ends_at_approval():
    assert INVESTIGATION_CHAIN[0] == "TiepNhanCanhBao"
    assert INVESTIGATION_CHAIN[-1] == "ChoNguoiPheDuyet"


def test_chain_has_no_duplicates():
    assert len(set(INVESTIGATION_CHAIN)) == len(INVESTIGATION_CHAIN)


def test_every_step_advances_by_exactly_one():
    for current, expected in zip(INVESTIGATION_CHAIN, INVESTIGATION_CHAIN[1:], strict=False):
        assert next_state(current) == expected


def test_chain_never_reaches_export_on_its_own():
    """NT3 — lối vào XuatHoSo phải là quyết định của con người.

    Không bước tự động nào được dẫn tới đó, kể cả từ ChoNguoiPheDuyet.
    """
    reachable = {next_state(state) for state in INVESTIGATION_CHAIN}
    assert "XuatHoSo" not in reachable
    assert next_state("ChoNguoiPheDuyet") is None


def test_terminal_states_have_no_next_step():
    for state in TERMINAL_STATES:
        assert next_state(state) is None


def test_unknown_state_has_no_next_step():
    assert next_state("TrangThaiBiaRa") is None


def test_every_state_in_the_chain_has_a_label():
    for state in INVESTIGATION_CHAIN:
        assert CASE_STATE_LABELS[state] != state


def test_all_twelve_states_are_labelled():
    """Đúng 12 trạng thái của ràng buộc CHECK trong db/init/001_schema.sql."""
    assert len(CASE_STATE_LABELS) == 12
    assert TERMINAL_STATES <= set(CASE_STATE_LABELS)


def test_label_falls_back_to_the_raw_code():
    assert state_label("KhongCoTrongDanhSach") == "KhongCoTrongDanhSach"
    assert typology_label("T99") == "T99"


def test_typology_codes_cover_t01_to_t10():
    assert set(TYPOLOGY_LABELS) == {f"T{n:02d}" for n in range(1, 11)}
