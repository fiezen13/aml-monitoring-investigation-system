"""Đường ống Bitcoin real-time: replay giao dịch Elliptic → Kafka → chấm RF trực
tiếp → ghi ``bitcoin_scored_tx`` → console /crypto hiện ngay (poll + cache SWR).

Đây là XƯƠNG SỐNG real-time đầu tiên (lát A). Chọn Bitcoin vì RF chấm ĐỘC LẬP
từng giao dịch: điểm streaming GIỐNG HỆT điểm batch — không trôi theo cửa sổ như
nhánh đồ thị SAML-D. Ngữ cảnh đồ thị Elliptic là dữ liệu tham chiếu cố định, nạp
một lần lúc consumer khởi động (xem src/bitcoin_aml/scoring.py).

Hai chế độ, cùng một module:

    # phát lại giao dịch vào Kafka (mô phỏng đường ingestion thực)
    python -m src.bitcoin_aml.stream produce --rate 1.0 --batch 200

    # consumer thường trú: chấm trực tiếp và ghi kết quả
    python -m src.bitcoin_aml.stream score

Chạy end-to-end ở LOCAL (docker-compose có sẵn Kafka). Chưa deploy prod — VM
prod nhỏ, và quyết định hạ tầng streaming để bàn sau.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.bitcoin_aml.scoring import (
    DATA,
    DEFAULT_RELEASE,
    INSERT_SQL,
    MODEL_VERSION,
    BitcoinScoringContext,
)
from src.db.session import get_session

logging.basicConfig(
    level=os.getenv("BTC_STREAM_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fin07.bitcoin.stream")

# --- Cấu hình qua env (tự chứa, không phụ thuộc AmlSettings của nhánh IBM) ---
BOOTSTRAP = os.getenv("BTC_KAFKA_BOOTSTRAP", os.getenv("AML_KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"))
TOPIC = os.getenv("BTC_RAW_TOPIC", "aml.bitcoin.raw.v1")
GROUP_ID = os.getenv("BTC_SCORER_GROUP", "bitcoin-scorer-v1")
#: Kích thước lô chấm (tumbling theo số lượng). RF chấm độc lập nên lô chỉ ảnh
#: hưởng thông lượng/độ trễ, KHÔNG ảnh hưởng điểm.
BATCH_SIZE = int(os.getenv("BTC_SCORE_BATCH", "200"))
#: Chờ tối đa (giây) để gom đủ lô trước khi chấm phần đang có — để lô cuối/thưa
#: không kẹt vô hạn.
BATCH_TIMEOUT_S = float(os.getenv("BTC_SCORE_BATCH_TIMEOUT", "2.0"))
RELEASE_ID = os.getenv("BTC_RELEASE_ID", DEFAULT_RELEASE)


def _feature_names_from(width: int) -> list[str]:
    """Tên cột theo độ rộng thực tế của file (167 cột → feature_1..165)."""
    return ["txId", "timestep"] + [f"feature_{i}" for i in range(1, width - 1)]


# ------------------------------------------------------------------ producer
def _load_test_features(all_rows: bool) -> pd.DataFrame:
    feats = pd.read_csv(DATA / "elliptic_txs_features.csv", header=None)
    feats.columns = _feature_names_from(feats.shape[1])
    feats["txId"] = feats["txId"].astype(str)
    # Mặc định phát tập test theo thời gian (timestep>34) — đúng vùng model chấm.
    return feats if all_rows else feats[feats.timestep > 34].reset_index(drop=True)


def produce(args: argparse.Namespace) -> int:
    from confluent_kafka import Producer

    df = _load_test_features(args.all)
    if args.max_records:
        df = df.iloc[: args.max_records]
    producer = Producer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "enable.idempotence": True,
            "compression.type": "lz4",
            "linger.ms": 20,
        }
    )
    logger.info(
        "Producer → %s @ %s: %d giao dịch, lô %d, nhịp %.2fs%s",
        TOPIC,
        BOOTSTRAP,
        len(df),
        args.batch,
        args.rate,
        " (lặp vô hạn)" if args.loop else "",
    )

    sent = 0

    def _emit_once() -> None:
        nonlocal sent
        for start in range(0, len(df), args.batch):
            chunk = df.iloc[start : start + args.batch]
            for rec in chunk.to_dict(orient="records"):
                producer.produce(TOPIC, key=str(rec["txId"]), value=json.dumps(rec).encode("utf-8"))
                sent += 1
            producer.poll(0)
            if args.rate > 0:
                time.sleep(args.rate)
            logger.info("  đã phát %d/%d", min(start + args.batch, len(df)), len(df))

    _emit_once()
    while args.loop:
        _emit_once()
    producer.flush(30)
    logger.info("Xong: phát %d bản tin.", sent)
    return 0


# ------------------------------------------------------------------ consumer
def _ensure_release(session: Any) -> None:
    """Chắc chắn có dòng release để bitcoin_scored_tx tham chiếu (idempotent)."""
    zero = "0" * 64
    session.execute(
        text(
            """INSERT INTO edge_model_release
               (release_id,model_version,dataset,split,model_sha256,scores_sha256,
                source_database_sha256,threshold,transaction_rows,positive_rows,
                triggered_rows,feature_count,benchmark,policy,status,trained_at,activated_at)
               VALUES (:rid,:mv,'Elliptic (original)','test',:z,:z,:z,0.5,0,0,0,166,
                       '{}'::jsonb,'{}'::jsonb,'reference',now(),NULL)
               ON CONFLICT (release_id) DO NOTHING"""
        ),
        {"rid": RELEASE_ID, "mv": MODEL_VERSION, "z": zero},
    )


def _write_batch(ctx: BitcoinScoringContext, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Chấm một lô message thô → ghi bitcoin_scored_tx. Trả (đã chấm, gắn cờ)."""
    feats = pd.DataFrame(rows)
    records = ctx.build_records(feats)
    if not records:
        return 0, 0
    flagged = sum(1 for r in records if r["predicted_label"] == "illicit")
    with get_session() as session:
        session.execute(text(INSERT_SQL), records)
        session.commit()
    return len(records), flagged


def score(args: argparse.Namespace) -> int:
    from confluent_kafka import Consumer

    logger.info("Nạp model + ngữ cảnh đồ thị Elliptic …")
    ctx = BitcoinScoringContext.load(release_id=RELEASE_ID)
    with get_session() as session:
        _ensure_release(session)
        session.commit()

    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "group.id": GROUP_ID,
            "auto.offset.reset": os.getenv("BTC_KAFKA_OFFSET_RESET", "earliest"),
            # Tự commit TẮT: chỉ commit sau khi ghi DB thành công (at-least-once).
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info(
        "Consumer ⟵ %s @ %s (group=%s), lô %d / timeout %.1fs", TOPIC, BOOTSTRAP, GROUP_ID, BATCH_SIZE, BATCH_TIMEOUT_S
    )

    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))

    buffer: list[dict[str, Any]] = []
    last_flush = time.time()
    total_scored = total_flagged = 0

    def flush() -> None:
        nonlocal buffer, last_flush, total_scored, total_flagged
        if not buffer:
            last_flush = time.time()
            return
        t0 = time.time()
        n, flagged = _write_batch(ctx, buffer)
        total_scored += n
        total_flagged += flagged
        consumer.commit(asynchronous=False)  # chỉ commit sau khi DB đã ghi
        logger.info(
            "Chấm %d gd (%d gắn cờ) trong %.2fs · tổng %d/%d", n, flagged, time.time() - t0, total_flagged, total_scored
        )
        buffer = []
        last_flush = time.time()

    try:
        while not stop["flag"]:
            msg = consumer.poll(0.5)
            if msg is None:
                if buffer and (time.time() - last_flush) >= BATCH_TIMEOUT_S:
                    flush()
                continue
            if msg.error():
                logger.warning("Kafka error: %s", msg.error())
                continue
            try:
                buffer.append(json.loads(msg.value()))
            except (ValueError, TypeError) as exc:
                logger.warning("Bỏ message hỏng: %s", exc)
                continue
            if len(buffer) >= BATCH_SIZE:
                flush()
    finally:
        flush()  # đừng mất lô đang dở khi dừng
        consumer.close()
        logger.info("Dừng. Tổng đã chấm %d, gắn cờ %d.", total_scored, total_flagged)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đường ống Bitcoin real-time (Elliptic RF).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("produce", help="Phát lại giao dịch Elliptic vào Kafka.")
    p.add_argument("--batch", type=int, default=200, help="Số giao dịch mỗi nhịp phát.")
    p.add_argument("--rate", type=float, default=1.0, help="Nghỉ (giây) giữa các nhịp để mô phỏng dòng liên tục.")
    p.add_argument("--max-records", type=int, default=0, help="Giới hạn số bản tin (0 = tất cả).")
    p.add_argument("--all", action="store_true", help="Phát cả dataset thay vì chỉ tập test (timestep>34).")
    p.add_argument("--loop", action="store_true", help="Phát lại vô hạn (demo dòng không ngừng).")
    p.set_defaults(func=produce)

    s = sub.add_parser("score", help="Consumer thường trú: chấm trực tiếp và ghi DB.")
    s.set_defaults(func=score)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
