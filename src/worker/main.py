"""Worker xử lý tác vụ nền của FIN-07.

Vòng đời một tác vụ điều tra kéo dài hàng phút (mục tiêu ≤ 3 phút,
ARC-001 mục 5.3) nên không chạy được trong vòng đời một HTTP request.
API đẩy tác vụ vào Redis, tiến trình này lấy ra và chạy.

Phần điều phối agent LangGraph do Hiển hiện thực ở Sprint 3. Ở đây worker
đã chạy được đầu–cuối: nhận tác vụ, chuyển trạng thái vụ việc, ghi nhật ký
kiểm toán, và giữ nhịp tim cho healthcheck của container.
"""

import asyncio
import json
import logging
import signal
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from opentelemetry import propagate, trace
from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_session
from src.domain import next_state, state_label
from src.investigation.repository import InvestigationRepository
from src.investigation.workflow import InvestigationWorkflow
from src.observability.context import bind_context
from src.observability.metrics import METRICS, attrs
from src.observability.telemetry import (
    initialize_observability,
    record_safe_exception,
    shutdown_observability,
    tracer,
)
from src.services.queue import get_redis

logger = logging.getLogger("fin07.worker")

_shutdown = False


def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Nhận tín hiệu %s — dừng sau khi xong tác vụ hiện tại", signal.Signals(signum).name)
    _shutdown = True


def beat() -> None:
    """Ghi nhịp tim. Healthcheck của container đọc đúng khoá này."""
    settings = get_settings()
    client = get_redis()
    client.set(settings.worker_heartbeat_key, str(time.time()), ex=settings.worker_heartbeat_ttl)
    METRICS.worker_available.set(1, attrs(queue=settings.worker_queue))
    depth = client.llen(settings.worker_queue)
    METRICS.worker_queue_depth.set(depth, attrs(queue=settings.worker_queue))
    oldest_age = 0.0
    if depth:
        try:
            oldest = json.loads(client.lindex(settings.worker_queue, 0) or "{}")
            enqueued_at = datetime.fromisoformat(str(oldest.get("enqueued_at", "")))
            oldest_age = max(0.0, (datetime.now(UTC) - enqueued_at).total_seconds())
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("oldest queued job has invalid metadata", extra={"queue": settings.worker_queue})
    METRICS.worker_oldest_queue_age.set(oldest_age, attrs(queue=settings.worker_queue))


def handle_investigate_case(payload: dict[str, Any]) -> None:
    """Chạy một bước điều tra: đẩy vụ việc sang trạng thái kế tiếp.

    Bước kế tiếp do src.domain.next_state quyết định, nên worker đi đúng
    chuỗi ở Hình 4 chứ không nhảy cóc. Chuỗi dừng ở ChoNguoiPheDuyet: không
    có nhánh nào ở đây đi tới XuatHoSo — lối vào duy nhất của XuatHoSo là
    một quyết định phê duyệt có người ký tên (NT3).
    """
    case_id = payload["case_id"]
    with get_session() as session:
        # Khoá dòng để hai lượt điều tra chạy song song không cùng đọc một
        # trạng thái rồi cùng ghi đè: nếu không, hai lần bấm nút gần nhau chỉ
        # tiến được một bước và một dòng nhật ký nói dối về trạng thái trước.
        current = session.execute(
            text("SELECT state FROM aml_case WHERE case_id = :case_id FOR UPDATE"),
            {"case_id": case_id},
        ).scalar_one_or_none()
        if current is None:
            logger.warning("Không tìm thấy vụ việc %s — bỏ qua", case_id)
            return

        target = next_state(current)
        if target is None:
            logger.info(
                "Vụ việc %s đang ở '%s' — cần quyết định của người phê duyệt, worker dừng",
                case_id,
                state_label(current),
            )
            return

        session.execute(
            text("UPDATE aml_case SET state = :target, updated_at = now() WHERE case_id = :case_id"),
            {"case_id": case_id, "target": target},
        )
        session.execute(
            text(
                """
                INSERT INTO audit_log (case_id, event_type, actor, actor_role, payload)
                VALUES (:case_id, 'case_state_changed', 'worker', 'system', :payload)
                """
            ),
            {
                "case_id": case_id,
                "payload": json.dumps({"from": current, "to": target}),
            },
        )
    logger.info("Vụ việc %s chuyển %s → %s", case_id, current, target)


def handle_ping(payload: dict[str, Any]) -> None:
    """Tác vụ rỗng dùng để kiểm chứng hàng đợi thông suốt."""
    logger.info("ping %s", payload)


def handle_investigate_alert(payload: dict[str, Any]) -> None:
    """Run the complete bounded explainable workflow for one alert."""
    investigation_id = payload["investigation_id"]
    started = time.monotonic()
    METRICS.investigations.add(1, attrs(status="started"))
    METRICS.investigations_active.add(1)
    final_status = "failed"
    with tracer().start_as_current_span(
        "investigation.run",
        attributes={"aml.investigation.id": investigation_id},
        record_exception=False,
    ) as span:
        try:
            with get_session() as session:
                workflow = InvestigationWorkflow(session)
                asyncio.run(workflow.run(investigation_id))
                state = InvestigationRepository(session).get(investigation_id)
                final_status = str(state.status.value if hasattr(state.status, "value") else state.status).lower()
                span.set_attribute("aml.investigation.status", final_status)
                usage = session.execute(
                    text(
                        """SELECT COALESCE(sum(input_token_count), 0),
                                  COALESCE(sum(output_token_count), 0),
                                  COALESCE(sum(total_token_count), 0),
                                  count(*)
                             FROM investigation_agent_run WHERE investigation_id = :id"""
                    ),
                    {"id": investigation_id},
                ).one()
                span.set_attribute("aml.genai.input_token_count", int(usage[0]))
                span.set_attribute("aml.genai.output_token_count", int(usage[1]))
                span.set_attribute("aml.genai.total_token_count", int(usage[2]))
                span.set_attribute("aml.agent.run_count", int(usage[3]))
                span.set_attribute("aml.agent.iteration_count", state.iteration)
                span.set_attribute("aml.tool.call_count", state.tool_call_count)
                METRICS.supervisor_accounts_expanded.record(len(state.accounts_expanded))
        except Exception as exc:
            record_safe_exception(span, exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
            raise
        finally:
            duration = time.monotonic() - started
            METRICS.investigation_duration.record(duration, attrs(status=final_status))
            METRICS.investigations.add(1, attrs(status=final_status))
            METRICS.investigations_active.add(-1)
            review_reason = {
                "completed": "validated_output",
                "needs_human_review": "provider_failure",
                "insufficient_evidence": "insufficient_evidence",
            }.get(final_status)
            if review_reason:
                METRICS.human_review.add(1, attrs(reason=review_reason))
            if final_status == "insufficient_evidence":
                METRICS.insufficient_evidence.add(1)
    logger.info("Explainable investigation %s finished", investigation_id)


HANDLERS = {
    "investigate_case": handle_investigate_case,
    "investigate_alert": handle_investigate_alert,
    "ping": handle_ping,
}


def process(raw: str) -> None:
    job = json.loads(raw)
    handler = HANDLERS.get(job.get("type", ""))
    if handler is None:
        METRICS.worker_dead_jobs.add(1, attrs(job_type="unknown", reason="missing_handler"))
        logger.error("Không có handler cho tác vụ loại %r (job %s)", job.get("type"), job.get("job_id"))
        return
    settings = get_settings()
    job_id = str(job.get("job_id", "unknown"))
    job_type = str(job.get("type", "unknown"))
    payload = job.get("payload", {})
    parent = propagate.extract(job.get("trace_context", {}))
    started = time.monotonic()
    queue_wait = 0.0
    try:
        enqueued_at = datetime.fromisoformat(job.get("enqueued_at", ""))
        queue_wait = max(0.0, (datetime.now(UTC) - enqueued_at).total_seconds())
    except (TypeError, ValueError):
        pass
    dimensions = attrs(job_type=job_type)
    METRICS.worker_jobs.add(1, attrs(job_type=job_type, status="received"))
    METRICS.worker_queue_wait.record(queue_wait, dimensions)
    retry_count = max(0, int(job.get("retry_count", 0)))
    if retry_count:
        METRICS.worker_retries.add(retry_count, attrs(job_type=job_type))
    with tracer().start_as_current_span(
        "worker.process_job",
        context=parent,
        kind=trace.SpanKind.CONSUMER,
        attributes={
            "messaging.system": "redis",
            "messaging.operation.name": "process",
            "messaging.destination.name": settings.worker_queue,
            "messaging.message.id": job_id,
            "fin07.job.type": job_type,
            "fin07.worker.queue_wait_seconds": queue_wait,
            "fin07.job.retry_count": retry_count,
        },
        record_exception=False,
    ) as span:
        with bind_context(
            job_id=job_id,
            investigation_id=payload.get("investigation_id"),
            case_id=payload.get("case_id"),
        ):
            METRICS.worker_active.add(1, dimensions)
            try:
                handler(payload)
            except Exception as exc:
                METRICS.worker_failures.add(1, attrs(job_type=job_type, error_type=type(exc).__name__))
                METRICS.worker_jobs.add(1, attrs(job_type=job_type, status="failed"))
                METRICS.worker_dead_jobs.add(1, attrs(job_type=job_type, reason="processing_failure"))
                record_safe_exception(span, exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, type(exc).__name__))
                logger.exception("Tác vụ %s thất bại", job_id)
            else:
                METRICS.worker_jobs.add(1, attrs(job_type=job_type, status="completed"))
                logger.info("Tác vụ %s xong trong %.2fs", job_id, time.monotonic() - started)
            finally:
                METRICS.worker_active.add(-1, dimensions)
                METRICS.worker_duration.record(time.monotonic() - started, dimensions)


def main() -> int:
    settings = get_settings()
    initialize_observability(settings)
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    client = get_redis()
    beat()
    logger.info("Worker sẵn sàng, đang nghe hàng đợi %s", settings.worker_queue)

    while not _shutdown:
        beat()
        item = client.blpop([settings.worker_queue], timeout=int(settings.worker_poll_interval))
        if item is None:
            continue
        METRICS.worker_queue_depth.set(client.llen(settings.worker_queue), attrs(queue=settings.worker_queue))
        process(item[1])

    METRICS.worker_available.set(0, attrs(queue=settings.worker_queue))
    logger.info("Worker đã dừng")
    shutdown_observability()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
