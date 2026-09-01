"""Gán lại nhãn nhóm hành vi cho cảnh báo, đo bằng ĐÚNG thước đo mà bản giải thích dùng.

Vì sao cần script này
---------------------
``scripts/build_mega_pna_alerts.py`` gán T04 khi ô chấm điểm có **≥5 giao dịch
vào và ≥5 giao dịch ra**, rồi đặt tên nhãn là "Nhiều nguồn dồn vào rồi toả ra
nhiều đích". Nó đếm GIAO DỊCH nhưng gọi là NGUỒN: 9 giao dịch vào có thể chỉ đến
từ 2 người gửi. Bản giải thích của tác tử đếm đúng số đối tác khác nhau trong
cửa sổ 30 ngày, nên cùng một cảnh báo hiện ra hai câu đá nhau:

    nhãn:        T04 — Gom vào rồi toả ra bất thường
    giải thích:  "chưa đạt ngưỡng nhiều nguồn dồn vào (2 đối tác gửi, ngưỡng ≥ 5)"

Đo trên 1.500 cảnh báo IBM lấy ngẫu nhiên: chỉ 28 (1,9%) thật sự có ≥5 nguồn và
≥5 đích; trung bình là 2,0 nguồn / 2,3 đích.

Cách sửa
--------
Một thước đo duy nhất cho cả hai nơi: cửa sổ 30 ngày tính lùi từ giao dịch gần
nhất của tài khoản tại thời điểm cảnh báo — đúng mốc mà
``InvestigationRepository._snapshot_time`` dùng. Tín hiệu suy ra từ cửa sổ ấy rồi
đối chiếu danh mục ``typologies.json`` qua ``match_typology``. Không nhóm nào
chứng minh được thì gán ``T00`` (nói thẳng là chưa đối chiếu được) thay vì mặc
định vào một nhóm có thật.

Chạy::

    python scripts/relabel_alert_typologies.py --detector mega_pna --dry-run
    python scripts/relabel_alert_typologies.py --detector mega_pna --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402
from src.domain import typology_label  # noqa: E402
from src.investigation.agents import (  # noqa: E402
    FAN_COUNTERPARTIES,
    RAPID_OUTFLOW_PERCENT,
    RETAINED_OUTFLOW_RATIO,
    SHORT_DWELL_HOURS,
)
from src.investigation.typology_match import match_typology  # noqa: E402

WINDOW_DAYS = 30
#: Cửa sổ "đi ngay sau khi nhận" — khớp `rapid_window_hours` của công cụ đặc trưng.
RAPID_WINDOW_HOURS = 2

#: Một lượt đo cho cả lô tài khoản. Mốc cửa sổ (`as_of`) là giao dịch gần nhất
#: của chính tài khoản tại thời điểm cảnh báo — cùng mốc với phiên điều tra, nếu
#: khác thì nhãn và lời giải thích lại đá nhau lần nữa.
_MEASURE_SQL = f"""
WITH a AS (
    SELECT alert_id, account_key, created_at FROM alert WHERE alert_id = ANY(:alert_ids)
), anchor AS (
    SELECT a.*,
           (SELECT max(occurred_at) FROM transaction t
             WHERE t.occurred_at <= a.created_at
               AND (t.from_account_key = a.account_key OR t.to_account_key = a.account_key)) AS as_of
      FROM a
), ev AS (
    SELECT anchor.alert_id,
           (t.to_account_key = anchor.account_key) AS is_in,
           CASE WHEN t.to_account_key = anchor.account_key THEN t.from_account_key ELSE t.to_account_key END AS cp,
           t.amount, t.occurred_at
      FROM anchor
      LEFT JOIN transaction t
        ON (t.from_account_key = anchor.account_key OR t.to_account_key = anchor.account_key)
       AND t.occurred_at >  anchor.as_of - interval '{WINDOW_DAYS} days'
       AND t.occurred_at <= anchor.as_of
), rapid AS (
    -- Tiền RA trong vòng 2 giờ sau một lần NHẬN — cùng định nghĩa với
    -- `_observed_from_rows` trong src/investigation/tools.py.
    SELECT o.alert_id, coalesce(sum(o.amount), 0) AS rapid_out
      FROM ev o
     WHERE NOT o.is_in
       AND EXISTS (
           SELECT 1 FROM ev i
            WHERE i.alert_id = o.alert_id AND i.is_in
              AND i.occurred_at <= o.occurred_at
              AND i.occurred_at >= o.occurred_at - interval '{RAPID_WINDOW_HOURS} hours')
     GROUP BY o.alert_id
)
SELECT ev.alert_id,
       count(DISTINCT cp) FILTER (WHERE is_in)            AS unique_in,
       count(DISTINCT cp) FILTER (WHERE NOT is_in)        AS unique_out,
       coalesce(sum(amount) FILTER (WHERE is_in), 0)      AS inflow,
       coalesce(sum(amount) FILTER (WHERE NOT is_in), 0)  AS outflow,
       coalesce(max(rapid.rapid_out), 0)                  AS rapid_out
  FROM ev LEFT JOIN rapid ON rapid.alert_id = ev.alert_id
 GROUP BY ev.alert_id
"""


def signals_from_window(row: dict[str, Any]) -> set[str]:
    """Tín hiệu suy từ cửa sổ giao dịch — cùng ngưỡng với ``agents._observed_signals``.

    Ngưỡng nhập trực tiếp từ ``agents`` chứ không chép lại: chép số là cách chắc
    chắn để hai bên trôi ra khỏi nhau sau vài lần chỉnh.
    """
    signals: set[str] = set()
    inflow, outflow = float(row["inflow"]), float(row["outflow"])
    if int(row["unique_in"]) >= FAN_COUNTERPARTIES:
        signals.add("fan_in")
    if int(row["unique_out"]) >= FAN_COUNTERPARTIES:
        signals.add("fan_out")
    if inflow > 0 and outflow >= RETAINED_OUTFLOW_RATIO * inflow:
        signals.add("pass_through")
    rapid_percent = 100 * float(row["rapid_out"]) / outflow if outflow > 0 else 0.0
    if rapid_percent >= RAPID_OUTFLOW_PERCENT:
        signals.add("rapid_outflow")
    return signals


#: Nhánh mà phép đo này KHÔNG áp dụng được.
#:
#: Cảnh báo địa lý gán nhãn từ `geo_context` (hành lang, mức nền xuyên biên
#: giới) — thứ không nằm trong cửa sổ giao dịch của một tài khoản. Chạy phép đo
#: hành vi lên chúng sẽ biến toàn bộ T06 thành T00/T02, tức là xoá đúng phần
#: nhãn đang khớp với bản giải thích.
_UNSUPPORTED_DETECTORS = {"geo_rule"}


def relabel(detector: str, *, apply: bool, batch: int = 500, limit: int | None = None) -> Counter:
    if detector in _UNSUPPORTED_DETECTORS:
        raise SystemExit(
            f"Nhánh {detector} gán nhãn từ ngữ cảnh địa lý, không phải từ cửa sổ giao dịch — "
            "chạy script này lên nó sẽ xoá mất nhãn đang đúng."
        )
    moves: Counter = Counter()
    with get_session() as session:
        ids = (
            session.execute(
                text(
                    "SELECT alert_id FROM alert WHERE detector = :d ORDER BY alert_id"
                    + (" LIMIT :lim" if limit else "")
                ),
                {"d": detector, **({"lim": limit} if limit else {})},
            )
            .scalars()
            .all()
        )
    print(f"{len(ids)} cảnh báo của nhánh {detector}", flush=True)

    for start in range(0, len(ids), batch):
        chunk = ids[start : start + batch]
        with get_session() as session:
            measured = session.execute(text(_MEASURE_SQL), {"alert_ids": chunk}).mappings().all()
            current = dict(
                session.execute(
                    text("SELECT alert_id, typology_code FROM alert WHERE alert_id = ANY(:ids)"), {"ids": chunk}
                ).all()
            )
            updates: list[dict[str, str]] = []
            for row in measured:
                match = match_typology(signals_from_window(dict(row)))
                before = current[row["alert_id"]]
                moves[(before, match.typology_code)] += 1
                if match.typology_code != before:
                    updates.append({"id": row["alert_id"], "code": match.typology_code})
            if apply and updates:
                session.execute(text("UPDATE alert SET typology_code = :code WHERE alert_id = :id"), updates)
        print(f"  ... {min(start + batch, len(ids))}/{len(ids)}", flush=True)
    return moves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detector", default="mega_pna")
    parser.add_argument("--limit", type=int, default=None, help="Chỉ xử lý N cảnh báo đầu (để thử)")
    parser.add_argument("--apply", action="store_true", help="Ghi thật; mặc định chỉ báo cáo")
    args = parser.parse_args(argv)

    print(
        "Ngưỡng đang dùng: "
        f"fan ≥ {FAN_COUNTERPARTIES} đối tác · tiền ra nhanh ≥ {RAPID_OUTFLOW_PERCENT:.0f}% "
        f"· giữ lại < {RETAINED_OUTFLOW_RATIO:.0%} · nằm lại ≤ {SHORT_DWELL_HOURS:.0f} giờ\n"
    )
    moves = relabel(args.detector, apply=args.apply, limit=args.limit)

    print("\n=== NHÃN CŨ → NHÃN MỚI ===")
    for (before, after), n in sorted(moves.items(), key=lambda kv: -kv[1]):
        mark = "  (giữ nguyên)" if before == after else ""
        print(f"  {before} → {after:4} {n:>6}{mark}   {typology_label(after)}")
    after_total: Counter = Counter()
    for (_, after), n in moves.items():
        after_total[after] += n
    print("\n=== PHÂN BỐ SAU KHI GÁN LẠI ===")
    for code, n in after_total.most_common():
        print(f"  {code:4} {n:>6}   {typology_label(code)}")
    if not args.apply:
        print("\n(chưa ghi gì — thêm --apply để ghi thật)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
