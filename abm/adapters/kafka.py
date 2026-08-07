"""Publish canonical ABM-BANK CloudEvents to Kafka with delivery accounting."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from abm.adapters.events import iter_release_events


def publish_release(
    release_dir: str | Path,
    *,
    bootstrap_servers: str,
    topic: str,
    limit: int = 1000,
    flush_timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("publish limit must be positive")
    if not topic.strip():
        raise ValueError("Kafka topic cannot be empty")
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise RuntimeError("confluent-kafka is required to publish ABM events") from exc

    state = {"attempted": 0, "acked": 0, "failed": 0}

    def delivered(error: Any, _: Any) -> None:
        if error is None:
            state["acked"] += 1
        else:
            state["failed"] += 1

    producer = Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "abm-bank-release-publisher",
            "acks": "all",
            "enable.idempotence": True,
            "compression.type": "lz4",
            "linger.ms": 20,
            "batch.size": 262144,
            "queue.buffering.max.messages": 100000,
            "message.timeout.ms": 120000,
        }
    )
    started = time.monotonic()
    for event in iter_release_events(release_dir, limit=limit):
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        key = event["data"]["transaction_id"].encode("utf-8")
        headers = [
            ("schema-version", event["data"]["schema_version"].encode()),
            ("event-type", event["type"].encode()),
            ("content-type", b"application/json"),
        ]
        while True:
            try:
                producer.produce(topic, key=key, value=payload, headers=headers, on_delivery=delivered)
                state["attempted"] += 1
                break
            except BufferError:
                producer.poll(0.5)
        producer.poll(0)
    remaining = producer.flush(flush_timeout_seconds)
    elapsed = max(time.monotonic() - started, 1e-9)
    if remaining or state["failed"] or state["acked"] != state["attempted"]:
        raise RuntimeError(
            "Kafka delivery incomplete: "
            f"attempted={state['attempted']} acked={state['acked']} failed={state['failed']} remaining={remaining}"
        )
    return {
        "status": "PASS",
        "topic": topic,
        "attempted": state["attempted"],
        "acked": state["acked"],
        "failed": state["failed"],
        "elapsed_seconds": round(elapsed, 3),
        "events_per_second": round(state["acked"] / elapsed, 1),
    }
