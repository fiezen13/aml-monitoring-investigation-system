import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response
from opentelemetry import trace
from sqlalchemy import text

from src.api import ai_assistant, authz
from src.api.permissions import data_scope_for, permission_codes, scope_own_records
from src.api.sar_drafter import draft_sar
from src.api.sar_pdf import build_sar_pdf
from src.config import get_settings
from src.db.session import get_session
from src.domain import (
    INVESTIGATION_CHAIN,
    next_state,
    state_label,
    typology_label,
)
from src.investigation.report import build_case_package
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import (
    EvidenceEnvelope,
    Explanation,
    InvestigationOut,
    InvestigationPackage,
    InvestigationStartOut,
    InvestigationStatus,
    ReviewFeedbackOut,
    ReviewFeedbackPage,
    ReviewRequest,
    TraceEvent,
    WorkflowState,
)
from src.models.schemas import (
    AlertDetailOut,
    AlertOut,
    AlertPageOut,
    AlertReasonOut,
    AlertTrendPointOut,
    ApprovalDecisionRequest,
    AuditEventOut,
    CaseAgeOut,
    CaseBandOut,
    CaseDetailOut,
    CaseOut,
    CaseTimelineStepOut,
    CustomerOut,
    DashboardOut,
    InternalAlertCreate,
    InternalAlertCreateOut,
    InvestigateOut,
    LoginOut,
    LoginRequest,
    QueueStatsOut,
    SarActionRequest,
    SarChatRequest,
    SarNarrativeRequest,
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
        # Quyền + phạm vi tính từ vai trò ở máy chủ — không tin client.
        permissions=permission_codes(row["role"]),
        data_scope=data_scope_for(row["role"]).value,
    )


def _audit_role(role: str) -> str:
    # Ánh xạ vai trò -> actor_role của audit_log. Cột này bị ràng buộc CHECK vào
    # tập giá trị lịch sử (analyst/investigator/mlro/auditor/system/agent); "manager"
    # (gộp các vai trò nghiệp vụ cũ) ghi nhận là "investigator" để không phải nới
    # ràng buộc và không làm hỏng các bản ghi kiểm toán đã có.
    return {
        "analyst": "analyst",
        "manager": "investigator",
        "admin": "system",
    }.get(role, "system")


def _require_user(authorization: str | None) -> dict[str, Any]:
    """Người dùng của phiên hiện tại.

    Cổng phân quyền ở ``src/api/authz.py`` đã giải mã token trước khi endpoint
    chạy; ở đây gọi lại cùng một hàm để lấy bản ghi, thay vì lặp lại câu SQL.
    Các endpoint còn cần nó vì phần kiểm tra riêng của chúng phụ thuộc *dữ liệu*
    chứ không chỉ vai trò — ví dụ "người gửi không được tự phê duyệt hồ sơ".
    """
    return authz.resolve_user(authorization)


def _enforce_case_scope(authorization: str | None, assigned_to: str | None) -> None:
    """Phạm vi cấp-BẢN-GHI cho vụ việc.

    ``/cases`` (danh sách) đã lọc theo người được giao với vai trò phạm vi
    ASSIGNED (analyst). Các endpoint CHI TIẾT vụ việc phải áp CÙNG điều kiện —
    nếu không, analyst có thể đọc vụ việc không được giao chỉ bằng cách đoán
    ``case_id`` (IDOR ở cấp đối tượng). Trả 404 (không phải 403) để không tiết
    lộ sự tồn tại của vụ việc ngoài phạm vi. Compliance/MLRO/Auditor thấy toàn
    bộ nên không bị chặn.
    """
    user = _require_user(authorization)
    if scope_own_records(user["role"]) and assigned_to != user["user_id"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy vụ việc")


@router.get("/auth/users", response_model=list[UserOut])
def login_users() -> list[UserOut]:
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


def _pbkdf2(password: str, salt_hex: str) -> str:
    """Băm mật khẩu (PBKDF2, 200k vòng). Tách hàm để chạy được trong thread."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000).hex()


@router.post("/auth/login", response_model=LoginOut)
async def login(request: LoginRequest) -> LoginOut:
    # PBKDF2 200k vòng tốn ~50–100ms CPU. Handler này là `async`, chạy trên một
    # event loop DUY NHẤT (uvicorn 1 worker), nên nếu băm ngay tại đây thì mỗi
    # lượt đăng nhập KHOÁ cả loop suốt thời gian băm — nhiều người vào cùng lúc
    # (một lớp học, một buổi demo) sẽ xếp hàng tuyến tính rồi chạm timeout, trông
    # như "server chặn". Vì vậy: (1) đọc user rồi TRẢ kết nối DB ngay, (2) băm
    # trong thread bằng asyncio.to_thread — pbkdf2 nhả GIL nên các lượt băm chạy
    # song song thật và loop vẫn rảnh phục vụ request khác, (3) mới mở kết nối
    # thứ hai để ghi phiên. Không giữ kết nối pool trong lúc băm.
    with get_session() as session:
        row = (
            session.execute(text("SELECT * FROM app_user WHERE lower(email) = lower(:email)"), {"email": request.email})
            .mappings()
            .first()
        )
    user_row = dict(row) if row is not None else None

    actual = None
    if user_row is not None and user_row["active"]:
        actual = await asyncio.to_thread(_pbkdf2, request.password, user_row["password_salt"])
    if (
        user_row is None
        or not user_row["active"]
        or actual is None
        or not secrets.compare_digest(actual, user_row["password_hash"])
    ):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    raw_token = secrets.token_urlsafe(32)
    with get_session() as session:
        session.execute(text("DELETE FROM app_session WHERE expires_at <= now()"))
        session.execute(
            text(
                """INSERT INTO app_session(token_hash, user_id, expires_at)
                   VALUES (:token_hash, :user_id, :expires_at)"""
            ),
            {
                "token_hash": hashlib.sha256(raw_token.encode()).hexdigest(),
                "user_id": user_row["user_id"],
                "expires_at": datetime.now(UTC) + timedelta(hours=8),
            },
        )
        session.execute(text("UPDATE app_user SET last_login = now() WHERE user_id = :id"), {"id": user_row["user_id"]})
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (NULL, 'user_login', :actor, :role, CAST(:payload AS jsonb))"""
            ),
            {
                "actor": user_row["user_id"],
                "role": _audit_role(user_row["role"]),
                "payload": json.dumps({"email": user_row["email"]}),
            },
        )
    user_row["last_login"] = datetime.now(UTC)
    return LoginOut(token=raw_token, user=_user_out(user_row))


@router.get("/auth/me", response_model=UserOut)
def me(authorization: str | None = Header(default=None)) -> UserOut:
    return _user_out(_require_user(authorization))


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
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
def list_cases(
    state: str | None = Query(default=None, description="Lọc theo trạng thái máy trạng thái"),
    dataset: str | None = Query(default=None, description="ibm_hi_medium | saml_d"),
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> list[CaseOut]:
    """Hàng đợi vụ việc, xếp theo điểm rủi ro giảm dần.

    ``dataset``: aml_case không có cột bộ dữ liệu riêng — một vụ việc thuộc bộ
    nào là do các cảnh báo gom vào nó quyết định. Lọc qua ``EXISTS`` trên
    ``alert.dataset``.

    PHẠM VI DỮ LIỆU: vai trò phạm vi ASSIGNED (analyst) chỉ thấy vụ việc ĐƯỢC
    GIAO cho mình (``assigned_to = user``). Điều kiện này áp ở MÁY CHỦ từ vai trò
    của token, KHÔNG nhận từ tham số client. Compliance/MLRO/Auditor thấy toàn bộ.
    """
    user = _require_user(authorization)
    own_only = scope_own_records(user["role"])
    sql = """
        SELECT c.case_id, c.subject_account_key, c.title, c.state, c.risk_score,
               c.priority, c.assigned_to, c.created_at,
               (SELECT count(*) FROM alert a WHERE a.case_id = c.case_id) AS alert_count
          FROM aml_case c
         -- Ép kiểu tường minh: với tham số NULL không có ngữ cảnh, PostgreSQL
         -- không suy ra được kiểu và từ chối câu lệnh.
         WHERE (CAST(:state AS text) IS NULL OR c.state = CAST(:state AS text))
           AND (CAST(:dataset AS text) IS NULL
                OR EXISTS (SELECT 1 FROM alert a
                            WHERE a.case_id = c.case_id
                              AND a.dataset = CAST(:dataset AS text)))
           -- Phạm vi ASSIGNED: chỉ vụ việc được giao cho chính người dùng.
           AND (CAST(:assignee AS text) IS NULL OR c.assigned_to = CAST(:assignee AS text))
         ORDER BY c.risk_score DESC, c.created_at DESC
         LIMIT :limit
    """
    params = {
        "state": state,
        "dataset": dataset,
        "limit": limit,
        "assignee": user["user_id"] if own_only else None,
    }
    with get_session() as session:
        rows = session.execute(text(sql), params).mappings().all()
    return [CaseOut(**row) for row in rows]


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
def get_case(case_id: str, authorization: str | None = Header(default=None)) -> CaseDetailOut:
    """Chi tiết một vụ việc kèm các yếu tố đóng góp.

    Mọi cảnh báo trả về ở đây phải có tối thiểu ba yếu tố có giá trị số (NT7).

    PHẠM VI DỮ LIỆU: áp cùng điều kiện với danh sách ``/cases`` — vai trò
    ASSIGNED (analyst) chỉ mở được vụ việc được giao cho mình.
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
        _enforce_case_scope(authorization, case["assigned_to"])

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
    cả khi nhật ký không có dòng chuyển trạng thái tương ứng — dữ liệu cũ
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
def investigate(case_id: str) -> InvestigateOut:
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
           al.dataset,
           (SELECT count(*) FROM alert_reason r WHERE r.alert_id = al.alert_id) AS factor_count
      FROM alert al
      JOIN account ac  ON ac.account_key = al.account_key
      JOIN customer c  ON c.customer_id  = ac.customer_id
"""


# Giao dịch gần nhất của MỘT tài khoản (cả chiều gửi lẫn nhận).
#
# TRÁNH `WHERE from_account_key = :a OR to_account_key = :a ORDER BY occurred_at
# DESC LIMIT n`: với OR trên hai cột + ORDER BY thời gian + LIMIT, planner bỏ cả
# hai index (from_time_idx / to_time_idx) và đi index thời gian rồi lọc — nếu tài
# khoản ít giao dịch, nó quét gần hết bảng 15,6 triệu dòng → treo hàng trăm giây
# trên Cloud SQL nhỏ, và các lượt gọi chồng nhau làm nghẽn cả API.
#
# UNION ALL hai nhánh: mỗi nhánh khớp ĐÚNG một index tổ hợp (account, occurred_at
# DESC) nên chỉ lấy n dòng đầu tức thì; gộp 2n dòng rồi sắp lấy n. Không trùng vì
# transaction cấm cạnh tự trỏ (from <> to).
_ACCOUNT_TX_SQL = text(
    """
    SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency, channel,
           CASE WHEN to_account_key = :account THEN 'in' ELSE 'out' END AS direction
      FROM (
            (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency, channel
               FROM transaction WHERE from_account_key = :account
              ORDER BY occurred_at DESC LIMIT :lim)
            UNION ALL
            (SELECT transaction_id, occurred_at, from_account_key, to_account_key, amount, currency, channel
               FROM transaction WHERE to_account_key = :account
              ORDER BY occurred_at DESC LIMIT :lim)
           ) u
     ORDER BY occurred_at DESC
     LIMIT :lim
    """
)


def _recent_account_transactions(session: Any, account_key: str, limit: int) -> list[Any]:
    """Giao dịch gần nhất của một tài khoản, dùng index — xem ``_ACCOUNT_TX_SQL``."""
    return session.execute(_ACCOUNT_TX_SQL, {"account": account_key, "lim": limit}).mappings().all()


def _alert_out(row: dict) -> AlertOut:
    return AlertOut(**row, typology_label=typology_label(row["typology_code"]))


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
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
                {
                    "status": status,
                    "typology_code": typology_code,
                    "min_risk": min_risk,
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    return [_alert_out(dict(row)) for row in rows]


@router.get("/alerts/page", response_model=AlertPageOut)
def list_alerts_page(
    status: str | None = Query(default=None, description="open | grouped | closed"),
    typology_code: str | None = Query(default=None, description="Mã typology T01–T10"),
    min_risk: float = Query(default=0, ge=0, le=100),
    q: str | None = Query(default=None, max_length=160),
    dataset: str | None = Query(default=None, description="ibm_hi_medium | saml_d"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
) -> AlertPageOut:
    """Hàng đợi cảnh báo phân trang trên DB.

    ``dataset`` lọc theo bộ dữ liệu. Không lọc thì hàng đợi trộn hai vũ trụ tài
    khoản không liên quan gì đến nhau: một cảnh báo ví ngân hàng SAML-D nằm cạnh
    một cảnh báo IBM, và chuyên viên mở ra thấy hồ sơ khách hàng trống thì tưởng
    hệ thống hỏng.
    """
    where = """
         WHERE (CAST(:status AS text) IS NULL OR al.status = CAST(:status AS text))
           AND (CAST(:typology_code AS text) IS NULL OR al.typology_code = CAST(:typology_code AS text))
           AND (CAST(:dataset AS text) IS NULL OR al.dataset = CAST(:dataset AS text))
           AND al.risk_score >= :min_risk
           AND (
               CAST(:q AS text) IS NULL
               OR al.alert_id ILIKE :q_like
               OR ac.account_key ILIKE :q_like
               OR ac.customer_id ILIKE :q_like
               OR c.occupation ILIKE :q_like
           )

    """
    clean_q = q.strip() if q and q.strip() else None
    params = {
        "status": status,
        "typology_code": typology_code,
        "dataset": dataset,
        "min_risk": min_risk,
        "q": clean_q,
        "q_like": f"%{clean_q}%" if clean_q else None,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    # ĐẾM KHÔNG JOIN khi không tìm kiếm: account/customer chỉ cần cho bộ lọc `q`
    # (khớp account_key/customer_id/occupation). Không có `q` thì JOIN account
    # (596k dòng) + customer chỉ để đếm là vô ích — planner hash-join quét cả
    # account → ~9s. Đếm thẳng trên `alert` (26k, có index dataset) → ~ms.
    if clean_q is None:
        count_sql = """SELECT count(*) FROM alert al
                 WHERE (CAST(:status AS text) IS NULL OR al.status = CAST(:status AS text))
                   AND (CAST(:typology_code AS text) IS NULL OR al.typology_code = CAST(:typology_code AS text))
                   AND (CAST(:dataset AS text) IS NULL OR al.dataset = CAST(:dataset AS text))
                   AND al.risk_score >= :min_risk"""
    else:
        count_sql = (
            """SELECT count(*)
                 FROM alert al
                 JOIN account ac ON ac.account_key = al.account_key
                 JOIN customer c ON c.customer_id = ac.customer_id
            """
            + where
        )
    with get_session() as session:
        total = session.execute(text(count_sql), params).scalar_one()
        if clean_q is None:
            # Không tìm kiếm: SẮP XẾP + PHÂN TRANG trên `alert` (26k, index) TRƯỚC,
            # rồi mới JOIN account/customer cho đúng 50 dòng của trang. Nếu để
            # _ALERT_SELECT join trước rồi sort, planner hash-join quét cả account
            # (596k) mỗi lần mở trang → ~4s. Đẩy limit vào trong → ~0,x s.
            rows_sql = """
                SELECT sub.alert_id, sub.account_key, ac.customer_id, c.occupation, c.risk_rating,
                       sub.typology_code, sub.detector, sub.risk_score, sub.status, sub.case_id,
                       sub.created_at, sub.dataset,
                       (SELECT count(*) FROM alert_reason r WHERE r.alert_id = sub.alert_id) AS factor_count
                  FROM (
                        SELECT al.alert_id, al.account_key, al.typology_code, al.detector,
                               al.risk_score, al.status, al.case_id, al.created_at, al.dataset
                          FROM alert al
                         WHERE (CAST(:status AS text) IS NULL OR al.status = CAST(:status AS text))
                           AND (CAST(:typology_code AS text) IS NULL OR al.typology_code = CAST(:typology_code AS text))
                           AND (CAST(:dataset AS text) IS NULL OR al.dataset = CAST(:dataset AS text))
                           AND al.risk_score >= :min_risk
                         ORDER BY al.risk_score DESC, al.created_at DESC, al.alert_id
                         LIMIT :limit OFFSET :offset
                       ) sub
                  JOIN account ac ON ac.account_key = sub.account_key
                  JOIN customer c ON c.customer_id = ac.customer_id
                 ORDER BY sub.risk_score DESC, sub.created_at DESC, sub.alert_id
            """
        else:
            rows_sql = (
                _ALERT_SELECT
                + where
                + """
                 ORDER BY al.risk_score DESC, al.created_at DESC, al.alert_id
                 LIMIT :limit OFFSET :offset
                """
            )
        rows = session.execute(text(rows_sql), params).mappings().all()
    return AlertPageOut(
        rows=[_alert_out(dict(row)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
def get_alert(alert_id: str) -> AlertDetailOut:
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
        transactions = _recent_account_transactions(session, alert["account_key"], 20)

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
        # get_session: commit neu OK, rollback neu exception — alert + reasons cung 1 TX.
        with get_session() as session:
            result = insert_ml_alert(
                session,
                alert_id=alert_id,
                account_key=body.account_key,
                risk_score=body.risk_score,
                typology_code=body.typology_code,
                features=body.features,
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
def list_audit(
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


# Gộp 9 bước máy của INVESTIGATION_CHAIN thành các GIAI ĐOẠN mà con người đọc
# được trong nhật ký kiểm toán. Mỗi giai đoạn = một cột mốc: đã đạt lúc nào, ai
# làm. Thứ tự phải khớp chuỗi điều tra + hai trạng thái kết thúc.
_AUDIT_MILESTONES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("tiep_nhan", "Tiếp nhận cảnh báo", frozenset({"TiepNhanCanhBao"})),
    (
        "dieu_tra",
        "Điều tra & phân tích",
        frozenset(
            {
                "TruyHoiBangChung",
                "PhanTichDoThi",
                "DoiChieuTrungPhatPEP",
                "TinhToanBangCongCu",
                "LapLuanGanTypology",
                "DieuTraBoSung",
            }
        ),
    ),
    ("soan_ho_so", "Soạn hồ sơ nghi vấn", frozenset({"SoanHoSoNghiVan"})),
    ("kiem_chung", "Kiểm chứng bằng chứng", frozenset({"KiemChungBangChung"})),
    ("phe_duyet", "Trình phê duyệt", frozenset({"ChoNguoiPheDuyet"})),
    ("ket_thuc", "Kết thúc hồ sơ", frozenset({"XuatHoSo", "DongKhongBaoCao"})),
)
_STATE_TO_MILESTONE: dict[str, int] = {
    st: idx for idx, (_, _, states) in enumerate(_AUDIT_MILESTONES) for st in states
}
_TERMINAL_STATES = frozenset({"XuatHoSo", "DongKhongBaoCao"})


def _actor_display(actor: str | None, actor_role: str | None, names: dict[str, str]) -> str:
    """Tên người/tác tử để hiển thị trong nhật ký.

    Người thật (``U-xxx``) tra ra họ tên; tác tử AI và mọi actor kỹ thuật
    (worker, api, seed test…) gom về nhãn chung — kiểm toán viên quan tâm "ai
    chịu trách nhiệm", không phải tên tiến trình.
    """
    if actor and actor in names:
        return names[actor]
    if actor_role == "agent":
        return "Tác tử điều tra (AI)"
    return "Hệ thống"


@router.get("/audit/by-case")
def audit_by_case(limit: int = Query(default=40, ge=1, le=100)) -> list[dict[str, Any]]:
    """Nhật ký kiểm toán GỘP THEO VỤ VIỆC — dựng lại được toàn bộ vòng đời hồ sơ.

    Mỗi vụ trả về: (1) chuỗi cột mốc (``milestones``) cho biết vụ đã đi qua những
    giai đoạn nào, đạt lúc nào, đang dừng ở đâu; (2) dòng thời gian ``events``
    theo thứ tự thời gian THUẬN — ai làm gì, lúc nào, kèm ghi chú/lý do lấy từ
    payload. Bỏ 'case_viewed' (chỉ là lượt xem). Sắp vụ theo hoạt động mới nhất.
    """
    with get_session() as session:
        names = {
            r["user_id"]: r["name"]
            for r in session.execute(text("SELECT user_id, name FROM app_user")).mappings()
        }
        cases = (
            session.execute(
                text(
                    """SELECT c.case_id, c.subject_account_key, c.title, c.state, c.risk_score,
                              c.priority, c.assigned_to, c.created_at,
                              count(*) AS event_count, max(l.occurred_at) AS last_at
                         FROM audit_log l JOIN aml_case c ON c.case_id = l.case_id
                        WHERE l.case_id IS NOT NULL AND l.event_type <> 'case_viewed'
                        GROUP BY c.case_id, c.subject_account_key, c.title, c.state, c.risk_score,
                                 c.priority, c.assigned_to, c.created_at
                        ORDER BY max(l.occurred_at) DESC
                        LIMIT :lim"""
                ),
                {"lim": limit},
            )
            .mappings()
            .all()
        )
        out: list[dict[str, Any]] = []
        for c in cases:
            events = (
                session.execute(
                    text(
                        """SELECT event_type, actor, actor_role, occurred_at, payload
                             FROM audit_log
                            WHERE case_id = :cid AND event_type <> 'case_viewed'
                            ORDER BY occurred_at ASC, audit_id ASC LIMIT 40"""
                    ),
                    {"cid": c["case_id"]},
                )
                .mappings()
                .all()
            )

            # Cột mốc đạt lúc nào: quét case_state_changed để lấy thời điểm SỚM
            # NHẤT bước sang mỗi giai đoạn. Giai đoạn "Tiếp nhận" lấy created_at.
            reached: dict[int, Any] = {}
            if c["created_at"] is not None:
                reached[0] = c["created_at"]
            for e in events:
                if e["event_type"] != "case_state_changed":
                    continue
                to_state = (e["payload"] or {}).get("to") if isinstance(e["payload"], dict) else None
                mi = _STATE_TO_MILESTONE.get(to_state) if to_state else None
                if mi is not None and mi not in reached:
                    reached[mi] = e["occurred_at"]

            cur_idx = _STATE_TO_MILESTONE.get(c["state"], 0)
            closed = c["state"] in _TERMINAL_STATES
            milestones = []
            for idx, (key, label, _states) in enumerate(_AUDIT_MILESTONES):
                if idx < cur_idx:
                    status = "done"
                elif idx == cur_idx:
                    status = "done" if closed else "current"
                else:
                    status = "pending"
                lbl = label
                if key == "ket_thuc" and c["state"] == "DongKhongBaoCao":
                    lbl = "Đóng — không báo cáo"
                elif key == "ket_thuc" and c["state"] == "XuatHoSo":
                    lbl = "Đã xuất hồ sơ SAR"
                milestones.append(
                    {"key": key, "label": lbl, "status": status, "reached_at": reached.get(idx)}
                )

            out.append(
                {
                    "case_id": c["case_id"],
                    "subject": c["subject_account_key"],
                    "title": c["title"],
                    "state": c["state"],
                    "priority": c["priority"],
                    "risk_score": float(c["risk_score"]) if c["risk_score"] is not None else 0.0,
                    "assigned_to": c["assigned_to"],
                    "assigned_name": names.get(c["assigned_to"]) if c["assigned_to"] else None,
                    "event_count": c["event_count"],
                    "opened_at": c["created_at"],
                    "last_at": c["last_at"],
                    "closed": closed,
                    "milestones": milestones,
                    "events": [
                        {
                            "event_type": e["event_type"],
                            "actor": e["actor"],
                            "actor_name": _actor_display(e["actor"], e["actor_role"], names),
                            "actor_role": e["actor_role"],
                            "occurred_at": e["occurred_at"],
                            "payload": e["payload"] if isinstance(e["payload"], dict) else None,
                        }
                        for e in events
                    ],
                }
            )
    return out


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    dataset: str | None = Query(default=None, description="ibm_hi_medium | saml_d"),
) -> DashboardOut:
    """Số liệu Trung tâm Điều hành — đếm thật, không cứng hoá con số nào.

    ``dataset`` phải đi cùng bộ lọc của hàng đợi. Lọc bảng mà bốn thẻ số liệu
    trên đầu vẫn là tổng của mọi bộ thì màn hình tự mâu thuẫn: hàng đợi hiện
    5.004 dòng SAML-D còn thẻ ghi 10.004 cảnh báo.
    """
    with get_session() as session:
        counts = (
            session.execute(
                text(
                    """WITH latest AS (
                           -- Chọn release ĐÚNG bộ dữ liệu đang xem, không cứng
                           -- lấy release 'active'. Trước đây bốn thẻ trên đầu lọc
                           -- theo SAML-D nhưng thẻ "nguồn/lô" vẫn khai IBM MEGA-PNA
                           -- với 6,75 triệu dòng — màn hình tự mâu thuẫn. Mã dataset
                           -- (ibm_hi_medium/saml_d) khớp với release qua tên; NULL thì
                           -- quay về release đang phục vụ hàng đợi chính.
                           SELECT release_id, dataset, transaction_rows, triggered_rows
                             FROM edge_model_release
                            WHERE CASE
                                    WHEN CAST(:dataset AS text) = 'ibm_hi_medium' THEN dataset ILIKE '%IBM%'
                                    WHEN CAST(:dataset AS text) = 'saml_d'        THEN dataset ILIKE '%SAML%'
                                    ELSE status = 'active'
                                  END
                            ORDER BY (status = 'active') DESC
                            LIMIT 1
                       )
                       SELECT
                         -- "Chưa xử lý" là mọi cảnh báo chưa đóng, không chỉ cái chưa gom
                         -- vào vụ việc: một cảnh báo `grouped` vẫn đang chờ người xử lý.
                         --
                         -- Đếm trên TOÀN BỘ cảnh báo, không giới hạn theo edge-model
                         -- release. Nhánh rule và nhánh anomaly chấm điểm ở cấp tài
                         -- khoản nên `alert.transaction_id` là NULL; điều kiện cũ loại
                         -- sạch chúng, và bảng điều khiển báo 0 trong khi hàng đợi có
                         -- hai vạn cảnh báo. Các số liệu theo lô nằm riêng bên dưới.
                         (SELECT count(*) FROM alert WHERE status <> 'closed'
                            AND (CAST(:dataset AS text) IS NULL OR dataset = CAST(:dataset AS text)))  AS open_alerts,
                         -- Cùng phạm vi với open_alerts. Không lọc `closed` ở đây từng
                         -- khiến bảng điều khiển báo 14.592 cảnh báo rủi ro cao trên tổng
                         -- 10.414 đang mở — một con số không thể đúng.
                         (SELECT count(*) FROM alert
                           WHERE status <> 'closed' AND risk_score >= 80
                             AND (CAST(:dataset AS text) IS NULL
                                  OR dataset = CAST(:dataset AS text)))                         AS high_risk_alerts,
                         (SELECT count(*) FROM aml_case
                           WHERE state NOT IN ('XuatHoSo', 'DongKhongBaoCao')
                             AND EXISTS (
                                 SELECT 1 FROM alert al
                                  WHERE al.case_id = aml_case.case_id))                         AS cases_investigating,
                         (SELECT count(*) FROM approval ap
                           JOIN sar_draft sd USING (sar_draft_id)
                           WHERE ap.decision = 'pending'
                             AND EXISTS (
                                 SELECT 1 FROM alert al WHERE al.case_id = sd.case_id))         AS sar_pending,
                         (SELECT coalesce(avg(risk_score), 0) FROM alert
                           WHERE status <> 'closed'
                             AND (CAST(:dataset AS text) IS NULL
                                  OR dataset = CAST(:dataset AS text)))                         AS avg_risk_score,
                         -- Số liệu theo lô: chỉ có nghĩa khi đang có một edge-model
                         -- release hoạt động. Không có thì phải trả 0, không được trả
                         -- NULL — DashboardOut khai kiểu int, và NULL làm cả endpoint
                         -- trả 500 thay vì hiện một bảng điều khiển rỗng.
                         (SELECT release_id FROM latest)                                        AS latest_batch_id,
                         (SELECT dataset FROM latest)                                           AS latest_source_name,
                         coalesce((SELECT transaction_rows FROM latest), 0)                     AS transactions_analyzed,
                         coalesce((SELECT transaction_rows FROM latest), 0)                     AS subjects_analyzed,
                         coalesce((SELECT transaction_rows-triggered_rows FROM latest), 0)      AS subjects_below_threshold,
                         coalesce((SELECT triggered_rows FROM latest), 0)                       AS subjects_triggered,
                         coalesce((SELECT triggered_rows FROM latest), 0)                       AS batch_alerts_created"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .one()
        )

        distribution = (
            session.execute(
                text(
                    # Phân bố trên hàng đợi *đang mở*, không giới hạn theo edge-model
                    # release — xem chú thích ở truy vấn bộ đếm phía trên. Đếm cả cảnh
                    # báo đã đóng sẽ khiến biểu đồ nhóm hành vi không cộng lại thành
                    # tổng cảnh báo hiển thị ngay bên cạnh nó.
                    """SELECT typology_code, count(*) AS alert_count
                         FROM alert
                        WHERE status <> 'closed'
                          AND (CAST(:dataset AS text) IS NULL OR dataset = CAST(:dataset AS text))
                        GROUP BY typology_code
                        ORDER BY count(*) DESC, typology_code"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .all()
        )

        top = (
            session.execute(
                # Top 5 cũng phải theo đúng bộ dữ liệu đang xem, nếu không thẻ
                # "cảnh báo nổi bật" lại kéo cảnh báo IBM vào lúc đang xem SAML-D.
                #
                # SẮP XẾP + LIMIT trên `alert` (26k) TRƯỚC rồi mới JOIN account
                # (1,43 triệu) cho đúng 5 dòng — nếu để _ALERT_SELECT join trước,
                # planner hash-join quét cả account, trên Cloud SQL nhỏ (cache lạnh)
                # mất 10–18s mỗi lần mở Tổng quan.
                text(
                    """SELECT sub.alert_id, sub.account_key, ac.customer_id, c.occupation, c.risk_rating,
                              sub.typology_code, sub.detector, sub.risk_score, sub.status, sub.case_id,
                              sub.created_at, sub.dataset,
                              (SELECT count(*) FROM alert_reason r WHERE r.alert_id = sub.alert_id) AS factor_count
                         FROM (
                               SELECT al.alert_id, al.account_key, al.typology_code, al.detector,
                                      al.risk_score, al.status, al.case_id, al.created_at, al.dataset
                                 FROM alert al
                                WHERE (CAST(:dataset AS text) IS NULL OR al.dataset = CAST(:dataset AS text))
                                ORDER BY al.risk_score DESC, al.created_at DESC, al.alert_id
                                LIMIT 5
                              ) sub
                         JOIN account ac ON ac.account_key = sub.account_key
                         JOIN customer c ON c.customer_id = ac.customer_id
                        ORDER BY sub.risk_score DESC, sub.created_at DESC, sub.alert_id"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .all()
        )

        # --- Số liệu VỤ VIỆC cho dashboard theo vai trò ---
        # Vụ việc gắn bộ dữ liệu qua cảnh báo của nó; lọc đúng bộ đang xem để
        # khớp với bốn thẻ số liệu phía trên. Chỉ đếm vụ CHƯA kết thúc.
        _case_scope = (
            "c.state NOT IN ('XuatHoSo','DongKhongBaoCao') "
            "AND (CAST(:dataset AS text) IS NULL OR EXISTS "
            "(SELECT 1 FROM alert al WHERE al.case_id = c.case_id "
            "AND al.dataset = CAST(:dataset AS text)))"
        )
        risk_bands = (
            session.execute(
                text(
                    f"""SELECT band, count(*) AS n FROM (
                            SELECT CASE WHEN c.risk_score >= 90 THEN 'critical'
                                        WHEN c.risk_score >= 75 THEN 'high'
                                        WHEN c.risk_score >= 50 THEN 'medium'
                                        ELSE 'low' END AS band
                              FROM aml_case c
                             WHERE {_case_scope}
                        ) x GROUP BY band"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .all()
        )
        age_buckets = (
            session.execute(
                text(
                    f"""SELECT bucket, count(*) AS n FROM (
                            SELECT CASE WHEN now() - c.created_at < interval '1 day'  THEN 'lt1d'
                                        WHEN now() - c.created_at < interval '7 day'  THEN 'd1_7'
                                        WHEN now() - c.created_at < interval '30 day' THEN 'd7_30'
                                        ELSE 'gt30d' END AS bucket
                              FROM aml_case c
                             WHERE {_case_scope}
                        ) x GROUP BY bucket"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .all()
        )
        case_totals = (
            session.execute(
                text(
                    f"""SELECT count(*) AS total,
                               count(*) FILTER (WHERE c.assigned_to IS NULL) AS unassigned
                          FROM aml_case c WHERE {_case_scope}"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .one()
        )
        # Xu hướng cảnh báo theo TUẦN trên cả cửa sổ dữ liệu — trend thật để bắt
        # spike, không phải 5 cảnh báo lẻ. Lọc theo đúng bộ đang xem.
        alert_trend = (
            session.execute(
                text(
                    """SELECT to_char(date_trunc('week', created_at), 'YYYY-MM-DD') AS week,
                              count(*) AS total,
                              count(*) FILTER (WHERE risk_score >= 80) AS high
                         FROM alert
                        WHERE (CAST(:dataset AS text) IS NULL OR dataset = CAST(:dataset AS text))
                        GROUP BY 1 ORDER BY 1"""
                ),
                {"dataset": dataset},
            )
            .mappings()
            .all()
        )

    _band_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    _age_order = {"lt1d": 0, "d1_7": 1, "d7_30": 2, "gt30d": 3}
    total_alerts = sum(d["alert_count"] for d in distribution) or 1
    return DashboardOut(
        open_alerts=counts["open_alerts"],
        high_risk_alerts=counts["high_risk_alerts"],
        cases_investigating=counts["cases_investigating"],
        sar_pending=counts["sar_pending"],
        avg_risk_score=round(float(counts["avg_risk_score"]), 1),
        latest_batch_id=counts["latest_batch_id"],
        latest_source_name=counts["latest_source_name"],
        transactions_analyzed=counts["transactions_analyzed"],
        subjects_analyzed=counts["subjects_analyzed"],
        subjects_below_threshold=counts["subjects_below_threshold"],
        subjects_triggered=counts["subjects_triggered"],
        batch_alerts_created=counts["batch_alerts_created"],
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
        case_risk_bands=[
            CaseBandOut(band=r["band"], count=r["n"])
            for r in sorted(risk_bands, key=lambda r: _band_order.get(r["band"], 9))
        ],
        case_age_buckets=[
            CaseAgeOut(bucket=r["bucket"], count=r["n"])
            for r in sorted(age_buckets, key=lambda r: _age_order.get(r["bucket"], 9))
        ],
        cases_unassigned=case_totals["unassigned"],
        cases_total=case_totals["total"],
        alert_trend=[
            AlertTrendPointOut(week=r["week"], total=r["total"], high=r["high"]) for r in alert_trend
        ],
    )


@router.get("/queue", response_model=QueueStatsOut)
def queue_stats() -> QueueStatsOut:
    return QueueStatsOut(depth=queue.queue_depth(), worker_alive=queue.worker_alive())


@router.get("/status")
def agent_status() -> dict[str, Any]:
    """Trạng thái của tầng tác tử điều tra.

    Trước đây endpoint này trả về hằng số ``"LangGraph Agent v1.0"`` — tên của
    một khung mẫu sinh sẵn, không phải tầng tác tử thật đang chạy điều tra
    (``src/investigation/``). Khung mẫu ấy nay đã gỡ khỏi repo. Giờ endpoint báo
    đúng thứ đang chạy và ngân sách an toàn đang áp dụng.
    """
    settings = get_settings()
    return {
        "status": "ready",
        "runtime": "fin07.investigation.workflow",
        "agents": ["investigation_supervisor", "explanation_agent", "evidence_critic"],
        "model": settings.gemini_model,
        "max_agent_iterations": settings.max_agent_iterations,
        "max_tool_calls": settings.max_tool_calls,
    }


# ---------------------------------------------------------------------
# Explainable Multi-Agent AML Investigation
# ---------------------------------------------------------------------


@router.post("/alerts/{alert_id}/investigate", response_model=InvestigationStartOut)
def investigate_alert(alert_id: str, authorization: str | None = Header(default=None)) -> InvestigationStartOut:
    """Create a persistent investigation and enqueue the bounded workflow."""
    triggered_by = "system"
    if authorization:
        triggered_by = _require_user(authorization)["user_id"]
    try:
        with get_session() as session:
            investigation = InvestigationRepository(session).create(alert_id, triggered_by=triggered_by)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        job_id = queue.enqueue("investigate_alert", {"investigation_id": investigation.investigation_id})
    except Exception as exc:
        with get_session() as session:
            InvestigationRepository(session).update_state(
                investigation.investigation_id,
                status=InvestigationStatus.FAILED,
                workflow_state=WorkflowState.FAILED,
                failure_reason=f"Redis enqueue failed: {type(exc).__name__}",
                completed=True,
            )
        raise HTTPException(status_code=503, detail="Không thể giao tác vụ điều tra cho worker") from exc
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("aml.alert.id", investigation.alert_id)
        span.set_attribute("aml.case.id", investigation.case_id)
        span.set_attribute("aml.investigation.id", investigation.investigation_id)
        span.set_attribute("messaging.message.id", job_id)
    return InvestigationStartOut(
        investigation_id=investigation.investigation_id,
        alert_id=investigation.alert_id,
        case_id=investigation.case_id,
        job_id=job_id,
    )


@router.get("/alerts/{alert_id}/investigation", response_model=InvestigationOut | None)
def latest_alert_investigation(alert_id: str) -> InvestigationOut | None:
    with get_session() as session:
        row = session.execute(
            text("SELECT investigation_id FROM investigation WHERE alert_id = :id ORDER BY created_at DESC LIMIT 1"),
            {"id": alert_id},
        ).scalar_one_or_none()
        return InvestigationRepository(session).get(row) if row else None


@router.get("/feedback/labels", response_model=ReviewFeedbackPage)
def list_review_feedback(
    label: Literal["SUSPICIOUS", "NOT_SUSPICIOUS", "INCONCLUSIVE"] | None = None,
    since: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None),
) -> ReviewFeedbackPage:
    """Nhãn từ chuyên viên, dùng để hiệu chỉnh ngưỡng và huấn luyện lại.

    Đây là đầu ra của vòng phản hồi: mỗi dòng là một quyết định của con người
    kèm đúng điểm số mà họ nhìn thấy lúc ra quyết định. Không có endpoint này
    thì nhãn nằm chết trong DB và mũi tên "learning loop" chỉ là hình vẽ.
    """
    user = _require_user(authorization)
    if user["role"] not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="Vai trò này không được đọc nhãn rà soát")

    filters = ["1=1"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if label:
        filters.append("label = :label")
        params["label"] = label
    if since:
        filters.append("reviewed_at >= :since")
        params["since"] = since
    where = " AND ".join(filters)

    with get_session() as session:
        total = session.execute(text(f"SELECT count(*) FROM review_feedback WHERE {where}"), params).scalar_one()
        rows = (
            session.execute(
                text(
                    f"""SELECT feedback_id, investigation_id, alert_id, case_id, account_key,
                               decision, label, reason, risk_score, detector, typology_code,
                               typology_was_fallback, investigation_status, reviewed_by, reviewed_at
                          FROM review_feedback WHERE {where}
                         ORDER BY reviewed_at DESC, feedback_id
                         LIMIT :limit OFFSET :offset"""
                ),
                params,
            )
            .mappings()
            .all()
        )
    return ReviewFeedbackPage(
        total=int(total),
        items=[ReviewFeedbackOut.model_validate(dict(row)) for row in rows],
    )


@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
def get_investigation(investigation_id: str) -> InvestigationOut:
    try:
        with get_session() as session:
            return InvestigationRepository(session).get(investigation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/investigations/{investigation_id}/evidence", response_model=list[EvidenceEnvelope])
def get_investigation_evidence(investigation_id: str) -> list[EvidenceEnvelope]:
    with get_session() as session:
        repository = InvestigationRepository(session)
        try:
            repository.get(investigation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return repository.list_evidence(investigation_id)


@router.get("/investigations/{investigation_id}/trace", response_model=list[TraceEvent])
def get_investigation_trace(investigation_id: str) -> list[TraceEvent]:
    with get_session() as session:
        repository = InvestigationRepository(session)
        try:
            repository.get(investigation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return repository.list_trace(investigation_id)


@router.get("/investigations/{investigation_id}/explanation", response_model=Explanation)
def get_investigation_explanation(investigation_id: str) -> Explanation:
    with get_session() as session:
        repository = InvestigationRepository(session)
        try:
            repository.get(investigation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        # A run stopped by the critic still holds the explanation that sent it
        # to a human, and that is what the reviewer has to read to act on it.
        # The unvalidated version is served here and labelled in the UI; the
        # case package below still refuses anything the critic has not passed.
        explanation = repository.latest_explanation(investigation_id) or repository.latest_explanation(
            investigation_id, validated_only=False
        )
        if explanation is None:
            raise HTTPException(status_code=409, detail="Chưa có bản giải thích nào cho phiên điều tra này")
        return explanation


@router.get("/investigations/{investigation_id}/package", response_model=InvestigationPackage)
def get_investigation_package(investigation_id: str) -> InvestigationPackage:
    with get_session() as session:
        repository = InvestigationRepository(session)
        try:
            state = repository.get(investigation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        explanation = repository.latest_explanation(investigation_id)
        if explanation is None:
            raise HTTPException(status_code=409, detail="Chưa có bản giải thích đã kiểm chứng")
        return build_case_package(
            investigation_id,
            state.account_key,
            state.risk_summary,
            explanation,
            repository.list_evidence(investigation_id),
        )


@router.post("/investigations/{investigation_id}/review", response_model=InvestigationOut)
def review_investigation(
    investigation_id: str,
    request: ReviewRequest,
    authorization: str | None = Header(default=None),
) -> InvestigationOut:
    user = _require_user(authorization)
    if user["role"] not in {"manager"}:
        raise HTTPException(status_code=403, detail="Vai trò này không được rà soát phiên điều tra")
    try:
        with get_session() as session:
            reviewed = InvestigationRepository(session).review(
                investigation_id,
                user_id=user["user_id"],
                decision=request.decision,
                reason=request.reason,
            )
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("aml.investigation.id", investigation_id)
                span.set_attribute("aml.case.id", reviewed.case_id)
                span.set_attribute("aml.human_review.decision", request.decision)
            return reviewed
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
        transactions = _recent_account_transactions(session, draft["subject_account_key"], 20)
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
                # type + inner payload để giao diện render DỄ ĐỌC theo loại (không
                # đổ JSON thô cho chuyên viên).
                "type": payload.get("type", ""),
                "payload": payload.get("payload", payload),
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
    # Đồ thị mạng lưới của vụ cho PDF: chủ thể + đối tác, cạnh = giao dịch. Cạnh
    # có số tiền ở nhóm cao (>= phân vị 75) được đánh dấu đáng ngờ (vẽ đỏ).
    _amounts = sorted(float(t["amount"]) for t in transactions) or [0.0]
    _thr = _amounts[int(len(_amounts) * 0.75)] if len(_amounts) > 1 else _amounts[0]
    _net_nodes: set[str] = {draft["subject_account_key"]}
    _net_edges: list[dict[str, Any]] = []
    for t in transactions:
        _net_nodes.add(t["from_account_key"])
        _net_nodes.add(t["to_account_key"])
        _net_edges.append(
            {"from": t["from_account_key"], "to": t["to_account_key"], "suspicious": float(t["amount"]) >= _thr}
        )
    network = {"subject": draft["subject_account_key"], "nodes": sorted(_net_nodes), "edges": _net_edges}
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
        # Câu "-SUM" là TÓM TẮT hành vi nghi vấn (AI soạn); còn lại là NHẬN ĐỊNH.
        # Tách để PDF/UI hiện tóm tắt riêng, danh sách nhận định riêng.
        "statements": [
            {"id": s["statement_id"], "text": s["body"], "evidenceIds": list(s["evidence_ids"])}
            for s in statements
            if not str(s["statement_id"]).endswith("-SUM")
        ],
        "behaviourSummary": next(
            (s["body"] for s in statements if str(s["statement_id"]).endswith("-SUM")),
            " ".join(s["body"] for s in statements),
        ),
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
        "network": network,
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
def list_sars() -> list[dict[str, Any]]:
    with get_session() as session:
        ids = session.execute(text("SELECT sar_draft_id FROM sar_draft ORDER BY created_at DESC")).scalars().all()
    return [_sar_payload(sar_id) for sar_id in ids]


@router.get("/sars/{sar_id}")
def get_sar(sar_id: str) -> dict[str, Any]:
    return _sar_payload(sar_id)


@router.post("/cases/{case_id}/sar")
def create_sar(case_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"analyst", "manager"}:
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
        txs = _recent_account_transactions(session, case["subject_account_key"], 3)
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
        # --- AI soạn narrative: gom TẤT CẢ bằng chứng của vụ (bằng chứng điều tra
        # đã lưu + evidence giao dịch vừa tạo) để AI trích dẫn được nguồn thật. ---
        case_evidence = (
            session.execute(
                text(
                    "SELECT evidence_id, source_table, source_ref, payload FROM evidence "
                    "WHERE case_id = :c ORDER BY retrieved_at, evidence_id"
                ),
                {"c": case_id},
            )
            .mappings()
            .all()
        )
        ai_context = {
            "case_id": case_id,
            "subject_account": case["subject_account_key"],
            "transactions": [
                {
                    "transaction_id": str(tx["transaction_id"]),
                    "amount": str(tx["amount"]),
                    "currency": tx.get("currency"),
                    "direction": tx.get("direction"),
                }
                for tx in txs
            ],
            "evidence": [
                {
                    "id": e["evidence_id"],
                    "source": e["source_table"],
                    "ref": e["source_ref"],
                    "data": e["payload"] if isinstance(e["payload"], dict) else {},
                }
                for e in case_evidence
            ],
        }
        draft = draft_sar(ai_context)

        # ordinal 0 = TÓM TẮT hành vi nghi vấn; ordinal 1+ = các NHẬN ĐỊNH. Câu tóm
        # tắt cũng gắn một bằng chứng để không bị đánh "thiếu bằng chứng" khi kiểm.
        if draft:
            all_ev = sorted({ev for f in draft["findings"] for ev in f["evidence_ids"]})
            statements_to_write: list[tuple[str, list[str]]] = [
                (draft["summary"], (all_ev[:1] or evidence_ids[:1])),
                *[(f["text"], f["evidence_ids"]) for f in draft["findings"]],
            ]
        else:
            fallback_summary = (
                f"Tài khoản {case['subject_account_key']} phát sinh các giao dịch cần rà soát. "
                "Xem các nhận định và bằng chứng bên dưới."
            )
            statements_to_write = [
                (fallback_summary, evidence_ids[:1]),
                *[
                    (
                        f"Tài khoản {case['subject_account_key']} có giao dịch {tx['transaction_id']} "
                        f"trị giá {tx['amount']} {tx['currency']}.",
                        [evidence_ids[i]],
                    )
                    for i, tx in enumerate(txs)
                ],
            ]

        # ordinal >= 1 (ràng buộc CHECK). Câu tóm tắt (idx 0) mang id "-SUM" để
        # _sar_payload tách ra làm behaviourSummary; nhận định là "-LIVE-*".
        for idx, (body, evids) in enumerate(statements_to_write):
            statement_id = f"ST-{case_id}-SUM" if idx == 0 else f"ST-{case_id}-LIVE-{idx:03d}"
            session.execute(
                text(
                    "INSERT INTO sar_statement(statement_id, sar_draft_id, ordinal, body) VALUES (:id, :sar, :n, :body)"
                ),
                {"id": statement_id, "sar": sar_id, "n": idx + 1, "body": body},
            )
            for evid in evids:
                session.execute(
                    text("INSERT INTO sar_statement_evidence(statement_id, evidence_id) VALUES (:statement, :evidence)"),
                    {"statement": statement_id, "evidence": evid},
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


@router.put("/sars/{sar_id}/narrative")
def update_sar_narrative(
    sar_id: str, request: SarNarrativeRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Chuyên viên SỬA bản nháp SAR (tóm tắt + nội dung nhận định).

    Chỉ sửa được khi CHƯA gửi phê duyệt; sau khi sửa, hồ sơ quay về trạng thái
    ``drafting`` để buộc kiểm chứng lại trước khi gửi. Chỉ đổi PHẦN CHỮ; liên kết
    bằng chứng của mỗi nhận định giữ nguyên.
    """
    user = _require_user(authorization)
    if user["role"] not in {"analyst", "manager"}:
        raise HTTPException(status_code=403, detail="Vai trò hiện tại không được sửa SAR")
    with get_session() as session:
        draft = (
            session.execute(text("SELECT case_id, status FROM sar_draft WHERE sar_draft_id = :id"), {"id": sar_id})
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")
        if draft["status"] in {"submitted_for_approval", "approved"}:
            raise HTTPException(status_code=409, detail="Hồ sơ đã gửi phê duyệt, không sửa được nữa")
        # Tóm tắt (câu "-SUM").
        session.execute(
            text("UPDATE sar_statement SET body = :b WHERE sar_draft_id = :s AND statement_id = :sid"),
            {"b": request.summary.strip(), "s": sar_id, "sid": f"ST-{draft['case_id']}-SUM"},
        )
        # Nội dung từng nhận định theo id (không đụng liên kết bằng chứng).
        for f in request.findings:
            session.execute(
                text("UPDATE sar_statement SET body = :b WHERE sar_draft_id = :s AND statement_id = :id"),
                {"b": f.text.strip(), "s": sar_id, "id": f.id},
            )
        # Sửa xong → về drafting để kiểm chứng lại trước khi gửi.
        session.execute(
            text("UPDATE sar_draft SET status = 'drafting' WHERE sar_draft_id = :id"), {"id": sar_id}
        )
        session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'sar_updated', :actor, :role, CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": draft["case_id"],
                "actor": user["user_id"],
                "role": _audit_role(user["role"]),
                "payload": json.dumps({"sar_draft_id": sar_id, "action": "edited"}),
            },
        )
    return _sar_payload(sar_id)


@router.post("/sars/{sar_id}/validate")
def validate_sar(sar_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
def submit_sar(
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
def decide_approval(
    approval_id: str, request: ApprovalDecisionRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"manager"}:
        raise HTTPException(status_code=403, detail="Chỉ Quản lý được ra quyết định phê duyệt")
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


def _sar_queue_context(session: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Dựng NGỮ CẢNH THẬT cho trợ lý từ bảng sar_draft/approval/aml_case.

    Trả (trusted, untrusted): trusted là số liệu/định danh do hệ tính; untrusted là
    văn bản tự do (tiêu đề vụ) — đánh dấu để mô hình không làm theo chỉ thị trong đó.
    """
    rows = (
        session.execute(
            text(
                """SELECT d.sar_draft_id, d.case_id, d.status AS sar_status,
                          c.risk_score, c.priority, c.state, c.subject_account_key, c.title,
                          (a.decision = 'pending') AS awaiting_decision,
                          (SELECT count(*) FROM uncited_statement u WHERE u.sar_draft_id = d.sar_draft_id) AS uncited
                     FROM sar_draft d
                     JOIN aml_case c USING (case_id)
                     LEFT JOIN approval a ON a.sar_draft_id = d.sar_draft_id AND a.decision = 'pending'
                    ORDER BY (a.decision = 'pending') DESC NULLS LAST, c.risk_score DESC
                    LIMIT 25"""
            )
        )
        .mappings()
        .all()
    )
    trusted_items: list[dict[str, Any]] = []
    untrusted: list[dict[str, Any]] = []
    pending = 0
    high_risk = 0
    for r in rows:
        risk = round(float(r["risk_score"] or 0), 1)
        if r["awaiting_decision"]:
            pending += 1
        if risk >= 80:
            high_risk += 1
        trusted_items.append(
            {
                "sar_id": r["sar_draft_id"],
                "case_id": r["case_id"],
                "sar_status": r["sar_status"],
                "awaiting_decision": bool(r["awaiting_decision"]),
                "risk_score": risk,
                "priority": r["priority"],
                "case_state": r["state"],
                "subject_account": r["subject_account_key"],
                "uncited_statements": int(r["uncited"] or 0),
            }
        )
        if r["title"]:
            untrusted.append({"sar_id": r["sar_draft_id"], "case_title_raw": r["title"]})
    trusted = {
        "queue_name": "Hàng đợi phê duyệt SAR",
        "summary": {
            "total_drafts_shown": len(trusted_items),
            "awaiting_decision": pending,
            "high_risk_ge_80": high_risk,
        },
        "drafts": trusted_items,
        "notes": "Số liệu tổng hợp trực tiếp từ bảng sar_draft/approval/aml_case tại thời điểm hỏi.",
    }
    return trusted, untrusted


@router.post("/sars/ai-chat")
def sar_ai_chat(request: SarChatRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Trợ lý AI (Gemini) hỏi–đáp về hàng đợi SAR, có nền dữ liệu thật, chỉ tư vấn.

    Không tự quyết định duyệt/từ chối (NT3). Trả lời dựa trên ngữ cảnh hàng đợi
    được dựng server-side; văn bản tự do được cách ly (RK2).
    """
    user = _require_user(authorization)
    if user["role"] not in {"analyst", "manager", "admin"}:
        raise HTTPException(status_code=403, detail="Vai trò hiện tại không dùng được trợ lý")
    with get_session() as session:
        trusted, untrusted = _sar_queue_context(session)
    history = [{"role": m.role, "text": m.text} for m in request.history]
    answer = ai_assistant.ask(request.question, trusted, untrusted, history)
    return {"answer": answer, "grounded_on": trusted["summary"]}


@router.post(
    "/sars/{sar_id}/export",
    responses={200: {"content": {"application/pdf": {}}, "description": "Hồ sơ SAR dạng PDF tải về"}},
)
def export_sar(sar_id: str, authorization: str | None = Header(default=None)) -> Response:
    """Xuất hồ sơ SAR đã phê duyệt thành PDF tải về được.

    Trả về CHÍNH file PDF (không phải JSON): dựng từ ``_sar_payload`` — cùng dữ
    liệu giao diện hiển thị — nên tài liệu khớp màn hình. Vẫn giữ nguyên hai điều
    kiện nghiệp vụ: chỉ hồ sơ ``approved`` mới xuất được; và mỗi lần xuất ghi
    ``file_exported`` vào audit + chuyển vụ việc sang ``XuatHoSo``.
    """
    user = _require_user(authorization)
    exported_at = datetime.now(UTC)
    with get_session() as session:
        draft = (
            session.execute(text("SELECT case_id, status FROM sar_draft WHERE sar_draft_id = :id"), {"id": sar_id})
            .mappings()
            .first()
        )
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy SAR {sar_id}")
        # Hồ sơ đã phê duyệt → xuất CHÍNH THỨC: chuyển vụ sang XuatHoSo + ghi audit.
        # Chưa duyệt → xuất BẢN NHÁP để chuyên viên đọc/soát trước khi gửi duyệt:
        # KHÔNG chuyển trạng thái, PDF đóng dấu "BẢN NHÁP — CHƯA PHÊ DUYỆT".
        is_final = draft["status"] == "approved"
        if is_final:
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
                    "payload": json.dumps({"sar_draft_id": sar_id, "format": "pdf"}),
                },
            )

    # Dựng PDF SAU khi commit trạng thái/audit; nội dung là ảnh chụp dữ liệu hiện tại.
    payload = _sar_payload(sar_id)
    pdf_bytes = build_sar_pdf(
        payload, exported_by=user.get("name") or user["user_id"], exported_at=exported_at, draft=not is_final
    )
    filename = f"{sar_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cases/{case_id}/network")
def case_network(case_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    with get_session() as session:
        case = (
            session.execute(
                text(
                    """SELECT c.case_id, c.subject_account_key, c.risk_score, c.assigned_to, cu.customer_id
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
        # Cùng phạm vi cấp-bản-ghi với chi tiết vụ việc: chặn đọc đồ thị của vụ
        # việc không được giao (IDOR).
        _enforce_case_scope(authorization, case["assigned_to"])
        txs = _recent_account_transactions(session, case["subject_account_key"], 30)
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
def list_users(authorization: str | None = Header(default=None)) -> list[UserOut]:
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
def list_settings(authorization: str | None = Header(default=None)) -> dict[str, Any]:
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
def update_user(user_id: str, request: UserUpdateRequest, authorization: str | None = Header(default=None)) -> UserOut:
    user = _require_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Chỉ Quản trị viên được thay đổi trạng thái tài khoản")
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
def update_setting(
    code: str, request: SettingUpdateRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    user = _require_user(authorization)
    if user["role"] not in {"admin"}:
        raise HTTPException(status_code=403, detail="Chỉ Quản trị viên được sửa cấu hình")
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
