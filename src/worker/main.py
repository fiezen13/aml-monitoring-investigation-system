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
import threading
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from opentelemetry import propagate, trace
from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_session
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
from src.services import queue
from src.services.queue import get_redis

logger = logging.getLogger("fin07.worker")

_shutdown = False


def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Nhận tín hiệu %s — dừng sau khi xong tác vụ hiện tại", signal.Signals(signum).name)
    _shutdown = True


def beat() -> None:
    """Ghi nhịp tim. Healthcheck của container đọc đúng khoá này.

    Gọi từ luồng nền (xem ``_start_heartbeat``) chứ không từ vòng lặp chính:
    nhịp tim phải trả lời "tiến trình còn sống và còn nói chuyện được với Redis",
    không phải "đang rảnh".
    """
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


def _start_heartbeat(ttl: int) -> None:
    """Đập nhịp tim ở luồng riêng, độc lập với tác vụ đang chạy.

    Trước đây nhịp tim nằm ngay đầu vòng lặp chính, nên nó chỉ được ghi lại khi
    worker rảnh. Một phiên điều tra mất ~30 giây — đúng bằng TTL — nên khoá hết
    hạn giữa chừng và container bị đánh dấu ``unhealthy`` trong khi nó đang làm
    việc bình thường. Tệ hơn: Docker `restart: unless-stopped` cộng với một
    orchestrator tin vào healthcheck sẽ giết worker đúng lúc nó bận nhất.

    Nhịp gấp ba lần TTL để mất một nhịp vì mạng chập chờn vẫn chưa hết hạn.
    """
    interval = max(1.0, ttl / 3)

    def loop() -> None:
        while not _shutdown:
            try:
                beat()
            except Exception:  # noqa: BLE001 — mất một nhịp không được phép giết worker
                logger.warning("Không ghi được nhịp tim, sẽ thử lại sau %.0fs", interval, exc_info=True)
            time.sleep(interval)

    threading.Thread(target=loop, name="worker-heartbeat", daemon=True).start()
    logger.info("Nhịp tim mỗi %.0fs, TTL %ds", interval, ttl)


#: Phiên điều tra bị bỏ rơi: đã ghi vào cơ sở dữ liệu nhưng không còn tác vụ nào
#: nhắc tới. Hàng đợi Redis dùng ``blpop`` — việc bị lấy ra *trước* khi chạy, nên
#: worker tắt giữa chừng là mất việc. Bản ghi nằm lại ở QUEUED mãi mãi, và giao
#: diện hiển thị "đang chờ" không bao giờ đổi, cũng không có lỗi nào để đọc.
#:
#: Ngưỡng năm phút: dài hơn mọi phiên điều tra bình thường (30–60 giây), nên
#: không có nguy cơ nhân đôi việc đang chạy dở của một worker khác.
_ORPHAN_SQL = """
    SELECT investigation_id
      FROM investigation
     WHERE status IN ('QUEUED', 'INVESTIGATING')
       AND updated_at < now() - make_interval(mins => 5)
     ORDER BY created_at
"""


def requeue_orphans() -> int:
    """Nhặt lại các phiên điều tra mồ côi lúc khởi động.

    Chạy một lần khi worker lên, không định kỳ: thời điểm duy nhất sinh ra bản
    ghi mồ côi là lúc worker chết, và ngay sau đó nó khởi động lại. Sửa ở đây là
    đủ, mà không phải dựng thêm một vòng quét nền.
    """
    try:
        with get_session() as session:
            ids = list(session.execute(text(_ORPHAN_SQL)).scalars())
    except Exception:  # noqa: BLE001 — không nối được DB thì để vòng lặp chính báo lỗi
        logger.warning("Không kiểm tra được phiên điều tra mồ côi", exc_info=True)
        return 0

    for investigation_id in ids:
        queue.enqueue("investigate_alert", {"investigation_id": investigation_id})
        logger.info("Giao lại phiên điều tra bị bỏ rơi %s", investigation_id)
    if ids:
        logger.info("Đã giao lại %d phiên điều tra mồ côi", len(ids))
    return len(ids)


# handle_investigate_case đã gỡ ngày 27/08/2026 cùng endpoint gọi nó.
#
# Nó đẩy vụ việc đi từng bước qua sáu trạng thái trung gian. Không giao diện
# nào từng gọi tới, nên sáu trạng thái ấy chưa có vụ nào đi qua. Quy trình
# thật do người bấm: chuyên viên kết luận và soạn hồ sơ, quản lý phê duyệt.


def handle_ping(payload: dict[str, Any]) -> None:
    """Tác vụ rỗng dùng để kiểm chứng hàng đợi thông suốt."""
    logger.info("ping %s", payload)


def _mark_failed(investigation_id: str, exc: BaseException) -> None:
    """Lưới an toàn cuối: không để phiên điều tra nào chết lặng.

    Quy trình đã tự ghi trạng thái thất bại ở đường xử lý lỗi của nó. Nhưng nếu
    chính lượt ghi ấy hỏng — phiên làm việc đã rollback, mất kết nối, hết giờ —
    thì bản ghi nằm nguyên ở QUEUED và giao diện treo ở "đang chờ" mãi mãi.

    Nên mở một phiên **mới** ở đây và ghi lại. Phiên mới là điểm mấu chốt: phiên
    cũ có thể đang hỏng, dùng lại nó chỉ sinh thêm PendingRollbackError.
    Chỉ ghi khi trạng thái chưa phải kết thúc, để không đè lên kết quả đã có.
    """
    try:
        with get_session() as session:
            session.execute(
                text(
                    """UPDATE investigation
                          SET status = 'FAILED', workflow_state = 'FAILED',
                              failure_reason = :reason, updated_at = now(), completed_at = now()
                        WHERE investigation_id = :id
                          AND status NOT IN ('COMPLETED', 'FAILED', 'INSUFFICIENT_EVIDENCE',
                                             'NEEDS_HUMAN_REVIEW')"""
                ),
                {"id": investigation_id, "reason": f"{type(exc).__name__}: {str(exc)[:400]}"},
            )
    except Exception:  # noqa: BLE001 — đây đã là đường cứu hộ, không được ném tiếp
        logger.warning("Không ghi được trạng thái thất bại cho %s", investigation_id, exc_info=True)


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
            _mark_failed(investigation_id, exc)
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


def _serve_metrics(port: int) -> None:
    """Phơi /metrics của chính tiến trình worker.

    Vì sao cần: chỉ số OpenTelemetry sống **trong tiến trình** phát ra chúng.
    API phơi /metrics của riêng nó, nhưng toàn bộ công việc của tầng tác tử —
    lời gọi mô hình, token, độ trễ, kết quả phản biện — chạy ở đây, trong
    worker. Không có cổng này thì Prometheus chỉ thấy chỉ số HTTP của API và
    năm trong sáu nhóm chỉ số trên Grafana trống, dù hệ thống chạy đúng.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - chữ ký của thư viện chuẩn
            if self.path.rstrip("/") not in ("/metrics", ""):
                self.send_error(404)
                return
            payload = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: Any) -> None:
            """Im lặng: mỗi lần scrape một dòng log là nhiễu, không phải thông tin."""

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="worker-metrics", daemon=True).start()
    logger.info("Worker phơi chỉ số ở cổng %d", port)


def main() -> int:
    settings = get_settings()
    initialize_observability(settings)
    _serve_metrics(settings.worker_metrics_port)
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    client = get_redis()
    beat()
    _start_heartbeat(settings.worker_heartbeat_ttl)
    requeue_orphans()
    logger.info("Worker sẵn sàng, đang nghe hàng đợi %s", settings.worker_queue)

    while not _shutdown:
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
