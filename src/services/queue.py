"""Hàng đợi tác vụ trên Redis.

Agent điều tra chạy hàng phút nên không thể chạy đồng bộ trong vòng đời
request (ARC-001 mục 6). API đẩy tác vụ vào đây, worker lấy ra xử lý.
"""

import json
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import redis
from opentelemetry import propagate, trace

from src.config import get_settings
from src.observability.metrics import METRICS, attrs
from src.observability.telemetry import tracer


@lru_cache
def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def ping() -> bool:
    """True nếu Redis trả lời PING."""
    return bool(get_redis().ping())


def enqueue(job_type: str, payload: dict[str, Any]) -> str:
    """Đẩy một tác vụ vào cuối hàng đợi. Trả về mã tác vụ."""
    settings = get_settings()
    client = get_redis()
    with tracer().start_as_current_span(
        f"send {settings.worker_queue}",
        kind=trace.SpanKind.PRODUCER,
        attributes={
            "messaging.system": "redis",
            "messaging.operation.name": "send",
            "messaging.destination.name": settings.worker_queue,
            "fin07.job.type": job_type,
        },
    ) as span:
        job_id = f"job-{client.incr('fin07:job_seq'):08d}"
        carrier: dict[str, str] = {}
        propagate.inject(carrier)
        message = {
            "job_id": job_id,
            "type": job_type,
            "payload": payload,
            "enqueued_at": datetime.now(UTC).isoformat(),
            "trace_context": carrier,
            "retry_count": 0,
        }
        client.rpush(settings.worker_queue, json.dumps(message))
        span.set_attribute("messaging.message.id", job_id)
        METRICS.worker_queue_depth.set(client.llen(settings.worker_queue), attrs(queue=settings.worker_queue))
    return job_id


def queue_depth() -> int:
    """Số tác vụ đang chờ."""
    settings = get_settings()
    return int(get_redis().llen(settings.worker_queue))


def worker_alive() -> bool:
    """True nếu có worker ghi nhịp tim trong khoảng TTL gần nhất."""
    settings = get_settings()
    return bool(get_redis().exists(settings.worker_heartbeat_key))
