"""Pha 1 — Nạp giao dịch theo dòng, dựng đồ thị TĂNG DẦN từng cạnh một.

Consumer đọc sự kiện canonical (``aml.transactions.raw.v1`` — chính topic mà
producer AML đang bơm), và với MỖI giao dịch:

  1. Ghi cạnh thô vào ``stream_transaction`` (idempotent theo source_transaction_id).
  2. Cộng dồn adjacency gộp ``stream_edge`` (đồ thị sống cho thuật toán mẫu hình).
  3. Cập nhật trạng thái node lăn ``stream_account_state`` cho cả hai đầu.

Chỉ khi cạnh THẬT SỰ mới (không phải replay) mới cộng dồn edge/state — nếu không
một lần phát lại Kafka sẽ đếm gấp đôi. Hàm ``handle_events`` tách khỏi Kafka để
kiểm thử được mà không cần broker.

Đây là NỀN MÓNG; chấm điểm cục bộ (Pha 2), bộ dò mẫu (Pha 3) và bồi tụ vụ việc
(Pha 4) dựng tiếp trên các bảng stream_* này.

Chạy (local-dev, giống bitcoin scorer):
    python -m src.streaming.graph_ingest
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any

from sqlalchemy import text

from src.db.session import get_session

logging.basicConfig(
    level=os.getenv("STREAM_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fin07.streaming.graph_ingest")

BOOTSTRAP = os.getenv("STREAM_KAFKA_BOOTSTRAP", os.getenv("AML_KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"))
TOPIC = os.getenv("STREAM_RAW_TOPIC", os.getenv("AML_RAW_TOPIC", "aml.transactions.raw.v1"))
GROUP_ID = os.getenv("STREAM_INGEST_GROUP", "graph-ingest-v1")
BATCH_SIZE = int(os.getenv("STREAM_INGEST_BATCH", "500"))
BATCH_TIMEOUT_S = float(os.getenv("STREAM_INGEST_BATCH_TIMEOUT", "2.0"))

# --- SQL (tách hằng để đọc + tái dùng) ---
_INSERT_TX = text(
    """INSERT INTO stream_transaction
         (source_transaction_id, occurred_at, from_account_key, to_account_key,
          amount_paid, payment_currency, amount_received, receiving_currency,
          payment_format, is_laundering, source_dataset)
       VALUES (:sid, :ts, :src, :dst, :ap, :pc, :ar, :rc, :pf, :lbl, :ds)
       ON CONFLICT (source_transaction_id) DO NOTHING
       RETURNING stream_txn_id"""
)
_UPSERT_EDGE = text(
    """INSERT INTO stream_edge (from_account_key, to_account_key, txn_count, total_amount, first_seen, last_seen)
       VALUES (:src, :dst, 1, :amt, :ts, :ts)
       ON CONFLICT (from_account_key, to_account_key) DO UPDATE SET
         txn_count = stream_edge.txn_count + 1,
         total_amount = stream_edge.total_amount + EXCLUDED.total_amount,
         first_seen = LEAST(stream_edge.first_seen, EXCLUDED.first_seen),
         last_seen = GREATEST(stream_edge.last_seen, EXCLUDED.last_seen)"""
)
_UPSERT_ACCT = text(
    """INSERT INTO stream_account_state
         (account_key, first_seen, last_seen, in_count, out_count, total_in, total_out, updated_at)
       VALUES (:acct, :ts, :ts, :inc, :outc, :tin, :tout, now())
       ON CONFLICT (account_key) DO UPDATE SET
         first_seen = LEAST(stream_account_state.first_seen, EXCLUDED.first_seen),
         last_seen  = GREATEST(stream_account_state.last_seen, EXCLUDED.last_seen),
         in_count   = stream_account_state.in_count  + EXCLUDED.in_count,
         out_count  = stream_account_state.out_count + EXCLUDED.out_count,
         total_in   = stream_account_state.total_in  + EXCLUDED.total_in,
         total_out  = stream_account_state.total_out + EXCLUDED.total_out,
         updated_at = now()"""
)


def _acct_key(bank: Any, account: Any) -> str:
    return f"{bank}:{account}"


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ts(ev: dict[str, Any]) -> datetime:
    """Mốc thời gian của giao dịch: ưu tiên epoch_ms (chắc chắn), rồi ISO."""
    ms = ev.get("event_time_epoch_ms")
    if ms is not None:
        try:
            return datetime.fromtimestamp(int(ms) / 1000.0)
        except (TypeError, ValueError, OSError):
            pass
    raw = str(ev.get("event_time", "")).replace("Z", "")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now()


def handle_events(session: Any, events: list[dict[str, Any]]) -> tuple[int, int]:
    """Xử lý một lô sự kiện trong CÙNG một transaction. Trả (đã nạp, bỏ qua trùng).

    Cạnh trùng (source_transaction_id đã có) bị bỏ qua — KHÔNG cộng dồn lại.
    """
    ingested = skipped = 0
    for ev in events:
        src = _acct_key(ev.get("from_bank"), ev.get("from_account"))
        dst = _acct_key(ev.get("to_bank"), ev.get("to_account"))
        if src == dst:
            skipped += 1  # cạnh tự trỏ vô nghĩa cho đồ thị
            continue
        ts = _ts(ev)
        amount_paid = _num(ev.get("amount_paid"))
        amount_recv = _num(ev.get("amount_received"))
        row = session.execute(
            _INSERT_TX,
            {
                "sid": ev.get("transaction_id"),
                "ts": ts,
                "src": src,
                "dst": dst,
                "ap": amount_paid,
                "pc": ev.get("payment_currency"),
                "ar": amount_recv,
                "rc": ev.get("receiving_currency"),
                "pf": ev.get("payment_format"),
                "lbl": ev.get("is_laundering"),
                "ds": ev.get("source_dataset"),
            },
        ).first()
        if row is None:
            skipped += 1  # trùng → không cộng dồn edge/state
            continue
        ingested += 1
        # Cạnh gộp: trọng số theo tiền GỬI (payment) để nhất quán một phía.
        session.execute(_UPSERT_EDGE, {"src": src, "dst": dst, "amt": amount_paid, "ts": ts})
        # Node gửi: +1 out, +tiền gửi. Node nhận: +1 in, +tiền nhận.
        session.execute(_UPSERT_ACCT, {"acct": src, "ts": ts, "inc": 0, "outc": 1, "tin": 0, "tout": amount_paid})
        session.execute(_UPSERT_ACCT, {"acct": dst, "ts": ts, "inc": 1, "outc": 0, "tin": amount_recv, "tout": 0})
    return ingested, skipped


def run() -> int:
    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "group.id": GROUP_ID,
            "auto.offset.reset": os.getenv("STREAM_KAFKA_OFFSET_RESET", "earliest"),
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info(
        "Graph-ingest ⟵ %s @ %s (group=%s), lô %d / timeout %.1fs",
        TOPIC,
        BOOTSTRAP,
        GROUP_ID,
        BATCH_SIZE,
        BATCH_TIMEOUT_S,
    )

    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))

    buf: list[dict[str, Any]] = []
    last = time.time()
    tot_in = tot_skip = 0

    def flush() -> None:
        nonlocal buf, last, tot_in, tot_skip
        if not buf:
            last = time.time()
            return
        t0 = time.time()
        with get_session() as s:
            ing, sk = handle_events(s, buf)
            s.commit()
        consumer.commit(asynchronous=False)  # chỉ commit offset sau khi DB đã ghi
        tot_in += ing
        tot_skip += sk
        logger.info("Nạp %d cạnh (%d bỏ trùng) trong %.2fs · tổng %d", ing, sk, time.time() - t0, tot_in)
        buf = []
        last = time.time()

    try:
        while not stop["flag"]:
            msg = consumer.poll(0.5)
            if msg is None:
                if buf and (time.time() - last) >= BATCH_TIMEOUT_S:
                    flush()
                continue
            if msg.error():
                logger.warning("Kafka error: %s", msg.error())
                continue
            try:
                buf.append(json.loads(msg.value()))
            except (ValueError, TypeError) as exc:
                logger.warning("Bỏ message hỏng: %s", exc)
                continue
            if len(buf) >= BATCH_SIZE:
                flush()
    finally:
        flush()
        consumer.close()
        logger.info("Dừng. Tổng nạp %d cạnh, bỏ trùng %d.", tot_in, tot_skip)
    return 0


if __name__ == "__main__":
    sys.exit(run())
