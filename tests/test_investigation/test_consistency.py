"""Bộ kiểm tính nhất quán logic của bản giải thích.

Mỗi ca là một câu "có dẫn nguồn, số có thật, ghép lại thì vô lý" — loại lỗi mà
bộ kiểm ở mức token không thấy, và cũng là loại làm người đọc mất niềm tin
nhanh nhất.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.investigation import consistency
from src.investigation.schemas import EvidenceEnvelope, EvidenceIntegrity, EvidenceType

ACCOUNT = "001:A"
FAN = 5


def _evidence(evidence_type: EvidenceType, payload: dict, *, source: str) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=f"EV-{evidence_type.value}",
        type=evidence_type,
        source=source,
        account_key=ACCOUNT,
        payload=payload,
        created_at=datetime.now(UTC),
        integrity=EvidenceIntegrity(source_system=source, source_record_ids=["r1"], content_hash="a" * 64),
    )


def _behaviour(**overrides) -> EvidenceEnvelope:
    observed = {
        "window_start": "2022-08-25T00:00:00Z",
        "window_end": "2022-09-01T00:00:00Z",
        "window_days": 30,
        "currency": "USD",
        "inflow_amount": 41000.5,
        "outflow_amount": 39900.25,
        "incoming_count": 9,
        "outgoing_count": 12,
        "unique_in_counterparties": 2,
        "unique_out_counterparties": 3,
        "new_counterparties": 4,
        "rapid_outflow_percent": 92.73,
        "rapid_window_hours": 2,
        "median_dwell_hours": 1.25,
        "active_days": 3,
        **overrides,
    }
    return _evidence(EvidenceType.BEHAVIOR_FEATURE, {"observed": observed}, source="feature_service")


def _ledger(*records: dict) -> EvidenceEnvelope:
    return _evidence(
        EvidenceType.TRANSACTION,
        {"items": list(records), "limit": 50, "truncated": False},
        source="transaction_service",
    )


def _tx(tid: str, *, outgoing: bool, amount: float) -> dict:
    return {
        "transaction_id": tid,
        "source": ACCOUNT if outgoing else "002:B",
        "destination": "002:B" if outgoing else ACCOUNT,
        "timestamp": "2022-08-28T10:00:00Z",
        "amount": amount,
        "currency": "USD",
        "payment_format": "ACH",
    }


def _check(claim: str, evidence: list[EvidenceEnvelope]) -> list[consistency.ConsistencyIssue]:
    return consistency.check([claim], evidence, account_key=ACCOUNT, fan_threshold=FAN)


def test_phu_dinh_dong_tien_trai_voi_so_lieu_bi_bat() -> None:
    issues = _check("Trong cửa sổ quan sát, tài khoản không nhận đồng nào.", [_behaviour()])

    assert [i.rule for i in issues] == ["FLOW_CONTRADICTION"]
    assert "41000.5" in issues[0].detail


def test_phu_dinh_dong_tien_dung_voi_so_lieu_thi_khong_bi_bat() -> None:
    """Cửa sổ thật sự không có tiền vào thì câu ấy là sự thật, không phải mâu thuẫn."""
    assert _check("Tài khoản không nhận đồng nào.", [_behaviour(inflow_amount=0.0)]) == []


def test_ke_sai_chieu_cua_dung_giao_dich_duoc_dan() -> None:
    """Đọc ngược ``source``/``destination`` là lỗi hay gặp nhất của mô hình."""
    ledger = _ledger(_tx("777", outgoing=True, amount=8433.84))

    issues = _check("Ngày 28/08, tài khoản nhận 8433.84 USD (mã giao dịch 777).", [ledger])

    assert [i.rule for i in issues] == ["DIRECTION_MISMATCH"]
    assert "777" in issues[0].detail


def test_ke_dung_chieu_thi_khong_bi_bat() -> None:
    ledger = _ledger(_tx("777", outgoing=True, amount=8433.84))

    assert _check("Tài khoản chuyển 8433.84 USD (mã giao dịch 777).", [ledger]) == []


def test_khang_dinh_lon_nhat_khi_so_co_dong_lon_hon() -> None:
    ledger = _ledger(_tx("1", outgoing=True, amount=9930.84), _tx("2", outgoing=True, amount=906270.88))

    issues = _check("Giao dịch lớn nhất của tài khoản là 9930.84 USD.", [ledger])

    assert [i.rule for i in issues] == ["SUPERLATIVE_UNSUPPORTED"]
    assert "906270.88" in issues[0].detail


def test_khang_dinh_lon_nhat_dung_thi_khong_bi_bat() -> None:
    ledger = _ledger(_tx("1", outgoing=True, amount=9930.84), _tx("2", outgoing=True, amount=906270.88))

    assert _check("Giao dịch lớn nhất của tài khoản là 906270.88 USD.", [ledger]) == []


def test_noi_nhieu_nguon_khi_chi_do_duoc_hai_doi_tac() -> None:
    """Đúng mâu thuẫn hiện trên màn hình thật: câu chữ nói nhiều nguồn, số đo ghi 2."""
    issues = _check("Tài khoản nhận tiền từ nhiều nguồn dồn vào rồi giữ lại.", [_behaviour()])

    assert [i.rule for i in issues] == ["THRESHOLD_CONTRADICTION"]
    assert "2 đối tác gửi" in issues[0].detail


def test_noi_nhieu_nguon_khi_so_do_du_nguong_thi_khong_bi_bat() -> None:
    evidence = [_behaviour(unique_in_counterparties=18)]

    assert _check("Tài khoản nhận tiền từ nhiều nguồn dồn vào.", evidence) == []


def test_noi_toa_ra_nhieu_dich_khi_chi_co_ba_dich() -> None:
    issues = _check("Sau đó tài khoản phân tán ra nhiều đích khác nhau.", [_behaviour()])

    assert [i.rule for i in issues] == ["THRESHOLD_CONTRADICTION"]
    assert "3 đối tác nhận" in issues[0].detail


def test_khong_co_so_lieu_thi_im_lang_chu_khong_doan() -> None:
    """Thiếu ô số liệu thì không có mốc để so — im lặng còn hơn báo bừa."""
    assert _check("Tài khoản không nhận đồng nào.", []) == []


def test_nhieu_cau_duoc_kiem_doc_lap() -> None:
    evidence = [_behaviour(), _ledger(_tx("777", outgoing=True, amount=100.0))]
    claims = [
        "Tài khoản không nhận đồng nào.",
        "Tài khoản chuyển 100.00 USD (mã giao dịch 777).",
        "Tiền được nhiều nguồn dồn vào tài khoản.",
    ]

    rules = sorted(i.rule for i in consistency.check(claims, evidence, account_key=ACCOUNT, fan_threshold=FAN))

    assert rules == ["FLOW_CONTRADICTION", "THRESHOLD_CONTRADICTION"]


def test_check_kiem_dung_nhung_cau_duoc_truyen_vao() -> None:
    """`check()` không tự khử trùng lặp — nơi gọi phải làm.

    Bản giải thích tất định đặt CÙNG một câu vào cả `claims` lẫn `facts`, nên
    `EvidenceCriticAgent._deterministic_validate` khử trùng trước khi gọi; nếu
    không, mỗi mâu thuẫn bị báo hai lần và vòng sửa lỗi tưởng có gấp đôi việc.
    """
    claim = "Tài khoản không nhận đồng nào."

    issues = consistency.check([claim, claim], [_behaviour()], account_key=ACCOUNT, fan_threshold=FAN)

    assert len(issues) == 2
