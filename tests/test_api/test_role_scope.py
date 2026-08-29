"""Phạm vi dữ liệu theo VAI — cho cả màn hình lẫn trợ lý AI.

Chuyên viên và Quản lý dùng chung một endpoint trò chuyện và chung một danh sách
hồ sơ. Nếu phạm vi không bị ép ở máy chủ, chuyên viên hỏi "hồ sơ nào đang chờ
duyệt" sẽ nghe về cả hồ sơ đồng nghiệp vừa trình, kèm mức rủi ro và quyết định
của quản lý — một lỗ rò không thấy được qua giao diện vì giao diện có ẩn gì đâu.

Đây từng là lỗ hổng thật: `/sars` và ngữ cảnh trợ lý đều không lọc gì.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.api import routes
from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def two_specialists():
    """Hai chuyên viên, mỗi người một hồ sơ đã trình."""
    suffix = uuid.uuid4().hex[:8]
    ids = {
        "an": f"US-A-{suffix}"[:20],
        "binh": f"US-B-{suffix}"[:20],
        "customer": f"USC-{suffix}",
        "account": f"996:{suffix}",
        "case_an": f"US-CASE-{suffix}-A",
        "case_binh": f"US-CASE-{suffix}-B",
    }
    try:
        with get_engine().begin() as conn:
            for uid, name in ((ids["an"], f"An {suffix}"), (ids["binh"], f"Bình {suffix}")):
                conn.execute(
                    text(
                        """INSERT INTO app_user(user_id, name, email, role, role_label, active,
                                                password_salt, password_hash)
                           VALUES (:u, :n, :e, 'analyst', 'Chuyên viên', true, 's', 'h')"""
                    ),
                    {"u": uid, "n": name, "e": f"{uid}@test.local"},
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
                       VALUES (:a, :c, '996', :n, DATE '2026-01-01')"""
                ),
                {"a": ids["account"], "c": ids["customer"], "n": suffix},
            )
            for case_id, owner in ((ids["case_an"], ids["an"]), (ids["case_binh"], ids["binh"])):
                conn.execute(
                    text(
                        """INSERT INTO aml_case (case_id, subject_account_key, title, state,
                                                 risk_score, priority, assigned_to)
                           VALUES (:id, :a, 'Hồ sơ kiểm thử', 'ChoNguoiPheDuyet', 90, 'high', :o)"""
                    ),
                    {"id": case_id, "a": ids["account"], "o": owner},
                )
                conn.execute(
                    text(
                        """INSERT INTO sar_draft(sar_draft_id, case_id, version, status)
                           VALUES (:s, :c, 1, 'submitted_for_approval')"""
                    ),
                    {"s": f"SAR-{case_id}", "c": case_id},
                )
                conn.execute(
                    text(
                        """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                           VALUES (:c, 'submitted_for_approval', :a, 'analyst', '{}'::jsonb)"""
                    ),
                    {"c": case_id, "a": owner},
                )
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")

    yield ids

    with get_engine().begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        cases = [ids["case_an"], ids["case_binh"]]
        conn.execute(text("DELETE FROM approval WHERE case_id = ANY(:c)"), {"c": cases})
        conn.execute(text("DELETE FROM sar_statement WHERE sar_draft_id = ANY(:s)"),
                     {"s": [f"SAR-{c}" for c in cases]})
        conn.execute(text("DELETE FROM sar_draft WHERE case_id = ANY(:c)"), {"c": cases})
        conn.execute(text("DELETE FROM audit_log WHERE case_id = ANY(:c)"), {"c": cases})
        conn.execute(text("DELETE FROM aml_case WHERE case_id = ANY(:c)"), {"c": cases})
        conn.execute(text("DELETE FROM account WHERE account_key = :a"), {"a": ids["account"]})
        conn.execute(text("DELETE FROM customer WHERE customer_id = :c"), {"c": ids["customer"]})
        conn.execute(text("DELETE FROM app_user WHERE user_id = ANY(:u)"), {"u": [ids["an"], ids["binh"]]})


@pytest.fixture
def as_user(monkeypatch):
    def _apply(user_id: str, role: str) -> None:
        monkeypatch.setattr(
            routes,
            "_require_user",
            lambda _auth=None: {"user_id": user_id, "role": role, "role_label": role, "active": True},
        )

    return _apply


# --------------------------------------------------------------------------- #
# Danh sách hồ sơ
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_chuyen_vien_khong_doc_duoc_ho_so_cua_dong_nghiep(client, two_specialists, as_user) -> None:
    as_user(two_specialists["an"], "analyst")

    ids = [s["sar_id"] for s in (await client.get("/api/v1/sars")).json()]

    assert f"SAR-{two_specialists['case_an']}" in ids
    assert f"SAR-{two_specialists['case_binh']}" not in ids, "đọc được hồ sơ của người khác"


@pytest.mark.asyncio
async def test_quan_ly_van_thay_toan_hang_doi(client, two_specialists, as_user) -> None:
    """Siết phạm vi cho chuyên viên mà chặn nhầm Quản lý thì hàng đợi phê duyệt rỗng."""
    as_user("U-MGR-TEST", "manager")

    ids = [s["sar_id"] for s in (await client.get("/api/v1/sars")).json()]

    assert f"SAR-{two_specialists['case_an']}" in ids
    assert f"SAR-{two_specialists['case_binh']}" in ids


# --------------------------------------------------------------------------- #
# Ngữ cảnh của trợ lý
# --------------------------------------------------------------------------- #


def test_ngu_canh_tro_ly_cua_chuyen_vien_chi_co_ho_so_cua_ho(two_specialists) -> None:
    """Chốt thật nằm ở NGỮ CẢNH, không ở lời nhắc.

    Dặn mô hình "đừng nói về hồ sơ người khác" mà vẫn đưa dữ liệu của họ vào thì
    chỉ cần một câu hỏi khéo là rò. Ở đây dữ liệu ấy không có mặt.
    """
    from src.db.session import get_session

    with get_session() as session:
        trusted, _ = routes._sar_queue_context(session, own_only_for=two_specialists["an"])

    ids = {r["sar_id"] for r in trusted["danh_sach_ho_so"]}
    assert f"SAR-{two_specialists['case_an']}" in ids
    assert f"SAR-{two_specialists['case_binh']}" not in ids


def test_ngu_canh_khong_con_ten_truong_ky_thuat(two_specialists) -> None:
    """Khoá tiếng Việt: mô hình đọc lại nguyên văn thứ nó được đưa.

    Đưa `awaiting_decision` thì câu trả lời hiện ra tên trường, và rào chắn đầu
    ra phải chặn một câu vốn đúng nội dung — trợ lý thành vô dụng.
    """
    from src.db.session import get_session

    with get_session() as session:
        trusted, _ = routes._sar_queue_context(session, own_only_for=two_specialists["an"])

    keys = set().union(*(set(r) for r in trusted["danh_sach_ho_so"]), set(trusted["tong_hop"]))
    for cam in ("awaiting_decision", "sar_status", "risk_score", "uncited_statements"):
        assert cam not in keys, f"khoá kỹ thuật còn trong ngữ cảnh: {cam}"


def test_ngu_canh_cua_quan_ly_khong_bi_gioi_han(two_specialists) -> None:
    from src.db.session import get_session

    with get_session() as session:
        trusted, _ = routes._sar_queue_context(session)

    ids = {r["sar_id"] for r in trusted["danh_sach_ho_so"]}
    assert {f"SAR-{two_specialists['case_an']}", f"SAR-{two_specialists['case_binh']}"} <= ids


# --------------------------------------------------------------------------- #
# Hồ sơ tôi đã trình
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ho_so_toi_da_trinh_chi_co_cua_toi(client, two_specialists, as_user) -> None:
    as_user(two_specialists["an"], "analyst")

    rows = (await client.get("/api/v1/my-sars")).json()

    assert [r["case_id"] for r in rows] == [two_specialists["case_an"]]


@pytest.mark.asyncio
async def test_ho_so_bi_tu_choi_hien_ro_ly_do(client, two_specialists, as_user) -> None:
    """Lý do trả lại là thứ chuyên viên cần nhất — và trước đây không thấy ở đâu."""
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """INSERT INTO approval(approval_id, case_id, sar_draft_id, decision, decided_by, reason, decided_at)
                   VALUES (:a, :c, :s, 'rejected', :who, 'Thiếu bằng chứng cho hai nhận định.', now())"""
            ),
            {
                "a": f"APR-{two_specialists['case_an']}",
                "c": two_specialists["case_an"],
                "s": f"SAR-{two_specialists['case_an']}",
                "who": two_specialists["binh"],
            },
        )
    as_user(two_specialists["an"], "analyst")

    row = (await client.get("/api/v1/my-sars")).json()[0]

    assert row["decision"] == "rejected"
    assert "Thiếu bằng chứng" in row["reason"]


@pytest.mark.asyncio
async def test_chua_trinh_ho_so_nao_thi_danh_sach_rong(client, two_specialists, as_user) -> None:
    as_user("U-CHUA-TRINH", "analyst")

    assert (await client.get("/api/v1/my-sars")).json() == []


@pytest.mark.asyncio
async def test_ho_so_trinh_lai_chi_hien_mot_dong(client, two_specialists, as_user) -> None:
    """Trả lại rồi trình lại sinh HAI bản ghi phê duyệt cho cùng một hồ sơ.

    Nối thẳng bảng `approval` thì hồ sơ hiện hai dòng với hai kết quả trái nhau
    ("cần bổ sung" và "đã duyệt") — chuyên viên không biết tin dòng nào. Danh
    sách này trả lời "hồ sơ đang ở đâu", nên chỉ lấy quyết định MỚI NHẤT.
    """
    case_id = two_specialists["case_an"]
    sar_id = f"SAR-{case_id}"
    with get_engine().begin() as conn:
        for suffix, decision, reason, minutes in (
            ("old", "more_info", "Bổ sung chứng từ nguồn tiền.", 120),
            ("new", "approved", "Đã đủ chứng từ, đồng ý báo cáo.", 5),
        ):
            conn.execute(
                text(
                    """INSERT INTO approval(approval_id, case_id, sar_draft_id, decision,
                                            decided_by, reason, decided_at)
                       VALUES (:a, :c, :s, :d, :who, :r, now() - make_interval(mins => :m))"""
                ),
                {
                    "a": f"APR-{case_id}-{suffix}",
                    "c": case_id,
                    "s": sar_id,
                    "d": decision,
                    "who": two_specialists["binh"],
                    "r": reason,
                    "m": minutes,
                },
            )
    as_user(two_specialists["an"], "analyst")

    rows = (await client.get("/api/v1/my-sars")).json()

    assert len(rows) == 1, "cùng một hồ sơ không được hiện hai dòng"
    assert rows[0]["decision"] == "approved", "phải là quyết định mới nhất"
    assert "đồng ý báo cáo" in rows[0]["reason"]
