import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    # Phải báo đúng tầng tác tử đang chạy, không phải tên khung mẫu.
    assert body["runtime"] == "fin07.investigation.workflow"
    assert body["agents"] == [
        "investigation_supervisor",
        "explanation_agent",
        "evidence_critic",
    ]
    assert body["max_agent_iterations"] >= 1


def test_moc_thoi_gian_cua_vu_viec_chi_co_mot_dinh_nghia() -> None:
    """Bản kể đồ thị và bản giải thích phải đo trên CÙNG một cửa sổ.

    Bản kể từng tự neo vào giao dịch mới nhất MỌI THỜI ĐIỂM, còn phiên điều tra
    neo vào giao dịch mới nhất TÍNH ĐẾN LÚC CÓ CẢNH BÁO. Tài khoản còn giao dịch
    sau khi cảnh báo nổ thì hai cửa sổ 30 ngày lệch nhau, và cùng một vụ hiện ra
    hai bộ số: "tiền vào từ đâu" nói 13 979.96 còn tóm tắt nói 12 068.26.
    """
    import inspect

    from src.api import fc_routes
    from src.investigation.repository import InvestigationRepository, snapshot_time

    # Kho điều tra không còn tự tính mốc: nó gọi đúng hàm dùng chung.
    assert "snapshot_time(" in inspect.getsource(InvestigationRepository._snapshot_time)
    # Endpoint bản kể cũng gọi đúng hàm ấy khi biết vụ việc.
    assert "snapshot_time(" in inspect.getsource(fc_routes.graph_narrative)
    assert callable(snapshot_time)
