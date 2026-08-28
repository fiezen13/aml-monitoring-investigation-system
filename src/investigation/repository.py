from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.llm import GeminiCallMetadata
from src.investigation.schemas import (
    EvidenceEnvelope,
    EvidenceIntegrity,
    EvidenceType,
    Explanation,
    InvestigationOut,
    InvestigationStatus,
    TraceEvent,
    ValidationResult,
    WorkflowState,
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def snapshot_time(session: Session, account_key: str, alert_created_at: datetime) -> datetime:
    """Mốc thời gian điểm-trong-quá-khứ cho MỌI phép đo của một vụ việc.

    ``now()`` là sai ở đây: cảnh báo dựng trên dữ liệu lịch sử, nên cửa sổ neo
    vào giờ hệ thống sẽ nằm hoàn toàn sau giao dịch cuối cùng và mọi công cụ trả
    về rỗng. Mốc là giao dịch gần nhất của tài khoản TÍNH ĐẾN LÚC CÓ CẢNH BÁO —
    dữ liệu mà bộ phát hiện cũng nhìn thấy được, và không bao giờ là tương lai.

    Hàm này ở cấp module vì nó phải dùng chung. Bản kể đồ thị trên trang vụ việc
    từng tự neo vào giao dịch mới nhất MỌI THỜI ĐIỂM: cùng một vụ, khối "tiền vào
    từ đâu" nói 13 979.96 còn bản giải thích nói 12 068.26, vì hai cửa sổ 30 ngày
    lệch nhau khi tài khoản còn giao dịch sau lúc cảnh báo nổ.
    """
    latest = session.execute(
        text(
            """SELECT max(occurred_at) FROM transaction
                WHERE occurred_at <= :alert_time
                  AND (from_account_key = :account OR to_account_key = :account)"""
        ),
        {"alert_time": alert_created_at, "account": account_key},
    ).scalar_one_or_none()
    return latest or alert_created_at


class InvestigationRepository:
    """Persistence boundary for the explicit workflow.

    SQL is fixed and parameterized. No agent-produced SQL ever reaches this
    class, and no prompt or hidden reasoning is stored.
    """

    def __init__(self, session: Session):
        self.session = session

    def _snapshot_time(self, account_key: str, alert_created_at: datetime) -> datetime:
        return snapshot_time(self.session, account_key, alert_created_at)

    def create(self, alert_id: str, *, triggered_by: str = "system") -> InvestigationOut:
        alert = (
            self.session.execute(
                text(
                    """SELECT alert_id, account_key, case_id, risk_score, typology_code, created_at
                         FROM alert WHERE alert_id = :alert_id FOR UPDATE"""
                ),
                {"alert_id": alert_id},
            )
            .mappings()
            .first()
        )
        if alert is None:
            raise LookupError(f"Không tìm thấy cảnh báo {alert_id}")

        existing = (
            self.session.execute(
                text(
                    """SELECT * FROM investigation
                        WHERE alert_id = :alert_id AND status IN ('QUEUED', 'INVESTIGATING')
                        ORDER BY created_at DESC LIMIT 1"""
                ),
                {"alert_id": alert_id},
            )
            .mappings()
            .first()
        )
        if existing:
            return self._out(dict(existing))

        case_id = alert["case_id"]
        if not case_id:
            case_id = _id("CASE")
            score = float(alert["risk_score"])
            priority = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low"
            self.session.execute(
                text(
                    """INSERT INTO aml_case
                       (case_id, subject_account_key, title, risk_score, priority)
                       VALUES (:case_id, :account_key, :title, :risk_score, :priority)"""
                ),
                {
                    "case_id": case_id,
                    "account_key": alert["account_key"],
                    "title": f"Rà soát cảnh báo {alert_id}",
                    "risk_score": alert["risk_score"],
                    "priority": priority,
                },
            )
            self.session.execute(
                text("UPDATE alert SET case_id = :case_id, status = 'grouped' WHERE alert_id = :alert_id"),
                {"case_id": case_id, "alert_id": alert_id},
            )

        settings = get_settings()
        investigation_id = _id("INV")
        snapshot = self._snapshot_time(alert["account_key"], alert["created_at"])
        config = {
            "max_agent_iterations": settings.max_agent_iterations,
            "max_tool_calls": settings.max_tool_calls,
            "max_graph_hops": settings.max_graph_hops,
            "max_graph_nodes": settings.max_graph_nodes,
            "max_graph_edges": settings.max_graph_edges,
            "transaction_limit": settings.investigation_tx_limit,
            "llm_mode": settings.llm_mode,
            "gemini_model": settings.gemini_model,
        }
        self.session.execute(
            text(
                """INSERT INTO investigation
                   (investigation_id, alert_id, case_id, account_key, status, workflow_state,
                    snapshot_time, config_snapshot, triggered_by)
                   VALUES (:id, :alert_id, :case_id, :account_key, 'QUEUED', 'INITIALIZED',
                           :snapshot, CAST(:config AS jsonb), :triggered_by)"""
            ),
            {
                "id": investigation_id,
                "alert_id": alert_id,
                "case_id": case_id,
                "account_key": alert["account_key"],
                "snapshot": snapshot,
                "config": _json(config),
                "triggered_by": triggered_by,
            },
        )
        self.session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'investigation_started', :actor, 'system', CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": case_id,
                "actor": triggered_by,
                "payload": _json({"investigation_id": investigation_id, "alert_id": alert_id}),
            },
        )
        self.add_trace(
            investigation_id,
            agent="orchestrator",
            event_type="INVESTIGATION_STARTED",
            output_ref=investigation_id,
            rationale="Alert accepted and immutable snapshot time fixed.",
        )
        return self.get(investigation_id)

    def get(self, investigation_id: str) -> InvestigationOut:
        row = (
            self.session.execute(
                text("SELECT * FROM investigation WHERE investigation_id = :id"), {"id": investigation_id}
            )
            .mappings()
            .first()
        )
        if row is None:
            raise LookupError(f"Không tìm thấy phiên điều tra {investigation_id}")
        return self._out(dict(row))

    @staticmethod
    def _out(row: dict[str, Any]) -> InvestigationOut:
        return InvestigationOut(**row)

    def update_state(
        self,
        investigation_id: str,
        *,
        status: InvestigationStatus | None = None,
        workflow_state: WorkflowState | None = None,
        iteration: int | None = None,
        tool_call_count: int | None = None,
        risk_summary: dict[str, Any] | None = None,
        accounts_expanded: list[str] | None = None,
        open_questions: list[str] | None = None,
        validation: ValidationResult | None = None,
        failure_reason: str | None = None,
        completed: bool = False,
    ) -> None:
        values: dict[str, Any] = {"id": investigation_id}
        assignments = ["updated_at = now()"]
        fields = {
            "status": status.value if status else None,
            "workflow_state": workflow_state.value if workflow_state else None,
            "iteration": iteration,
            "tool_call_count": tool_call_count,
            "failure_reason": failure_reason,
        }
        for key, value in fields.items():
            if value is not None:
                assignments.append(f"{key} = :{key}")
                values[key] = value
        for key, value in {
            "risk_summary": risk_summary,
            "accounts_expanded": accounts_expanded,
            "open_questions": open_questions,
            "validation": validation,
        }.items():
            if value is not None:
                if key == "accounts_expanded":
                    assignments.append("accounts_expanded = :accounts_expanded")
                    values[key] = value
                else:
                    assignments.append(f"{key} = CAST(:{key} AS jsonb)")
                    values[key] = _json(value)
        if completed:
            assignments.append("completed_at = now()")
        self.session.execute(
            text(f"UPDATE investigation SET {', '.join(assignments)} WHERE investigation_id = :id"), values
        )

    def add_evidence(
        self,
        investigation_id: str,
        *,
        evidence_type: EvidenceType,
        source: str,
        account_key: str,
        payload: dict[str, Any],
        source_record_ids: list[str],
        transaction_refs: list[str] | None = None,
        untrusted: bool = False,
    ) -> EvidenceEnvelope:
        investigation = self.get(investigation_id)
        canonical = {
            "type": evidence_type.value,
            "source": source,
            "account_key": account_key,
            "payload": payload,
            "source_record_ids": sorted(source_record_ids),
        }
        content_hash = _hash(canonical)
        evidence_id = f"EV-{content_hash[:24]}"
        envelope = EvidenceEnvelope(
            evidence_id=evidence_id,
            type=evidence_type,
            source=source,
            account_key=account_key,
            payload=payload,
            transaction_refs=transaction_refs or [],
            created_at=datetime.now(UTC),
            integrity=EvidenceIntegrity(
                source_system=source,
                source_record_ids=source_record_ids,
                content_hash=content_hash,
            ),
            is_untrusted_content=untrusted,
        )
        self.session.execute(
            text(
                """INSERT INTO evidence(evidence_id, case_id, source_table, source_ref, payload, evidence_hash)
                   VALUES (:id, :case_id, :source, :source_ref, CAST(:payload AS jsonb), :hash)
                   ON CONFLICT (evidence_id) DO NOTHING"""
            ),
            {
                "id": evidence_id,
                "case_id": investigation.case_id,
                "source": source,
                "source_ref": ",".join(source_record_ids)[:512] or investigation.alert_id,
                "payload": _json(envelope),
                "hash": content_hash,
            },
        )
        self.session.execute(
            text(
                """INSERT INTO investigation_evidence(investigation_id, evidence_id)
                   VALUES (:investigation_id, :evidence_id) ON CONFLICT DO NOTHING"""
            ),
            {"investigation_id": investigation_id, "evidence_id": evidence_id},
        )
        self.add_trace(
            investigation_id,
            agent="investigation_supervisor",
            event_type="EVIDENCE_ADDED",
            output_ref=evidence_id,
            rationale=f"Added {evidence_type.value} from allow-listed source {source}.",
        )
        return envelope

    def list_evidence(self, investigation_id: str) -> list[EvidenceEnvelope]:
        rows = self.session.execute(
            text(
                """SELECT e.payload FROM evidence e
                   JOIN investigation_evidence ie ON ie.evidence_id = e.evidence_id
                  WHERE ie.investigation_id = :id ORDER BY ie.added_at, e.evidence_id"""
            ),
            {"id": investigation_id},
        ).scalars()
        return [EvidenceEnvelope.model_validate(payload) for payload in rows]

    def add_trace(
        self,
        investigation_id: str,
        *,
        agent: str,
        event_type: str,
        tool: str | None = None,
        input_summary: dict[str, Any] | None = None,
        output_ref: str | None = None,
        rationale: str = "",
        model_name: str | None = None,
        prompt_version: str | None = None,
    ) -> str:
        trace_id = _id("TRC")
        self.session.execute(
            text(
                """INSERT INTO investigation_trace
                   (trace_id, investigation_id, agent, event_type, tool, input_summary, output_ref,
                    short_rationale, model_name, prompt_version)
                   VALUES (:id, :investigation_id, :agent, :event_type, :tool,
                           CAST(:input AS jsonb), :output_ref, :rationale, :model_name, :prompt_version)"""
            ),
            {
                "id": trace_id,
                "investigation_id": investigation_id,
                "agent": agent,
                "event_type": event_type,
                "tool": tool,
                "input": _json(input_summary or {}),
                "output_ref": output_ref,
                "rationale": rationale[:2048],
                "model_name": model_name,
                "prompt_version": prompt_version,
            },
        )
        return trace_id

    def list_trace(self, investigation_id: str) -> list[TraceEvent]:
        rows = (
            self.session.execute(
                text(
                    """SELECT trace_id, investigation_id, agent, event_type, tool,
                              input_summary, output_ref, short_rationale, model_name,
                              prompt_version, occurred_at
                         FROM investigation_trace WHERE investigation_id = :id
                         ORDER BY occurred_at, trace_id"""
                ),
                {"id": investigation_id},
            )
            .mappings()
            .all()
        )
        return [TraceEvent(**row) for row in rows]

    def start_agent_run(
        self,
        investigation_id: str,
        agent_name: str,
        iteration: int,
        summary: dict,
        *,
        model_provider: str,
        model_name: str,
        prompt_version: str,
    ) -> str:
        run_id = _id("RUN")
        self.session.execute(
            text(
                """INSERT INTO investigation_agent_run
                   (run_id, investigation_id, agent_name, iteration, status, input_summary,
                    model_provider, model_name)
                   VALUES (:run_id, :investigation_id, :agent_name, :iteration, 'RUNNING',
                           CAST(:summary AS jsonb), :provider, :model)"""
            ),
            {
                "run_id": run_id,
                "investigation_id": investigation_id,
                "agent_name": agent_name,
                "iteration": iteration,
                "summary": _json(summary),
                "provider": model_provider,
                "model": model_name,
            },
        )
        self.session.execute(
            text("UPDATE investigation_agent_run SET prompt_version = :version WHERE run_id = :run_id"),
            {"version": prompt_version, "run_id": run_id},
        )
        return run_id

    def finish_agent_run(
        self,
        run_id: str,
        output: Any,
        *,
        status: str = "SUCCEEDED",
        error_type: str | None = None,
        metadata: GeminiCallMetadata | None = None,
    ) -> None:
        self.session.execute(
            text(
                """UPDATE investigation_agent_run
                      SET status = :status, output_summary = CAST(:output AS jsonb),
                          completed_at = now(), error_type = :error_type
                          , request_timestamp = :request_timestamp, duration_ms = :duration_ms,
                          attempt_count = :attempt_count, input_token_count = :input_tokens,
                          output_token_count = :output_tokens, total_token_count = :total_tokens,
                          provider_response_id = :response_id
                    WHERE run_id = :run_id"""
            ),
            {
                "status": status,
                "output": _json(output),
                "error_type": error_type,
                "run_id": run_id,
                "request_timestamp": metadata.request_timestamp if metadata else None,
                "duration_ms": metadata.duration_ms if metadata else None,
                "attempt_count": metadata.attempt_count if metadata else None,
                "input_tokens": metadata.input_token_count if metadata else None,
                "output_tokens": metadata.output_token_count if metadata else None,
                "total_tokens": metadata.total_token_count if metadata else None,
                "response_id": metadata.response_id if metadata else None,
            },
        )

    def record_tool_call(
        self,
        investigation_id: str,
        run_id: str,
        tool_name: str,
        arguments: dict,
        *,
        status: str,
        output_ref: str | None,
        result_summary: dict,
        started_at: datetime,
        duration_ms: int,
        error_type: str | None = None,
    ) -> str:
        call_id = _id("TC")
        self.session.execute(
            text(
                """INSERT INTO investigation_tool_call
                   (tool_call_id, investigation_id, run_id, tool_name, arguments, status,
                    output_ref, result_summary, started_at, completed_at, duration_ms, error_type)
                   VALUES (:id, :investigation_id, :run_id, :tool, CAST(:arguments AS jsonb), :status,
                           :output_ref, CAST(:summary AS jsonb), :started_at, now(), :duration_ms, :error_type)"""
            ),
            {
                "id": call_id,
                "investigation_id": investigation_id,
                "run_id": run_id,
                "tool": tool_name,
                "arguments": _json(arguments),
                "status": status,
                "output_ref": output_ref,
                "summary": _json(result_summary),
                "started_at": started_at,
                "duration_ms": max(0, duration_ms),
                "error_type": error_type,
            },
        )
        return call_id

    def save_validation(self, investigation_id: str, run_id: str, iteration: int, result: ValidationResult) -> str:
        validation_id = _id("VAL")
        self.session.execute(
            text(
                """INSERT INTO investigation_validation
                   (validation_id, investigation_id, run_id, iteration, status, confidence, result)
                   VALUES (:id, :investigation_id, :run_id, :iteration, :status, :confidence,
                           CAST(:result AS jsonb))"""
            ),
            {
                "id": validation_id,
                "investigation_id": investigation_id,
                "run_id": run_id,
                "iteration": iteration,
                "status": result.status,
                "confidence": result.confidence,
                "result": _json(result),
            },
        )
        return validation_id

    def save_explanation(self, investigation_id: str, explanation: Explanation, *, validated: bool) -> str:
        state = self.get(investigation_id)
        version = self.session.execute(
            text("SELECT coalesce(max(version), 0) + 1 FROM case_explanation WHERE investigation_id = :id"),
            {"id": investigation_id},
        ).scalar_one()
        explanation_id = _id("EXP")
        self.session.execute(
            text(
                """INSERT INTO case_explanation
                   (explanation_id, investigation_id, case_id, version, explanation, validated)
                   VALUES (:id, :investigation_id, :case_id, :version, CAST(:explanation AS jsonb), :validated)"""
            ),
            {
                "id": explanation_id,
                "investigation_id": investigation_id,
                "case_id": state.case_id,
                "version": version,
                "explanation": _json(explanation),
                "validated": validated,
            },
        )
        return explanation_id

    def latest_explanation(self, investigation_id: str, *, validated_only: bool = True) -> Explanation | None:
        condition = "AND validated" if validated_only else ""
        payload = self.session.execute(
            text(
                f"""SELECT explanation FROM case_explanation
                    WHERE investigation_id = :id {condition}
                    ORDER BY version DESC LIMIT 1"""
            ),
            {"id": investigation_id},
        ).scalar_one_or_none()
        return Explanation.model_validate(payload) if payload else None

    def review(self, investigation_id: str, *, user_id: str, decision: str, reason: str) -> InvestigationOut:
        state = self.get(investigation_id)
        if state.status not in {
            InvestigationStatus.COMPLETED,
            InvestigationStatus.NEEDS_HUMAN_REVIEW,
            InvestigationStatus.INSUFFICIENT_EVIDENCE,
        }:
            raise ValueError("Phiên điều tra chưa sẵn sàng để chuyên viên rà soát")
        review = {"decision": decision, "reason": reason, "reviewed_by": user_id, "reviewed_at": datetime.now(UTC)}
        self.session.execute(
            text(
                "UPDATE investigation SET human_review = CAST(:review AS jsonb), updated_at = now() WHERE investigation_id = :id"
            ),
            {"review": _json(review), "id": investigation_id},
        )
        self.session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'investigation_reviewed', :actor, 'investigator', CAST(:payload AS jsonb))"""
            ),
            {"case_id": state.case_id, "actor": user_id, "payload": _json(review)},
        )
        self._apply_case_transition(state, decision=decision, user_id=user_id)
        self._record_feedback(state, decision=decision, reason=reason, user_id=user_id)
        return self.get(investigation_id)

    #: Quyết định của người rà soát ĐẨY VỤ VIỆC ĐI ĐÂU.
    #:
    #: Trước đây `review()` chỉ ghi `human_review`, một dòng nhật ký và một nhãn
    #: huấn luyện — vụ việc không nhúc nhích. Chọn "Đóng — cảnh báo giả" xong vụ
    #: vẫn nằm ở "Tiếp nhận cảnh báo" giữa hàng nghìn vụ khác, nên năm lựa chọn
    #: ấy chỉ là nơi thu thập nhãn chứ chưa điều hành được quy trình.
    #:
    #: Hai lựa chọn KHÔNG đổi trạng thái, có chủ ý:
    #: * CONTINUE_MONITORING — nghĩa đen là giữ nguyên và theo dõi tiếp; đẩy đi
    #:   đâu cũng sai với chính lựa chọn ấy.
    #: * ESCALATE_TO_L2 — máy trạng thái không có khái niệm "cấp rà soát 2".
    #:   Bịa một trạng thái cho nó sẽ tạo một bậc quy trình không ai định nghĩa.
    _DECISION_STATES = {
        "REVIEW_FOR_SAR_STR": "SoanHoSoNghiVan",
        "REQUEST_MORE_INFORMATION": "DieuTraBoSung",
    }

    def _apply_case_transition(self, state: InvestigationOut, *, decision: str, user_id: str) -> None:
        # "Đóng, không báo cáo" KHÔNG đi thẳng: nó rẽ theo mức rủi ro.
        #
        # Đây là chốt phân tách nhiệm vụ. Cho chuyên viên đóng mọi vụ thì một
        # người vừa điều tra vừa tự kết luận không báo cáo, đúng thứ mà chốt
        # "người gửi không được tự phê duyệt" ở tầng SAR sinh ra để ngăn. Bắt
        # duyệt mọi vụ thì hàng đợi của quản lý nhận cả 14.263 vụ.
        if decision == "CLOSE_AS_LIKELY_FALSE_POSITIVE":
            self._close_or_request_close(state, user_id=user_id)
            return

        target = self._DECISION_STATES.get(decision)
        if target is None:
            return
        # KHÔNG kéo ngược một vụ đã kết thúc hoặc đang chờ phê duyệt: hồ sơ đã
        # xuất và hồ sơ nằm trong hàng đợi phê duyệt đều do luồng khác làm chủ,
        # một lượt rà soát muộn không được giành lại quyền ấy.
        if self.session.execute(
            text("SELECT state FROM aml_case WHERE case_id = :c"), {"c": state.case_id}
        ).scalar_one_or_none() == "ChoNguoiPheDuyet":
            # Vụ đang nằm trong hàng đợi phê duyệt thì quản lý làm chủ nó; một
            # kết luận muộn của chuyên viên không được giành lại quyền ấy.
            return
        self._set_case_state(state.case_id, target, user_id=user_id, decision=decision)

    #: Quy đổi quyết định của chuyên viên thành nhãn huấn luyện.
    #:
    #: "Cần thêm thông tin" và "tiếp tục theo dõi" KHÔNG phải nhãn âm: chuyên
    #: viên chưa kết luận. Gộp chúng vào nhóm âm sẽ dạy mô hình rằng mọi cảnh báo
    #: chưa xử lý xong đều là báo động giả.
    _DECISION_LABELS = {
        "REVIEW_FOR_SAR_STR": "SUSPICIOUS",
        "ESCALATE_TO_L2": "SUSPICIOUS",
        "CLOSE_AS_LIKELY_FALSE_POSITIVE": "NOT_SUSPICIOUS",
        "CONTINUE_MONITORING": "INCONCLUSIVE",
        "REQUEST_MORE_INFORMATION": "INCONCLUSIVE",
    }

    def _close_or_request_close(self, state: InvestigationOut, *, user_id: str) -> None:
        """Vụ nhẹ thì chuyên viên đóng thẳng; vụ nặng thì xin Quản lý duyệt.

        Ngưỡng lấy từ ``case_self_close_max_risk`` (mặc định 80 — cùng lằn ranh
        "nghiêm trọng" mà `priority` và badge critical đang dùng, không đẻ thêm
        một định nghĩa "rủi ro cao" thứ ba).
        """
        row = (
            self.session.execute(
                text("SELECT risk_score, state FROM aml_case WHERE case_id = :c FOR UPDATE"),
                {"c": state.case_id},
            )
            .mappings()
            .first()
        )
        if row is None or row["state"] in {"XuatHoSo", "DongKhongBaoCao", "ChoNguoiPheDuyet"}:
            return

        threshold = get_settings().case_self_close_max_risk
        if float(row["risk_score"]) < threshold:
            self._set_case_state(state.case_id, "DongKhongBaoCao", user_id=user_id, decision="tu_dong")
            return

        # Vượt ngưỡng: mở một đề xuất ĐÓNG trong hàng đợi phê duyệt. Dùng lại
        # bảng `approval` chứ không dựng bảng thứ hai — quản lý phải có MỘT chỗ
        # duy nhất để chốt, không phải hai hàng đợi cho hai loại đề xuất.
        # `sar_draft_id` để NULL: đề nghị đóng thì không có hồ sơ nào kèm theo.
        existing = self.session.execute(
            text(
                """SELECT approval_id FROM approval
                    WHERE case_id = :c AND request_kind = 'close' AND decision = 'pending'"""
            ),
            {"c": state.case_id},
        ).scalar_one_or_none()
        if existing is None:
            self.session.execute(
                text(
                    """INSERT INTO approval (approval_id, case_id, sar_draft_id, decision, request_kind)
                       VALUES (:a, :c, NULL, 'pending', 'close')"""
                ),
                {"a": _id("APR"), "c": state.case_id},
            )
        self._set_case_state(state.case_id, "ChoNguoiPheDuyet", user_id=user_id, decision="xin_duyet_dong")

    def _set_case_state(self, case_id: str, target: str, *, user_id: str, decision: str) -> None:
        changed = self.session.execute(
            text(
                """UPDATE aml_case SET state = :target, updated_at = now()
                    WHERE case_id = :case_id
                      AND state NOT IN ('XuatHoSo', 'DongKhongBaoCao')
                      AND state <> :target
                 RETURNING case_id"""
            ),
            {"target": target, "case_id": case_id},
        ).first()
        if changed is None:
            return
        self.session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, 'case_state_changed', :actor, 'analyst', CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": case_id,
                "actor": user_id,
                "payload": _json({"decision": decision, "new_state": target, "source": "human_review"}),
            },
        )

    def _record_feedback(self, state: InvestigationOut, *, decision: str, reason: str, user_id: str) -> None:
        """Lưu nhãn kèm ảnh chụp điểm tại thời điểm ra quyết định.

        Điểm trong bảng ``alert`` thay đổi mỗi khi nạp bản phát hành mới. Nhãn
        phải dính với con số mà chuyên viên thật sự nhìn thấy, nếu không thì
        không hiệu chỉnh được ngưỡng nào từ nó.
        """
        snapshot = (
            self.session.execute(
                text(
                    """SELECT a.risk_score, a.detector, a.typology_code, m.is_fallback
                         FROM alert a
                         LEFT JOIN alert_typology_match m ON m.alert_id = a.alert_id
                        WHERE a.alert_id = :alert"""
                ),
                {"alert": state.alert_id},
            )
            .mappings()
            .first()
        ) or {}
        self.session.execute(
            text(
                """INSERT INTO review_feedback (
                       feedback_id, investigation_id, alert_id, case_id, account_key,
                       decision, label, reason,
                       risk_score, detector, typology_code, typology_was_fallback,
                       investigation_status, reviewed_by
                   ) VALUES (
                       :feedback_id, :investigation_id, :alert_id, :case_id, :account_key,
                       :decision, :label, :reason,
                       :risk_score, :detector, :typology_code, :typology_was_fallback,
                       :investigation_status, :reviewed_by
                   )"""
            ),
            {
                "feedback_id": _id("FBK"),
                "investigation_id": state.investigation_id,
                "alert_id": state.alert_id,
                "case_id": state.case_id,
                "account_key": state.account_key,
                "decision": decision,
                "label": self._DECISION_LABELS.get(decision, "INCONCLUSIVE"),
                "reason": reason,
                "risk_score": snapshot.get("risk_score"),
                "detector": snapshot.get("detector"),
                "typology_code": snapshot.get("typology_code"),
                "typology_was_fallback": snapshot.get("is_fallback"),
                "investigation_status": str(state.status),
                "reviewed_by": user_id,
            },
        )
