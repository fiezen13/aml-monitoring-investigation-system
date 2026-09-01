#!/usr/bin/env python3
"""Ghi chu trình do bộ dò tìm được vào ``graph_detector_evidence``.

    python scripts/write_cycle_evidence.py --cycles /tmp/cycle-detect/cycles.jsonl

Chỉ ghi thứ BỘ DÒ tự tìm ra. File ``HI-Medium_Patterns.txt`` của IBM là đáp án
dùng để chấm điểm, không bao giờ được đổ vào bảng này — làm thế là trình bày
nhãn như thể hệ thống tự phát hiện.

Payload theo đúng hình dạng mà ``/fc/graph/patterns`` đọc: khoá ``edges`` với
``from`` / ``to`` / ``transaction_id``. Endpoint tự tra số tiền và thời điểm từ
bảng ``transaction``, nên không nhân bản dữ liệu ở đây.

Mỗi chu trình sinh MỘT dòng bằng chứng cho MỖI tài khoản trên vòng: chuyên viên
mở bất kỳ tài khoản nào trong vòng cũng phải thấy được mẫu hình, chứ không chỉ
tài khoản tình cờ được chọn làm điểm xuất phát.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc  # noqa: UP017
DETECTOR_VERSION = "cycle-v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cycles", type=Path, default=Path("/tmp/cycle-detect/cycles.jsonl"))
    p.add_argument("--max-cycles", type=int, default=4000)
    p.add_argument("--container", default="fin07-postgres-1")
    p.add_argument("--database", default="fin07_hi_medium")
    p.add_argument("--db-user", default="fin07")
    return p.parse_args()


def sql(args: argparse.Namespace, statement: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            args.database,
            "-tAc",
            statement,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        print(proc.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout.strip()


def main() -> int:
    args = parse_args()
    if not args.cycles.exists():
        print(f"Không thấy {args.cycles}", file=sys.stderr)
        return 1

    cycles = []
    with args.cycles.open(encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            if len(item["path"]) >= 3:
                cycles.append(item)
    # Vòng dài trước: chúng khó giải thích bằng trùng hợp hơn vòng ba chặng.
    cycles.sort(key=lambda c: -len(c["path"]))
    cycles = cycles[: args.max_cycles]
    print(f"{len(cycles):,} chu trình sẽ được ghi")

    # Thời điểm của chặng cuối, để as_of_time là mốc vòng khép lại.
    tids = sorted({int(t) for c in cycles for t in c["tids"]})
    print(f"tra thời điểm cho {len(tids):,} giao dịch …", flush=True)
    rows = sql(
        args,
        f"""SELECT transaction_id || '|' || extract(epoch FROM occurred_at)::bigint
                           FROM transaction WHERE transaction_id = ANY(ARRAY[{",".join(map(str, tids))}])""",
    )
    when = {int(a): int(b) for a, b in (r.split("|") for r in rows.splitlines() if r.strip())}

    out = Path("/tmp/cycle-detect/evidence.csv")
    written = 0
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for cyc in cycles:
            path, ids = cyc["path"], [int(x) for x in cyc["tids"]]
            edges = [
                # transaction_id là CHUỖI, không phải số: `GraphEvidenceResult` mà
                # công cụ GetGraphEvidence của tác tử dùng khai kiểu str, và một
                # số nguyên ở đây làm cả phiên điều tra hỏng ở bước đọc bằng chứng.
                {"from": path[i], "to": path[(i + 1) % len(path)], "transaction_id": str(ids[i])}
                for i in range(min(len(ids), len(path)))
            ]
            stamps = [when[i] for i in ids if i in when]
            if not stamps:
                continue
            as_of = datetime.fromtimestamp(max(stamps), UTC).isoformat()
            payload = json.dumps(
                {
                    "edges": edges,
                    "accounts": sorted(set(path)),
                    "duration_hours": round((max(stamps) - min(stamps)) / 3600, 2),
                    # Tên khoá theo đúng `GraphEvidenceResult`: `pattern` và
                    # `cycle_length`. Đặt tên khác thì công cụ của tác tử đọc ra
                    # None và bản giải thích mất hẳn phần cấu trúc.
                    "pattern": "CYCLE",
                    "cycle_length": len(edges),
                },
                ensure_ascii=False,
            )
            fingerprint = hashlib.sha256(("|".join(map(str, sorted(ids)))).encode()).hexdigest()[:16]
            for account in sorted(set(path)):
                eid = "GDE-CYC-" + hashlib.sha256(f"{fingerprint}|{account}".encode()).hexdigest()[:18]
                w.writerow([eid, account, as_of, "CYCLE", DETECTOR_VERSION, payload])
                written += 1

    sql(args, "DELETE FROM graph_detector_evidence WHERE pattern = 'CYCLE'")
    proc = subprocess.Popen(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            args.database,
            "-c",
            "COPY graph_detector_evidence (evidence_id, account_key, as_of_time, pattern,"
            " detector_version, payload) FROM STDIN WITH (FORMAT csv)",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    proc.stdin.write(out.read_bytes())
    proc.stdin.close()
    _, err = proc.communicate()
    if proc.returncode:
        print(err.decode("utf-8", "replace").strip(), file=sys.stderr)
        return 1

    n = sql(args, "SELECT count(*) FROM graph_detector_evidence WHERE pattern='CYCLE'")
    acc = sql(args, "SELECT count(DISTINCT account_key) FROM graph_detector_evidence WHERE pattern='CYCLE'")
    overlap = sql(
        args,
        """SELECT count(DISTINCT g.account_key)
                             FROM graph_detector_evidence g
                             JOIN alert a ON a.account_key = g.account_key AND a.status <> 'closed'""",
    )
    print(f"đã ghi {n} dòng · {acc} tài khoản · {overlap} tài khoản vừa có mẫu hình vừa có cảnh báo mở")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
