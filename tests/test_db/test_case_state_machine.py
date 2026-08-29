"""Máy trạng thái vụ việc — kiểm chứng trên cơ sở dữ liệu thật.

ARC-001 mục 3.4: "Không tồn tại cung nào từ SoanHoSo đi thẳng tới XuatHoSo."
Tài liệu ghi rõ tính chất này phải được khẳng định bằng kiểm thử, không phải
bằng việc đọc mã.

Ngày 27/08/2026 quy trình rút còn sáu trạng thái: sáu trạng thái trung gian cũ
chỉ tới được qua một endpoint không giao diện nào gọi, và chưa từng có vụ nào
đi qua. Các bài kiểm dựa trên `handle_investigate_case` đã bỏ cùng nó; phần còn
lại kiểm ĐÚNG thứ vẫn còn giá trị — danh sách trạng thái hợp lệ nằm trong ràng
buộc CHECK của cơ sở dữ liệu, không chỉ trong mã ứng dụng.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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


def test_unknown_state_is_rejected_by_the_database(db_engine, case_in_state):
    """Danh sách trạng thái hợp lệ nằm trong ràng buộc CHECK, không chỉ trong mã ứng dụng."""
    case_id = case_in_state("TiepNhanCanhBao")
    with pytest.raises(DBAPIError), db_engine.begin() as conn:
        conn.execute(text("UPDATE aml_case SET state = 'TrangThaiBiaRa' WHERE case_id = :c"), {"c": case_id})


@pytest.mark.parametrize(
    "dead_state",
    [
        "TruyHoiBangChung",
        "PhanTichDoThi",
        "DoiChieuTrungPhatPEP",
        "TinhToanBangCongCu",
        "LapLuanGanTypology",
        "KiemChungBangChung",
    ],
)
def test_removed_states_cannot_come_back(db_engine, case_in_state, dead_state):
    """Sáu trạng thái đã gỡ phải bị CHÍNH cơ sở dữ liệu từ chối.

    Gỡ khỏi mã Python thôi thì chưa đủ: một script nạp dữ liệu hay một bản vá
    tay vẫn ghi vào được, và nhật ký kiểm toán lại hiện những giai đoạn chưa
    từng xảy ra. Ràng buộc CHECK là chỗ khoá thật.
    """
    case_id = case_in_state("TiepNhanCanhBao")
    with pytest.raises(DBAPIError), db_engine.begin() as conn:
        conn.execute(
            text("UPDATE aml_case SET state = :s WHERE case_id = :c"),
            {"s": dead_state, "c": case_id},
        )
