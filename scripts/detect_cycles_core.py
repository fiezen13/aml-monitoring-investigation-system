#!/usr/bin/env python3
"""Dò chu trình dòng tiền trên lõi đồ thị, có ngân sách duyệt.

    python scripts/detect_cycles_core.py --core /tmp/cycle-detect/core.csv

Vì sao không liệt kê đệ quy trong SQL
-------------------------------------
Đã thử: ``WITH RECURSIVE`` trên 28,8 triệu cạnh ăn hết 30,7 GB đĩa tạm rồi chết,
kể cả sau khi bóc vỏ còn 5,46 triệu cạnh. Bậc ra trung bình của lõi là 22, nên
số đường đi độ dài 6 về lý thuyết là 22^6 ≈ 113 triệu **cho mỗi đỉnh xuất phát**.
Liệt kê toàn bộ là bài toán sai, không phải bài toán chậm.

Ba ràng buộc cắt không gian tìm kiếm
------------------------------------
1. **Thứ tự thời gian** — mỗi chặng phải xảy ra sau chặng trước, và cách nhau
   không quá ``--max-gap-hours``. Đây là ràng buộc mạnh nhất: dòng tiền có
   chiều thời gian, một vòng "khép kín" mà các chặng lộn xộn về thời gian thì
   không phải dòng tiền chảy vòng.
2. **Chuẩn hoá điểm xuất phát** — chỉ đi qua đỉnh có mã lớn hơn đỉnh xuất phát.
   Mỗi vòng vì thế được tìm đúng một lần thay vì một lần cho mỗi đỉnh trên nó.
3. **Ngân sách mỗi đỉnh** — quá ``--budget`` bước duyệt thì bỏ đỉnh đó và ghi
   nhận. Thà báo "đã bỏ qua N đỉnh vì quá dày" còn hơn chạy vô hạn rồi chết.

Số đỉnh bị bỏ được ghi vào báo cáo, vì nó là giới hạn thật của kết quả: recall
đo được là recall CỦA BỘ DÒ CÓ NGÂN SÁCH, không phải của một bộ dò lý tưởng.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from array import array
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc  # noqa: UP017


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core", type=Path, default=Path("/tmp/cycle-detect/core.csv"))
    p.add_argument("--min-len", type=int, default=3)
    p.add_argument("--max-len", type=int, default=6)
    p.add_argument("--max-gap-hours", type=int, default=72)
    p.add_argument("--budget", type=int, default=20000, help="số bước duyệt tối đa mỗi đỉnh")
    p.add_argument("--max-cycles", type=int, default=20000)
    p.add_argument("--patterns", type=Path, default=ROOT / "data/raw/ibm-aml/HI-Medium_Patterns.txt")
    p.add_argument("--out", type=Path, default=ROOT / "reports/graph-detector/cycle_v1.json")
    p.add_argument("--cycles-out", type=Path, default=Path("/tmp/cycle-detect/cycles.jsonl"))
    return p.parse_args()


def load_truth(path: Path) -> dict[tuple[str, str], int]:
    truth: dict[tuple[str, str], int] = {}
    cur, aid = None, 0
    head = re.compile(r"BEGIN LAUNDERING ATTEMPT - (.+?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = head.match(line)
        if m:
            cur = m.group(1).split(":")[0].strip()
            aid += 1
            continue
        if line.startswith("END LAUNDERING ATTEMPT"):
            cur = None
            continue
        if cur == "CYCLE" and line.strip():
            f = next(csv.reader([line]))
            if len(f) >= 11:
                truth[(f"{int(f[1])}:{f[2]}", f"{int(f[3])}:{f[4]}")] = aid
    return truth


def main() -> int:
    args = parse_args()
    if not args.core.exists():
        print(f"Không thấy {args.core}", file=sys.stderr)
        return 1

    print("[1/4] Nạp lõi …", flush=True)
    ids: dict[str, int] = {}
    names: list[str] = []

    def nid(key: str) -> int:
        got = ids.get(key)
        if got is None:
            got = len(names)
            ids[key] = got
            names.append(key)
        return got

    adj: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    n_edges = 0
    with args.core.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for s, t, ts, tid in reader:
            adj[nid(s)].append((nid(t), int(ts), int(tid)))
            n_edges += 1
    for node in adj:
        adj[node].sort(key=lambda item: item[1])
    print(f"      {n_edges:,} cạnh · {len(names):,} đỉnh", flush=True)

    gap = args.max_gap_hours * 3600
    cycles: list[tuple[list[int], list[int]]] = []
    skipped = 0
    seeds = sorted(adj)
    print(f"[2/4] Duyệt {len(seeds):,} đỉnh (ngân sách {args.budget:,}/đỉnh) …", flush=True)

    for done, seed in enumerate(seeds, 1):
        if done % 25000 == 0:
            print(f"      {done:,}/{len(seeds):,} · {len(cycles):,} vòng · {skipped:,} đỉnh bỏ qua", flush=True)
        if len(cycles) >= args.max_cycles:
            break
        steps = 0
        # Ngăn xếp: (đỉnh hiện tại, mốc thời gian chặng vừa đi, đường đỉnh, đường cạnh)
        stack: list[tuple[int, int, array, array]] = []
        for nxt, ts, tid in adj[seed]:
            if nxt == seed or nxt < seed:
                continue
            stack.append((nxt, ts, array("i", [seed, nxt]), array("q", [tid])))
        blown = False
        while stack:
            cur, last_ts, path, tids = stack.pop()
            steps += 1
            if steps > args.budget:
                blown = True
                break
            depth = len(tids)
            if depth >= args.max_len:
                continue
            for nxt, ts, tid in adj.get(cur, ()):
                if ts <= last_ts:
                    continue
                if ts > last_ts + gap:
                    break  # adj đã sắp theo thời gian: quá cửa sổ thì phần sau cũng quá
                if nxt == seed:
                    if depth + 1 >= args.min_len:
                        cycles.append((list(path), [*tids, tid]))
                    continue
                if nxt < seed or nxt in path:
                    continue
                stack.append((nxt, ts, array("i", [*path, nxt]), array("q", [*tids, tid])))
        if blown:
            skipped += 1

    print(f"      {len(cycles):,} vòng · {skipped:,} đỉnh vượt ngân sách", flush=True)

    # Chấm điểm là TUỲ CHỌN. `HI-Medium_Patterns.txt` là ĐÁP ÁN của IBM: nó
    # đúng ra KHÔNG được có mặt trên máy chủ đang phục vụ, và việc dò chu trình
    # không cần tới nó. Thiếu file thì bỏ qua bước chấm và ghi recall là null,
    # thay vì để cả đường ống chết sau khi đã dò xong.
    if args.patterns.exists():
        print("[3/4] Chấm điểm theo nhãn IBM …", flush=True)
        truth = load_truth(args.patterns)
    else:
        print(f"[3/4] Bỏ qua chấm điểm: không có {args.patterns} (đáp án IBM)", flush=True)
        truth = {}
    attempts = set(truth.values())
    hits: dict[int, int] = defaultdict(int)
    for path, _ in cycles:
        keys = [names[i] for i in path]
        seen: set[int] = set()
        for i in range(len(keys)):
            edge = (keys[i], keys[(i + 1) % len(keys)])
            a = truth.get(edge)
            if a is not None:
                seen.add(a)
        for a in seen:
            hits[a] += 1
    matched1 = set(hits)
    if truth:
        print(f"      vụ CYCLE có nhãn: {len(attempts)} · bộ dò chạm: {len(matched1)}")

    args.cycles_out.parent.mkdir(parents=True, exist_ok=True)
    with args.cycles_out.open("w", encoding="utf-8") as fh:
        for path, tids in cycles:
            fh.write(json.dumps({"path": [names[i] for i in path], "tids": tids}) + "\n")

    report = {
        "schema_version": "fin07.graph_detector.cycle.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "params": {
            "min_len": args.min_len,
            "max_len": args.max_len,
            "max_gap_hours": args.max_gap_hours,
            "budget_per_node": args.budget,
        },
        "core_edges": n_edges,
        "core_nodes": len(names),
        "cycles_found": len(cycles),
        "nodes_over_budget": skipped,
        "labelled_cycle_attempts": len(attempts),
        "attempts_touched": len(matched1),
        "recall": round(len(matched1) / len(attempts), 4) if attempts else None,
        "note": (
            "HI-Medium_Patterns.txt là ĐÁP ÁN, chỉ dùng để chấm điểm; không đổ vào "
            "graph_detector_evidence. Recall ở đây là recall của bộ dò CÓ NGÂN SÁCH: "
            f"{skipped:,} đỉnh quá dày đã bị bỏ qua."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # `relative_to` ném lỗi khi --out nằm ngoài cây repo (ví dụ /tmp trên máy
    # chủ). Báo cáo đã ghi xong ở dòng trên; đừng để một dòng in làm hỏng cả
    # lượt chạy.
    try:
        shown = args.out.relative_to(ROOT)
    except ValueError:
        shown = args.out
    print(f"[4/4] đã ghi {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
