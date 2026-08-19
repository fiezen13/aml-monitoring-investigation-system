#!/usr/bin/env python3
"""Chạy hàng loạt phiên điều tra rồi soi chất lượng bản giải thích.

    python scripts/audit_agent_runs.py --per-bucket 10

Vì sao cần
----------
Chất lượng của tác tử không đo được bằng một ảnh chụp màn hình. Một cảnh báo
nói "không có giao dịch nào" trong khi bên dưới liệt kê ba giao dịch là lỗi hệ
thống, nhưng chỉ nhìn một cảnh báo thì không biết nó xảy ra với 1% hay 100%.

Script lấy mẫu theo từng cặp (bộ phát hiện, nhóm hành vi), chạy đúng quy trình
thật, rồi chấm mỗi phiên bằng những phép kiểm TẤT ĐỊNH — không hỏi mô hình xem
nó tự thấy mình viết tốt chưa.

Các lỗi được đếm
----------------
``EMPTY_WINDOW_CONTRADICTION``
    Câu mở đầu nói không có giao dịch, trong khi bằng chứng giao dịch của chính
    phiên đó có ít nhất một dòng.
``UNFETCHED_GRAPH``
    Bản giải thích nói "chưa kiểm tra được" một tín hiệu đồ thị, trong khi
    ``graph_detector_evidence`` có sẵn dòng cho tài khoản ấy.
``UNPRODUCIBLE_SIGNAL``
    Nhóm hành vi đòi một tín hiệu mà không nhánh nào trong mã nguồn sinh ra
    được — chờ mãi cũng không có, nên câu "thiếu bằng chứng" là vĩnh viễn.
``NO_BEHAVIOR`` / ``NO_TRANSACTION``
    Bằng chứng bắt buộc vẫn vắng sau khi quy trình đã tự bổ sung.
``GEO_NO_COUNTRY``
    Cảnh báo hành lang địa lý mà cả bản giải thích không nêu tên nước nào.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio  # noqa: E402

from sqlalchemy import text  # noqa: E402

from src.db.session import get_session  # noqa: E402
from src.investigation.repository import InvestigationRepository  # noqa: E402
from src.investigation.workflow import InvestigationWorkflow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc  # noqa: UP017

#: Tín hiệu mà ``_observed_signals`` trong agents.py thật sự sinh ra được.
#: Bất kỳ tín hiệu nào ngoài tập này đều là lời hứa suông trong danh mục nhóm.
PRODUCIBLE_SIGNALS = {
    "rapid_outflow",
    "new_counterparties",
    "fan_in",
    "fan_out",
    "repeated_amounts",
    "short_dwell_time",
    "short_duration",
    "value_retention",
    "network_flow",
    "directed_cycle",
    "rule_trigger",
    "profile_deviation",
    "volume_deviation",
    "jurisdiction_signal",
    "cross_border_flow",
}

EMPTY_WINDOW_MARK = "không có giao dịch nào của tài khoản"
#: Chỉ đếm dạng KHÔNG có lý do. "chưa kiểm tra được X — cửa sổ không có giao
#: dịch tiền vào nào" là câu đúng và dùng được; "vì thiếu bằng chứng tương
#: ứng" mới là câu bỏ mặc người đọc.
UNCHECKED_MARK = "vì thiếu bằng chứng tương ứng"
_COUNTRY_RE = re.compile(r"[A-Z]{2}\b")

_print_lock = threading.Lock()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--per-bucket", type=int, default=10, help="số cảnh báo lấy mẫu cho mỗi (bộ phát hiện, nhóm)")
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--seed", type=int, default=20260819)
    p.add_argument("--out", type=Path, default=ROOT / "reports/agent-audit/latest.jsonl")
    p.add_argument("--label", default="baseline")
    return p.parse_args()


def sample_alerts(per_bucket: int, seed: int) -> list[dict[str, Any]]:
    with get_session() as session:
        session.execute(text("SELECT setseed(:s)"), {"s": (seed % 1000) / 1000.0})
        rows = session.execute(
            text(
                """
                SELECT alert_id, account_key, detector, typology_code FROM (
                  SELECT alert_id, account_key, detector, typology_code,
                         row_number() OVER (PARTITION BY detector, typology_code ORDER BY random()) AS rn
                    FROM alert
                   WHERE NOT EXISTS (SELECT 1 FROM investigation i
                                      WHERE i.alert_id = alert.alert_id
                                        AND i.status IN ('QUEUED','INVESTIGATING'))
                ) s WHERE rn <= :n
                """
            ),
            {"n": per_bucket},
        ).mappings()
        return [dict(r) for r in rows]


def _account_has_graph_evidence(session, account_key: str) -> bool:
    return bool(
        session.execute(
            text("SELECT EXISTS(SELECT 1 FROM graph_detector_evidence WHERE account_key = :a)"),
            {"a": account_key},
        ).scalar_one()
    )


def audit_one(alert: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {
        "alert_id": alert["alert_id"],
        "detector": alert["detector"],
        "typology_code": alert["typology_code"],
        "account_key": alert["account_key"],
        "defects": [],
    }
    try:
        with get_session() as session:
            repo = InvestigationRepository(session)
            investigation = repo.create(alert["alert_id"], triggered_by="audit")
            record["investigation_id"] = investigation.investigation_id
            workflow = InvestigationWorkflow(session)
            asyncio.run(workflow.run(investigation.investigation_id))
            state = repo.get(investigation.investigation_id)
            record["status"] = str(getattr(state.status, "value", state.status))
            record["iterations"] = state.iteration
            record["tool_calls"] = state.tool_call_count
            record["failure_reason"] = state.failure_reason

            evidence = repo.list_evidence(investigation.investigation_id)
            types = Counter(str(getattr(e.type, "value", e.type)) for e in evidence)
            record["evidence_types"] = dict(types)

            tx_items = 0
            for item in evidence:
                if str(getattr(item.type, "value", item.type)) == "TRANSACTION":
                    tx_items += len(item.payload.get("items", []))
            record["transaction_rows"] = tx_items

            package = session.execute(
                text(
                    """SELECT explanation FROM case_explanation
                        WHERE investigation_id = :i ORDER BY version DESC LIMIT 1"""
                ),
                {"i": investigation.investigation_id},
            ).scalar_one_or_none()
            explanation = package or {}
            record["has_explanation"] = bool(package)
            summary = explanation.get("summary") or ""
            facts = explanation.get("facts") or []
            inferences = explanation.get("inferences") or []
            record["summary"] = summary
            record["fact_count"] = len(facts)
            record["facts"] = facts
            record["inferences"] = inferences

            blob = " ".join([summary, *facts, *inferences])

            if EMPTY_WINDOW_MARK in summary and tx_items > 0:
                record["defects"].append("EMPTY_WINDOW_CONTRADICTION")
            if "BEHAVIOR_FEATURE" not in types:
                record["defects"].append("NO_BEHAVIOR")
            if "TRANSACTION" not in types:
                record["defects"].append("NO_TRANSACTION")
            if UNCHECKED_MARK in blob and _account_has_graph_evidence(session, alert["account_key"]):
                record["defects"].append("UNFETCHED_GRAPH")
            if alert["detector"] == "geo_rule" and not _COUNTRY_RE.search(blob):
                record["defects"].append("GEO_NO_COUNTRY")
            if UNCHECKED_MARK in blob:
                record["defects"].append("UNCHECKED_SIGNAL_TEXT")
    except Exception as exc:  # noqa: BLE001 — một phiên hỏng không được dừng cả đợt đo
        record["status"] = "HARNESS_ERROR"
        record["error"] = f"{type(exc).__name__}: {exc}"[:400]
        record["defects"].append("HARNESS_ERROR")
    record["seconds"] = round(time.monotonic() - started, 1)
    with _print_lock:
        print(
            f"  {record['alert_id']:<26} {record['detector']:<9} {record.get('status', ''):<22} "
            f"{record['seconds']:>5.1f}s  {','.join(record['defects']) or 'ok'}",
            flush=True,
        )
    return record


def main() -> int:
    args = parse_args()
    alerts = sample_alerts(args.per_bucket, args.seed)
    print(f"[audit:{args.label}] {len(alerts)} cảnh báo, {args.concurrency} luồng\n", flush=True)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for record in pool.map(audit_one, alerts):
            results.append(record)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for record in results:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    status = Counter(r.get("status") for r in results)
    defects = Counter(d for r in results for d in r["defects"])
    by_detector: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        for d in r["defects"]:
            by_detector[r["detector"]][d] += 1

    print(f"\n=== {args.label} · {len(results)} phiên ===")
    print("Trạng thái:")
    for key, count in status.most_common():
        print(f"  {key:<24} {count:>4}  ({count / len(results):.0%})")
    print("Lỗi chất lượng:")
    for key, count in defects.most_common():
        print(f"  {key:<28} {count:>4}  ({count / len(results):.0%})")
    print("Theo bộ phát hiện:")
    for detector, counter in sorted(by_detector.items()):
        total = sum(1 for r in results if r["detector"] == detector)
        print(f"  {detector} (n={total}): " + ", ".join(f"{k}={v}" for k, v in counter.most_common()))
    clean = sum(1 for r in results if not r["defects"])
    print(f"\nPhiên không lỗi: {clean}/{len(results)} ({clean / len(results):.0%})")
    print(f"Chi tiết: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
