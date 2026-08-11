"""Worker đi hết chuỗi điều tra trên cơ sở dữ liệu thật.

test_case_state_machine.py kiểm chứng một bước đơn lẻ. Ở đây kiểm chứng
tính chất quan trọng hơn cho luồng demo: bấm nút nhiều lần thì vụ việc bò
dần lên tới chỗ cần người phê duyệt rồi dừng hẳn, và mỗi bước để lại đúng
một dòng nhật ký kể đúng cung vừa đi.
"""

import uuid

import pytest
from sqlalchemy import text

from src.domain import INVESTIGATION_CHAIN
from src.worker.main import handle_investigate_case

pytestmark = pytest.mark.integration


@pytest.fixture
def fresh_case(db_engine):
    suffix = uuid.uuid4().hex[:8]
    ids = {
        "customer_id": f"TESTCH-{suffix}",
        "account_key": f"997:{suffix}",
        "case_id": f"TESTCH-{suffix}",
        "number": suffix,
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
                   VALUES (:account_key, :customer_id, '997', :number, DATE '2026-01-01')"""
            ),
            ids,
        )
        conn.execute(
            text(
                """INSERT INTO aml_case (case_id, subject_account_key, title, state, risk_score, priority)
                   VALUES (:case_id, :account_key, 'Kiểm thử chuỗi điều tra',
                           'TiepNhanCanhBao', 50, 'low')"""
            ),
            ids,
        )

    yield ids["case_id"]

    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        conn.execute(text("DELETE FROM audit_log WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM aml_case WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM account WHERE account_key = :account_key"), ids)
        conn.execute(text("DELETE FROM customer WHERE customer_id = :customer_id"), ids)


def _state_of(db_engine, case_id: str) -> str:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT state FROM aml_case WHERE case_id = :c"), {"c": case_id}).scalar_one()


def test_repeated_runs_walk_the_whole_chain(db_engine, fresh_case):
    for expected in INVESTIGATION_CHAIN[1:]:
        handle_investigate_case({"case_id": fresh_case})
        assert _state_of(db_engine, fresh_case) == expected


def test_chain_stops_at_approval_and_stays_there(db_engine, fresh_case):
    """Chạy thừa vài lượt cũng không đẩy được vụ việc qua tay người duyệt."""
    for _ in range(len(INVESTIGATION_CHAIN) + 5):
        handle_investigate_case({"case_id": fresh_case})
    assert _state_of(db_engine, fresh_case) == "ChoNguoiPheDuyet"


def test_each_step_logs_the_transition_it_made(db_engine, fresh_case):
    handle_investigate_case({"case_id": fresh_case})
    handle_investigate_case({"case_id": fresh_case})

    with db_engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """SELECT payload ->> 'from' AS from_state, payload ->> 'to' AS to_state
                         FROM audit_log
                        WHERE case_id = :c AND event_type = 'case_state_changed'
                        ORDER BY audit_id"""
                ),
                {"c": fresh_case},
            )
            .mappings()
            .all()
        )

    assert [(r["from_state"], r["to_state"]) for r in rows] == [
        ("TiepNhanCanhBao", "TruyHoiBangChung"),
        ("TruyHoiBangChung", "PhanTichDoThi"),
    ]


def test_missing_case_is_ignored_without_raising(db_engine):
    """Tác vụ trỏ tới vụ việc đã bị xoá không được làm chết worker."""
    handle_investigate_case({"case_id": "TESTCH-khong-ton-tai"})
