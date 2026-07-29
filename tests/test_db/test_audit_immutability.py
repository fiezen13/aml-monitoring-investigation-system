"""Nhật ký kiểm toán chỉ ghi thêm — kiểm chứng ở tầng cơ sở dữ liệu.

QD6 nói rõ vì sao bài kiểm thử này tồn tại: quy ước trong mã nguồn có thể bị
vi phạm do sơ suất, ràng buộc ở tầng dữ liệu thì không. Nhưng "ràng buộc ở
tầng dữ liệu" cũng chỉ là một dòng SQL cho tới khi có ai đó chứng minh nó
thật sự chặn. Đó là việc của file này.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_case(db_engine):
    """Một vụ việc dùng một lần, kèm tài khoản và khách hàng tối thiểu."""
    suffix = uuid.uuid4().hex[:8]
    ids = {
        "customer_id": f"TESTCUS-{suffix}",
        "account_key": f"999:{suffix}",
        "case_id": f"TESTCASE-{suffix}",
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
                   VALUES (:account_key, :customer_id, '999', :number, DATE '2026-01-01')"""
            ),
            {**ids, "number": suffix},
        )
        conn.execute(
            text(
                """INSERT INTO aml_case (case_id, subject_account_key, title, risk_score, priority)
                   VALUES (:case_id, :account_key, 'Vụ việc kiểm thử', 50, 'low')"""
            ),
            ids,
        )
    yield ids
    with db_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        conn.execute(text("DELETE FROM approval WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM audit_log WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM evidence WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM aml_case WHERE case_id = :case_id"), ids)
        conn.execute(text("DELETE FROM account WHERE account_key = :account_key"), ids)
        conn.execute(text("DELETE FROM customer WHERE customer_id = :customer_id"), ids)


def _write_audit(conn, case_id: str) -> int:
    return conn.execute(
        text(
            """INSERT INTO audit_log (case_id, event_type, actor, actor_role)
               VALUES (:case_id, 'case_viewed', 'pytest', 'auditor')
               RETURNING audit_id"""
        ),
        {"case_id": case_id},
    ).scalar_one()


def test_audit_log_accepts_inserts(db_engine, sample_case):
    with db_engine.begin() as conn:
        assert _write_audit(conn, sample_case["case_id"]) > 0


def test_audit_log_rejects_update(db_engine, sample_case):
    with db_engine.begin() as conn:
        audit_id = _write_audit(conn, sample_case["case_id"])

    with pytest.raises(DBAPIError, match="chỉ cho phép ghi thêm"), db_engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET actor = 'ai đó khác' WHERE audit_id = :i"), {"i": audit_id})


def test_audit_log_rejects_delete(db_engine, sample_case):
    with db_engine.begin() as conn:
        audit_id = _write_audit(conn, sample_case["case_id"])

    with pytest.raises(DBAPIError, match="chỉ cho phép ghi thêm"), db_engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE audit_id = :i"), {"i": audit_id})


def test_evidence_rejects_update(db_engine, sample_case):
    evidence_id = f"EV-{sample_case['case_id']}"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO evidence (evidence_id, case_id, source_table, source_ref, payload, evidence_hash)
                   VALUES (:evidence_id, :case_id, 'transaction', '1', '{}'::jsonb, 'hash')"""
            ),
            {"evidence_id": evidence_id, "case_id": sample_case["case_id"]},
        )

    with pytest.raises(DBAPIError, match="chỉ cho phép ghi thêm"), db_engine.begin() as conn:
        # jsonb_build_object thay vì literal JSON: dấu hai chấm trong chuỗi
        # JSON bị SQLAlchemy hiểu nhầm là tham số ràng buộc.
        conn.execute(
            text("UPDATE evidence SET payload = jsonb_build_object('x', 1) WHERE evidence_id = :i"),
            {"i": evidence_id},
        )


def test_approval_decides_once_then_locks(db_engine, sample_case):
    """NT3 — người quyết định cuối cùng, và quyết định đã ghi thì không sửa lại."""
    approval_id = f"APR-{sample_case['case_id']}"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO approval (approval_id, case_id, decision)
                   VALUES (:approval_id, :case_id, 'pending')"""
            ),
            {"approval_id": approval_id, "case_id": sample_case["case_id"]},
        )
        # Lượt quyết định đầu tiên: được.
        conn.execute(
            text(
                """UPDATE approval
                      SET decision = 'approved', decided_by = 'mlro.bao',
                          reason = 'Đủ bằng chứng cho ba khẳng định trong hồ sơ', decided_at = now()
                    WHERE approval_id = :approval_id"""
            ),
            {"approval_id": approval_id},
        )

    # Lượt thứ hai: bị chặn.
    with pytest.raises(DBAPIError, match="không sửa được"), db_engine.begin() as conn:
        conn.execute(
            text("UPDATE approval SET decision = 'rejected' WHERE approval_id = :approval_id"),
            {"approval_id": approval_id},
        )


def test_approval_requires_reason(db_engine, sample_case):
    """Phê duyệt không kèm lý do bị chặn bằng CHECK, không chỉ bằng giao diện."""
    approval_id = f"APR2-{sample_case['case_id']}"
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO approval (approval_id, case_id, decision) VALUES (:a, :c, 'pending')"),
            {"a": approval_id, "c": sample_case["case_id"]},
        )

    with pytest.raises(DBAPIError, match="approval_decided_needs_reason"), db_engine.begin() as conn:
        conn.execute(
            text(
                """UPDATE approval SET decision = 'approved', decided_by = 'mlro.bao', decided_at = now()
                    WHERE approval_id = :a"""
            ),
            {"a": approval_id},
        )
