"""Chạy lại các phiên điều tra đã có, để bản giải thích dùng logic hiện hành.

Vì sao cần
----------
``case_explanation`` lưu NGUYÊN VĂN bản giải thích tại thời điểm sinh ra. Mọi
sửa đổi về cách kể — định dạng số và ngày, không cộng gộp nhiều loại tiền, một
định nghĩa cho chữ "nhiều", bỏ ngoặc lồng, xếp lại mạch dữ kiện, các luật kiểm
nhất quán — chỉ áp cho phiên chạy MỚI. Vụ đã điều tra trước đó vẫn hiện bản cũ,
nên cùng một hệ thống lại có hai lối kể.

Nguyên tắc
----------
* **Không đụng vụ đã kết thúc.** ``XuatHoSo``/``DongKhongBaoCao`` đã có hồ sơ
  xuất ra và quyết định của con người; sinh thêm một phiên điều tra sau đó chỉ
  làm rối vết kiểm toán.
* **Chạy theo lô và chờ xong.** Đẩy cả trăm việc vào hàng đợi một lúc thì worker
  nghẽn và không quan sát được tiến độ.
* **Đếm lại chất lượng ở cuối.** Chạy lại mà không đo thì không biết có thật sự
  tốt hơn không.

Chạy::

    python scripts/rerun_investigations.py                 # chỉ liệt kê
    python scripts/rerun_investigations.py --apply         # chạy thật
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402
from src.investigation.repository import InvestigationRepository  # noqa: E402
from src.services import queue  # noqa: E402

#: Trạng thái phiên coi là đã dừng.
_TERMINAL = ("COMPLETED", "NEEDS_HUMAN_REVIEW", "INSUFFICIENT_EVIDENCE", "FAILED")

#: Vụ đã kết thúc thì không sinh thêm phiên điều tra.
_CLOSED_CASES = ("XuatHoSo", "DongKhongBaoCao")


#: Phiên dừng vì lỗi gọi mô hình, KHÔNG phải vì thiếu bằng chứng.
#:
#: Cả quy trình chạy trong một giao dịch; lỗi Gemini làm rollback nên phiên
#: không để lại bản giải thích nào và màn hình vẫn hiện bản cũ. Chạy 15 việc
#: song song là đủ để Google trả 429 — bài học đo được ngày 27/08/2026.
_MODEL_ERROR = "GeminiServiceError"


def pick_alerts(limit: int | None = None, *, only_failed: bool = False) -> list[str]:
    """Cảnh báo đã từng điều tra, vụ chưa kết thúc.

    ``only_failed`` chỉ lấy những vụ mà lần chạy gần nhất hỏng vì lỗi gọi mô
    hình — dùng để chạy bù sau khi bị giới hạn tần suất.
    """
    where_failed = (
        """ AND EXISTS (
                SELECT 1 FROM investigation f
                 WHERE f.alert_id = i.alert_id AND f.failure_reason LIKE :model_error
                   AND f.created_at = (SELECT max(g.created_at) FROM investigation g
                                        WHERE g.alert_id = i.alert_id))"""
        if only_failed
        else ""
    )
    sql = f"""
        SELECT DISTINCT i.alert_id
          FROM investigation i
          JOIN aml_case c ON c.case_id = i.case_id
         WHERE c.state NOT IN {_CLOSED_CASES}{where_failed}
         ORDER BY i.alert_id
    """ + (" LIMIT :lim" if limit else "")
    params: dict[str, object] = {}
    if only_failed:
        params["model_error"] = f"{_MODEL_ERROR}%"
    if limit:
        params["lim"] = limit
    with get_session() as session:
        return list(session.execute(text(sql), params).scalars().all())


def run_batch(alert_ids: list[str], *, timeout: int = 900) -> dict[str, str]:
    """Đẩy một lô vào hàng đợi rồi chờ tất cả dừng."""
    started: dict[str, str] = {}
    for alert_id in alert_ids:
        with get_session() as session:
            investigation = InvestigationRepository(session).create(alert_id, triggered_by="chay-lai-dong-bo")
        queue.enqueue("investigate_alert", {"investigation_id": investigation.investigation_id})
        started[investigation.investigation_id] = alert_id

    done: dict[str, str] = {}
    deadline = time.time() + timeout
    while time.time() < deadline and len(done) < len(started):
        time.sleep(10)
        with get_session() as session:
            for investigation_id in started:
                if investigation_id in done:
                    continue
                status = session.execute(
                    text("SELECT status FROM investigation WHERE investigation_id = :i"),
                    {"i": investigation_id},
                ).scalar()
                if status in _TERMINAL:
                    done[investigation_id] = status
    for investigation_id in started:
        done.setdefault(investigation_id, "QUÁ HẠN CHỜ")
    return done


def quality_report(sample: int = 40) -> dict[str, int]:
    """Đếm khiếm khuyết trình bày trên các bản giải thích mới nhất."""
    long_decimal = re.compile(r"\d+\.\d{5,}")
    iso_date = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
    flaws: Counter = Counter()
    with get_session() as session:
        rows = session.execute(
            text("SELECT explanation FROM case_explanation ORDER BY created_at DESC LIMIT :n"), {"n": sample}
        ).scalars().all()
    for explanation in rows:
        prose = " ".join(
            [explanation.get("summary") or "", *(explanation.get("facts") or []), *(explanation.get("inferences") or [])]
        )
        depth = maximum = 0
        for char in prose:
            depth += char == "("
            depth -= char == ")"
            maximum = max(maximum, depth)
        if iso_date.search(prose):
            flaws["ngày định dạng máy"] += 1
        if long_decimal.search(prose):
            flaws["số thập phân dài"] += 1
        if maximum > 1:
            flaws["ngoặc lồng > 1 tầng"] += 1
        if " ." in prose or "  " in prose:
            flaws["dấu cách thừa"] += 1
        if any(code in prose.lower() for code in ("mega_pna", "geo_rule", "feature_service")):
            flaws["mã nội bộ"] += 1
    flaws["tổng bản đã soi"] = len(rows)
    return dict(flaws)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Chạy thật; mặc định chỉ liệt kê")
    parser.add_argument("--batch", type=int, default=15, help="Số phiên chạy song song mỗi lô")
    parser.add_argument("--limit", type=int, default=None, help="Chỉ xử lý N cảnh báo đầu")
    parser.add_argument("--only-failed", action="store_true", help="Chỉ chạy bù vụ hỏng vì lỗi gọi mô hình")
    parser.add_argument("--pause", type=int, default=0, help="Nghỉ bao nhiêu giây giữa hai lô (tránh 429)")
    args = parser.parse_args(argv)

    alerts = pick_alerts(args.limit, only_failed=args.only_failed)
    print(f"{len(alerts)} cảnh báo cần chạy lại (đã bỏ vụ ở trạng thái kết thúc)", flush=True)
    if not args.apply:
        print("(chưa chạy — thêm --apply)")
        return 0

    results: Counter = Counter()
    for start in range(0, len(alerts), args.batch):
        chunk = alerts[start : start + args.batch]
        outcome = run_batch(chunk)
        results.update(outcome.values())
        print(
            f"  ... {min(start + args.batch, len(alerts))}/{len(alerts)} · lô này: {dict(Counter(outcome.values()))}",
            flush=True,
        )
        if args.pause and start + args.batch < len(alerts):
            time.sleep(args.pause)

    print(f"\nKẾT QUẢ: {dict(results)}")
    print(f"CHẤT LƯỢNG TRÌNH BÀY: {quality_report()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
