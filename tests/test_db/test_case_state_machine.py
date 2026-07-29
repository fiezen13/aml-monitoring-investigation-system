"""Máy trạng thái vụ việc — kiểm chứng trên cơ sở dữ liệu thật.

ARC-001 mục 3.4: "Không tồn tại cung nào từ SoanHoSo đi thẳng tới XuatHoSo."
Tài liệu ghi rõ tính chất này phải được khẳng định bằng kiểm thử, không phải
bằng việc đọc mã. Đây là phần kiểm thử ấy ở tầng dữ liệu; phần duyệt toàn bộ
đồ thị chuyển trạng thái nằm ở hạng mục thiết kế máy trạng thái của epic E07.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.worker.main import handle_investigate_case

pytestmark = pytest.mark.integration


@pytest.fixture
def case_in_state(db_engine):
    created: list[dict[str, str]] = []

    def _make(state: str) -> str:
        suffix = uuid.uuid4().hex[:8]
        ids = {
            "customer_id": f"TESTCUS-{suffix}",
            "account_key": f"998:{suffix}",
            "case_id": f"TESTSM-{suffix}",
            "number": suffix,
            "state": state,
        }
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO customer (customer_id, customer_type, prototype, occupation,
                                             declared_income_band, expected_monthly_volume,
                                             registered_country, onboarding_date, risk_rating)
                       VALUES (:customer_id, 'individual', 'salaried', 'Kiểm thử', '<10tr', 1000,
                               'VN', DATE '2026-01-01', 'low')"""
                ),
                ids,
            )
            conn.execute(
                text(
                    """INSERT INTO account (account_key, customer_id, bank_code, account_number, opened_at)
                       VALUES (:account_key, :customer_id, '998', :number, DATE '2026-01-01')"""
                ),
                ids,
            )
            conn.execute(
                text(
                    """INSERT INTO aml_case (case_id, subject_account_key, title, state, risk_score, priority)
                       VALUES (:case_id, :account_key, 'Kiểm thử máy trạng thái', :state, 50, 'low')"""
                ),
                ids,
            )
        created.append(ids)
        return ids["case_id"]

    yield _make

    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        for ids in created:
            conn.execute(text("DELETE FROM audit_log WHERE case_id = :case_id"), ids)
            conn.execute(text("DELETE FROM aml_case WHERE case_id = :case_id"), ids)
            conn.execute(text("DELETE FROM account WHERE account_key = :account_key"), ids)
            conn.execute(text("DELETE FROM customer WHERE customer_id = :customer_id"), ids)


def _state_of(db_engine, case_id: str) -> str:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT state FROM aml_case WHERE case_id = :c"), {"c": case_id}).scalar_one()


def test_investigation_moves_new_case_forward(db_engine, case_in_state):
    case_id = case_in_state("TiepNhanCanhBao")
    handle_investigate_case({"case_id": case_id})
    assert _state_of(db_engine, case_id) == "TruyHoiBangChung"


def test_investigation_writes_an_audit_entry(db_engine, case_in_state):
    """NT4 — mọi thay đổi trạng thái vào nhật ký."""
    case_id = case_in_state("TiepNhanCanhBao")
    handle_investigate_case({"case_id": case_id})
    with db_engine.connect() as conn:
        events = (
            conn.execute(text("SELECT event_type FROM audit_log WHERE case_id = :c ORDER BY audit_id"), {"c": case_id})
            .scalars()
            .all()
        )
    assert "case_state_changed" in events


def test_investigation_does_not_touch_a_case_awaiting_approval(db_engine, case_in_state):
    """Vụ việc đang chờ người phê duyệt không bị worker kéo ngược lại."""
    case_id = case_in_state("ChoNguoiPheDuyet")
    handle_investigate_case({"case_id": case_id})
    assert _state_of(db_engine, case_id) == "ChoNguoiPheDuyet"


def test_unknown_state_is_rejected_by_the_database(db_engine, case_in_state):
    """Danh sách trạng thái hợp lệ nằm trong ràng buộc CHECK, không chỉ trong mã ứng dụng."""
    case_id = case_in_state("TiepNhanCanhBao")
    with pytest.raises(DBAPIError), db_engine.begin() as conn:
        conn.execute(text("UPDATE aml_case SET state = 'TrangThaiBiaRa' WHERE case_id = :c"), {"c": case_id})
