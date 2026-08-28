"""Chất lượng ĐỌC của bản giải thích: logic, dễ hiểu, trực quan.

Bộ kiểm ở `test_consistency.py` bắt câu SAI. Bộ này bắt câu ĐÚNG mà đọc không
vào: số không có đơn vị, ngày định dạng máy, cùng một phép đo hiện hai con số,
ngoặc lồng ba tầng, mã nội bộ, dữ kiện xếp lộn mạch.

Mỗi luật ở đây là một khiếm khuyết ĐÃ ĐO ĐƯỢC trên bản giải thích thật của
production ngày 27/08/2026, không phải sở thích trình bày.
"""

from __future__ import annotations

import re

import pytest

from src.investigation.agents import ExplanationAgent
from tests.test_investigation.test_agents import (
    _typology,
    alert,
    behavior_evidence,
    risk_evidence,
)


def _explain(**observed_overrides):
    return ExplanationAgent._deterministic(
        alert("ml"),
        [
            risk_evidence("ml"),
            behavior_evidence(**observed_overrides),
            _typology("T04", "Gom vào rồi toả ra bất thường", ["fan_in", "fan_out"], ["short_dwell_time"]),
        ],
    )


def _all_prose(explanation) -> str:
    return " ".join([explanation.summary, *explanation.facts, *explanation.inferences])


def test_khong_con_ngay_dinh_dang_may() -> None:
    """"2022-09-16" là định dạng máy; người Việt đọc "16/09/2022"."""
    prose = _all_prose(_explain())

    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", prose), "còn ngày ISO trong câu chữ"
    assert re.search(r"\b\d{2}/\d{2}/\d{4}\b", prose), "phải có ngày dạng dd/mm/yyyy"


def test_so_tien_co_tach_hang_nghin() -> None:
    """"41000.50" là chín ký tự phải đếm bằng mắt mới biết là bao nhiêu."""
    prose = _all_prose(_explain())

    assert "41 000.50" in prose
    assert "41000.50" not in prose


def test_so_tien_luon_di_kem_loai_tien() -> None:
    """Một số tiền không có đơn vị là một con số vô nghĩa."""
    explanation = _explain()

    window_fact = next(fact for fact in explanation.facts if fact.startswith("Trong khoảng"))
    assert "USD" in window_fact


def test_cua_so_nhieu_loai_tien_thi_khong_cong_gop_thanh_mot_tong() -> None:
    """Cộng đô-la với yên rồi in một con số trần là phép tính vô nghĩa.

    Đây là câu đã lọt lên màn hình thật: "tài khoản nhận 30 752 077.04 từ 2 đối
    tác" — tổng của USD cộng Yen, không đơn vị.
    """
    explanation = _explain(currency=None)

    assert "không cộng gộp thành một tổng" in explanation.summary
    # Không có con số tiền trần nào đứng một mình trong câu tóm tắt.
    assert "41 000.50" not in explanation.summary


def test_cung_mot_phep_do_chi_hien_mot_con_so() -> None:
    """Tóm tắt in "1.2 giờ" còn dữ kiện in "1.25 giờ" thì người đọc mất tin."""
    explanation = _explain()
    prose = _all_prose(explanation)

    dwell_values = set(re.findall(r"(\d+\.\d+) giờ", prose))
    assert len(dwell_values) <= 1, f"thời gian giữ tiền hiện nhiều con số khác nhau: {dwell_values}"

    rapid_values = set(re.findall(r"(\d+(?:\.\d+)?)% tổng tiền ra", prose))
    summary_rapid = set(re.findall(r"(\d+(?:\.\d+)?)% số tiền ra", explanation.summary))
    assert not (rapid_values ^ summary_rapid) or not summary_rapid, (
        f"tỉ lệ tiền ra nhanh hiện hai kiểu: dữ kiện {rapid_values}, tóm tắt {summary_rapid}"
    )


def test_khong_co_ngoac_long_qua_mot_tang() -> None:
    """Ngoặc trong ngoặc trong ngoặc là câu không đọc được."""
    for sentence in _all_prose(_explain()).split(". "):
        depth = maximum = 0
        for char in sentence:
            if char == "(":
                depth += 1
                maximum = max(maximum, depth)
            elif char == ")":
                depth = max(0, depth - 1)
        assert maximum <= 1, f"ngoặc lồng {maximum} tầng: {sentence[:120]}"


def test_khong_co_dau_cach_thua_truoc_dau_cau() -> None:
    prose = _all_prose(_explain())

    assert " ." not in prose and " ," not in prose
    assert "  " not in prose


def test_khong_lo_ma_noi_bo_ra_cau_chu() -> None:
    """Tên nhánh kỹ thuật và mã enum không được lọt lên màn hình nghiệp vụ."""
    prose = _all_prose(_explain()).lower()

    for token in ("mega_pna", "geo_rule", "feature_service", "typology_registry", "isolation forest"):
        assert token not in prose, f"còn mã nội bộ: {token}"


def test_du_kien_ke_hanh_vi_truoc_cach_cham_diem() -> None:
    """Người mở cảnh báo cần biết tài khoản đã LÀM GÌ trước, cách cộng điểm sau."""
    facts = _explain().facts

    behaviour = next(i for i, fact in enumerate(facts) if fact.startswith("Trong khoảng"))
    scoring = next(i for i, fact in enumerate(facts) if "Hệ thống chấm mức rủi ro" in fact)
    assert behaviour < scoring, "dữ kiện chấm điểm đang đứng trước dữ kiện hành vi"


def test_khong_co_du_kien_trung_lap() -> None:
    facts = _explain().facts

    assert len(facts) == len(set(facts)), "có dữ kiện lặp lại nguyên văn"


def test_khong_noi_hai_lan_cung_mot_con_so() -> None:
    """"đạt 92 điểm — yếu tố này đóng góp 91.76 điểm" là một câu nói hai lần."""
    from src.investigation.agents import _label_already_states

    assert _label_already_states("Giao dịch rủi ro nhất trong kỳ đạt 92 điểm rủi ro", 91.76) is True
    assert _label_already_states("3 giao dịch đổi loại tiền", 12.5) is False


@pytest.mark.parametrize("sources,destinations", [(2, 2), (6, 8)])
def test_chu_nhieu_chi_dung_khi_vuot_dung_nguong_do_duoc(sources: int, destinations: int) -> None:
    """Một trang không được dùng hai định nghĩa cho chữ "nhiều".

    Bản trước: văn xuôi gọi 3 nguồn là "nhiều nguồn", còn dòng dưới ghi "chưa đạt
    ngưỡng nhiều nguồn dồn vào (3 đối tác gửi, ngưỡng ≥ 5)".
    """
    from src.investigation.agents import FAN_COUNTERPARTIES

    explanation = _explain(
        unique_in_counterparties=sources,
        unique_out_counterparties=destinations,
        rapid_outflow_percent=10.0,
        rapid_outflow_amount=100.0,
    )
    summary = explanation.summary

    if sources < FAN_COUNTERPARTIES:
        assert "nhiều nguồn" not in summary, "gọi là nhiều nguồn trong khi số đo dưới ngưỡng"
    if destinations < FAN_COUNTERPARTIES:
        assert "nhiều đích" not in summary, "gọi là nhiều đích trong khi số đo dưới ngưỡng"


def test_cau_khong_dai_qua_muc_doc_duoc() -> None:
    """Câu dài quá thì người đọc bỏ qua, và bỏ qua thì bản giải thích vô dụng."""
    for fact in _explain().facts:
        for sentence in fact.split(". "):
            assert len(sentence) <= 320, f"câu dài {len(sentence)} ký tự: {sentence[:100]}…"


def test_ty_le_khac_khong_khong_bi_lam_tron_thanh_khong() -> None:
    """"332.79 được chuyển đi… chiếm 0% tổng tiền ra" là câu tự mâu thuẫn."""
    from src.investigation.agents import _percent

    assert _percent(0.34) == "dưới 1"
    assert _percent(0.0) == "0"
    assert _percent(92.73) == "93"
    # Tỉ lệ được làm tròn 2 chữ số ngay từ nguồn: một lượng khác 0 nhưng rất nhỏ
    # cho ra đúng 0.0. Nơi gọi biết lượng gốc khác 0 thì phải nói "dưới 1".
    assert _percent(0.0, of_nonzero=True) == "dưới 1"


def test_yeu_to_dem_bang_khong_viet_thanh_cau_tieng_viet() -> None:
    """Một dòng "0 giao dịch tiền mặt." đọc như dòng rác."""
    from src.investigation.agents import _absence_wording

    assert _absence_wording("0 giao dịch tiền mặt") == "Kỳ chấm điểm không ghi nhận giao dịch tiền mặt"
    assert _absence_wording("4 giao dịch tiền mặt") == "4 giao dịch tiền mặt"


def test_ve_dong_tien_rong_khong_viet_thanh_khong_phay_khong() -> None:
    """"nhận 0.00 US Dollar từ 0 đối tác" là cách máy nói, không phải tiếng Việt."""
    explanation = _explain(inflow_amount=0.0, incoming_count=0, unique_in_counterparties=0, rapid_outflow_amount=0.0)

    assert "không nhận giao dịch nào" in explanation.summary
    assert "0.00" not in explanation.summary


def test_moi_phep_do_phai_neu_ro_pham_vi_cua_no() -> None:
    """Hai phép đo khác phạm vi không được gọi cùng một tên.

    Đây là nguyên nhân phần lớn phiên điều tra nhánh địa lý không chạy xong (đo
    27/08/2026): bản giải thích nói "hành lang UK → Nigeria" đọc từ sổ giao dịch,
    còn phần phân rã điểm ghi hành lang UK → Albania của ô chấm điểm. Tác tử
    phản biện thấy hai câu đá nhau và đánh trượt — nó bắt đúng.
    """
    from src.investigation.agents import _absence_wording

    # Câu về sổ giao dịch phải tự nói rõ nó là quan sát trên sổ.
    import inspect

    from src.investigation.agents import ExplanationAgent

    source = inspect.getsource(ExplanationAgent._deterministic)
    assert "Trong sổ giao dịch đính kèm" in source
    assert "không phải hành lang mà bộ luật địa lý" in source

    # Câu "không có ..." phải gắn với kỳ chấm điểm, không phải khẳng định tuyệt đối.
    assert _absence_wording("0 giao dịch tiền mặt").startswith("Kỳ chấm điểm")


def test_cua_so_nhieu_loai_tien_thi_khong_co_ty_le_nao_tinh_tren_so_tien() -> None:
    """Một đoạn không được vừa từ chối cộng gộp vừa cộng gộp.

    Bản thật trên production: câu tóm tắt nói "Các giao dịch thuộc nhiều loại
    tiền khác nhau nên không cộng gộp thành một tổng" rồi ghi ngay "nhận
    4 932.33 rồi chuyển đi 4 694.59 — 95% số tiền nhận được đã đi tiếp" — hai
    con số ấy chính là USD cộng EUR.
    """
    explanation = _explain(currency=None)
    prose = _all_prose(explanation)

    assert "không cộng gộp thành một tổng" in explanation.summary
    for cum_tu in ("% số tiền nhận được đã đi tiếp", "% tiền ra đi nhanh", "% số tiền ra rời đi"):
        assert cum_tu not in prose, f"vẫn còn tỉ lệ tính trên số tiền: {cum_tu}"


def test_cua_so_mot_loai_tien_van_giu_du_cac_ty_le() -> None:
    """Chặn theo loại tiền không được làm mất phép đo của cửa sổ bình thường."""
    prose = _all_prose(_explain())

    assert "% tiền ra đi nhanh" in prose or "% số tiền ra rời đi" in prose


def test_moi_so_tien_deu_di_kem_loai_tien() -> None:
    """Một con số trần không nói được nó là bốn nghìn đô hay bốn nghìn yên."""
    import re

    prose = _all_prose(_explain())
    # Mọi số có phần thập phân hai chữ số (tức là một số tiền) phải có đơn vị
    # ngay sau, hoặc là một tỉ lệ/thời lượng có đơn vị riêng.
    for match in re.finditer(r"\d[\d ]*\.\d\d(?!\d)", prose):
        duoi = prose[match.end() : match.end() + 14]
        assert re.match(r"\s*(USD|Euro|Yen|UK pounds|Rupee|[A-Z][a-zà-ỹ]+)|\s*(giờ|%|điểm)", duoi), (
            f"số tiền không có đơn vị: …{prose[max(0, match.start() - 40) : match.end() + 20]}…"
        )
