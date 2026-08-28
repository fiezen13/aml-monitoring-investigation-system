"""Các endpoint mà giao diện AML Console gọi.

Chạy trên PostgreSQL thật với batch LI-Small: hợp đồng ở đây là hình dạng
JSON mà React đọc, và một truy vấn sai cột chỉ lộ ra khi có dữ liệu thật để
đọc. Bỏ qua cả nhóm nếu không nối được cơ sở dữ liệu.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import get_engine
from src.domain import INVESTIGATION_CHAIN

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def li_small_loaded():
    """Bỏ qua nếu chưa nạp batch LI-Small — không có gì để khẳng định."""
    try:
        with get_engine().connect() as conn:
            alerts = conn.execute(text("SELECT count(*) FROM alert")).scalar_one()
            cases = conn.execute(text("SELECT count(*) FROM aml_case")).scalar_one()
    except SQLAlchemyError as exc:
        pytest.skip(f"Không nối được PostgreSQL: {exc}")
    if not alerts or not cases:
        pytest.skip("Cơ sở dữ liệu chưa có batch LI-Small")
    return {"alerts": alerts, "cases": cases}


@pytest.mark.asyncio
async def test_dashboard_counts_come_from_the_database(client, li_small_loaded):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert body["open_alerts"] <= li_small_loaded["alerts"]
    assert body["alerts_without_case"] + body["alerts_linked_to_case"] == body["open_alerts"]
    assert body["alerts_without_case"] == 0
    assert body["batch_cases_created"] == body["batch_alerts_created"]
    assert body["cases_investigating"] <= li_small_loaded["cases"]
    assert body["cases_investigating"] == body["cases_total"]
    assert 0 <= body["avg_risk_score"] <= 100
    assert body["typology_distribution"], "phải có ít nhất một typology"
    assert len(body["top_alerts"]) <= 5


@pytest.mark.asyncio
async def test_dashboard_typology_shares_add_up(client, li_small_loaded):
    body = (await client.get("/api/v1/dashboard")).json()
    total = sum(item["share_pct"] for item in body["typology_distribution"])
    # Mỗi phần trăm làm tròn tới một chữ số nên tổng lệch được vài phần mười.
    assert 99 <= total <= 101


@pytest.mark.asyncio
async def test_alerts_are_sorted_by_risk_descending(client, li_small_loaded):
    body = (await client.get("/api/v1/alerts?limit=50")).json()
    scores = [float(a["risk_score"]) for a in body]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_alert_list_filters_by_typology(client, li_small_loaded):
    everything = (await client.get("/api/v1/alerts?limit=200")).json()
    code = everything[0]["typology_code"]
    filtered = (await client.get(f"/api/v1/alerts?typology_code={code}")).json()
    assert filtered
    assert {a["typology_code"] for a in filtered} == {code}


@pytest.mark.asyncio
async def test_alert_list_filters_by_minimum_risk(client, li_small_loaded):
    filtered = (await client.get("/api/v1/alerts?min_risk=80&limit=200")).json()
    assert all(float(a["risk_score"]) >= 80 for a in filtered)


@pytest.mark.asyncio
async def test_alert_detail_always_carries_three_factors(client, li_small_loaded):
    """NT7 — mỗi điểm rủi ro kèm tối thiểu ba yếu tố đóng góp có giá trị số."""
    listing = (await client.get("/api/v1/alerts?limit=200")).json()
    for alert in listing:
        detail = (await client.get(f"/api/v1/alerts/{alert['alert_id']}")).json()
        assert len(detail["reasons"]) >= 3, alert["alert_id"]
        for reason in detail["reasons"]:
            assert float(reason["contribution"]) >= 0
            assert float(reason["weight"]) >= 0


@pytest.mark.asyncio
async def test_alert_detail_includes_subject_and_transactions(client, li_small_loaded):
    alert = (await client.get("/api/v1/alerts?limit=1")).json()[0]
    detail = (await client.get(f"/api/v1/alerts/{alert['alert_id']}")).json()

    assert detail["customer"]["account_key"] == detail["account_key"]
    # Lược đồ cố ý không lưu họ tên; giao diện định danh bằng mã khách hàng.
    assert "name" not in detail["customer"]
    assert all(t["direction"] in ("in", "out") for t in detail["transactions"])


@pytest.mark.asyncio
async def test_unknown_alert_returns_404(client, li_small_loaded):
    response = await client.get("/api/v1/alerts/ALT-khong-ton-tai")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_case_detail_timeline_covers_the_whole_chain(client, li_small_loaded):
    case_id = (await client.get("/api/v1/cases?limit=1")).json()[0]["case_id"]
    detail = (await client.get(f"/api/v1/cases/{case_id}")).json()

    assert [step["state"] for step in detail["timeline"]] == list(INVESTIGATION_CHAIN)
    assert sum(1 for step in detail["timeline"] if step["status"] == "active") <= 1
    # Các bước đã qua phải đứng trước bước hiện tại, không xen kẽ.
    statuses = [step["status"] for step in detail["timeline"]]
    assert statuses == sorted(statuses, key=["done", "active", "pending"].index)


@pytest.mark.asyncio
async def test_case_page_reports_total_and_uses_server_pagination(client, li_small_loaded):
    first = (await client.get("/api/v1/cases/page?page=1&page_size=10")).json()
    second = (await client.get("/api/v1/cases/page?page=2&page_size=10")).json()

    assert first["total"] >= len(first["rows"])
    assert first["page"] == 1
    assert first["pageSize"] == 10
    assert {row["case_id"] for row in first["rows"]}.isdisjoint(
        {row["case_id"] for row in second["rows"]}
    )


@pytest.mark.asyncio
async def test_investigating_a_case_awaiting_approval_is_refused(client, li_small_loaded):
    """Người bấm nút phải nhận được lời từ chối, không phải sự im lặng."""
    cases = (await client.get("/api/v1/cases?state=ChoNguoiPheDuyet")).json()
    if not cases:
        pytest.skip("Không có vụ việc nào đang chờ phê duyệt")

    response = await client.post(f"/api/v1/cases/{cases[0]['case_id']}/investigate")
    assert response.status_code == 409
    assert "phê duyệt" in response.json()["detail"]


@pytest.mark.asyncio
async def test_investigating_an_unknown_case_returns_404(client, li_small_loaded):
    response = await client.post("/api/v1/cases/CASE-khong-ton-tai/investigate")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_audit_feed_is_newest_first(client, li_small_loaded):
    body = (await client.get("/api/v1/audit?limit=50")).json()
    times = [event["occurred_at"] for event in body]
    assert times == sorted(times, reverse=True)


@pytest.mark.asyncio
async def test_audit_feed_filters_by_event_type(client, li_small_loaded):
    body = (await client.get("/api/v1/audit?event_type=case_state_changed&limit=50")).json()
    assert all(event["event_type"] == "case_state_changed" for event in body)
