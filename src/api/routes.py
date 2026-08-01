from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.agents.graph import agent
from src.db.session import get_session
from src.domain import (
    INVESTIGATION_CHAIN,
    next_state,
    state_label,
    typology_label,
)
from src.models.schemas import (
    AlertDetailOut,
    AlertOut,
    AlertReasonOut,
    AuditEventOut,
    CaseDetailOut,
    CaseOut,
    CaseTimelineStepOut,
    ChatRequest,
    ChatResponse,
    CustomerOut,
    DashboardOut,
    InvestigateOut,
    QueueStatsOut,
    TransactionOut,
    TypologyShareOut,
)
from src.services import queue

router = APIRouter()

# Hồ sơ chủ thể luôn lấy kèm tài khoản: giao diện cần cả hai và tách ra thành
# hai truy vấn chỉ đẻ thêm một vòng đi–về mà không đổi kết quả.
_CUSTOMER_SELECT = """
    SELECT c.customer_id, a.account_key, c.customer_type, c.prototype, c.occupation,
           c.declared_income_band, c.expected_monthly_volume, c.registered_country,
           c.risk_rating, c.onboarding_date, a.status AS account_status, a.bank_code
      FROM account a
      JOIN customer c ON c.customer_id = a.customer_id
     WHERE a.account_key = :account_key
"""


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

        customer = (
            session.execute(text(_CUSTOMER_SELECT), {"account_key": case["subject_account_key"]}).mappings().first()
        )

        alert_ids = list(
            session.execute(
                text("SELECT alert_id FROM alert WHERE case_id = :case_id ORDER BY risk_score DESC"),
                {"case_id": case_id},
            ).scalars()
        )

        # Mốc thời gian của từng bước lấy từ nhật ký kiểm toán — đó là nơi duy
        # nhất ghi lại vụ việc đã đi qua trạng thái nào lúc nào. Bảng aml_case
        # chỉ giữ trạng thái hiện tại.
        transitions = (
            session.execute(
                text(
                    """SELECT payload ->> 'to' AS to_state, min(occurred_at) AS occurred_at
                         FROM audit_log
                        WHERE case_id = :case_id AND event_type = 'case_state_changed'
                        GROUP BY payload ->> 'to'"""
                ),
                {"case_id": case_id},
            )
            .mappings()
            .all()
        )

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
        customer=CustomerOut(**customer) if customer else None,
        alert_ids=alert_ids,
        timeline=_build_timeline(case["state"], {t["to_state"]: t["occurred_at"] for t in transitions}),
    )


def _build_timeline(current: str, reached_at: dict[str, object]) -> list[CaseTimelineStepOut]:
    """Dựng dòng thời gian điều tra từ trạng thái hiện tại.

    Vụ việc đứng ở đâu trên chuỗi thì mọi bước trước đó coi như đã xong, kể
    cả khi nhật ký không có dòng chuyển trạng thái tương ứng — dữ liệu seed
    đặt thẳng trạng thái ban đầu mà không đi qua worker.
    """
    try:
        current_index = INVESTIGATION_CHAIN.index(current)
    except ValueError:
        # Trạng thái kết thúc: toàn bộ chuỗi điều tra đã đi qua.
        current_index = len(INVESTIGATION_CHAIN)

    steps: list[CaseTimelineStepOut] = []
    for index, state in enumerate(INVESTIGATION_CHAIN):
        if index < current_index:
            status = "done"
        elif index == current_index:
            status = "active"
        else:
            status = "pending"
        steps.append(
            CaseTimelineStepOut(
                state=state,
                label=state_label(state),
                status=status,
                occurred_at=reached_at.get(state),  # type: ignore[arg-type]
            )
        )
    return steps


@router.post("/cases/{case_id}/investigate", response_model=InvestigateOut)
async def investigate(case_id: str) -> InvestigateOut:
    """Giao tác vụ điều tra cho worker.

    Trả về ngay: một lượt điều tra chạy hàng phút, không nằm vừa trong vòng
    đời một request (ARC-001 mục 6). Giao diện theo dõi tiến độ bằng cách
    đọc lại trạng thái vụ việc và nhật ký kiểm toán.
    """
    with get_session() as session:
        row = (
            session.execute(text("SELECT state FROM aml_case WHERE case_id = :case_id"), {"case_id": case_id})
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy vụ việc {case_id}")

    current = row["state"]
    # Từ chối ngay ở đây thay vì để worker nhận rồi im lặng bỏ qua: người bấm
    # nút cần biết vì sao không có gì xảy ra.
    if next_state(current) is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Vụ việc đang ở '{state_label(current)}' — bước tiếp theo cần quyết định "
                "của người phê duyệt, không phải một lượt chạy tự động (NT3)."
            ),
        )

    job_id = queue.enqueue("investigate_case", {"case_id": case_id})
    return InvestigateOut(job_id=job_id, case_id=case_id, status="queued", state_before=current)


# ---------------------------------------------------------------------
# Cảnh báo
# ---------------------------------------------------------------------

_ALERT_SELECT = """
    SELECT al.alert_id, al.account_key, ac.customer_id, c.occupation, c.risk_rating,
           al.typology_code, al.detector, al.risk_score, al.status, al.case_id, al.created_at,
           (SELECT count(*) FROM alert_reason r WHERE r.alert_id = al.alert_id) AS factor_count
      FROM alert al
      JOIN account ac  ON ac.account_key = al.account_key
      JOIN customer c  ON c.customer_id  = ac.customer_id
"""


def _alert_out(row: dict) -> AlertOut:
    return AlertOut(**row, typology_label=typology_label(row["typology_code"]))


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    status: str | None = Query(default=None, description="open | grouped | closed"),
    typology_code: str | None = Query(default=None, description="Mã typology T01–T10"),
    min_risk: float = Query(default=0, ge=0, le=100, description="Ngưỡng điểm rủi ro tối thiểu"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertOut]:
    """Hàng đợi cảnh báo, xếp theo điểm rủi ro giảm dần."""
    sql = (
        _ALERT_SELECT
        + """
         WHERE (CAST(:status AS text) IS NULL OR al.status = CAST(:status AS text))
           AND (CAST(:typology_code AS text) IS NULL OR al.typology_code = CAST(:typology_code AS text))
           AND al.risk_score >= :min_risk
         ORDER BY al.risk_score DESC, al.created_at DESC
         LIMIT :limit
    """
    )
    with get_session() as session:
        rows = (
            session.execute(
                text(sql),
                {"status": status, "typology_code": typology_code, "min_risk": min_risk, "limit": limit},
            )
            .mappings()
            .all()
        )
    return [_alert_out(dict(row)) for row in rows]


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
async def get_alert(alert_id: str) -> AlertDetailOut:
    """Chi tiết cảnh báo kèm yếu tố đóng góp, hồ sơ chủ thể và giao dịch liên quan."""
    with get_session() as session:
        alert = (
            session.execute(text(_ALERT_SELECT + " WHERE al.alert_id = :alert_id"), {"alert_id": alert_id})
            .mappings()
            .first()
        )
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy cảnh báo {alert_id}")

        reasons = (
            session.execute(
                text(
                    """SELECT r.factor_code, r.factor_label, r.contribution, r.weight,
                              a.detector, a.typology_code
                         FROM alert_reason r
                         JOIN alert a ON a.alert_id = r.alert_id
                        WHERE r.alert_id = :alert_id
                        ORDER BY r.contribution DESC"""
                ),
                {"alert_id": alert_id},
            )
            .mappings()
            .all()
        )

        customer = session.execute(text(_CUSTOMER_SELECT), {"account_key": alert["account_key"]}).mappings().first()
        if customer is None:
            raise HTTPException(status_code=500, detail=f"Tài khoản {alert['account_key']} không có hồ sơ chủ thể")

        # Giao dịch gần nhất chạm tài khoản chủ thể, cả hai chiều. Đây là thứ
        # người phân tích nhìn đầu tiên khi mở một cảnh báo.
        transactions = (
            session.execute(
                text(
                    """SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                              amount, currency, channel,
                              CASE WHEN to_account_key = :account_key THEN 'in' ELSE 'out' END AS direction
                         FROM transaction
                        WHERE from_account_key = :account_key OR to_account_key = :account_key
                        ORDER BY occurred_at DESC
                        LIMIT 20"""
                ),
                {"account_key": alert["account_key"]},
            )
            .mappings()
            .all()
        )

        case_state = None
        if alert["case_id"]:
            case_state = session.execute(
                text("SELECT state FROM aml_case WHERE case_id = :case_id"), {"case_id": alert["case_id"]}
            ).scalar_one_or_none()

    return AlertDetailOut(
        **dict(alert),
        typology_label=typology_label(alert["typology_code"]),
        customer=CustomerOut(**customer),
        reasons=[AlertReasonOut(**r) for r in reasons],
        transactions=[TransactionOut(**t) for t in transactions],
        case_state=case_state,
    )


# ---------------------------------------------------------------------
# Nhật ký kiểm toán và bảng điều hành
# ---------------------------------------------------------------------


@router.get("/audit", response_model=list[AuditEventOut])
async def list_audit(
    case_id: str | None = Query(default=None, description="Lọc theo vụ việc"),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEventOut]:
    """Nhật ký kiểm toán, mới nhất trước. Bảng chỉ ghi thêm (NT4, QD6)."""
    sql = """
        SELECT audit_id, case_id, event_type, actor, actor_role, payload, occurred_at
          FROM audit_log
         WHERE (CAST(:case_id AS text) IS NULL OR case_id = CAST(:case_id AS text))
           AND (CAST(:event_type AS text) IS NULL OR event_type = CAST(:event_type AS text))
         ORDER BY occurred_at DESC, audit_id DESC
         LIMIT :limit
    """
    with get_session() as session:
        rows = (
            session.execute(text(sql), {"case_id": case_id, "event_type": event_type, "limit": limit}).mappings().all()
        )
    return [AuditEventOut(**row) for row in rows]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard() -> DashboardOut:
    """Số liệu Trung tâm Điều hành — đếm thật, không cứng hoá con số nào."""
    with get_session() as session:
        counts = (
            session.execute(
                text(
                    """SELECT
                         -- "Chưa xử lý" là mọi cảnh báo chưa đóng, không chỉ cái chưa gom
                         -- vào vụ việc: một cảnh báo `grouped` vẫn đang chờ người xử lý.
                         (SELECT count(*) FROM alert WHERE status <> 'closed')                 AS open_alerts,
                         (SELECT count(*) FROM alert WHERE risk_score >= 80)                   AS high_risk_alerts,
                         (SELECT count(*) FROM aml_case
                           WHERE state NOT IN ('XuatHoSo', 'DongKhongBaoCao'))                 AS cases_investigating,
                         (SELECT count(*) FROM approval WHERE decision = 'pending')            AS sar_pending,
                         (SELECT coalesce(avg(risk_score), 0) FROM alert)                      AS avg_risk_score"""
                )
            )
            .mappings()
            .one()
        )

        distribution = (
            session.execute(
                text(
                    """SELECT typology_code, count(*) AS alert_count
                         FROM alert
                        GROUP BY typology_code
                        ORDER BY count(*) DESC, typology_code"""
                )
            )
            .mappings()
            .all()
        )

        top = (
            session.execute(text(_ALERT_SELECT + " ORDER BY al.risk_score DESC, al.created_at DESC LIMIT 5"))
            .mappings()
            .all()
        )

    total_alerts = sum(d["alert_count"] for d in distribution) or 1
    return DashboardOut(
        open_alerts=counts["open_alerts"],
        high_risk_alerts=counts["high_risk_alerts"],
        cases_investigating=counts["cases_investigating"],
        sar_pending=counts["sar_pending"],
        avg_risk_score=round(float(counts["avg_risk_score"]), 1),
        typology_distribution=[
            TypologyShareOut(
                typology_code=d["typology_code"],
                typology_label=typology_label(d["typology_code"]),
                alert_count=d["alert_count"],
                share_pct=round(d["alert_count"] * 100 / total_alerts, 1),
            )
            for d in distribution
        ],
        top_alerts=[_alert_out(dict(row)) for row in top],
        queue_depth=queue.queue_depth(),
        worker_alive=queue.worker_alive(),
    )


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
