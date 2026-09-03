#!/usr/bin/env python3
"""Xuất lõi đồ thị giao dịch ra CSV cho ``detect_cycles_core.py``.

    python scripts/export_cycle_core.py --out /tmp/cycle-detect/core.csv

Mắt xích này trước đây làm thủ công nên không tái lập được. Nó là bước đầu của
chuỗi: xuất lõi → dò chu trình → ghi bằng chứng → sinh cảnh báo T03.

Bóc vỏ trước khi dò
-------------------
Một đỉnh chỉ có thể nằm trên chu trình có hướng nếu nó có **cả** cạnh vào lẫn
cạnh ra. Bỏ lặp các đỉnh thiếu một trong hai chiều cho tới khi ổn định — mỗi
lượt bỏ lại làm lộ ra đỉnh mới thiếu chiều. Lần chạy trước bóc 6,75 triệu cạnh
xuống còn 5,46 triệu.

Bóc bằng mảng số nguyên, KHÔNG bằng SQL đệ quy: ``WITH RECURSIVE`` trên bộ cạnh
này đã thử và ăn hết 30,7 GB đĩa tạm rồi chết (xem đầu ``detect_cycles_core.py``).

Chi phí bộ nhớ
--------------
Chỉ giữ hai mảng ``int32`` cho đỉnh nguồn/đích cộng hai mảng bậc — khoảng 12
byte mỗi cạnh, tức ~80 MB cho 6,75 triệu cạnh. Mốc thời gian và mã giao dịch
được đọc lại từ file thô ở lượt ghi cuối, không giữ trong RAM.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from src.config import get_settings  # noqa: E402

DATASET = "IBM AML HI-Medium"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("/tmp/cycle-detect/core.csv"))
    p.add_argument("--raw", type=Path, default=None, help="giữ lại file cạnh thô (mặc định: cạnh out)")
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--limit", type=int, default=0, help="chỉ lấy N cạnh — dùng để đo thời gian")
    p.add_argument("--database-url", default=None)
    return p.parse_args(argv)


def _dsn(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL phải trỏ tới PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def dump_edges(args: argparse.Namespace, raw: Path) -> int:
    """COPY thẳng từ máy chủ ra file — không đi qua bộ nhớ Python.

    Dùng COPY của psycopg chứ không gọi binary ``psql``: container ``api`` trên
    máy chủ đang phục vụ không cài client PostgreSQL, và thêm một phụ thuộc hệ
    thống chỉ để xuất một file là cái giá không đáng.
    """
    limit = f" LIMIT {args.limit}" if args.limit else ""
    query = (
        "SELECT from_account_key, to_account_key, "
        "extract(epoch FROM occurred_at)::bigint, transaction_id "
        "FROM transaction "
        "WHERE source_dataset = {dataset} "
        # KHÔNG ORDER BY: bắt máy chủ sắp 6,75 triệu dòng là chi phí thuần
        # lãng phí — `detect_cycles_core.py` tự sắp danh sách kề theo thời gian
        # sau khi nạp. `--limit` chỉ dùng để đo, không cần thứ tự ổn định.
        "AND from_account_key <> to_account_key"
        f"{limit}"
    )
    raw.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with (
        psycopg.connect(_dsn(args.database_url or get_settings().database_url)) as conn,
        conn.cursor() as cur,
        raw.open("wb") as fh,
    ):
        # `mogrify` không có trên Cursor của psycopg 3; dùng sql.Literal để
        # trích dẫn an toàn thay vì nối chuỗi tay.
        stmt = sql.SQL(query).format(dataset=sql.Literal(args.dataset))
        with cur.copy(sql.SQL("COPY ({}) TO STDOUT WITH (FORMAT csv)").format(stmt)) as copy:
            for chunk in copy:
                fh.write(chunk)
                n += bytes(chunk).count(b"\n")
    return n


def peel(raw: Path) -> tuple[set[int], dict[str, int], int]:
    """Bỏ lặp đỉnh thiếu cạnh vào hoặc cạnh ra. Trả về (đỉnh lõi, bảng mã, số cạnh)."""
    ids: dict[str, int] = {}
    src, dst = array("i"), array("i")

    def nid(key: str) -> int:
        got = ids.get(key)
        if got is None:
            got = len(ids)
            ids[key] = got
        return got

    with raw.open(newline="", encoding="utf-8") as fh:
        for s, t, _ts, _tid in csv.reader(fh):
            src.append(nid(s))
            dst.append(nid(t))

    n_nodes = len(ids)
    alive = bytearray([1]) * n_nodes
    edge_alive = bytearray([1]) * len(src)
    while True:
        indeg = array("i", [0]) * n_nodes
        outdeg = array("i", [0]) * n_nodes
        for i in range(len(src)):
            if edge_alive[i]:
                outdeg[src[i]] += 1
                indeg[dst[i]] += 1
        drop = {n for n in range(n_nodes) if alive[n] and (indeg[n] == 0 or outdeg[n] == 0)}
        if not drop:
            break
        for n in drop:
            alive[n] = 0
        for i in range(len(src)):
            if edge_alive[i] and (not alive[src[i]] or not alive[dst[i]]):
                edge_alive[i] = 0

    core = {n for n in range(n_nodes) if alive[n]}
    return core, ids, sum(edge_alive)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw = args.raw or args.out.with_name(args.out.stem + "_raw.csv")

    t0 = time.time()
    n_raw = dump_edges(args, raw)
    t_dump = time.time() - t0
    print(f"[1/3] Xuất {n_raw:,} cạnh thô trong {t_dump:.0f}s → {raw}", flush=True)

    t0 = time.time()
    core, ids, n_core_edges = peel(raw)
    t_peel = time.time() - t0
    print(
        f"[2/3] Bóc vỏ: {len(ids):,} → {len(core):,} đỉnh · {n_raw:,} → {n_core_edges:,} cạnh trong {t_peel:.0f}s",
        flush=True,
    )

    t0 = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with raw.open(newline="", encoding="utf-8") as fh, args.out.open("w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["from_account_key", "to_account_key", "occurred_at_epoch", "transaction_id"])
        for s, t, ts, tid in csv.reader(fh):
            if ids[s] in core and ids[t] in core:
                w.writerow([s, t, ts, tid])
                written += 1
    print(f"[3/3] Ghi {written:,} cạnh lõi trong {time.time() - t0:.0f}s → {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
