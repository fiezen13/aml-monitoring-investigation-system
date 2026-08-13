from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.agents import EvidenceCriticAgent, ExplanationAgent, InvestigationSupervisorAgent
from src.investigation.llm import GeminiCallMetadata, GeminiService, GeminiServiceError, get_gemini_service
from src.investigation.prompts import get_prompt
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import InvestigationStatus, ValidationResult, WorkflowState
from src.investigation.tools import InvestigationTools, timed_execute

logger = logging.getLogger("fin07.investigation")


class InvestigationWorkflow:
    """Explicit bounded Supervisor → Explanation → Critic state machine."""

    def __init__(self, session: Session, *, gemini_service: GeminiService | None = None):
        self.session = session
        self.repository = InvestigationRepository(session)
        self.settings = get_settings()
        self.gemini_service = gemini_service

    def _alert(self, alert_id: str) -> dict[str, Any]:
        row = (
            self.session.execute(
                text(
                    """SELECT alert_id, account_key, case_id, detector, typology_code,
                              risk_score, created_at
                         FROM alert WHERE alert_id = :id"""
                ),
                {"id": alert_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise LookupError(f"Không tìm thấy cảnh báo {alert_id}")
        return dict(row)

    async def run(self, investigation_id: str) -> None:
        state = self.repository.get(investigation_id)
        alert = self._alert(state.alert_id)
        self.repository.update_state(
            investigation_id,
            status=InvestigationStatus.INVESTIGATING,
            workflow_state=WorkflowState.COLLECTING_EVIDENCE,
        )
        last_validation: ValidationResult | None = None
        last_explanation = None
        tool_count = state.tool_call_count
        service: GeminiService | None = self.gemini_service
        owns_service = service is None

        try:
            service = service or get_gemini_service(self.settings)
            supervisor = InvestigationSupervisorAgent(service, investigation_id)
            explanation_agent = ExplanationAgent(service, investigation_id)
            critic = EvidenceCriticAgent(self.session, service, investigation_id)
            model_provider = "google-genai" if self.settings.llm_mode == "gemini" else "fake-gemini"
            for iteration in range(1, self.settings.max_agent_iterations + 1):
                self.repository.update_state(investigation_id, iteration=iteration)
                evidence = self.repository.list_evidence(investigation_id)
                supervisor_run = self.repository.start_agent_run(
                    investigation_id,
                    supervisor.name,
                    iteration,
                    {"alert_id": alert["alert_id"], "evidence_count": len(evidence)},
                    model_provider=model_provider,
                    model_name=service.model_for(supervisor.name),
                    prompt_version=get_prompt(supervisor.name).version,
                )
                self._trace_gemini_request(investigation_id, supervisor.name, service)
                try:
                    plan_result = await supervisor.plan(alert=alert, evidence=evidence, validation=last_validation)
                except GeminiServiceError as exc:
                    self.repository.finish_agent_run(
                        supervisor_run, {}, status=self._run_error_status(exc), error_type=type(exc).__name__
                    )
                    raise
                plan = plan_result.output
                self.repository.finish_agent_run(supervisor_run, plan, metadata=plan_result.metadata)
                self._trace_gemini_response(investigation_id, supervisor.name, plan_result.metadata)
                remaining = max(0, self.settings.max_tool_calls - tool_count)
                plan.decisions = plan.decisions[:remaining]
                self.repository.add_trace(
                    investigation_id,
                    agent=supervisor.name,
                    event_type="AGENT_DECISION",
                    input_summary={"iteration": iteration, "evidence_count": len(evidence)},
                    output_ref=supervisor_run,
                    rationale="; ".join(decision.short_rationale for decision in plan.decisions)
                    or "Không chọn thêm công cụ nào trong danh sách được phép.",
                )

                tools = InvestigationTools(self.session, self.repository, investigation_id)
                for decision in plan.decisions:
                    arguments = decision.arguments.model_dump(mode="json", exclude_none=True)
                    self.repository.add_trace(
                        investigation_id,
                        agent=supervisor.name,
                        event_type="TOOL_CALL",
                        tool=decision.tool,
                        input_summary=arguments,
                        rationale=decision.short_rationale,
                    )
                    started_at = datetime.now(UTC)
                    started_monotonic = time.monotonic()
                    try:
                        execution, started_at, duration_ms = timed_execute(tools, decision.tool, arguments)
                        tool_count += 1
                        output_ref = execution.evidence.evidence_id if execution.evidence else None
                        call_id = self.repository.record_tool_call(
                            investigation_id,
                            supervisor_run,
                            decision.tool,
                            arguments,
                            status=execution.status,
                            output_ref=output_ref,
                            result_summary={
                                "available": execution.status == "SUCCEEDED",
                                "evidence_ref": output_ref,
                                "result_fields": sorted(execution.result),
                            },
                            started_at=started_at,
                            duration_ms=duration_ms,
                        )
                        self.repository.add_trace(
                            investigation_id,
                            agent=supervisor.name,
                            event_type="TOOL_RESULT",
                            tool=decision.tool,
                            output_ref=output_ref or call_id,
                            rationale=f"Công cụ hoàn tất với trạng thái {execution.status}.",
                        )
                        if decision.tool == "GetRiskBreakdown":
                            self.repository.update_state(investigation_id, risk_summary=execution.result)
                    except Exception as exc:  # noqa: BLE001 — errors are persisted and bounded
                        tool_count += 1
                        duration_ms = round((time.monotonic() - started_monotonic) * 1000)
                        call_id = self.repository.record_tool_call(
                            investigation_id,
                            supervisor_run,
                            decision.tool,
                            arguments,
                            status="FAILED",
                            output_ref=None,
                            result_summary={},
                            started_at=started_at,
                            duration_ms=duration_ms,
                            error_type=type(exc).__name__,
                        )
                        self.repository.add_trace(
                            investigation_id,
                            agent=supervisor.name,
                            event_type="TOOL_RESULT",
                            tool=decision.tool,
                            output_ref=call_id,
                            rationale=f"Công cụ thất bại với lỗi {type(exc).__name__}; không ghi nội dung dữ liệu.",
                        )
                        logger.warning(
                            "investigation tool failed",
                            extra={
                                "investigation_id": investigation_id,
                                "alert_id": alert["alert_id"],
                                "agent": supervisor.name,
                                "tool": decision.tool,
                                "error_type": type(exc).__name__,
                            },
                        )
                self.repository.update_state(
                    investigation_id,
                    tool_call_count=tool_count,
                    open_questions=plan.open_questions,
                    workflow_state=WorkflowState.EXPLAINING,
                )
                evidence = self.repository.list_evidence(investigation_id)
                explanation_run = self.repository.start_agent_run(
                    investigation_id,
                    explanation_agent.name,
                    iteration,
                    {"evidence_refs": [item.evidence_id for item in evidence]},
                    model_provider=model_provider,
                    model_name=service.model_for(explanation_agent.name),
                    prompt_version=get_prompt(explanation_agent.name).version,
                )
                self._trace_gemini_request(investigation_id, explanation_agent.name, service)
                try:
                    explanation_result = await explanation_agent.explain(alert, evidence)
                except GeminiServiceError as exc:
                    self.repository.finish_agent_run(
                        explanation_run, {}, status=self._run_error_status(exc), error_type=type(exc).__name__
                    )
                    raise
                last_explanation = explanation_result.output
                explanation_id = self.repository.save_explanation(investigation_id, last_explanation, validated=False)
                self.repository.finish_agent_run(
                    explanation_run, last_explanation, metadata=explanation_result.metadata
                )
                self._trace_gemini_response(investigation_id, explanation_agent.name, explanation_result.metadata)
                self.repository.add_trace(
                    investigation_id,
                    agent=explanation_agent.name,
                    event_type="EXPLANATION_GENERATED",
                    output_ref=explanation_id,
                    rationale="Đã tạo đầu ra DỮ KIỆN/SUY LUẬN có cấu trúc chỉ từ bằng chứng được trích dẫn.",
                )

                self.repository.update_state(investigation_id, workflow_state=WorkflowState.VALIDATING)
                critic_run = self.repository.start_agent_run(
                    investigation_id,
                    critic.name,
                    iteration,
                    {"explanation_id": explanation_id, "claim_count": len(last_explanation.claims)},
                    model_provider=model_provider,
                    model_name=service.model_for(critic.name),
                    prompt_version=get_prompt(critic.name).version,
                )
                self._trace_gemini_request(investigation_id, critic.name, service)
                try:
                    critic_result = await critic.validate(last_explanation, evidence)
                except GeminiServiceError as exc:
                    self.repository.finish_agent_run(
                        critic_run, {}, status=self._run_error_status(exc), error_type=type(exc).__name__
                    )
                    raise
                last_validation = critic_result.output
                validation_id = self.repository.save_validation(
                    investigation_id, critic_run, iteration, last_validation
                )
                self.repository.finish_agent_run(critic_run, last_validation, metadata=critic_result.metadata)
                self._trace_gemini_response(investigation_id, critic.name, critic_result.metadata)
                self.repository.update_state(investigation_id, validation=last_validation)
                event = "VALIDATION_PASS" if last_validation.status == "PASS" else "VALIDATION_FAIL"
                self.repository.add_trace(
                    investigation_id,
                    agent=critic.name,
                    event_type=event,
                    output_ref=validation_id,
                    rationale=(
                        "Mọi nhận định và bản ghi nguồn đều vượt qua bước kiểm chứng tất định."
                        if last_validation.status == "PASS"
                        else f"Phát hiện {len(last_validation.issues)} vấn đề; chuyển lại tác tử điều phối trong giới hạn cho phép."
                    ),
                )

                if last_validation.status == "PASS":
                    validated_id = self.repository.save_explanation(investigation_id, last_explanation, validated=True)
                    self.repository.update_state(
                        investigation_id,
                        status=InvestigationStatus.COMPLETED,
                        workflow_state=WorkflowState.COMPLETED,
                        completed=True,
                    )
                    self.repository.add_trace(
                        investigation_id,
                        agent="orchestrator",
                        event_type="INVESTIGATION_COMPLETED",
                        output_ref=validated_id,
                        rationale="Tác tử phản biện xác nhận đạt; gói bản nháp đã kiểm chứng sẵn sàng cho chuyên viên.",
                    )
                    self.repository.add_trace(
                        investigation_id,
                        agent="orchestrator",
                        event_type="HUMAN_REVIEW_REQUIRED",
                        output_ref=validated_id,
                        rationale="Đầu ra của tác tử chỉ mang tính tư vấn và không thể tự thực hiện quyết định nghiệp vụ AML cuối cùng.",
                    )
                    self._audit_completion(investigation_id, state.case_id, "investigation_completed")
                    return

                if tool_count >= self.settings.max_tool_calls:
                    break

            final_status = InvestigationStatus.INSUFFICIENT_EVIDENCE
            self.repository.update_state(
                investigation_id,
                status=final_status,
                workflow_state=WorkflowState.COMPLETED,
                failure_reason="Kiểm chứng bằng chứng chưa đạt trong giới hạn tác tử/công cụ đã cấu hình.",
                completed=True,
            )
            self.repository.add_trace(
                investigation_id,
                agent="orchestrator",
                event_type="HUMAN_REVIEW_REQUIRED",
                rationale="Đã đạt giới hạn cấu hình nhưng vẫn còn khoảng trống bằng chứng chưa được xử lý.",
            )
            self._audit_completion(investigation_id, state.case_id, "investigation_completed")
        except Exception as exc:
            if isinstance(exc, GeminiServiceError):
                self.repository.update_state(
                    investigation_id,
                    status=InvestigationStatus.NEEDS_HUMAN_REVIEW,
                    workflow_state=WorkflowState.COMPLETED,
                    failure_reason=f"{type(exc).__name__}: không thể chạy tác tử Gemini",
                    completed=True,
                )
                self.repository.add_trace(
                    investigation_id,
                    agent="orchestrator",
                    event_type="GEMINI_ERROR",
                    rationale=f"Lệnh gọi Gemini thất bại với lỗi {type(exc).__name__}; nội dung dữ liệu và thông tin xác thực không được ghi lại.",
                )
                self.repository.add_trace(
                    investigation_id,
                    agent="orchestrator",
                    event_type="HUMAN_REVIEW_REQUIRED",
                    rationale="Không thể hoàn tất tác vụ Gemini; cảnh báo vẫn được giữ lại để chuyên viên rà soát.",
                )
                logger.error("Gemini workflow unavailable: %s", type(exc).__name__)
            else:
                self.repository.update_state(
                    investigation_id,
                    status=InvestigationStatus.FAILED,
                    workflow_state=WorkflowState.FAILED,
                    failure_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
                    completed=True,
                )
                self.repository.add_trace(
                    investigation_id,
                    agent="orchestrator",
                    event_type="INVESTIGATION_FAILED",
                    rationale=f"Quy trình thất bại với lỗi {type(exc).__name__}; nội dung nhạy cảm không được ghi lại.",
                )
                logger.exception("Investigation %s failed", investigation_id)
            self._audit_completion(investigation_id, state.case_id, "investigation_failed")
        finally:
            if owns_service and service is not None:
                await service.close()

    @staticmethod
    def _run_error_status(exc: GeminiServiceError) -> str:
        return "TIMEOUT" if "Timeout" in type(exc).__name__ else "FAILED"

    def _trace_gemini_request(self, investigation_id: str, agent_name: str, service: GeminiService) -> None:
        prompt = get_prompt(agent_name)
        self.repository.add_trace(
            investigation_id,
            agent=agent_name,
            event_type="GEMINI_REQUEST",
            input_summary={"structured_output": True},
            rationale="Đã gửi chỉ dẫn hệ thống có phiên bản cùng ngữ cảnh bằng chứng có cấu trúc.",
            model_name=service.model_for(agent_name),
            prompt_version=prompt.version,
        )

    def _trace_gemini_response(self, investigation_id: str, agent_name: str, metadata: GeminiCallMetadata) -> None:
        self.repository.add_trace(
            investigation_id,
            agent=agent_name,
            event_type="GEMINI_RESPONSE",
            input_summary={
                "duration_ms": metadata.duration_ms,
                "attempt_count": metadata.attempt_count,
                "input_token_count": metadata.input_token_count,
                "output_token_count": metadata.output_token_count,
                "total_token_count": metadata.total_token_count,
            },
            output_ref=metadata.response_id,
            rationale="Đầu ra có cấu trúc của Gemini đã vượt qua kiểm chứng SDK và Pydantic.",
            model_name=metadata.model,
            prompt_version=metadata.prompt_version,
        )

    def _audit_completion(self, investigation_id: str, case_id: str, event_type: str) -> None:
        self.session.execute(
            text(
                """INSERT INTO audit_log(case_id, event_type, actor, actor_role, payload)
                   VALUES (:case_id, :event_type, 'investigation-worker', 'agent',
                           CAST(:payload AS jsonb))"""
            ),
            {
                "case_id": case_id,
                "event_type": event_type,
                "payload": '{"investigation_id":"' + investigation_id + '"}',
            },
        )
