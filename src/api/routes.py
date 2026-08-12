import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
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
    ApprovalDecisionRequest,
    AuditEventOut,
    CaseDetailOut,
    CaseOut,
    CaseTimelineStepOut,
    ChatRequest,
    ChatResponse,
    CustomerOut,
    DashboardOut,
    InternalAlertCreate,
    InternalAlertCreateOut,
    InvestigateOut,
    LoginOut,
    LoginRequest,
    QueueStatsOut,
    SarActionRequest,
    SettingUpdateRequest,
    TransactionOut,
    TypologyShareOut,
    UserOut,
    UserUpdateRequest,
)
from src.services import queue
from src.services.if_alert_publish import insert_ml_alert, stable_alert_id

router = APIRouter()


def _user_out(row: dict[str, Any]) -> UserOut:
    return UserOut(
        id=row["user_id"],
        name=row["name"],
        email=row["email"],
        role=row["role"],
        role_label=row["role_label"],
        active=row["active"],
        last_login=row.get("last_login"),
    )


def _audit_role(role: str) -> str:
    return {
        "mlro": "mlro",
        "auditor": "auditor",
        "analyst": "analyst",
        "compliance_officer": "investigator",
        "admin": "system",
    }.get(role, "system")


def _require_user(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không tồn tại")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with get_session() as session:
        row = (
            session.execute(
                text(
                    """SELECT u.user_id, u.name, u.email, u.role, u.role_label, u.active, u.last_login
                         FROM app_session s JOIN app_user u ON u.user_id = s.user_id
                        WHERE s.token_hash = :token_hash AND s.expires_at > now() AND u.active"""
                ),
                {"token_hash": token_hash},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn")
    return dict(row)


@router.get("/auth/users", response_model=list[UserOut])
async def login_users() -> list[UserOut]:
    """Danh sách tài khoản demo lấy từ DB; không trả bất kỳ dữ liệu mật khẩu nào."""
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    "SELECT user_id, name, email, role, role_label, active, last_login FROM app_user WHERE active ORDER BY user_id"
                )
            )
            .mappings()
            .all()
        )
    return [_user_out(dict(row)) for row in rows]


@router.post("/auth/login", response_model=LoginOut)
async def login(request: LoginRequest) -> LoginOut:
    with get_session() as session:
        row = (
            session.execute(text("SELECT * FROM app_user WHERE lower(email) = lower(:email)"), {"email": request.email})
            .mappings()
            .first()
        )
        if row is None or not row["active"]:
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
        actual = hashlib.pbkdf2_hmac(
            "sha256", request.password.encode(), bytes.fromhex(row["password_salt"]), 200_000
        ).hex()
        if not secrets.compare_digest(actual, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

        raw_token = secrets.token_urlsafe(32)
        session.execute(text("DELETE FROM app_session WHERE expires_at <= now()"))
        session.execute(
            text(
                """INSERT INTO app_session(token_hash, user_id, expires_at)
                   VALUES (:token_hash, :user_id, :expires_at)"""
            ),
            {
                "token_hash": hashlib.sha256(raw_token.encode()).hexdigest(),
                "user_id": row["user_id"],
                "expires_at": datetime.now(UTC) + timedelta(hours=8),
            },
        )
        session.execute(text("UPDATE app_user SET last_login = now() WHERE user_id = :id"), {"id": row["user_id"]})
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (NULL, 'user_login', :actor, :role, CAST(:payload AS jsonb))"""
            ),
            {
                "actor": row["user_id"],
                "role": _audit_role(row["role"]),
                "payload": json.dumps({"email": row["email"]}),
            },
        )
        user = dict(row)
        user["last_login"] = datetime.now(UTC)
    return LoginOut(token=raw_token, user=_user_out(user))


@router.get("/auth/me", response_model=UserOut)
async def me(authorization: str | None = Header(default=None)) -> UserOut:
    return _user_out(_require_user(authorization))


@router.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization and authorization.startswith("Bearer "):
        with get_session() as session:
            session.execute(
                text("DELETE FROM app_session WHERE token_hash = :token_hash"),
                {"token_hash": hashlib.sha256(authorization[7:].encode()).hexdigest()},
            )
    return {"ok": True}


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


@router.post("/internal/alerts", response_model=InternalAlertCreateOut)
def create_internal_ml_alert(body: InternalAlertCreate) -> InternalAlertCreateOut:
    """Ingest một alert Isolation Forest (detector=ml) — ops/internal, không phải UI upload.

    Body cần >= 3 ``reasons`` (NT7). ``risk_score`` thang 0–100.
    Idempotent theo ``alert_id`` (tự sinh từ account/as_of/window/model nếu bỏ trống).
    """
    alert_id = body.alert_id or stable_alert_id(
        body.account_key,
        body.as_of_ts or datetime.now(tz=UTC),
        body.window,
        body.model_version,
    )
    reasons = [r.model_dump() for r in body.reasons]
    try:
        with get_session() as session:
            result = insert_ml_alert(
                session,
                alert_id=alert_id,
                account_key=body.account_key,
                risk_score=body.risk_score,
                typology_code=body.typology_code,
                reasons=reasons,
                as_of_ts=body.as_of_ts,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return InternalAlertCreateOut(
        alert_id=result["alert_id"],
        created=bool(result["created"]),
        subjects_created=bool(result.get("subjects_created")),
        risk_score=result.get("risk_score"),
        factor_count=result.get("factor_count"),
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


# ---------------------------------------------------------------------
# SAR, phê duyệt, bằng chứng và mạng lưới — toàn bộ lấy từ PostgreSQL.
# ---------------------------------------------------------------------

_SAR_STATUS = {
    "drafting": "DRAFT",
    "verified": "VALIDATION_PASSED",
    "submitted_for_approval": "PENDING_REVIEW",
    "approved": "APPROVED",
    "rejected": "REJECTED",
}


def _sar_payload(sar_id: str) -> dict[str, Any]:
    with get_session() as session:
        draft = (
            session.execute(
                text(
                    """SELECT d.sar_draft_id, d.case_id, d.version, d.status, d.created_at,
                          c.subject_account_key, c.risk_score, c.priority, c.assigned_to,
                          cu.customer_id, cu.customer_type, cu.occupation, cu.risk_rating,
                          cu.onboarding_date, a.alert_id, a.typology_code,
                          ap.approval_id, ap.decision, ap.decided_by, ap.reason,
                          ap.requested_at, ap.decided_at
                     FROM sar_draft d
                     JOIN aml_case c ON c.case_id = d.case_id
                     JOIN account ac ON ac.account_key = c.subject_account_key
                     JOIN customer cu ON cu.customer_id = ac.customer_id
                     LEFT JOIN LATERAL (
                         SELECT alert_id, typology_code FROM alert
                          WHERE case_id = c.case_id ORDER BY risk_score DESC LIMIT 1
                     ) a ON true
                     LEFT JOIN LATERAL (
                         SELECT * FROM approval WHERE sar_draft_id = d.sar_draft_id
                          ORDER BY requested_at DESC LIMIT 1
                     ) ap ON true
                    WHERE d.sar_draft_id = :sar_id"""
                ),
                {"sar_id": sar_id},
            )
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")

        statements = (
            session.execute(
                text(
                    """SELECT s.statement_id, s.ordinal, s.body,
                          coalesce(array_agg(se.evidence_id ORDER BY se.evidence_id)
                                   FILTER (WHERE se.evidence_id IS NOT NULL), '{}') AS evidence_ids
                     FROM sar_statement s
                     LEFT JOIN sar_statement_evidence se ON se.statement_id = s.statement_id
                    WHERE s.sar_draft_id = :sar_id
                    GROUP BY s.statement_id, s.ordinal, s.body ORDER BY s.ordinal"""
                ),
                {"sar_id": sar_id},
            )
            .mappings()
            .all()
        )
        evidence = (
            session.execute(
                text("SELECT * FROM evidence WHERE case_id = :case_id ORDER BY retrieved_at, evidence_id"),
                {"case_id": draft["case_id"]},
            )
            .mappings()
            .all()
        )
        transactions = (
            session.execute(
                text(
                    """SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                          amount, currency, channel,
                          CASE WHEN to_account_key = :account THEN 'in' ELSE 'out' END AS direction
                     FROM transaction
                    WHERE from_account_key = :account OR to_account_key = :account
                    ORDER BY occurred_at DESC LIMIT 20"""
                ),
                {"account": draft["subject_account_key"]},
            )
            .mappings()
            .all()
        )
        history = (
            session.execute(
                text(
                    """SELECT event_type, actor, actor_role, payload, occurred_at
                     FROM audit_log WHERE case_id = :case_id
                    ORDER BY occurred_at DESC, audit_id DESC LIMIT 30"""
                ),
                {"case_id": draft["case_id"]},
            )
            .mappings()
            .all()
        )
        uncited = (
            session.execute(
                text("SELECT statement_id FROM uncited_statement WHERE sar_draft_id = :sar_id"), {"sar_id": sar_id}
            )
            .scalars()
            .all()
        )
        submitter = session.execute(
            text(
                """SELECT coalesce(u.name, l.actor)
                     FROM audit_log l LEFT JOIN app_user u ON u.user_id = l.actor
                    WHERE l.case_id = :case_id AND l.event_type = 'submitted_for_approval'
                    ORDER BY l.occurred_at DESC LIMIT 1"""
            ),
            {"case_id": draft["case_id"]},
        ).scalar_one_or_none()

    evidence_out = []
    for item in evidence:
        payload = item["payload"] if isinstance(item["payload"], dict) else {}
        evidence_out.append(
            {
                "id": item["evidence_id"],
                "kind": "statement" if item["source_table"] == "transaction" else "calculation",
                "title": f"{item['source_table']} · {item['source_ref']}",
                "description": json.dumps(payload, ensure_ascii=False, default=str),
                "source": item["source_table"],
                "fileType": "JSON RECORD",
                "fileSize": f"{len(json.dumps(payload, default=str))} B",
                "createdAt": item["retrieved_at"],
                "tags": [item["source_table"], item["source_ref"]],
                "hash": item["evidence_hash"],
            }
        )
    inflow = sum(float(t["amount"]) for t in transactions if t["direction"] == "in")
    outflow = sum(float(t["amount"]) for t in transactions if t["direction"] == "out")
    issues = [{"id": sid, "severity": "error", "title": "Nhận định thiếu bằng chứng", "detail": sid} for sid in uncited]
    status = _SAR_STATUS[draft["status"]]
    if draft["decision"] == "more_info":
        status = "NEEDS_INFO"
    return {
        "sar_id": draft["sar_draft_id"],
        "case_id": draft["case_id"],
        "alert_id": draft["alert_id"] or "",
        "status": status,
        "suspicionType": typology_label(draft["typology_code"])
        if draft["typology_code"]
        else "Rà soát giao dịch đáng ngờ",
        "riskLevel": "CAO" if float(draft["risk_score"]) >= 80 else "TRUNG BÌNH",
        "subjectName": draft["customer_id"],
        "subject": {
            "customerId": draft["customer_id"],
            "accountKey": draft["subject_account_key"],
            "customerType": draft["customer_type"],
            "occupation": draft["occupation"],
            "riskRating": draft["risk_rating"],
            "onboardingDate": draft["onboarding_date"],
        },
        "submittedBy": submitter or draft["assigned_to"] or "Chưa gửi",
        "submittedByRole": "Analyst",
        "statements": [
            {"id": s["statement_id"], "text": s["body"], "evidenceIds": list(s["evidence_ids"])} for s in statements
        ],
        "behaviourSummary": " ".join(s["body"] for s in statements),
        "inflow": inflow,
        "outflow": outflow,
        "inflowNote": "Tiền vào tài khoản",
        "outflowNote": "Tiền ra khỏi tài khoản",
        "validationIssues": issues,
        "relatedTransactions": [
            {
                "transaction_id": str(t["transaction_id"]),
                "time": t["occurred_at"],
                "amount": f"{t['amount']} {t['currency']}",
                "location": t["channel"],
                "direction": t["direction"],
                "from_account_key": t["from_account_key"],
                "to_account_key": t["to_account_key"],
            }
            for t in transactions
        ],
        "evidence": evidence_out,
        "networkConfidence": round(min(99, 50 + len(transactions) * 2.5), 1),
        "history": [
            {"time": h["occurred_at"], "text": h["event_type"], "actor": h["actor"], "payload": h["payload"]}
            for h in history
        ],
        "approval": {
            "approval_id": draft["approval_id"],
            "decision": draft["decision"],
            "decided_by": draft["decided_by"],
            "reason": draft["reason"],
            "requested_at": draft["requested_at"],
            "decided_at": draft["decided_at"],
        }
        if draft["approval_id"]
        else None,
    }


@router.get("/sars")
async def list_sars() -> list[dict[str, Any]]:
    with get_session() as session:
        ids = session.execute(text("SELECT sar_draft_id FROM sar_draft ORDER BY created_at DESC")).scalars().all()
    return [_sar_payload(sar_id) for sar_id in ids]


@router.get("/sars/{sar_id}")
async def get_sar(sar_id: str) -> dict[str, Any]:
    return _sar_payload(sar_id)


@router.post("/cases/{case_id}/sar")
async def create_sar(case_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"analyst", "compliance_officer", "admin"}:
        raise HTTPException(status_code=403, detail="Vai trò hiện tại không được tạo SAR")
    sar_id = f"SAR-{case_id}"
    with get_session() as session:
        existing = session.execute(
            text("SELECT sar_draft_id FROM sar_draft WHERE case_id = :case_id ORDER BY version DESC LIMIT 1"),
            {"case_id": case_id},
        ).scalar_one_or_none()
        if existing:
            return _sar_payload(existing)
        case = (
            session.execute(
                text("SELECT subject_account_key, state FROM aml_case WHERE case_id = :case_id FOR UPDATE"),
                {"case_id": case_id},
            )
            .mappings()
            .first()
        )
        if case is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy vụ việc {case_id}")
        if case["state"] in {"XuatHoSo", "DongKhongBaoCao"}:
            raise HTTPException(status_code=409, detail="Vụ việc đã kết thúc")
        txs = (
            session.execute(
                text(
                    """SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency, channel
                     FROM transaction WHERE from_account_key = :a OR to_account_key = :a
                     ORDER BY occurred_at DESC LIMIT 3"""
                ),
                {"a": case["subject_account_key"]},
            )
            .mappings()
            .all()
        )
        if not txs:
            raise HTTPException(status_code=409, detail="Vụ việc chưa có giao dịch để làm bằng chứng")
        session.execute(
            text("INSERT INTO sar_draft(sar_draft_id, case_id, version, status) VALUES (:id, :case_id, 1, 'drafting')"),
            {"id": sar_id, "case_id": case_id},
        )
        evidence_ids = []
        for index, tx in enumerate(txs, start=1):
            evidence_id = f"EV-{case_id}-LIVE-{index:03d}"
            payload = json.dumps(dict(tx), ensure_ascii=False, default=str, sort_keys=True)
            evidence_ids.append(evidence_id)
            session.execute(
                text(
                    """INSERT INTO evidence(evidence_id, case_id, source_table, source_ref, payload, evidence_hash)
                       VALUES (:id, :case_id, 'transaction', :ref, CAST(:payload AS jsonb), :hash)"""
                ),
                {
                    "id": evidence_id,
                    "case_id": case_id,
                    "ref": str(tx["transaction_id"]),
                    "payload": payload,
                    "hash": hashlib.sha256(payload.encode()).hexdigest(),
                },
            )
        bodies = [
            f"Tài khoản {case['subject_account_key']} có giao dịch {tx['transaction_id']} trị giá {tx['amount']} {tx['currency']}."
            for tx in txs
        ]
        for index, body in enumerate(bodies, start=1):
            statement_id = f"ST-{case_id}-LIVE-{index:03d}"
            session.execute(
                text(
                    "INSERT INTO sar_statement(statement_id, sar_draft_id, ordinal, body) VALUES (:id, :sar, :n, :body)"
                ),
                {"id": statement_id, "sar": sar_id, "n": index, "body": body},
            )
            session.execute(
                text("INSERT INTO sar_statement_evidence(statement_id, evidence_id) VALUES (:statement, :evidence)"),
                {"statement": statement_id, "evidence": evidence_ids[index - 1]},
            )
        session.execute(
            text("UPDATE aml_case SET state = 'SoanHoSoNghiVan', updated_at = now() WHERE case_id = :case_id"),
            {"case_id": case_id},
        )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'sar_updated', :actor, :role,
                           CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": case_id,
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps({"sar_draft_id": sar_id, "action": "created"}),
            },
        )
    return _sar_payload(sar_id)


@router.post("/sars/{sar_id}/validate")
async def validate_sar(sar_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _require_user(authorization)
    with get_session() as session:
        draft = (
            session.execute(
                text("SELECT case_id, status FROM sar_draft WHERE sar_draft_id = :id FOR UPDATE"), {"id": sar_id}
            )
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")
        if draft["status"] not in {"drafting", "verified"}:
            raise HTTPException(status_code=409, detail="SAR đã được gửi nên không thể kiểm chứng lại")
        uncited = session.execute(
            text("SELECT count(*) FROM uncited_statement WHERE sar_draft_id = :id"), {"id": sar_id}
        ).scalar_one()
        if uncited:
            raise HTTPException(status_code=409, detail=f"Có {uncited} nhận định chưa gắn bằng chứng")
        session.execute(text("UPDATE sar_draft SET status = 'verified' WHERE sar_draft_id = :id"), {"id": sar_id})
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'validation_run', :actor, :role,
                           CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": draft["case_id"],
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps({"sar_draft_id": sar_id, "uncited": uncited}),
            },
        )
    return _sar_payload(sar_id)


@router.post("/sars/{sar_id}/submit")
async def submit_sar(
    sar_id: str, request: SarActionRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    user = _require_user(authorization)
    with get_session() as session:
        draft = (
            session.execute(
                text("SELECT case_id, status FROM sar_draft WHERE sar_draft_id = :id FOR UPDATE"), {"id": sar_id}
            )
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")
        if draft["status"] != "verified":
            raise HTTPException(status_code=409, detail="SAR phải kiểm chứng đạt trước khi gửi")
        approval_id = f"APR-{sar_id}-{secrets.token_hex(3)}"
        session.execute(
            text("INSERT INTO approval(approval_id, case_id, sar_draft_id, decision) VALUES (:a, :c, :s, 'pending')"),
            {"a": approval_id, "c": draft["case_id"], "s": sar_id},
        )
        session.execute(
            text("UPDATE sar_draft SET status = 'submitted_for_approval' WHERE sar_draft_id = :id"), {"id": sar_id}
        )
        session.execute(
            text("UPDATE aml_case SET state = 'ChoNguoiPheDuyet', updated_at = now() WHERE case_id = :id"),
            {"id": draft["case_id"]},
        )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'submitted_for_approval', :actor, :role,
                           CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": draft["case_id"],
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps({"sar_draft_id": sar_id, "reason": request.reason}),
            },
        )
    return _sar_payload(sar_id)


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str, request: ApprovalDecisionRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"mlro", "admin"}:
        raise HTTPException(status_code=403, detail="Chỉ MLRO hoặc Admin được ra quyết định")
    with get_session() as session:
        approval = (
            session.execute(text("SELECT * FROM approval WHERE approval_id = :id FOR UPDATE"), {"id": approval_id})
            .mappings()
            .first()
        )
        if approval is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy phê duyệt {approval_id}")
        if approval["decision"] != "pending":
            raise HTTPException(status_code=409, detail="Quyết định đã được ghi và không thể sửa")
        submitter = session.execute(
            text(
                """SELECT actor FROM audit_log WHERE case_id = :case_id AND event_type = 'submitted_for_approval'
                   ORDER BY occurred_at DESC LIMIT 1"""
            ),
            {"case_id": approval["case_id"]},
        ).scalar_one_or_none()
        if submitter == user["user_id"]:
            raise HTTPException(status_code=403, detail="Người gửi không được tự phê duyệt hồ sơ")
        event = {"approved": "approved", "rejected": "rejected", "more_info": "more_info_requested"}[request.decision]
        session.execute(
            text(
                """UPDATE approval SET decision = :decision, decided_by = :user_id,
                       reason = :reason, decided_at = now() WHERE approval_id = :id"""
            ),
            {"decision": request.decision, "user_id": user["user_id"], "reason": request.reason, "id": approval_id},
        )
        draft_status = "approved" if request.decision == "approved" else "rejected"
        session.execute(
            text("UPDATE sar_draft SET status = :status WHERE sar_draft_id = :id"),
            {"status": draft_status, "id": approval["sar_draft_id"]},
        )
        if request.decision != "approved":
            session.execute(
                text("UPDATE aml_case SET state = 'DieuTraBoSung', updated_at = now() WHERE case_id = :id"),
                {"id": approval["case_id"]},
            )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, :event, :actor, :role,
                           CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": approval["case_id"],
                "event": event,
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps(
                    {
                        "sar_draft_id": approval["sar_draft_id"],
                        "approval_id": approval_id,
                        "reason": request.reason,
                    }
                ),
            },
        )
        sar_id = approval["sar_draft_id"]
    return _sar_payload(sar_id)


@router.post("/sars/{sar_id}/export")
async def export_sar(sar_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _require_user(authorization)
    with get_session() as session:
        draft = (
            session.execute(text("SELECT case_id, status FROM sar_draft WHERE sar_draft_id = :id"), {"id": sar_id})
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")
        if draft["status"] != "approved":
            raise HTTPException(status_code=409, detail="Chỉ hồ sơ đã phê duyệt mới được xuất")
        session.execute(
            text("UPDATE aml_case SET state = 'XuatHoSo', updated_at = now() WHERE case_id = :id"),
            {"id": draft["case_id"]},
        )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'file_exported', :actor, :role, CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": draft["case_id"],
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps({"sar_draft_id": sar_id}),
            },
        )
    return {"sar_id": sar_id, "case_id": draft["case_id"], "status": "exported", "filename": f"{sar_id}.json"}


@router.get("/cases/{case_id}/network")
async def case_network(case_id: str) -> dict[str, Any]:
    with get_session() as session:
        case = (
            session.execute(
                text(
                    """SELECT c.case_id, c.subject_account_key, c.risk_score, cu.customer_id
                     FROM aml_case c JOIN account a ON a.account_key = c.subject_account_key
                     JOIN customer cu ON cu.customer_id = a.customer_id WHERE c.case_id = :id"""
                ),
                {"id": case_id},
            )
            .mappings()
            .first()
        )
        if case is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy vụ việc {case_id}")
        txs = (
            session.execute(
                text(
                    """SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency, channel
                     FROM transaction WHERE from_account_key = :a OR to_account_key = :a
                     ORDER BY occurred_at DESC LIMIT 30"""
                ),
                {"a": case["subject_account_key"]},
            )
            .mappings()
            .all()
        )
        accounts = {case["subject_account_key"]}
        for tx in txs:
            accounts.update((tx["from_account_key"], tx["to_account_key"]))
        profiles = (
            session.execute(
                text(
                    """SELECT a.account_key, c.customer_id, c.customer_type, c.risk_rating
                     FROM account a JOIN customer c ON c.customer_id = a.customer_id
                    WHERE a.account_key = ANY(:accounts)"""
                ),
                {"accounts": list(accounts)},
            )
            .mappings()
            .all()
        )
    profile_by_account = {p["account_key"]: p for p in profiles}
    nodes = []
    for account in accounts:
        p = profile_by_account.get(account)
        nodes.append(
            {
                "id": account,
                "label": p["customer_id"] if p else account,
                "sublabel": account,
                "kind": "subject" if account == case["subject_account_key"] else "company",
                "risk": "primary" if account == case["subject_account_key"] else (p["risk_rating"] if p else "medium"),
            }
        )
    edges = [
        {
            "id": f"tx-{t['transaction_id']}",
            "source": t["from_account_key"],
            "target": t["to_account_key"],
            "label": f"{t['amount']} {t['currency']}",
            "suspicious": float(t["amount"]) >= 100_000,
        }
        for t in txs
    ]
    return {
        "case_id": case_id,
        "risk_score": case["risk_score"],
        "subject_account_key": case["subject_account_key"],
        "nodes": nodes,
        "edges": edges,
        "transactions": [dict(t) for t in txs],
    }


# ---------------------------------------------------------------------
# Người dùng và cấu hình hệ thống.
# ---------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
async def list_users(authorization: str | None = Header(default=None)) -> list[UserOut]:
    _require_user(authorization)
    with get_session() as session:
        rows = (
            session.execute(
                text("SELECT user_id, name, email, role, role_label, active, last_login FROM app_user ORDER BY user_id")
            )
            .mappings()
            .all()
        )
    return [_user_out(dict(row)) for row in rows]


@router.get("/settings")
async def list_settings(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_user(authorization)
    with get_session() as session:
        settings = (
            session.execute(
                text("SELECT code, label, value, unit, source, updated_at FROM system_setting ORDER BY code")
            )
            .mappings()
            .all()
        )
        versions = (
            session.execute(
                text(
                    """SELECT watchlist_version_id, source AS provider,
                              loaded_at AS published_at, checksum AS content_hash
                         FROM watchlist_version ORDER BY loaded_at DESC"""
                )
            )
            .mappings()
            .all()
        )
    return {"settings": [dict(row) for row in settings], "watchlistVersions": [dict(row) for row in versions]}


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, request: UserUpdateRequest, authorization: str | None = Header(default=None)
) -> UserOut:
    user = _require_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Chỉ Admin được thay đổi trạng thái tài khoản")
    if user_id == user["user_id"] and not request.active:
        raise HTTPException(status_code=409, detail="Không thể tự khóa tài khoản đang đăng nhập")
    with get_session() as session:
        before = session.execute(
            text("SELECT active FROM app_user WHERE user_id = :id FOR UPDATE"), {"id": user_id}
        ).scalar_one_or_none()
        if before is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy người dùng {user_id}")
        row = (
            session.execute(
                text(
                    """UPDATE app_user SET active = :active WHERE user_id = :id
                   RETURNING user_id, name, email, role, role_label, active, last_login"""
                ),
                {"active": request.active, "id": user_id},
            )
            .mappings()
            .one()
        )
        if before != request.active:
            session.execute(
                text(
                    """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                       VALUES (NULL, 'user_changed', :actor, :role,
                               CAST(:payload AS jsonb))"""
                ),
                {
                    "actor": user["user_id"],
                    "role": _audit_role(user["role"]),
                    "payload": json.dumps(
                        {"user_id": user_id, "before": before, "after": request.active, "reason": request.reason}
                    ),
                },
            )
    return _user_out(dict(row))


@router.put("/settings/{code}")
async def update_setting(
    code: str, request: SettingUpdateRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"admin", "mlro"}:
        raise HTTPException(status_code=403, detail="Chỉ Admin hoặc MLRO được sửa cấu hình")
    with get_session() as session:
        before = session.execute(
            text("SELECT value FROM system_setting WHERE code = :code"), {"code": code}
        ).scalar_one_or_none()
        if before is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy cấu hình {code}")
        row = (
            session.execute(
                text(
                    """UPDATE system_setting SET value = :value, updated_by = :user, updated_at = now()
                    WHERE code = :code RETURNING code, label, value, unit, source, updated_at"""
                ),
                {"value": request.value, "user": user["user_id"], "code": code},
            )
            .mappings()
            .one()
        )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (NULL, 'setting_changed', :actor, :role,
                           CAST(:payload AS jsonb))"""
            ),
            {
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps(
                    {"code": code, "before": before, "after": request.value, "reason": request.reason}
                ),
            },
        )
    return dict(row)
