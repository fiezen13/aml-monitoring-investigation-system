"""Bản SAR xuất ra PDF — khoá lại ba lỗi đã sửa của bản dựng cũ.

Không đọc lại nội dung file (không phụ thuộc thư viện bóc chữ từ PDF): kiểm ở
tầng hàm thuần, nơi ba lỗi thực sự nằm, cộng một lượt dựng đầy đủ để chắc rằng
bố cục không ném lỗi với dữ liệu biên (thiếu người lập, thiếu giao dịch).
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.api.sar_pdf import (
    _currency_totals,
    _split_amount,
    _trim_decimals,
    build_sar_pdf,
    evidence_label,
)


def _payload(**over):
    base = {
        "sar_id": "SAR-CASE-AUTO-fdab754f8b86731f4eec8224",
        "case_id": "CASE-AUTO-fdab754f8b86731f4eec8224",
        "alert_id": "ALT-MP-cf18b5fc2f8ea305",
        "suspicionType": "Gom vào và toả ra bất thường",
        "riskLevel": "CAO",
        "subject": {"customerId": "CUS-1", "accountKey": "159430:816572970"},
        "institution": {"name": "NGÂN HÀNG X", "unit": "Khối Tuân thủ", "recipient": "Cục PCRT"},
        "preparer": {"name": "Nguyễn Gia Bảo", "title": "Chuyên viên", "declared": True},
        "behaviourSummary": "Tài khoản gom tiền từ nhiều nguồn rồi phân tán nhanh.",
        "statements": [{"id": "ST-1", "text": "Nhận định A.", "evidenceIds": ["EV-a", "EV-b"]}],
        "evidence": [
            {"id": "EV-a", "type": "RISK_BREAKDOWN", "source": "detection_engine"},
            {"id": "EV-b", "type": "", "source": "feature_service"},
        ],
        "relatedTransactions": [
            {
                "transaction_id": "1",
                "time": "2022-09-10T15:20:00Z",
                "amount": "13087.82 Euro",
                "direction": "out",
                "from_account_key": "159430:816572970",
                "to_account_key": "13119:8098B74B0",
            }
        ],
        "network": {"subject": "159430:816572970", "nodes": ["159430:816572970"], "edges": []},
        "approval": None,
    }
    base.update(over)
    return base


def test_evidence_gets_a_business_name_never_the_internal_id():
    """Mã ``EV-…`` là khoá nội bộ; tài liệu gửi ra ngoài không được in nó."""
    assert evidence_label({"type": "RISK_BREAKDOWN"}) == "Cơ sở tính điểm rủi ro"
    # Không có `type` thì lấy theo nguồn sinh ra bằng chứng.
    assert evidence_label({"type": "", "source": "feature_service"}) == "Dấu hiệu hành vi tài khoản"
    # Nguồn lạ vẫn ra tên đọc được, không rơi về mã kỹ thuật.
    assert evidence_label({"source": "hệ thống lạ"}) == "Bằng chứng nghiệp vụ"


def test_amounts_are_split_from_their_currency():
    assert _split_amount("13087.82 US Dollar") == (13087.82, "13 087.82", "US Dollar")
    assert _split_amount(None)[0] is None


def test_money_is_never_summed_across_currencies():
    """Cộng Yên với Euro thành một con số là vô nghĩa trong báo cáo — phải tách."""
    txs = [
        {"amount": "100.00 Euro", "direction": "in"},
        {"amount": "50.00 Euro", "direction": "out"},
        {"amount": "900000.00 Yen", "direction": "out"},
    ]
    totals = _currency_totals(txs)
    assert set(totals) == {"Euro", "Yen"}
    assert totals["Euro"] == {"in": 100.0, "out": 50.0, "n": 2}
    assert totals["Yen"]["out"] == 900000.0
    # Yên có tổng lớn hơn nên đứng trước — bảng xếp theo quy mô.
    assert next(iter(totals)) == "Yen"


def test_pdf_builds_for_draft_and_final():
    now = datetime.now(UTC)
    draft = build_sar_pdf(_payload(), exported_by="Lê Anh Tuấn", exported_at=now, draft=True)
    final = build_sar_pdf(
        _payload(
            approval={
                "decision": "approved",
                "decided_by": "Trần Minh Quân",
                "reason": "Đủ căn cứ.",
                "requested_at": now,
                "decided_at": now,
            }
        ),
        exported_by="Lê Anh Tuấn",
        exported_at=now,
        draft=False,
    )
    assert draft[:4] == b"%PDF" and final[:4] == b"%PDF"
    # Bản nháp có dấu chìm nên nặng hơn bản chính; cả hai phải là tài liệu thật.
    assert len(draft) > 5000 and len(final) > 5000


def test_pdf_builds_when_preparer_and_transactions_are_missing():
    """Hồ sơ chưa khai người lập / chưa có giao dịch vẫn phải xuất được."""
    data = _payload(preparer={"name": "", "declared": False}, relatedTransactions=[], statements=[])
    out = build_sar_pdf(data, exported_by="Lê Anh Tuấn", exported_at=datetime.now(UTC), draft=True)
    assert out[:4] == b"%PDF"


def test_nhan_can_bo_sung_khong_bam_vinh_vien():
    """Nhãn NEEDS_INFO phải nhường chỗ khi chuyên viên đã sửa và kiểm chứng lại.

    Nút "Gửi phê duyệt" của giao diện chỉ mở với VALIDATION_PASSED. Nếu nhãn
    NEEDS_INFO bám theo quyết định `more_info` gần nhất bất kể bản nháp đã sang
    'verified', hồ sơ bị trả lại sẽ không bao giờ gửi lại được bằng giao diện
    (phát hiện khi chạy thử luồng trên production 2026-08-27).
    """
    from src.api.routes import _sar_display_status

    assert _sar_display_status("rejected", "more_info") == "NEEDS_INFO"  # vừa bị trả lại
    assert _sar_display_status("drafting", "more_info") == "DRAFT"  # chuyên viên đang sửa
    assert _sar_display_status("verified", "more_info") == "VALIDATION_PASSED"  # gửi lại được
    assert _sar_display_status("rejected", "rejected") == "REJECTED"  # từ chối hẳn
    assert _sar_display_status("submitted_for_approval", "pending") == "PENDING_REVIEW"


def test_tach_so_tien_da_dinh_dang_san_tu_may_chu():
    """Máy chủ nay trả "10 924.92 US Dollar"; PDF phải đọc đúng phần số.

    Trước khi sửa, biểu thức dừng ở khoảng trắng đầu tiên nên số thành 10 còn
    "924.92 US Dollar" bị coi là TÊN LOẠI TIỀN — bảng tổng hợp theo loại tiền
    của bản PDF hiện ra một cột toàn "873.91 US Dollar", "396.45 US Dollar".
    """
    value, text_value, currency = _split_amount("10 924.92 US Dollar")

    assert value == 10924.92
    assert currency == "US Dollar"
    assert text_value == "10 924.92"


def test_gop_theo_loai_tien_khong_bi_vo_boi_dau_tach_hang_nghin():
    txs = [
        {"amount": "10 924.92 US Dollar", "direction": "out"},
        {"amount": "1 000.00 US Dollar", "direction": "in"},
    ]
    totals = _currency_totals(txs)

    assert list(totals) == ["US Dollar"]
    assert totals["US Dollar"] == {"in": 1000.0, "out": 10924.92, "n": 2}


def test_khong_lam_vo_so_viet_kieu_viet_nam():
    """ "97.103,33 USD" từng bị cắt thành "97.10,33 USD" ngay trên bản chính thức.

    Nhóm hàng nghìn luôn đúng ba chữ số, nên chỉ đuôi từ bốn chữ số trở lên mới
    là số thập phân dài của kiểu NUMERIC.
    """
    assert _trim_decimals("97.103,33 USD") == "97.103,33 USD"
    assert _trim_decimals("1.083.674,33 Ruble") == "1.083.674,33 Ruble"
    assert _trim_decimals("đạt 100.000 điểm") == "đạt 100.000 điểm"


def test_van_rut_gon_duoc_duoi_numeric_that():
    assert _trim_decimals("1083674.330000000000000000") == "1 083 674.33"
    assert _trim_decimals("giá trị 5016.8000 EUR") == "giá trị 5 016.80 EUR"


def test_khoi_doi_tuong_khong_in_gia_tri_tho_ra_ho_so_gui_ngoai() -> None:
    """Hồ sơ gửi cơ quan quản lý không được in `organisation` hay `medium`.

    API cố ý giữ giá trị thô vì mã còn so sánh trên chúng; việc Việt hoá là
    của lớp xuất bản, và đây là nơi khoá lại điều đó.
    """
    from src.api.sar_pdf import _subject_value

    assert _subject_value("organisation") == "Tổ chức"
    assert _subject_value("individual") == "Cá nhân"
    assert _subject_value("medium") == "Trung bình"


def test_thieu_kyc_thi_khong_lo_ten_bo_du_lieu_noi_bo() -> None:
    """Nghề nghiệp khi thiếu KYC được ghi kèm tên kho dữ liệu gốc."""
    from src.api.sar_pdf import _subject_value

    assert _subject_value("KYC unavailable - IBM AML HI-Medium") == "Chưa có thông tin KYC"
    assert _subject_value("KYC unavailable - SAML-D") == "Chưa có thông tin KYC"


def test_gia_tri_that_thi_giu_nguyen() -> None:
    from src.api.sar_pdf import _subject_value

    assert _subject_value("Kỹ sư phần mềm") == "Kỹ sư phần mềm"
