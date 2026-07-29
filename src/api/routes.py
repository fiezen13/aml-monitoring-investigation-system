from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.agents.graph import agent
from src.db.session import get_session
from src.models.schemas import (
    AlertReasonOut,
    CaseDetailOut,
    CaseOut,
    ChatRequest,
    ChatResponse,
    QueueStatsOut,
)
from src.services import queue

router = APIRouter()


@router.get("/cases", response_model=list[CaseOut])
async def list_cases(
    state: str | None = Query(default=None, description="Lọc theo trạng thái máy trạng thái"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CaseOut]:
    """Hàng đợi vụ việc, xếp theo điểm rủi ro giảm dần."""
    sql = """
        SELECT c.case_id, c.subject_account_key, c.title, c.state, c.risk_score,
               c.priority, c.assigned_to, c.created_at,
               (SELECT count(*) FROM alert a WHERE a.case_id = c.case_id) AS alert_count
          FROM aml_case c
         -- Ép kiểu tường minh: với tham số NULL không có ngữ cảnh, PostgreSQL
         -- không suy ra được kiểu và từ chối câu lệnh.
         WHERE (CAST(:state AS text) IS NULL OR c.state = CAST(:state AS text))
         ORDER BY c.risk_score DESC, c.created_at DESC
         LIMIT :limit
    """
    with get_session() as session:
        rows = session.execute(text(sql), {"state": state, "limit": limit}).mappings().all()
    return [CaseOut(**row) for row in rows]


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
async def get_case(case_id: str) -> CaseDetailOut:
    """Chi tiết một vụ việc kèm các yếu tố đóng góp.

    Mọi cảnh báo trả về ở đây phải có tối thiểu ba yếu tố có giá trị số (NT7).
    """
    with get_session() as session:
        case = (
            session.execute(
                text(
                    """SELECT case_id, subject_account_key, title, state, risk_score, priority, assigned_to, created_at,
                          (SELECT count(*) FROM alert a WHERE a.case_id = c.case_id) AS alert_count
                     FROM aml_case c WHERE case_id = :case_id"""
                ),
                {"case_id": case_id},
            )
            .mappings()
            .first()
        )
        if case is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy vụ việc {case_id}")

        reasons = (
            session.execute(
                text(
                    """SELECT r.factor_code, r.factor_label, r.contribution, r.weight, a.detector, a.typology_code
                     FROM alert_reason r
                     JOIN alert a ON a.alert_id = r.alert_id
                    WHERE a.case_id = :case_id
                    ORDER BY r.contribution DESC"""
                ),
                {"case_id": case_id},
            )
            .mappings()
            .all()
        )

        evidence_count = session.execute(
            text("SELECT count(*) FROM evidence WHERE case_id = :case_id"), {"case_id": case_id}
        ).scalar_one()

        # NT4 — mọi lần xem hồ sơ đều vào nhật ký, không chỉ các thao tác ghi.
        session.execute(
            text(
                """INSERT INTO audit_log (case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'case_viewed', 'api', 'system', '{}'::jsonb)"""
            ),
            {"case_id": case_id},
        )

    return CaseDetailOut(
        **case,
        evidence_count=evidence_count,
        reasons=[AlertReasonOut(**r) for r in reasons],
    )


@router.post("/cases/{case_id}/investigate")
async def investigate(case_id: str) -> dict[str, str]:
    """Giao tác vụ điều tra cho worker.

    Trả về ngay: một lượt điều tra chạy hàng phút, không nằm vừa trong vòng
    đời một request (ARC-001 mục 6).
    """
    with get_session() as session:
        exists = session.execute(text("SELECT 1 FROM aml_case WHERE case_id = :case_id"), {"case_id": case_id}).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy vụ việc {case_id}")

    job_id = queue.enqueue("investigate_case", {"case_id": case_id})
    return {"job_id": job_id, "case_id": case_id, "status": "queued"}


@router.get("/queue", response_model=QueueStatsOut)
async def queue_stats() -> QueueStatsOut:
    return QueueStatsOut(depth=queue.queue_depth(), worker_alive=queue.worker_alive())


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent."""
    try:
        result = await agent.ainvoke({"query": request.message})
        return ChatResponse(
            response=result.get("response", ""),
            analysis=result.get("analysis", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
