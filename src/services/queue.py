"""Hàng đợi tác vụ trên Redis.

Agent điều tra chạy hàng phút nên không thể chạy đồng bộ trong vòng đời
request (ARC-001 mục 6). API đẩy tác vụ vào đây, worker lấy ra xử lý.
"""

import json
from functools import lru_cache
from typing import Any

import redis

from src.config import get_settings


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
    job_id = f"job-{client.incr('fin07:job_seq'):08d}"
    client.rpush(settings.worker_queue, json.dumps({"job_id": job_id, "type": job_type, "payload": payload}))
    return job_id


def queue_depth() -> int:
    """Số tác vụ đang chờ."""
    settings = get_settings()
    return int(get_redis().llen(settings.worker_queue))


def worker_alive() -> bool:
    """True nếu có worker ghi nhịp tim trong khoảng TTL gần nhất."""
    settings = get_settings()
    return bool(get_redis().exists(settings.worker_heartbeat_key))
