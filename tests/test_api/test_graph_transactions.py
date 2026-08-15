"""Tầng giao dịch của đồ thị mạng lưới.

Chạy trên PostgreSQL thật vì hợp đồng cần kiểm ở đây là một phép JOIN: cạnh
trong `fc.relationship` phải nối được xuống dòng trong `transaction` qua
`fc.entity.attributes->>'account_key'`. Mock cái join đó đi thì bài test chỉ
còn khẳng định lại chính đoạn mã đang viết — mà lỗi thật trước đây nằm đúng ở
chỗ khoá nối không ổn định giữa hai lần chạy.

Bỏ qua cả nhóm nếu chưa nạp mô phỏng ABM.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def linked():
    """Số cạnh có giao dịch thật đứng sau. Bỏ qua nếu chưa nạp ABM."""
    try:
        with get_engine().connect() as conn:
            entities = conn.execute(
                text("SELECT count(*) FROM fc.entity WHERE attributes ? 'account_key'")
            ).scalar_one()
            pairs = conn.execute(
                text(
                    """SELECT count(DISTINCT (src.entity_id, dst.entity_id))
                         FROM transaction t
                         JOIN fc.entity src ON src.attributes ->> 'account_key' = t.from_account_key
                         JOIN fc.entity dst ON dst.attributes ->> 'account_key' = t.to_account_key"""
                )
            ).scalar_one()
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")
    if not entities or not pairs:
        pytest.skip("Chưa có dữ liệu Graph LI-Small")
    return {"entities": entities, "pairs": pairs}


@pytest.mark.asyncio
async def test_graph_edges_carry_transaction_evidence(client, linked):
    """Cạnh mang số đo tổng hợp từ sổ cái, không phải từ chính bảng quan hệ."""
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    assert response.status_code == 200
    edges = response.json()["edges"]

    assert edges, "Đồ thị rỗng — mô phỏng chưa được nạp"
    for edge in edges:
        assert "tx_count" in edge
        assert "amounts_by_currency" in edge
        assert edge["tx_count"] >= 0

    with_tx = [e for e in edges if e["tx_count"] > 0]
    assert with_tx, "Không cạnh nào nối được xuống giao dịch — phép join đã hỏng"

    for edge in with_tx:
        # Có giao dịch thì phải có cả mốc đầu và mốc cuối; thiếu một trong hai
        # nghĩa là phần gộp đã bỏ sót nhánh nào đó.
        assert edge["tx_first_seen"] is not None
        assert edge["tx_last_seen"] is not None
        assert edge["tx_first_seen"] <= edge["tx_last_seen"]
        assert edge["amounts_by_currency"], "Có giao dịch nhưng không có số tiền theo loại tiền"
        assert all(v > 0 for v in edge["amounts_by_currency"].values())


@pytest.mark.asyncio
async def test_amounts_are_never_summed_across_currencies(client, linked):
    """Nhiều loại tiền phải nằm ở nhiều khoá, không cộng thành một số.

    Cộng 120.000 USD với 45.000 EUR thành 165.000 là sai về nghiệp vụ và
    analyst không thể phát hiện ra khi chỉ nhìn thấy một con số.
    """
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    edges = response.json()["edges"]

    with get_engine().connect() as conn:
        rows = (
            conn.execute(
                text(
                    """SELECT src.entity_id AS s, dst.entity_id AS t, t.currency, sum(t.amount) AS total
                     FROM transaction t
                     JOIN fc.entity src ON src.attributes ->> 'account_key' = t.from_account_key
                     JOIN fc.entity dst ON dst.attributes ->> 'account_key' = t.to_account_key
                    GROUP BY 1, 2, 3"""
                )
            )
            .mappings()
            .all()
        )

    expected: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        expected.setdefault((r["s"], r["t"]), {})[r["currency"]] = float(r["total"])

    checked = 0
    for edge in edges:
        want = expected.get((edge["s"], edge["t"]))
        if want is None:
            continue
        got = edge["amounts_by_currency"]
        assert set(got) == set(want), f"Thiếu/thừa loại tiền ở cạnh {edge['id']}"
        for ccy, total in want.items():
            assert got[ccy] == pytest.approx(total, rel=1e-6)
        checked += 1
    assert checked, "Không đối chiếu được cạnh nào với sổ cái"


@pytest.mark.asyncio
async def test_edge_transactions_endpoint_returns_the_underlying_rows(client, linked):
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    edge = next(e for e in response.json()["edges"] if e["tx_count"] > 0)

    page = await client.get(f"/api/v1/fc/graph/edges/{edge['id']}/transactions", params={"page_size": 200})
    assert page.status_code == 200
    body = page.json()

    assert body["total"] == edge["tx_count"], "Tổng của trang không khớp số đo trên cạnh"
    assert len(body["rows"]) == edge["tx_count"]
    # Mỗi dòng phải đúng là một giao dịch giữa hai tài khoản của cạnh đó, không
    # phải giao dịch bất kỳ của một trong hai đầu.
    froms = {r["from_account"] for r in body["rows"]}
    tos = {r["to_account"] for r in body["rows"]}
    assert len(froms) == 1 and len(tos) == 1


@pytest.mark.asyncio
async def test_edge_without_banking_transactions_returns_empty_not_error(client, linked):
    """Quan hệ sở hữu / thiết bị không có giao dịch — đó là câu trả lời hợp lệ."""
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    edges = response.json()["edges"]
    structural = next(e for e in edges if e["kind"] in {"owns", "device", "control"})

    assert structural["tx_count"] == 0
    assert structural["amounts_by_currency"] == {}

    page = await client.get(f"/api/v1/fc/graph/edges/{structural['id']}/transactions")
    assert page.status_code == 200
    assert page.json()["total"] == 0
    assert page.json()["rows"] == []


@pytest.mark.asyncio
async def test_edge_transactions_paginate(client, linked):
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    edge = max((e for e in response.json()["edges"] if e["tx_count"] > 1), key=lambda e: e["tx_count"])

    first = await client.get(f"/api/v1/fc/graph/edges/{edge['id']}/transactions", params={"page_size": 1, "page": 1})
    second = await client.get(f"/api/v1/fc/graph/edges/{edge['id']}/transactions", params={"page_size": 1, "page": 2})

    assert first.json()["total"] == second.json()["total"] == edge["tx_count"]
    assert len(first.json()["rows"]) == len(second.json()["rows"]) == 1
    assert first.json()["rows"][0]["id"] != second.json()["rows"][0]["id"]


@pytest.mark.asyncio
async def test_unknown_edge_is_404_not_empty_page(client, linked):
    """Cạnh không tồn tại khác hẳn cạnh không có giao dịch — không được lẫn."""
    page = await client.get("/api/v1/fc/graph/edges/REL-KHONG-CO/transactions")
    assert page.status_code == 404


@pytest.mark.asyncio
async def test_node_transactions_cover_both_directions(client, linked):
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    edge = next(e for e in response.json()["edges"] if e["tx_count"] > 0)

    both = await client.get(f"/api/v1/fc/graph/nodes/{edge['t']}/transactions", params={"page_size": 200})
    incoming = await client.get(
        f"/api/v1/fc/graph/nodes/{edge['t']}/transactions", params={"direction": "in", "page_size": 200}
    )
    outgoing = await client.get(
        f"/api/v1/fc/graph/nodes/{edge['t']}/transactions", params={"direction": "out", "page_size": 200}
    )

    assert both.json()["total"] == incoming.json()["total"] + outgoing.json()["total"]
    assert incoming.json()["total"] >= edge["tx_count"]


@pytest.mark.asyncio
async def test_non_account_entity_has_no_ledger(client, linked):
    """Thiết bị, ví hay con người không có tài khoản ngân hàng — trả rỗng, không lỗi."""
    response = await client.get("/api/v1/fc/graph", params={"limit": 400})
    device = next(n for n in response.json()["nodes"] if n["type"] == "device")

    page = await client.get(f"/api/v1/fc/graph/nodes/{device['id']}/transactions")
    assert page.status_code == 200
    assert page.json()["total"] == 0


def test_account_keys_are_stable_across_runs(linked):
    """Khoá nối phải tất định.

    Đây là lỗi gốc khiến đồ thị và sổ cái không nối được với nhau: bộ sinh dùng
    `hash()` của Python, mà hàm đó bị randomize theo tiến trình. Test này khoá
    lại hành vi mới — băm blake2b — bằng cách tính lại khoá từ entity_id và so
    với thứ đang nằm trong cơ sở dữ liệu.
    """
    import hashlib

    with get_engine().connect() as conn:
        rows = (
            conn.execute(
                text(
                    """SELECT entity_id, attributes ->> 'bank_code' AS bank,
                          attributes ->> 'account_key' AS key
                     FROM fc.entity
                    WHERE attributes ? 'account_key'"""
                )
            )
            .mappings()
            .all()
        )

    assert rows
    for r in rows:
        # Phần số mới là thứ phải tất định. Mã ngân hàng lấy từ thuộc tính của
        # thực thể, và một số thực thể không khai báo nên bộ sinh gán luân
        # phiên — chỗ đó phụ thuộc thứ tự sinh chứ không phụ thuộc entity_id.
        digest = hashlib.blake2b(r["entity_id"].encode(), digest_size=6).digest()
        number = int.from_bytes(digest, "big") % 9_000_000 + 1_000_000
        bank, _, got = r["key"].partition(":")
        assert got == str(number), f"Khoá của {r['entity_id']} không tái tạo được"
        assert bank, "account_key thiếu mã ngân hàng"
        if r["bank"]:
            assert bank == r["bank"]
