"""Bơm SAML-D vào topic canonical để consumer đồ thị (Pha 1) dùng lại y nguyên.

SAML-D có lược đồ khác IBM (Sender_account/Receiver_account + quốc gia, không có
bank code). Producer này MAP mỗi dòng SAML-D → sự kiện canonical hình dạng IBM
(from_bank/from_account/to_bank/to_account…) nên ``graph_ingest`` không phải sửa
gì — account_key = "<quốc gia>:<số tài khoản>".

Chạy (local):
    python -m src.streaming.samld_producer --max-records 5000 --rate 0
rồi chạy consumer trỏ vào topic SAML-D:
    STREAM_RAW_TOPIC=aml.samld.raw.v1 python -m src.streaming.graph_ingest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(level=os.getenv("STREAM_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fin07.streaming.samld_producer")

BOOTSTRAP = os.getenv("STREAM_KAFKA_BOOTSTRAP", os.getenv("AML_KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"))
TOPIC = os.getenv("SAMLD_RAW_TOPIC", "aml.samld.raw.v1")
CSV_PATH = Path(os.getenv("SAMLD_RAW_CSV", "data/raw/saml-d/SAML-D.csv"))

#: Cột SAML-D thô → chỉ đọc những cột này.
COLS = [
    "Time", "Date", "Sender_account", "Receiver_account", "Amount",
    "Payment_currency", "Received_currency", "Sender_bank_location",
    "Receiver_bank_location", "Payment_type", "Is_laundering",
]


def _stable_id(row: dict, idx: int) -> str:
    material = "|".join(
        str(row.get(k, "")) for k in ("Date", "Time", "Sender_account", "Receiver_account", "Amount")
    ) + f"|{idx}"
    return "SAMLD-" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:20]


def _epoch_ms(date: str, tm: str) -> tuple[str, int]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(f"{date} {tm}".strip(), fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat(), int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return f"{date} {tm}".strip(), 0


def _to_canonical(row: dict, idx: int) -> dict:
    """Một dòng SAML-D → sự kiện canonical (hình dạng IBM) cho graph_ingest."""
    iso, ms = _epoch_ms(str(row.get("Date", "")), str(row.get("Time", "")))
    return {
        "transaction_id": _stable_id(row, idx),
        "event_time": iso,
        "event_time_epoch_ms": ms,
        # Không có bank code → dùng QUỐC GIA làm "bank" để account_key tách bạch.
        "from_bank": str(row.get("Sender_bank_location", "?")),
        "from_account": str(row.get("Sender_account", "?")),
        "to_bank": str(row.get("Receiver_bank_location", "?")),
        "to_account": str(row.get("Receiver_account", "?")),
        "amount_paid": float(row.get("Amount", 0) or 0),
        "payment_currency": str(row.get("Payment_currency", "")),
        "amount_received": float(row.get("Amount", 0) or 0),
        "receiving_currency": str(row.get("Received_currency", "")),
        "payment_format": str(row.get("Payment_type", "")),
        "is_laundering": int(row.get("Is_laundering", 0) or 0),
        "source_dataset": "SAML-D",
    }


def produce(args: argparse.Namespace) -> int:
    from confluent_kafka import Producer

    if not CSV_PATH.exists():
        logger.error("Không thấy %s (đặt SAMLD_RAW_CSV).", CSV_PATH)
        return 2
    n = args.max_records or None
    skip = range(1, args.skip + 1) if args.skip else None  # bỏ qua N dòng đầu (giữ header)
    df = pd.read_csv(CSV_PATH, usecols=lambda c: c in COLS, skiprows=skip, nrows=n)
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "enable.idempotence": True, "compression.type": "lz4", "linger.ms": 20})
    logger.info("Producer SAML-D → %s @ %s: %d giao dịch, lô %d, nhịp %.2fs", TOPIC, BOOTSTRAP, len(df), args.batch, args.rate)
    sent = 0
    for start in range(0, len(df), args.batch):
        for idx, row in df.iloc[start : start + args.batch].iterrows():
            ev = _to_canonical(row.to_dict(), int(idx))
            producer.produce(TOPIC, key=f"{ev['from_bank']}:{ev['from_account']}", value=json.dumps(ev).encode("utf-8"))
            sent += 1
        producer.poll(0)
        if args.rate > 0:
            time.sleep(args.rate)
        logger.info("  đã phát %d/%d", min(start + args.batch, len(df)), len(df))
    producer.flush(30)
    logger.info("Xong: phát %d bản tin SAML-D.", sent)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bơm SAML-D vào topic canonical cho đồ thị streaming.")
    p.add_argument("--batch", type=int, default=500)
    p.add_argument("--rate", type=float, default=0.0, help="Nghỉ (giây) giữa các lô để mô phỏng dòng.")
    p.add_argument("--max-records", type=int, default=0, help="0 = tất cả.")
    p.add_argument("--skip", type=int, default=0, help="Bỏ qua N dòng đầu (để bơm slice giai đoạn muộn/test).")
    return produce(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
