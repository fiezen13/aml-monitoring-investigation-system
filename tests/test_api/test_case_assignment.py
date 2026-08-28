"""Giao việc vụ việc: ai giao được cho ai, và thống kê khối lượng.

`aml_case.assigned_to` tồn tại từ đầu nhưng không có luồng nào ghi vào nó — cột
"Phụ trách" luôn là "Chưa giao" và bộ lọc "vụ của tôi" luôn rỗng. Bộ kiểm thử này
khoá lại các quy tắc của luồng vừa thêm.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def spare_case():
    """Một vụ chưa kết thúc, trả nguyên trạng người phụ trách sau khi chạy."""
    try:
        with get_engine().begin() as conn:
            row = (
                conn.execute(
                    text(
                        """SELECT case_id, assigned_to FROM aml_case
                            WHERE state NOT IN ('XuatHoSo', 'DongKhongBaoCao')
                            ORDER BY case_id DESC LIMIT 1"""
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                pytest.skip("Không có vụ việc đang mở để thử giao việc")
            conn.execute(
                text("UPDATE aml_case SET assigned_to = NULL WHERE case_id = :c"), {"c": row["case_id"]}
            )
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")
    yield row["case_id"]
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE aml_case SET assigned_to = :a WHERE case_id = :c"),
            {"a": row["assigned_to"], "c": row["case_id"]},
        )
        # KHÔNG xoá vết kiểm toán: audit_log chỉ-ghi-thêm (QD6/NT4), và một bài
        # kiểm thử cũng không được phép làm sạch lịch sử của chính nó.


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "demo-password"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.mark.asyncio
async def test_chuyen_vien_tu_nhan_vu_chua_ai_giu(client, spare_case):
    analyst = await _login(client, "tuan.la@velrix.vn")
    r = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=analyst, json={"assignee": "U-006", "reason": "Tự nhận"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to"] == "U-006"
    # Màn hình đọc TÊN người, không phải mã người dùng.
    assert body["assigned_name"] == "Lê Anh Tuấn"


@pytest.mark.asyncio
async def test_chuyen_vien_khong_gianh_duoc_vu_cua_nguoi_khac(client, spare_case):
    manager = await _login(client, "hung.nq@velrix.vn")
    analyst = await _login(client, "tuan.la@velrix.vn")
    assigned = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-007", "reason": "Phân công"}
    )
    assert assigned.status_code == 200, assigned.text

    grabbed = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=analyst, json={"assignee": "U-006", "reason": "Nhận"}
    )
    assert grabbed.status_code == 409
    released = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=analyst, json={"assignee": None, "reason": "Trả"}
    )
    assert released.status_code == 403


@pytest.mark.asyncio
async def test_chuyen_vien_khong_giao_ho_nguoi_khac(client, spare_case):
    analyst = await _login(client, "tuan.la@velrix.vn")
    r = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=analyst, json={"assignee": "U-007", "reason": "Giao hộ"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_quan_ly_giao_va_thu_hoi(client, spare_case):
    manager = await _login(client, "hung.nq@velrix.vn")
    assigned = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-008", "reason": "Phân công"}
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_name"] == "Vũ Thị Hồng Nhung"

    revoked = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": None, "reason": "Thu hồi"}
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["assigned_to"] is None


@pytest.mark.asyncio
async def test_khong_giao_cho_tai_khoan_khoa_hoac_khong_ton_tai(client, spare_case):
    manager = await _login(client, "hung.nq@velrix.vn")
    locked = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-004", "reason": "Khoá"}
    )
    assert locked.status_code == 409
    missing = await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-999", "reason": "Ma"}
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_moi_lan_doi_nguoi_phu_trach_deu_co_vet_kiem_toan(client, spare_case):
    manager = await _login(client, "hung.nq@velrix.vn")
    await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-006", "reason": "Phân công"}
    )
    with get_engine().connect() as conn:
        row = (
            conn.execute(
                text(
                    """SELECT actor, actor_role, payload FROM audit_log
                        WHERE case_id = :c AND event_type = 'case_assigned'
                        ORDER BY audit_id DESC LIMIT 1"""
                ),
                {"c": spare_case},
            )
            .mappings()
            .first()
        )
    assert row is not None, "giao việc phải để lại vết kiểm toán"
    assert row["actor"] == "U-001" and row["actor_role"] == "manager"
    assert row["payload"]["after"] == "U-006"


@pytest.mark.asyncio
async def test_thong_ke_khoi_luong_dem_dung_vu_vua_giao(client, spare_case):
    manager = await _login(client, "hung.nq@velrix.vn")
    before = (await client.get("/api/v1/workload", headers=manager)).json()
    mine_before = next(r for r in before["rows"] if r["user_id"] == "U-006")["open_cases"]

    await client.post(
        f"/api/v1/cases/{spare_case}/assign", headers=manager, json={"assignee": "U-006", "reason": "Phân công"}
    )
    after = (await client.get("/api/v1/workload", headers=manager)).json()
    mine_after = next(r for r in after["rows"] if r["user_id"] == "U-006")
    assert mine_after["open_cases"] == mine_before + 1
    assert sum(mine_after["by_state"].values()) == mine_after["open_cases"]
    # Vụ vừa giao rời khỏi hàng đợi chưa ai giữ.
    assert after["unassigned_cases"] == before["unassigned_cases"] - 1


@pytest.mark.asyncio
async def test_my_work_dem_dung_viec_cua_nguoi_dang_dang_nhap(client, monkeypatch, spare_case) -> None:
    """"Việc của tôi" phải là của TÔI, không phải tổng của cả đội.

    Bảng ``/workload`` đếm mọi người; endpoint này chỉ được đếm những vụ giao
    cho chính người gọi. Giao một vụ cho một người rồi hỏi bằng hai danh tính
    khác nhau: chỉ người được giao mới thấy con số tăng.
    """
    from src.api import routes

    def _as(user_id: str, role: str = "analyst"):
        monkeypatch.setattr(
            routes,
            "_require_user",
            lambda _auth=None: {"user_id": user_id, "role": role, "role_label": role, "active": True},
        )

    # Đo TRƯỚC khi giao, để so bằng hiệu số — con số tuyệt đối phụ thuộc dữ liệu
    # sẵn có trong DB nên không khẳng định được gì.
    _as("U-002")
    mine_before = (await client.get("/api/v1/my-work")).json()["assigned_open"]
    _as("U-007")
    other_before = (await client.get("/api/v1/my-work")).json()["assigned_open"]

    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE aml_case SET assigned_to = 'U-002' WHERE case_id = :c"), {"c": spare_case}
        )

    _as("U-002")
    mine_after = (await client.get("/api/v1/my-work")).json()["assigned_open"]
    _as("U-007")
    other_after = (await client.get("/api/v1/my-work")).json()["assigned_open"]

    assert mine_after == mine_before + 1, "người được giao phải thấy vụ mới"
    assert other_after == other_before, "người khác KHÔNG được thấy vụ của đồng nghiệp"


@pytest.mark.asyncio
async def test_chuyen_vien_khong_nhan_so_lieu_dieu_hanh(client, monkeypatch) -> None:
    """Hai con số điều hành chỉ dành cho Quản lý.

    "Hồ sơ chờ tôi duyệt" và "vụ chưa ai giữ" là việc phân công/phê duyệt;
    Chuyên viên không có thẩm quyền đó nên phải nhận 0, kể cả khi hàng đợi
    thật đang có hàng nghìn vụ chưa giao.
    """
    from src.api import routes

    monkeypatch.setattr(
        routes,
        "_require_user",
        lambda _auth=None: {"user_id": "U-002", "role": "analyst", "role_label": "Chuyên viên", "active": True},
    )
    body = (await client.get("/api/v1/my-work")).json()

    assert body["role"] == "analyst"
    assert body["awaiting_my_decision"] == 0
    assert body["unassigned_cases"] == 0


@pytest.mark.asyncio
async def test_khong_dem_ho_so_do_chinh_minh_trinh(client, monkeypatch) -> None:
    """"Chờ TÔI duyệt" phải trừ hồ sơ do chính tôi trình.

    Nguyên tắc bốn mắt chặn người trình tự phê duyệt (403 ở cổng quyết định).
    Nếu thẻ vẫn đếm hồ sơ đó, Quản lý thấy "1 hồ sơ chờ tôi duyệt", bấm vào rồi
    bị từ chối — con số hứa một việc không làm được. Đây là ca thật trên
    production: Quản lý U-001 trình hồ sơ rồi thấy chính nó trong hàng đợi
    của mình.
    """
    from src.api import routes

    pending = None
    with get_engine().begin() as conn:
        row = (
            conn.execute(
                text(
                    """SELECT ap.case_id,
                              (SELECT l.actor FROM audit_log l
                                WHERE l.case_id = ap.case_id
                                  AND l.event_type = 'submitted_for_approval'
                                ORDER BY l.occurred_at DESC LIMIT 1) AS nguoi_trinh
                         FROM approval ap WHERE ap.decision = 'pending' LIMIT 1"""
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["nguoi_trinh"] is None:
            pytest.skip("Không có hồ sơ nào đang chờ phê duyệt để kiểm")
        pending = row

    def _as_manager(user_id: str):
        monkeypatch.setattr(
            routes,
            "_require_user",
            lambda _auth=None: {"user_id": user_id, "role": "manager", "role_label": "Quản lý", "active": True},
        )

    _as_manager(pending["nguoi_trinh"])
    nguoi_trinh = (await client.get("/api/v1/my-work")).json()
    _as_manager("U-KHONG-LIEN-QUAN")
    nguoi_khac = (await client.get("/api/v1/my-work")).json()

    assert nguoi_khac["awaiting_my_decision"] > nguoi_trinh["awaiting_my_decision"], (
        "Quản lý khác phải duyệt được hồ sơ mà người trình không được duyệt"
    )
    assert nguoi_trinh["submitted_pending"] >= 1, "hồ sơ vẫn phải hiện ở mục 'tôi đã trình'"
