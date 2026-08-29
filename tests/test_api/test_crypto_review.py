"""Hàng đợi rà soát tiền mã hoá.

Bài đầu tiên là bài quan trọng nhất: giao dịch Bitcoin KHÔNG được biến thành vụ
việc ngân hàng. Dữ liệu Elliptic đã ẩn danh — không tài khoản, không khách hàng
— nên một "vụ việc" như vậy sẽ không điều tra được và không xuất được hồ sơ SAR.
Hàng đợi riêng này tồn tại chính vì lý do đó.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.api import crypto_review, routes
from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def fixtures():
    """Hai chuyên viên, một quản lý và hai giao dịch đã chấm điểm."""
    suffix = uuid.uuid4().hex[:8]
    ids = {
        "lan": f"UC-A-{suffix}"[:20],
        "duc": f"UC-B-{suffix}"[:20],
        "manager": f"UC-M-{suffix}"[:20],
        "tx_hi": f"9{suffix[:8]}1",
        "tx_lo": f"9{suffix[:8]}2",
    }
    try:
        with get_engine().begin() as conn:
            for uid, name, role in (
                (ids["lan"], f"Lan {suffix}", "analyst"),
                (ids["duc"], f"Đức {suffix}", "analyst"),
                (ids["manager"], f"Quản lý {suffix}", "manager"),
            ):
                conn.execute(
                    text(
                        """INSERT INTO app_user(user_id, name, email, role, role_label, active,
                                                password_salt, password_hash)
                           VALUES (:u, :n, :e, :r, :r, true, 's', 'h')"""
                    ),
                    {"u": uid, "n": name, "e": f"{uid}@test.local", "r": role},
                )
            for tx, level, prob in ((ids["tx_hi"], "CRITICAL", 0.93), (ids["tx_lo"], "LOW", 0.04)):
                conn.execute(
                    text(
                        """INSERT INTO bitcoin_scored_tx(tx_id, release_id, illicit_prob,
                                                         predicted_label, risk_level,
                                                         requires_review, headline, caveat)
                           VALUES (:t, 'REL-TEST', :p, :lb, :lv, :rv, 'Kiểm thử', 'Kiểm thử')"""
                    ),
                    {
                        "t": tx,
                        "p": prob,
                        "lb": "illicit" if prob > 0.5 else "licit",
                        "lv": level,
                        "rv": prob > 0.5,
                    },
                )
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")

    yield ids

    with get_engine().begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        conn.execute(text("DELETE FROM crypto_review WHERE tx_id = ANY(:t)"),
                     {"t": [ids["tx_hi"], ids["tx_lo"]]})
        conn.execute(text("DELETE FROM audit_log WHERE actor = ANY(:u)"),
                     {"u": [ids["lan"], ids["duc"], ids["manager"]]})
        conn.execute(text("DELETE FROM bitcoin_scored_tx WHERE tx_id = ANY(:t)"),
                     {"t": [ids["tx_hi"], ids["tx_lo"]]})
        conn.execute(text("DELETE FROM app_user WHERE user_id = ANY(:u)"),
                     {"u": [ids["lan"], ids["duc"], ids["manager"]]})


@pytest.fixture
def as_user(monkeypatch):
    def _apply(user_id: str, role: str) -> None:
        who = {"user_id": user_id, "role": role, "role_label": role, "active": True}
        monkeypatch.setattr(routes, "_require_user", lambda _auth=None: who)
        monkeypatch.setattr(crypto_review, "_user", lambda _auth=None: who)

    return _apply


async def _open(client, tx_id):
    return await client.post(f"/api/v1/fc/bitcoin/{tx_id}/review", json={})


# --------------------------------------------------------------------------- #
# Vì sao hàng đợi này tồn tại
# --------------------------------------------------------------------------- #


def test_giao_dich_bitcoin_khong_gan_duoc_vao_vu_viec_ngan_hang(fixtures) -> None:
    """Ràng buộc ở cơ sở dữ liệu, không phải quy ước.

    `aml_case.subject_account_key` là NOT NULL và trỏ tới `account`. Giao dịch
    Bitcoin không có tài khoản nào, nên đây là lý do kỹ thuật khiến hàng đợi rà
    soát phải tách riêng — bài này giữ cho lý do ấy không bị quên.
    """
    from src.db.session import get_session

    with get_session() as session:
        nullable = session.execute(
            text(
                """SELECT is_nullable FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='aml_case'
                      AND column_name='subject_account_key'"""
            )
        ).scalar_one()

    assert nullable == "NO", "nếu cột này thành nullable, hãy xem lại thiết kế hàng đợi riêng"


# --------------------------------------------------------------------------- #
# Vòng đời
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_mo_luot_ra_soat_chup_lai_diem_luc_mo(client, fixtures, as_user) -> None:
    """Bản chấm điểm nạp lại theo release; lượt rà soát phải giữ con số đã thấy."""
    as_user(fixtures["lan"], "analyst")

    body = (await _open(client, fixtures["tx_hi"])).json()

    assert body["state"] == "TiepNhan"
    assert body["risk_level"] == "CRITICAL"
    assert body["illicit_prob"] == pytest.approx(0.93)
    assert body["opened_by_name"].startswith("Lan")


@pytest.mark.asyncio
async def test_khong_mo_trung_mot_giao_dich_dang_ra_soat(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    await _open(client, fixtures["tx_hi"])

    again = await _open(client, fixtures["tx_hi"])

    assert again.status_code == 409


@pytest.mark.asyncio
async def test_giao_dich_khong_co_that_thi_khong_mo_duoc(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")

    assert (await _open(client, "khong-ton-tai")).status_code == 404


@pytest.mark.asyncio
async def test_nhan_luot_roi_ket_luan(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]

    await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["lan"]}
    )
    body = (
        await client.post(
            f"/api/v1/fc/crypto-reviews/{review_id}/conclude",
            json={"conclusion": "dang_ngo", "note": "Nhiều đối tác đã bị gắn cờ trong đồ thị."},
        )
    ).json()

    assert body["state"] == "KetLuan"
    assert body["conclusion"] == "dang_ngo"
    assert body["concluded_by_name"].startswith("Lan")


@pytest.mark.asyncio
async def test_ket_luan_bat_buoc_neu_ly_do(client, fixtures, as_user) -> None:
    """Kết luận không nói vì sao thì sáu tháng sau không ai dựng lại được."""
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["lan"]}
    )

    response = await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/conclude", json={"conclusion": "dang_ngo", "note": ""}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_da_ket_luan_thi_khong_ket_luan_lai(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["lan"]}
    )
    payload = {"conclusion": "khong_dang_ngo", "note": "Không thấy dấu hiệu bất thường."}
    await client.post(f"/api/v1/fc/crypto-reviews/{review_id}/conclude", json=payload)

    again = await client.post(f"/api/v1/fc/crypto-reviews/{review_id}/conclude", json=payload)

    assert again.status_code == 409


@pytest.mark.asyncio
async def test_ket_luan_xong_thi_mo_lai_duoc_luot_moi(client, fixtures, as_user) -> None:
    """Chỉ mục duy nhất chỉ áp cho lượt CHƯA kết luận — mở lại được, và lượt cũ ở nguyên."""
    as_user(fixtures["lan"], "analyst")
    first = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    await client.post(f"/api/v1/fc/crypto-reviews/{first}/assign", json={"assignee_id": fixtures["lan"]})
    await client.post(
        f"/api/v1/fc/crypto-reviews/{first}/conclude",
        json={"conclusion": "khong_dang_ngo", "note": "Đã rà soát, không có dấu hiệu."},
    )

    second = await _open(client, fixtures["tx_hi"])

    assert second.status_code == 200
    assert second.json()["review_id"] != first


# --------------------------------------------------------------------------- #
# Phân quyền
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_chuyen_vien_khong_giao_luot_cho_nguoi_khac(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]

    response = await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["duc"]}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_quan_ly_giao_duoc_cho_chuyen_vien(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    as_user(fixtures["manager"], "manager")

    body = (
        await client.post(
            f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["duc"]}
        )
    ).json()

    assert body["assignee_id"] == fixtures["duc"]
    assert body["state"] == "DangRaSoat"


@pytest.mark.asyncio
async def test_khong_giao_luot_ra_soat_cho_quan_ly(client, fixtures, as_user) -> None:
    """Cùng luật với hàng đợi vụ việc — hai nơi không dạy hai thói quen khác nhau."""
    as_user(fixtures["manager"], "manager")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]

    response = await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["manager"]}
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_nguoi_khong_giu_luot_thi_khong_ket_luan_duoc(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    await client.post(f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["lan"]})
    as_user(fixtures["duc"], "analyst")

    response = await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/conclude",
        json={"conclusion": "dang_ngo", "note": "Tôi không giữ lượt này."},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_quan_tri_he_thong_khong_mo_duoc_luot(client, fixtures, as_user) -> None:
    as_user("U-ADMIN-CR", "admin")

    assert (await _open(client, fixtures["tx_hi"])).status_code == 403


# --------------------------------------------------------------------------- #
# Vết kiểm toán
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ba_moc_deu_de_lai_vet(client, fixtures, as_user) -> None:
    """Vết đi chung `audit_log`, không dựng bảng nhật ký thứ hai."""
    as_user(fixtures["lan"], "analyst")
    review_id = (await _open(client, fixtures["tx_hi"])).json()["review_id"]
    await client.post(f"/api/v1/fc/crypto-reviews/{review_id}/assign", json={"assignee_id": fixtures["lan"]})
    await client.post(
        f"/api/v1/fc/crypto-reviews/{review_id}/conclude",
        json={"conclusion": "dang_ngo", "note": "Đối tác trong đồ thị đã bị gắn cờ."},
    )

    with get_engine().begin() as conn:
        events = [
            r[0]
            for r in conn.execute(
                text("SELECT event_type FROM audit_log WHERE actor = :a ORDER BY occurred_at"),
                {"a": fixtures["lan"]},
            ).all()
        ]

    assert events == ["crypto_review_opened", "crypto_review_assigned", "crypto_review_concluded"]


@pytest.mark.asyncio
async def test_hang_doi_loc_duoc_theo_trang_thai(client, fixtures, as_user) -> None:
    as_user(fixtures["lan"], "analyst")
    await _open(client, fixtures["tx_hi"])
    await _open(client, fixtures["tx_lo"])

    cho_tiep_nhan = (await client.get("/api/v1/fc/crypto-reviews?state=TiepNhan")).json()
    txs = {r["tx_id"] for r in cho_tiep_nhan}

    assert {fixtures["tx_hi"], fixtures["tx_lo"]} <= txs
