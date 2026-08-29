"""Màn "Phân công & tải công việc" — và chốt quan trọng nhất của nó.

Chốt ấy không phải giao diện: đó là việc TRỢ LÝ và MÀN HÌNH ghi qua cùng một
dịch vụ. Hai lối vào của cùng một nghiệp vụ mà có hai đường ghi riêng thì luật
của chúng trôi ra xa nhau, và câu hỏi "hồ sơ này đang ở đâu" bắt đầu có hai câu
trả lời khác nhau.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.api import assignment_routes, routes
from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def team():
    """Một quản lý, hai chuyên viên, bốn hồ sơ chưa ai giữ."""
    suffix = uuid.uuid4().hex[:8]
    ids = {
        "manager": f"UA-M-{suffix}"[:20],
        "lan": f"UA-A-{suffix}"[:20],
        "duc": f"UA-B-{suffix}"[:20],
        "customer": f"UAC-{suffix}",
        "account": f"997:{suffix}",
        "cases": [f"UA-CASE-{suffix}-{i}" for i in range(4)],
    }
    try:
        with get_engine().begin() as conn:
            for uid, name, role in (
                (ids["manager"], f"Quản lý {suffix}", "manager"),
                (ids["lan"], f"Lan {suffix}", "analyst"),
                (ids["duc"], f"Đức {suffix}", "analyst"),
            ):
                conn.execute(
                    text(
                        """INSERT INTO app_user(user_id, name, email, role, role_label, active,
                                                password_salt, password_hash)
                           VALUES (:u, :n, :e, :r, :r, true, 's', 'h')"""
                    ),
                    {"u": uid, "n": name, "e": f"{uid}@test.local", "r": role},
                )
            conn.execute(
                text(
                    """INSERT INTO customer (customer_id, customer_type, prototype, occupation,
                                             declared_income_band, expected_monthly_volume,
                                             registered_country, onboarding_date, risk_rating)
                       VALUES (:c, 'individual', 'salaried', 'Kiểm thử', '<10tr', 1000,
                               'VN', DATE '2026-01-01', 'low')"""
                ),
                {"c": ids["customer"]},
            )
            conn.execute(
                text(
                    """INSERT INTO account (account_key, customer_id, bank_code, account_number, opened_at)
                       VALUES (:a, :c, '997', :n, DATE '2026-01-01')"""
                ),
                {"a": ids["account"], "c": ids["customer"], "n": suffix},
            )
            for i, case_id in enumerate(ids["cases"]):
                conn.execute(
                    text(
                        """INSERT INTO aml_case (case_id, subject_account_key, title, state,
                                                 risk_score, priority)
                           VALUES (:id, :a, :t, 'TiepNhanCanhBao', :r, :p)"""
                    ),
                    {
                        "id": case_id,
                        "a": ids["account"],
                        "t": f"Vụ phân công {i}",
                        "r": 95 - i,
                        "p": "critical" if i < 2 else "medium",
                    },
                )
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")

    yield ids

    with get_engine().begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        conn.execute(text("DELETE FROM case_note WHERE case_id = ANY(:c)"), {"c": ids["cases"]})
        conn.execute(text("DELETE FROM audit_log WHERE case_id = ANY(:c)"), {"c": ids["cases"]})
        conn.execute(text("DELETE FROM aml_case WHERE case_id = ANY(:c)"), {"c": ids["cases"]})
        conn.execute(text("DELETE FROM account WHERE account_key = :a"), {"a": ids["account"]})
        conn.execute(text("DELETE FROM customer WHERE customer_id = :c"), {"c": ids["customer"]})
        conn.execute(
            text("DELETE FROM app_user WHERE user_id = ANY(:u)"),
            {"u": [ids["manager"], ids["lan"], ids["duc"]]},
        )


@pytest.fixture
def as_user(monkeypatch):
    def _apply(user_id: str, role: str) -> None:
        who = {"user_id": user_id, "role": role, "role_label": role, "active": True}
        monkeypatch.setattr(routes, "_require_user", lambda _auth=None: who)
        monkeypatch.setattr(assignment_routes, "_require", lambda _auth=None: who)

    return _apply


async def _assign(client, case_ids, assignee, **extra):
    return await client.post(
        "/api/v1/assignments/assign",
        json={"case_ids": case_ids, "assignee_id": assignee, **extra},
    )


async def _rows(client, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return (await client.get(f"/api/v1/assignments?{q}")).json()["rows"]


def _case(rows, case_id):
    return next((r for r in rows if r["case_id"] == case_id), None)


# --------------------------------------------------------------------------- #
# Giao việc thủ công
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_giao_thu_cong_hien_dung_tren_bang(client, team, as_user) -> None:
    as_user(team["manager"], "manager")

    response = await _assign(client, team["cases"][:1], team["lan"], reason="Chia việc")

    assert response.json()["assigned"] == team["cases"][:1]
    row = _case(await _rows(client, assignee=team["lan"]), team["cases"][0])
    assert row["assignee_id"] == team["lan"]
    assert row["source"] == "manual", "giao thủ công phải ghi nguồn là thủ công"
    assert row["assigned_at"] is not None
    assert row["status"] == "in_progress"


@pytest.mark.asyncio
async def test_giao_hang_loat_dung_so_luong(client, team, as_user) -> None:
    as_user(team["manager"], "manager")

    body = (await _assign(client, team["cases"], team["duc"], reason="Giao lô")).json()

    assert len(body["assigned"]) == 4
    assert body["conflicts"] == []
    assert len(await _rows(client, assignee=team["duc"])) >= 4


@pytest.mark.asyncio
async def test_giao_kem_han_va_chi_dan(client, team, as_user) -> None:
    as_user(team["manager"], "manager")
    due = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)

    await _assign(
        client,
        team["cases"][:1],
        team["lan"],
        due_at=due.isoformat(),
        priority="high",
        instruction="Rà soát bổ sung bằng chứng.",
    )

    detail = (await client.get(f"/api/v1/assignments/{team['cases'][0]}")).json()
    assert detail["row"]["due_at"] is not None
    assert detail["row"]["priority"] == "high"
    assert any("bằng chứng" in n["body"] for n in detail["notes"])


# --------------------------------------------------------------------------- #
# Cùng một dịch vụ cho cả hai lối vào
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tro_ly_va_man_hinh_ghi_cung_mot_kieu(client, team, as_user) -> None:
    """Lượt giao qua trợ lý phải hiện trên bảng NGAY, và ghi nguồn khác nhau.

    Đây là chốt của cả trang: nếu trợ lý ghi bằng một đường riêng thì bảng này
    không còn là nguồn sự thật duy nhất, và quản lý phải mở trò chuyện mới biết
    việc đã giao.
    """
    from src.api import assignment_service as svc
    from src.api.copilot import tools

    with get_engine().begin() as conn:
        tools.execute_action(
            conn,
            action_type=tools.ActionType.ASSIGN_TASK,
            payload={"case_ids": team["cases"][:1], "assignee_id": team["lan"]},
            actor=team["manager"],
            actor_role="manager",
        )
    as_user(team["manager"], "manager")

    row = _case(await _rows(client, assignee=team["lan"]), team["cases"][0])

    assert row["assignee_id"] == team["lan"]
    assert row["source"] == "ai_copilot", "lượt giao qua trợ lý phải ghi rõ nguồn"
    assert svc.Source.AI_COPILOT.value == "ai_copilot"


@pytest.mark.asyncio
async def test_loc_theo_nguon_phan_cong(client, team, as_user) -> None:
    from src.api.copilot import tools

    as_user(team["manager"], "manager")
    await _assign(client, team["cases"][:1], team["lan"])
    with get_engine().begin() as conn:
        tools.execute_action(
            conn,
            action_type=tools.ActionType.ASSIGN_TASK,
            payload={"case_ids": team["cases"][1:2], "assignee_id": team["duc"]},
            actor=team["manager"],
            actor_role="manager",
        )

    thu_cong = [r["case_id"] for r in await _rows(client, source="manual")]
    tro_ly = [r["case_id"] for r in await _rows(client, source="ai_copilot")]

    assert team["cases"][0] in thu_cong and team["cases"][0] not in tro_ly
    assert team["cases"][1] in tro_ly and team["cases"][1] not in thu_cong


# --------------------------------------------------------------------------- #
# Chuyển giao, lịch sử, tranh chấp
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_chuyen_giao_doi_nguoi_va_luu_lich_su(client, team, as_user) -> None:
    as_user(team["manager"], "manager")
    case_id = team["cases"][0]
    await _assign(client, [case_id], team["lan"])

    response = await client.post(
        f"/api/v1/assignments/{case_id}/reassign",
        json={
            "assignee_id": team["duc"],
            "reason": "Cân bằng lại tải công việc",
            "expected_assignee": team["lan"],
        },
    )

    assert response.status_code == 200
    detail = (await client.get(f"/api/v1/assignments/{case_id}")).json()
    assert detail["row"]["assignee_id"] == team["duc"]
    # Lịch sử KHÔNG ghi đè: cả hai lượt giao đều còn.
    giao = [h for h in detail["history"] if h["event"] == "case_assigned"]
    assert len(giao) >= 2
    assert any("Cân bằng lại tải" in (h["reason"] or "") for h in giao)


@pytest.mark.asyncio
async def test_nguoi_khac_vua_giao_thi_bao_xung_dot_khong_ghi_de(client, team, as_user) -> None:
    """Hai quản lý cùng thao tác trên một hồ sơ.

    Người thứ hai thấy màn hình cũ (đang là Lan) nhưng thực tế đã sang Đức. Ghi
    đè ở đây là âm thầm cướp việc, nên phải báo lại.
    """
    as_user(team["manager"], "manager")
    case_id = team["cases"][0]
    await _assign(client, [case_id], team["lan"])
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE aml_case SET assigned_to = :u WHERE case_id = :c"),
            {"u": team["duc"], "c": case_id},
        )

    response = await client.post(
        f"/api/v1/assignments/{case_id}/reassign",
        json={"assignee_id": team["lan"], "reason": "Chuyển lại", "expected_assignee": team["lan"]},
    )

    assert response.status_code == 409
    with get_engine().begin() as conn:
        holder = conn.execute(text("SELECT assigned_to FROM aml_case WHERE case_id = :c"), {"c": case_id}).scalar_one()
    assert holder == team["duc"], "không được ghi đè người vừa nhận"


# --------------------------------------------------------------------------- #
# Bộ lọc và số liệu
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_loc_chua_phan_cong(client, team, as_user) -> None:
    as_user(team["manager"], "manager")
    await _assign(client, team["cases"][:1], team["lan"])

    chua_giao = [r["case_id"] for r in await _rows(client, status="unassigned")]

    assert team["cases"][0] not in chua_giao
    assert team["cases"][1] in chua_giao


@pytest.mark.asyncio
async def test_loc_qua_han(client, team, as_user) -> None:
    as_user(team["manager"], "manager")
    case_id = team["cases"][0]
    await _assign(client, [case_id], team["lan"])
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE aml_case SET due_at = :d WHERE case_id = :c"),
            {"d": datetime.now(UTC) - timedelta(days=1), "c": case_id},
        )

    qua_han = await _rows(client, status="overdue")

    assert _case(qua_han, case_id) is not None
    assert _case(qua_han, case_id)["status"] == "overdue"


@pytest.mark.asyncio
async def test_so_lieu_tong_khop_voi_bang(client, team, as_user) -> None:
    """Thẻ đếm và bảng phải nói cùng một con số — nếu không thì tin bên nào?"""
    as_user(team["manager"], "manager")
    await _assign(client, team["cases"][:2], team["lan"])

    overview = (await client.get("/api/v1/assignments/overview")).json()
    lan = next(w for w in overview["workload"] if w["employee_id"] == team["lan"])

    assert lan["open_cases"] == 2
    assert lan["high_priority"] == 2  # hai hồ sơ đầu là 'critical'
    assert overview["sees_team"] is True


# --------------------------------------------------------------------------- #
# Phân quyền
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_chuyen_vien_khong_giao_duoc_viec(client, team, as_user) -> None:
    as_user(team["lan"], "analyst")

    response = await _assign(client, team["cases"][:1], team["duc"])

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chuyen_vien_khong_chuyen_giao_duoc(client, team, as_user) -> None:
    as_user(team["manager"], "manager")
    await _assign(client, team["cases"][:1], team["lan"])
    as_user(team["lan"], "analyst")

    response = await client.post(
        f"/api/v1/assignments/{team['cases'][0]}/reassign",
        json={"assignee_id": team["duc"], "reason": "Tôi bận quá"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_quan_tri_he_thong_khong_giao_duoc_viec(client, team, as_user) -> None:
    """Quản trị hệ thống là thẩm quyền KỸ THUẬT, không mặc nhiên cao hơn Quản lý."""
    as_user("U-ADMIN-TEST", "admin")

    response = await _assign(client, team["cases"][:1], team["lan"])

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chuyen_vien_chi_thay_viec_cua_minh(client, team, as_user) -> None:
    """Phạm vi bị ép ở máy chủ, không phụ thuộc tham số trình duyệt gửi lên."""
    as_user(team["manager"], "manager")
    await _assign(client, team["cases"][:1], team["lan"])
    await _assign(client, team["cases"][1:2], team["duc"])
    as_user(team["lan"], "analyst")

    # Cố tình hỏi việc của người khác.
    rows = await _rows(client, assignee=team["duc"])

    assert all(r["assignee_id"] == team["lan"] for r in rows)
    assert _case(rows, team["cases"][1]) is None


@pytest.mark.asyncio
async def test_chuyen_vien_khong_thay_tai_cong_viec_ca_nhom(client, team, as_user) -> None:
    as_user(team["lan"], "analyst")

    overview = (await client.get("/api/v1/assignments/overview")).json()

    assert overview["sees_team"] is False
    assert overview["workload"] == []
    assert overview["can_assign"] is False


# --------------------------------------------------------------------------- #
# Luật nghiệp vụ giữ nguyên ở cả hai lối vào
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_khong_giao_viec_cho_quan_ly(client, team, as_user) -> None:
    """Quản lý chốt hồ sơ, không lập hồ sơ — luật này phải đúng ở MỌI lối vào."""
    as_user(team["manager"], "manager")

    body = (await _assign(client, team["cases"][:1], team["manager"])).json()

    assert body["assigned"] == []
    assert body["conflicts"][0]["code"] == "assignee_not_analyst"


@pytest.mark.asyncio
async def test_mot_ho_so_hong_khong_keo_ca_lo_xuong(client, team, as_user) -> None:
    as_user(team["manager"], "manager")

    body = (await _assign(client, [*team["cases"][:2], "CASE-KHONG-TON-TAI"], team["lan"])).json()

    assert len(body["assigned"]) == 2
    assert body["conflicts"][0]["code"] == "case_not_found"
