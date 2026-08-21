"""Luồng console hoàn chỉnh dùng cùng API mà giao diện production gọi."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def production_flow_state():
    """Chọn case chưa có SAR và phục hồi DB chính xác sau bài kiểm thử."""
    try:
        with get_engine().begin() as conn:
            case = (
                conn.execute(
                    text(
                        """SELECT c.case_id, c.state, c.updated_at, c.assigned_to
                             FROM aml_case c
                            WHERE NOT EXISTS (SELECT 1 FROM sar_draft d WHERE d.case_id = c.case_id)
                              AND EXISTS (
                                  SELECT 1 FROM transaction t
                                   WHERE t.from_account_key = c.subject_account_key
                                      OR t.to_account_key = c.subject_account_key
                              )
                            ORDER BY c.case_id LIMIT 1"""
                    )
                )
                .mappings()
                .first()
            )
            if case is None:
                pytest.skip("Không có case chưa tạo SAR để chạy luồng production")
            # Chuyên viên (U-006) chỉ thấy hồ sơ ĐƯỢC GIAO. Giao tạm case này cho họ
            # để luồng "chuyên viên soạn SAR" chạy đúng; teardown trả lại người cũ.
            conn.execute(
                text("UPDATE aml_case SET assigned_to = 'U-006' WHERE case_id = :cid"),
                {"cid": case["case_id"]},
            )
            audit_before = conn.execute(text("SELECT coalesce(max(audit_id), 0) FROM audit_log")).scalar_one()
            last_logins = dict(conn.execute(text("SELECT user_id, last_login FROM app_user")).all())
            setting_before = conn.execute(
                text("SELECT value FROM system_setting WHERE code = 'SLA-ALERT'")
            ).scalar_one()
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL đã áp migration console: {exc}")

    state = {
        "case_id": case["case_id"],
        "case_state": case["state"],
        "case_updated_at": case["updated_at"],
        "case_assigned_to": case["assigned_to"],
        "audit_before": audit_before,
        "last_logins": last_logins,
        "setting_before": setting_before,
    }
    yield state

    sar_id = f"SAR-{state['case_id']}"
    with get_engine().begin() as conn:
        # Ba bảng chứng cứ có trigger bất biến. Chỉ bài test, với user DB test
        # là superuser, mới tắt trigger để đưa DB về đúng ảnh chụp ban đầu.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM app_session"))
        conn.execute(text("DELETE FROM audit_log WHERE audit_id > :before"), {"before": state["audit_before"]})
        conn.execute(text("DELETE FROM approval WHERE sar_draft_id = :sar"), {"sar": sar_id})
        conn.execute(
            text(
                """DELETE FROM sar_statement_evidence
                    WHERE statement_id IN (SELECT statement_id FROM sar_statement WHERE sar_draft_id = :sar)"""
            ),
            {"sar": sar_id},
        )
        conn.execute(text("DELETE FROM sar_statement WHERE sar_draft_id = :sar"), {"sar": sar_id})
        conn.execute(text("DELETE FROM sar_draft WHERE sar_draft_id = :sar"), {"sar": sar_id})
        conn.execute(
            text("DELETE FROM evidence WHERE case_id = :case_id AND evidence_id LIKE :pattern"),
            {"case_id": state["case_id"], "pattern": f"EV-{state['case_id']}-LIVE-%"},
        )
        conn.execute(
            text(
                """UPDATE aml_case SET state = :state, updated_at = :updated, assigned_to = :assigned
                    WHERE case_id = :case_id"""
            ),
            {
                "state": state["case_state"],
                "updated": state["case_updated_at"],
                "assigned": state["case_assigned_to"],
                "case_id": state["case_id"],
            },
        )
        for user_id, last_login in state["last_logins"].items():
            conn.execute(
                text("UPDATE app_user SET last_login = :last_login WHERE user_id = :user_id"),
                {"last_login": last_login, "user_id": user_id},
            )
        conn.execute(
            text("UPDATE system_setting SET value = :value WHERE code = 'SLA-ALERT'"),
            {"value": state["setting_before"]},
        )


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "demo-password"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.mark.asyncio
async def test_full_production_flow_and_cleanup(client, production_flow_state):
    """Chuyên viên: đăng nhập → network → soạn SAR → kiểm tra → nộp; Quản lý duyệt → xuất."""
    case_id = production_flow_state["case_id"]
    analyst = await _login(client, "tuan.la@velrix.vn")

    me = await client.get("/api/v1/auth/me", headers=analyst)
    assert me.status_code == 200
    assert me.json()["role"] == "analyst"

    network = await client.get(f"/api/v1/cases/{case_id}/network", headers=analyst)
    assert network.status_code == 200, network.text
    assert network.json()["nodes"]
    assert network.json()["transactions"]

    created = await client.post(f"/api/v1/cases/{case_id}/sar", headers=analyst)
    assert created.status_code == 200, created.text
    sar = created.json()
    assert sar["status"] == "DRAFT"
    assert sar["statements"] and sar["evidence"]
    assert all(statement["evidenceIds"] for statement in sar["statements"])

    validated = await client.post(f"/api/v1/sars/{sar['sar_id']}/validate", headers=analyst)
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "VALIDATION_PASSED"

    submitted = await client.post(
        f"/api/v1/sars/{sar['sar_id']}/submit",
        headers=analyst,
        json={"reason": "Bằng chứng đầy đủ, chuyển MLRO phê duyệt trong kiểm thử E2E."},
    )
    assert submitted.status_code == 200, submitted.text
    submitted_sar = submitted.json()
    assert submitted_sar["status"] == "PENDING_REVIEW"
    approval_id = submitted_sar["approval"]["approval_id"]

    self_decision = await client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=analyst,
        json={"decision": "approved", "reason": "Không được tự phê duyệt hồ sơ đã gửi."},
    )
    assert self_decision.status_code == 403

    manager = await _login(client, "hung.nq@velrix.vn")
    approved = await client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=manager,
        json={"decision": "approved", "reason": "Đã đối chiếu bằng chứng và chấp thuận hồ sơ E2E."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    exported = await client.post(f"/api/v1/sars/{sar['sar_id']}/export", headers=manager)
    assert exported.status_code == 200, exported.text
    # Xuất trả về CHÍNH file PDF tải về được, không phải JSON.
    assert exported.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="' in exported.headers["content-disposition"]
    assert exported.content[:5] == b"%PDF-"

    detail = await client.get(f"/api/v1/sars/{sar['sar_id']}", headers=manager)
    assert detail.status_code == 200
    assert detail.json()["approval"]["decided_by"] == "U-001"
    with get_engine().connect() as conn:
        assert (
            conn.execute(text("SELECT state FROM aml_case WHERE case_id = :case_id"), {"case_id": case_id}).scalar_one()
            == "XuatHoSo"
        )
        events = (
            conn.execute(
                text(
                    """SELECT event_type FROM audit_log WHERE case_id = :case_id
                   AND audit_id > :before ORDER BY audit_id"""
                ),
                {"case_id": case_id, "before": production_flow_state["audit_before"]},
            )
            .scalars()
            .all()
        )
    assert ["sar_updated", "validation_run", "submitted_for_approval", "approved", "file_exported"] == [
        event for event in events if event != "case_viewed"
    ]


@pytest.mark.asyncio
async def test_users_and_settings_are_database_backed(client, production_flow_state):
    admin = await _login(client, "manh.dh@velrix.vn")
    users = await client.get("/api/v1/users", headers=admin)
    assert users.status_code == 200
    assert len(users.json()) == 7

    settings = await client.get("/api/v1/settings", headers=admin)
    assert settings.status_code == 200
    assert any(item["code"] == "SLA-ALERT" for item in settings.json()["settings"])

    changed = await client.put(
        "/api/v1/settings/SLA-ALERT",
        headers=admin,
        json={"value": "5", "reason": "Kiểm thử ghi cấu hình thật và audit trail."},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["value"] == "5"

    admin = await _login(client, "manh.dh@velrix.vn")
    activated = await client.patch(
        "/api/v1/users/U-007",
        headers=admin,
        json={"active": True, "reason": "Kiểm thử kích hoạt tài khoản bằng dữ liệu DB."},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["active"] is True
    restored = await client.patch(
        "/api/v1/users/U-007",
        headers=admin,
        json={"active": False, "reason": "Phục hồi trạng thái tài khoản sau kiểm thử."},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["active"] is False
