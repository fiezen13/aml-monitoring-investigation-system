"""World Monitor ở chế độ vận hành.

Chạy trên PostgreSQL thật: hợp đồng ở đây là hình dạng JSON mà bản đồ React
đọc, và một truy vấn sai cột chỉ lộ ra khi có dữ liệu thật. Bỏ qua cả nhóm nếu
chưa nạp địa lý ngân hàng.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def located():
    try:
        with get_engine().connect() as conn:
            banks = conn.execute(text("SELECT count(*) FROM bank")).scalar_one()
            geo = conn.execute(text("SELECT count(*) FROM country_geo")).scalar_one()
            hubs = conn.execute(text("SELECT count(*) FROM edge_country_hub")).scalar_one()
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")
    if not banks or not geo:
        pytest.skip("Chưa chạy scripts/load_bank_geography.py")
    # Nạp địa lý xong KHÔNG có nghĩa rollup đã dựng: rollup vận hành gắn với
    # một edge-model release đang hoạt động, và release đó là artifact huấn
    # luyện riêng. Thiếu nó thì bản đồ vận hành không có gì để khẳng định —
    # phải bỏ qua, không phải báo hỏng.
    if not hubs:
        pytest.skip("Chưa có edge-model release đang hoạt động; rollup vận hành rỗng")
    return {"banks": banks, "countries": geo, "hubs": hubs}


@pytest.mark.asyncio
async def test_operational_map_is_built_from_real_accounts(client, located):
    response = await client.get("/api/v1/world", params={"mode": "operational"})
    assert response.status_code == 200
    body = response.json()

    assert body["data_mode"] == "operational"
    assert body["geography_available"] is True
    assert body["hubs"], "đã nạp địa lý mà bản đồ vẫn rỗng"
    for hub in body["hubs"]:
        assert hub["entities"] > 0, hub["id"]
        assert -90 <= hub["lat"] <= 90 and -180 <= hub["lon"] <= 180


@pytest.mark.asyncio
async def test_the_map_states_how_much_of_it_is_assigned(client, located):
    """Phần gán không được im lặng: bản đồ trông đầy đủ nhưng nền là suy diễn."""
    body = (await client.get("/api/v1/world", params={"mode": "operational"})).json()
    assert body["limitation"]
    assert "gán" in body["limitation"]


@pytest.mark.asyncio
async def test_flows_are_cross_border_and_anchored_to_hub_coordinates(client, located):
    body = (await client.get("/api/v1/world", params={"mode": "operational"})).json()
    coords = {hub["id"]: (hub["lat"], hub["lon"]) for hub in body["hubs"]}

    for flow in body["flows"]:
        assert flow["source_hub"] != flow["target_hub"], "hành lang trong nước không vẽ được thành cung"
        assert (flow["slat"], flow["slon"]) == coords[flow["source_hub"]]
        assert (flow["tlat"], flow["tlon"]) == coords[flow["target_hub"]]
        assert flow["txn_count"] > 0


@pytest.mark.asyncio
async def test_jurisdiction_risk_is_not_invented_for_operational_data(client, located):
    """Gán quốc gia là mô tả dữ liệu; gán mức rủi ro pháp vực là quyết định
    chính sách và theo fc.hub thì phải có ngày hiệu lực."""
    body = (await client.get("/api/v1/world", params={"mode": "operational"})).json()
    assert {hub["jurisdiction_risk"] for hub in body["hubs"]} == {"unknown"}
