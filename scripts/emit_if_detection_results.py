#!/usr/bin/env python3
"""Emit Isolation Forest scores as ``aml.detection.result.v1`` events.

Vi du:
  python scripts/emit_if_detection_results.py --limit 100 --dry-run
  python scripts/emit_if_detection_results.py --limit 1000
  python scripts/emit_if_detection_results.py --limit 500 --kafka
  python scripts/emit_if_detection_results.py --all --out data/processed/if_detection_results_v1.jsonl

Khong INSERT alert. Aggregator (fusion) moi tao alert tu cac result nay.
Mac dinh ghi JSONL outbox; ``--kafka`` gui them len topic ``aml.detection.result.v1``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.if_detection_result import (  # noqa: E402
    DEFAULT_THRESHOLD,
    DEFAULT_TYPOLOGY,
    TOPIC,
    build_detection_result,
    kafka_key,
    validate_detection_result,
)


def _typology_ok(code: str) -> bool:
    return bool(re.fullmatch(r"T(0[1-9]|10)", code))


logger = logging.getLogger("fin07.emit_if_detection_results")

PROCESSED_DIR = Path("data/processed")
DEFAULT_SCORES = PROCESSED_DIR / "if_scores_v1.parquet"
DEFAULT_OUT = PROCESSED_DIR / "if_detection_results_v1.jsonl"
NEEDED_COLS = {
    "account_key",
    "as_of_ts",
    "window",
    "anomaly_score",
    "model_version",
    "top_anomalous_features",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Emit IF scores as aml.detection.result.v1")
    p.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    p.add_argument("--window", default="7d", choices=("1d", "7d", "14d"))
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Score >= threshold => triggered=true (van emit ca triggered=false)",
    )
    p.add_argument("--typology", default=DEFAULT_TYPOLOGY)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="JSONL outbox path")
    p.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Toi da so event (an toan local). Dung --all de bo gioi han.",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Emit moi dong window (co the hang trieu). Bo --limit.",
    )
    p.add_argument(
        "--triggered-only",
        action="store_true",
        help="Chi ghi event triggered=true (khong dung cho audit day du)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="In sample JSON, khong ghi file / Kafka",
    )
    p.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate tung payload voi JSON Schema (mac dinh bat)",
    )
    p.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="Tat validate schema (nhanh hon khi --all)",
    )
    p.add_argument(
        "--kafka",
        action="store_true",
        help="Gui them len Kafka topic aml.detection.result.v1",
    )
    p.add_argument(
        "--bootstrap-servers",
        default="localhost:29092",
        help="Kafka bootstrap (khi --kafka)",
    )
    p.add_argument(
        "--sample-print",
        type=int,
        default=1,
        help="So payload in ra stdout khi dry-run / ket thuc",
    )
    return p.parse_args()


def iter_score_rows(scores_path: Path, window: str, limit: int | None) -> Iterator[dict[str, Any]]:
    if not scores_path.exists():
        raise FileNotFoundError(f"Khong tim thay {scores_path}")

    pf = pq.ParquetFile(scores_path)
    schema_names = set(pf.schema_arrow.names)
    missing = sorted(NEEDED_COLS - schema_names)
    if missing:
        raise ValueError(f"Thieu cot trong parquet: {missing}")

    cols = sorted(NEEDED_COLS)
    emitted = 0
    for batch in pf.iter_batches(batch_size=50_000, columns=cols):
        table = batch.to_pydict()
        n = len(table["account_key"])
        for i in range(n):
            if str(table["window"][i]) != window:
                continue
            score = table["anomaly_score"][i]
            if score is None:
                continue
            row = {c: table[c][i] for c in cols}
            yield row
            emitted += 1
            if limit is not None and emitted >= limit:
                return


class JsonlOutbox:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._handle = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = path.open("w", encoding="utf-8")

    def write(self, payload: dict[str, Any]) -> None:
        if self._handle is None:
            return
        self._handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None


class KafkaDetectionSink:
    """Minimal producer cho detection result (lazy confluent_kafka)."""

    def __init__(self, bootstrap_servers: str, topic: str = TOPIC) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Thieu confluent-kafka. Cai: pip install -r requirements.txt"
            ) from exc
        self._topic = topic
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "acks": "all",
                "enable.idempotence": True,
                "client.id": "fin07-if-detection-result",
            }
        )
        self._headers = [
            ("schema-version", "1.0"),
            ("content-type", "application/json"),
            ("detector-id", "isolation_forest_account_behavior"),
        ]
        self.acked = 0
        self.failed = 0

    def send(self, payload: dict[str, Any]) -> None:
        key = kafka_key(payload)
        value = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def on_delivery(err: Any, _msg: Any) -> None:
            if err is not None:
                self.failed += 1
                logger.error("Kafka delivery failed key=%s err=%s", key, err)
            else:
                self.acked += 1

        while True:
            try:
                self._producer.produce(
                    topic=self._topic,
                    key=key.encode("utf-8"),
                    value=value,
                    headers=self._headers,
                    on_delivery=on_delivery,
                )
                break
            except BufferError:
                self._producer.poll(0.5)
        self._producer.poll(0)

    def flush(self, timeout: float = 30.0) -> int:
        return int(self._producer.flush(timeout))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()

    if not (0.0 <= args.threshold <= 1.0):
        raise SystemExit("--threshold phai trong [0,1]")
    if not _typology_ok(args.typology):
        raise SystemExit(f"--typology khong hop le: {args.typology}")


    limit: int | None = None if args.all else max(1, args.limit)
    if args.all:
        logger.warning("Emitting ALL rows for window=%s — co the hang trieu event", args.window)

    print(
        f"[1/3] Doc {args.scores} | window={args.window} | "
        f"limit={'ALL' if limit is None else limit} | threshold={args.threshold}",
        flush=True,
    )

    outbox = JsonlOutbox(None if args.dry_run else args.out)
    kafka: KafkaDetectionSink | None = None
    if args.kafka and not args.dry_run:
        kafka = KafkaDetectionSink(args.bootstrap_servers)
        print(f"       Kafka → {args.bootstrap_servers} topic={TOPIC}", flush=True)

    evaluated_at = datetime.now(tz=UTC)
    n_total = 0
    n_triggered = 0
    n_invalid = 0
    samples: list[dict[str, Any]] = []

    print("[2/3] Build + emit detection results ...", flush=True)
    try:
        for row in iter_score_rows(args.scores, args.window, limit):
            payload = build_detection_result(
                row,
                threshold=args.threshold,
                typology_code=args.typology,
                evaluated_at=evaluated_at,
            )
            if args.triggered_only and not payload["triggered"]:
                continue

            if args.validate:
                errors = validate_detection_result(payload)
                if errors:
                    n_invalid += 1
                    if n_invalid <= 5:
                        logger.error(
                            "Schema invalid result_id=%s: %s",
                            payload.get("result_id"),
                            errors[:3],
                        )
                    continue

            outbox.write(payload)
            if kafka is not None:
                kafka.send(payload)

            n_total += 1
            if payload["triggered"]:
                n_triggered += 1
            if len(samples) < max(0, args.sample_print):
                samples.append(payload)
    finally:
        outbox.close()
        if kafka is not None:
            remaining = kafka.flush()
            if remaining:
                logger.error("Kafka flush: %d message chua gui", remaining)

    print("[3/3] Done", flush=True)
    summary = {
        "emitted": n_total,
        "triggered": n_triggered,
        "not_triggered": n_total - n_triggered,
        "schema_rejected": n_invalid,
        "out": None if args.dry_run else str(args.out),
        "kafka_acked": None if kafka is None else kafka.acked,
        "kafka_failed": None if kafka is None else kafka.failed,
        "topic": TOPIC,
        "detector_type": "ML_UNSUPERVISED",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    for sample in samples:
        print("--- sample ---", flush=True)
        print(json.dumps(sample, ensure_ascii=False, indent=2), flush=True)

    if args.dry_run:
        print("DRY-RUN: khong ghi file / Kafka.", flush=True)
    if n_invalid:
        raise SystemExit(f"{n_invalid} payload bi schema tu choi.")
    if n_total == 0:
        raise SystemExit("Khong emit duoc event nao.")


if __name__ == "__main__":
    main()

