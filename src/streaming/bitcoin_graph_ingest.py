"""Pha 1 — nhánh Bitcoin: dựng đồ thị GIAO DỊCH→GIAO DỊCH tăng dần từ dòng.

Khác nhánh ngân hàng (account→account), đồ thị Bitcoin là tx→tx. Topology tham
chiếu lấy từ edgelist Elliptic (trong Bitcoin thật là quan hệ input/output), nạp
một lần lúc khởi động. Mỗi giao dịch stream tới:

  1. Thêm node ``stream_bitcoin_tx`` (idempotent theo tx_id).
  2. Với mỗi láng giềng (từ edgelist) ĐÃ tới trước đó → vật chất hoá cạnh
     ``stream_bitcoin_edge`` (cả chiều tới lẫn chiều đi). Láng giềng tới sau sẽ
     tự nối khi nó được xử lý → "dựng từng cạnh một", back-fill đúng.

Chạy (local): produce giao dịch Bitcoin bằng src.bitcoin_aml.stream produce, rồi
    python -m src.streaming.bitcoin_graph_ingest
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.db.session import get_session

logging.basicConfig(
    level=os.getenv("STREAM_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("fin07.streaming.bitcoin_graph_ingest")

BOOTSTRAP = os.getenv("STREAM_KAFKA_BOOTSTRAP", os.getenv("AML_KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"))
TOPIC = os.getenv("BTC_RAW_TOPIC", "aml.bitcoin.raw.v1")
GROUP_ID = os.getenv("BTC_GRAPH_INGEST_GROUP", "bitcoin-graph-ingest-v1")
BATCH_SIZE = int(os.getenv("BTC_GRAPH_BATCH", "500"))
BATCH_TIMEOUT_S = float(os.getenv("BTC_GRAPH_BATCH_TIMEOUT", "2.0"))
EDGELIST = Path(os.getenv("BTC_EDGELIST", "data/raw/elliptic/elliptic_txs_edgelist.csv"))

_INSERT_NODE = text(
    "INSERT INTO stream_bitcoin_tx (tx_id, timestep) VALUES (:tx, :ts) ON CONFLICT (tx_id) DO NOTHING RETURNING tx_id"
)
_INSERT_EDGE = text("INSERT INTO stream_bitcoin_edge (src_tx, dst_tx) VALUES (:s, :d) ON CONFLICT DO NOTHING")
_ARRIVED = text("SELECT 1 FROM stream_bitcoin_tx WHERE tx_id = :tx")


def load_topology() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Nạp edgelist Elliptic → adjacency (succ = xuôi dòng, pred = ngược dòng)."""
    edges = pd.read_csv(EDGELIST)
    c0, c1 = edges.columns[:2]
    succ: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    for a, b in zip(edges[c0].astype(str), edges[c1].astype(str)):
        succ[a].append(b)
        pred[b].append(a)
    return dict(succ), dict(pred)


def handle_events(session: Any, events: list[dict[str, Any]], succ: dict, pred: dict) -> tuple[int, int]:
    """Thêm node cho từng tx tới + vật chất hoá cạnh tới láng giềng ĐÃ tới.

    Trả (node mới, cạnh mới vật chất hoá).
    """
    new_nodes = new_edges = 0
    for ev in events:
        tx = str(ev.get("txId") or ev.get("tx_id") or "")
        if not tx:
            continue
        row = session.execute(_INSERT_NODE, {"tx": tx, "ts": ev.get("timestep")}).first()
        if row is None:
            continue  # đã có → bỏ (idempotent)
        new_nodes += 1
        # Cạnh xuôi dòng tx→n: chỉ nối nếu n đã tới.
        for n in succ.get(tx, []):
            if session.execute(_ARRIVED, {"tx": n}).first():
                session.execute(_INSERT_EDGE, {"s": tx, "d": n})
                new_edges += 1
        # Cạnh ngược dòng p→tx: chỉ nối nếu p đã tới.
        for p in pred.get(tx, []):
            if session.execute(_ARRIVED, {"tx": p}).first():
                session.execute(_INSERT_EDGE, {"s": p, "d": tx})
                new_edges += 1
    return new_nodes, new_edges


def run() -> int:
    from confluent_kafka import Consumer

    logger.info("Nạp topology Elliptic (%s) …", EDGELIST)
    succ, pred = load_topology()
    logger.info("Topology: %d node có succ, %d node có pred", len(succ), len(pred))

    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "group.id": GROUP_ID,
            "auto.offset.reset": os.getenv("BTC_KAFKA_OFFSET_RESET", "earliest"),
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("Bitcoin graph-ingest ⟵ %s @ %s (group=%s)", TOPIC, BOOTSTRAP, GROUP_ID)

    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))

    buf: list[dict[str, Any]] = []
    last = time.time()
    tot_n = tot_e = 0

    def flush() -> None:
        nonlocal buf, last, tot_n, tot_e
        if not buf:
            last = time.time()
            return
        t0 = time.time()
        with get_session() as s:
            n, e = handle_events(s, buf, succ, pred)
            s.commit()
        consumer.commit(asynchronous=False)
        tot_n += n
        tot_e += e
        logger.info("Nạp %d node, +%d cạnh trong %.2fs · tổng node %d / cạnh %d", n, e, time.time() - t0, tot_n, tot_e)
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
        logger.info("Dừng. Tổng node %d, cạnh %d.", tot_n, tot_e)
    return 0


if __name__ == "__main__":
    sys.exit(run())
