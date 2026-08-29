"""Lớp BRONZE (data lake) — raw transactions ghi ra Parquet, KHÔNG vào Postgres.

Đúng kiến trúc medallion của dự án (docs/architecture/README.md, contracts/ingestion):
raw → Kafka → Flink → HDFS Bronze (Parquet, phân vùng ngày/giờ). Bản local KHÔNG có
HDFS nên đây là STAND-IN: Parquet trên đĩa, cùng cách phân vùng
``source_dataset=/event_date=/event_hour=``. PostgreSQL chỉ giữ OUTPUT (cảnh báo, vụ
việc, nhật ký) — không giữ giao dịch thô.

Đồ thị GNN dựng in-memory TỪ Bronze; chỉ cạnh gắn cờ mới thành alert/case xuống PG.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BRONZE_ROOT = Path(os.getenv("BRONZE_ROOT", "data/lake/bronze/transactions"))


def _partition(event_time: str) -> tuple[str, str]:
    """(event_date, event_hour) từ event_time ISO — để phân vùng như HDFS Bronze."""
    try:
        dt = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H")
    except (ValueError, TypeError):
        return "unknown", "00"


def write_events(events: Iterable[dict[str, Any]], root: Path = BRONZE_ROOT) -> int:
    """Ghi lô sự kiện thô ra Bronze Parquet. GIỮ NGUYÊN mọi cột (không ép schema) để
    dùng chung cho mọi nhánh (SAML-D/IBM có event_time; Bitcoin có timestep).

    Phân vùng: source_dataset + (event_date/event_hour nếu có event_time; hoặc
    timestep nếu là Bitcoin; hoặc 'all').
    """
    rows = list(events)
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    if "source_dataset" not in df.columns:
        df["source_dataset"] = "unknown"
    if "event_time" in df.columns and df["event_time"].notna().any():
        df["_p1"], df["_p2"] = zip(*df["event_time"].map(_partition))
        p1name, p2name = "event_date", "event_hour"
    elif "timestep" in df.columns:
        df["_p1"] = df["timestep"].astype(str)
        df["_p2"] = "0"
        p1name, p2name = "timestep", "part"
    else:
        df["_p1"], df["_p2"] = "all", "0"
        p1name, p2name = "event_date", "event_hour"
    written = 0
    for (ds, a, b), part in df.groupby(["source_dataset", "_p1", "_p2"], dropna=False):
        pdir = root / f"source_dataset={ds}" / f"{p1name}={a}" / f"{p2name}={b}"
        pdir.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["_p1", "_p2"]).to_parquet(pdir / f"part-{uuid.uuid4().hex[:12]}.parquet", index=False)
        written += len(part)
    return written


def read_frame(source_dataset: str | None = None, root: Path = BRONZE_ROOT) -> pd.DataFrame:
    """Đọc toàn bộ Bronze (hoặc một dataset) thành DataFrame — để dựng đồ thị/rollup."""
    base = root if source_dataset is None else root / f"source_dataset={source_dataset}"
    if not base.exists():
        return pd.DataFrame()
    parts = sorted(base.rglob("*.parquet"))
    if not parts:
        return pd.DataFrame()
    df = pd.concat((pd.read_parquet(p) for p in parts), ignore_index=True)
    if source_dataset is not None:
        df["source_dataset"] = source_dataset
    return df


def count(source_dataset: str | None = None, root: Path = BRONZE_ROOT) -> int:
    return len(read_frame(source_dataset, root))
