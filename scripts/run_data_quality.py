"""Chạy kiểm tra chất lượng dữ liệu và tính chỉ số giám sát mô hình.

Chạy theo lô, không phải lúc mở trang: mọi câu hỏi ở đây đều quét bảng
``transaction`` (6,1 triệu dòng). Kết quả ghi vào ``data_quality_check`` và
``model_monitor_metric``; hai endpoint ``/fc/data-quality`` và
``/fc/model-monitor`` chỉ đọc lại.

    python -m scripts.run_data_quality

Mỗi lần chạy **thay thế** kết quả của lần trước. Giữ lịch sử ở đây không có
tác dụng: hai lần chạy trên cùng một tập dữ liệu tĩnh cho cùng một kết quả, và
một trang đầy dòng trùng nhau thì khó đọc hơn chứ không giàu thông tin hơn.
"""

from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.session import get_session

logger = logging.getLogger("fin07.dq")

#: Dưới ngưỡng này là hỏng; giữa ngưỡng và 1.0 là cảnh báo.
#: Con số khác nhau theo từng phép kiểm vì hậu quả khác nhau: thiếu nhãn làm
#: hỏng việc đánh giá mô hình, còn thiếu mã giao dịch gốc chỉ làm khó truy vết.
_WARN_BAND = 0.999


@dataclass(frozen=True)
class Check:
    """Một phép kiểm: đếm tổng và đếm số dòng hỏng, phần còn lại suy ra được."""

    check_id: str
    dataset: str
    name: str
    dimension: str
    threshold: float
    detail: str
    total_sql: str
    failed_sql: str


CHECKS: tuple[Check, ...] = (
    Check(
        check_id="DQ-TX-SOURCE-ID",
        dataset="transaction",
        name="Giao dịch truy được về dòng gốc",
        dimension="completeness",
        threshold=1.0,
        detail="Không có source_transaction_id thì không đối chiếu ngược được với file IBM gốc.",
        total_sql="SELECT count(*) FROM transaction",
        failed_sql="SELECT count(*) FROM transaction WHERE source_transaction_id IS NULL",
    ),
    Check(
        check_id="DQ-TX-LABEL",
        dataset="transaction",
        name="Giao dịch có nhãn rửa tiền",
        dimension="completeness",
        threshold=1.0,
        detail="Thiếu nhãn thì mọi con số precision/recall tính ra đều sai lệch về phía lạc quan.",
        total_sql="SELECT count(*) FROM transaction",
        failed_sql="""SELECT count(*) FROM transaction t
                       WHERE NOT EXISTS (SELECT 1 FROM label.label_laundering l
                                          WHERE l.transaction_id = t.transaction_id)""",
    ),
    Check(
        check_id="DQ-TX-SELF-TRANSFER",
        dataset="transaction",
        name="Không có giao dịch tự chuyển",
        dimension="validity",
        threshold=1.0,
        detail="Cạnh nối một đỉnh với chính nó làm sai mọi phép đếm bậc trên đồ thị.",
        total_sql="SELECT count(*) FROM transaction",
        failed_sql="SELECT count(*) FROM transaction WHERE from_account_key = to_account_key",
    ),
    Check(
        check_id="DQ-TX-SCORED",
        dataset="transaction_model_score",
        name="Giao dịch đã được mô hình chấm điểm",
        dimension="completeness",
        threshold=1.0,
        detail="Giao dịch không có điểm là giao dịch mô hình chưa từng nhìn thấy.",
        total_sql="SELECT count(*) FROM transaction",
        failed_sql="""SELECT count(*) FROM transaction t
                       WHERE NOT EXISTS (SELECT 1 FROM transaction_model_score s
                                          WHERE s.transaction_id = t.transaction_id)""",
    ),
    Check(
        check_id="DQ-ALERT-REASONS",
        dataset="alert",
        name="Cảnh báo có đủ ba yếu tố giải thích",
        dimension="completeness",
        threshold=1.0,
        detail="NT7: một cảnh báo dưới ba yếu tố thì chuyên viên không có gì để rà.",
        total_sql="SELECT count(*) FROM alert",
        failed_sql="""SELECT count(*) FROM alert a
                       WHERE (SELECT count(*) FROM alert_reason r WHERE r.alert_id = a.alert_id) < 3""",
    ),
    Check(
        check_id="DQ-ALERT-TYPOLOGY",
        dataset="alert",
        name="Cảnh báo đã gán nhóm hành vi",
        dimension="consistency",
        threshold=1.0,
        detail="Không có nhóm hành vi thì cảnh báo không nối được vào quy trình xử lý nào.",
        total_sql="SELECT count(*) FROM alert",
        failed_sql="""SELECT count(*) FROM alert a
                       WHERE NOT EXISTS (SELECT 1 FROM alert_typology_match m
                                          WHERE m.alert_id = a.alert_id)""",
    ),
    Check(
        check_id="DQ-ALERT-ACCOUNT",
        dataset="alert",
        name="Cảnh báo trỏ tới tài khoản có thật",
        dimension="consistency",
        threshold=1.0,
        detail="Cảnh báo mồ côi không mở được hồ sơ và không điều tra được.",
        total_sql="SELECT count(*) FROM alert",
        failed_sql="""SELECT count(*) FROM alert a
                       WHERE NOT EXISTS (SELECT 1 FROM account c WHERE c.account_key = a.account_key)""",
    ),
    Check(
        check_id="DQ-DETECTION-THRESHOLD",
        dataset="detection_result",
        name="Cờ kích hoạt khớp ngưỡng đã ghi",
        dimension="accuracy",
        threshold=1.0,
        detail="triggered phải luôn bằng (score >= threshold); lệch nghĩa là kết quả đã bị sửa sau khi chấm.",
        total_sql="SELECT count(*) FROM detection_result",
        failed_sql="SELECT count(*) FROM detection_result WHERE triggered <> (score >= threshold)",
    ),
    Check(
        check_id="DQ-GRAPH-EVIDENCE",
        dataset="graph_detector_evidence",
        name="Bằng chứng đồ thị gắn được vào tài khoản",
        dimension="consistency",
        threshold=1.0,
        detail="Bằng chứng trỏ tới tài khoản không tồn tại thì tác tử đọc được nhưng không dùng được.",
        total_sql="SELECT count(*) FROM graph_detector_evidence",
        failed_sql="""SELECT count(*) FROM graph_detector_evidence g
                       WHERE NOT EXISTS (SELECT 1 FROM account c WHERE c.account_key = g.account_key)""",
    ),
)


def _status(pass_rate: float, threshold: float) -> str:
    if pass_rate >= threshold:
        return "pass"
    if pass_rate >= _WARN_BAND * threshold:
        return "warn"
    return "fail"


def run_checks(session: Session) -> int:
    session.execute(text("DELETE FROM data_quality_check"))
    for check in CHECKS:
        total = int(session.execute(text(check.total_sql)).scalar_one())
        failed = int(session.execute(text(check.failed_sql)).scalar_one())
        # Bảng rỗng thì coi là đạt: không có dòng nào hỏng. Nói "0% đạt" ở đây
        # là báo động giả — thứ đáng báo là bảng rỗng, và các phép kiểm khác
        # đã nói điều đó rõ hơn.
        pass_rate = 1.0 if total == 0 else (total - failed) / total
        session.execute(
            text(
                """INSERT INTO data_quality_check(check_id, dataset, check_name, dimension,
                                                  pass_rate, threshold, rows_checked, rows_failed,
                                                  status, detail)
                   VALUES (:id, :dataset, :name, :dimension, :rate, :threshold,
                           :total, :failed, :status, :detail)"""
            ),
            {
                "id": check.check_id,
                "dataset": check.dataset,
                "name": check.name,
                "dimension": check.dimension,
                "rate": round(pass_rate, 8),
                "threshold": check.threshold,
                "total": total,
                "failed": failed,
                "status": _status(pass_rate, check.threshold),
                "detail": check.detail,
            },
        )
        logger.info("%-24s %10d dòng, %6d hỏng, đạt %.4f", check.check_id, total, failed, pass_rate)
    return len(CHECKS)


# ---------------------------------------------------------------------
# Giám sát mô hình
# ---------------------------------------------------------------------

#: Mười khoang đều nhau trên [0, 1]. Điểm mô hình đã bị ràng buộc trong khoảng
#: này ở tầng cơ sở dữ liệu nên không cần khoang tràn hai đầu.
_BINS = 10

#: Ngưỡng PSI quen dùng trong ngành: dưới 0,1 coi như không đổi; 0,1–0,25 là
#: đáng theo dõi; trên 0,25 là phân phối đã lệch đủ để xem lại mô hình.
_PSI_WATCH = 0.10
_PSI_DEGRADED = 0.25

#: Dưới ngần này giao dịch, một tuần không đủ để kết luận mô hình đã xuống cấp.
#:
#: LI-Small kết thúc giữa tuần nên tuần cuối chỉ có vài chục dòng, và PSI của nó
#: vọt lên hàng đơn vị. Con số ấy đúng về mặt số học nhưng sai về mặt kết luận:
#: nó đo cái đuôi cụt của bộ dữ liệu, không đo mô hình. Vẫn ghi PSI xuống để ai
#: cần thì thấy, nhưng không cho phép nó bật cờ đỏ — một bảng điều khiển kêu
#: nhầm vài lần là một bảng điều khiển không ai còn đọc.
_MIN_WEEK_ROWS = 1_000

_WEEKLY_SQL = """
    SELECT date_trunc('week', t.occurred_at) AS week,
           width_bucket(s.model_score, 0, 1, :bins) AS bucket,
           count(*)                                 AS rows,
           avg(s.model_score)                       AS mean_score,
           count(*) FILTER (WHERE s.triggered)      AS triggered
      FROM transaction_model_score s
      JOIN transaction t ON t.transaction_id = s.transaction_id
     WHERE s.release_id = :release_id
     GROUP BY 1, 2
     ORDER BY 1, 2
"""


def _psi(actual: list[float], reference: list[float]) -> float:
    """Population Stability Index giữa hai phân phối đã chuẩn hoá.

    Khoang rỗng được thay bằng một giá trị sàn thay vì bỏ qua: bỏ qua sẽ khiến
    một khoang biến mất hoàn toàn — dấu hiệu trôi mạnh nhất — lại không đóng góp
    gì vào điểm số.
    """
    floor = 1e-6
    total = 0.0
    for a, r in zip(actual, reference, strict=True):
        a = max(a, floor)
        r = max(r, floor)
        total += (a - r) * math.log(a / r)
    return total


def _distribution(buckets: dict[int, int]) -> list[float]:
    total = sum(buckets.values()) or 1
    return [buckets.get(i, 0) / total for i in range(1, _BINS + 1)]


def run_monitor(session: Session) -> int:
    release = (
        session.execute(text("SELECT release_id FROM edge_model_release WHERE status = 'active' LIMIT 1"))
        .scalars()
        .first()
    )
    if release is None:
        logger.warning("Chưa có release nào đang hoạt động — bỏ qua phần giám sát mô hình")
        return 0

    rows = session.execute(text(_WEEKLY_SQL), {"bins": _BINS, "release_id": release}).mappings().all()
    if not rows:
        logger.warning("Release %s chưa có điểm nào — bỏ qua", release)
        return 0

    weeks: dict[Any, dict[str, Any]] = {}
    for row in rows:
        week = weeks.setdefault(row["week"], {"buckets": {}, "rows": 0, "triggered": 0, "score_sum": 0.0})
        week["buckets"][int(row["bucket"])] = int(row["rows"])
        week["rows"] += int(row["rows"])
        week["triggered"] += int(row["triggered"])
        week["score_sum"] += float(row["mean_score"]) * int(row["rows"])

    ordered = sorted(weeks.items())
    reference = _distribution(ordered[0][1]["buckets"])

    session.execute(text("DELETE FROM model_monitor_metric WHERE release_id = :r"), {"r": release})
    written = 0
    for index, (week, data) in enumerate(ordered):
        psi = None if index == 0 else _psi(_distribution(data["buckets"]), reference)
        status = "healthy"
        if psi is not None:
            status = "degraded" if psi >= _PSI_DEGRADED else "watch" if psi >= _PSI_WATCH else "healthy"
            if data["rows"] < _MIN_WEEK_ROWS and status == "degraded":
                status = "watch"
                logger.info("  tuần %s chỉ có %d dòng — hạ mức xuống 'watch'", week.date(), data["rows"])

        metrics = {
            "psi_score": psi,
            "alert_rate": data["triggered"] / data["rows"],
            "mean_score": data["score_sum"] / data["rows"],
            "scored_rows": float(data["rows"]),
        }
        for name, value in metrics.items():
            if value is None:
                continue
            session.execute(
                text(
                    """INSERT INTO model_monitor_metric(release_id, observed_at, metric_name,
                                                        metric_value, drift_score, status)
                       VALUES (:release, :at, :name, :value, :drift, :status)"""
                ),
                {
                    "release": release,
                    "at": week,
                    "name": name,
                    "value": value,
                    # Điểm trôi gắn cho *cả tuần*, không riêng một chỉ số; lặp
                    # lại ở mỗi dòng để giao diện tô màu được mà không phải join.
                    "drift": psi,
                    "status": status,
                },
            )
            written += 1
        logger.info(
            "%s  psi=%s  alert_rate=%.6f  n=%d",
            week.date(),
            f"{psi:.4f}" if psi else "—",
            metrics["alert_rate"],
            data["rows"],
        )
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-monitor", action="store_true", help="Chỉ chạy phần chất lượng dữ liệu")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with get_session() as session:
        checks = run_checks(session)
        monitor = 0 if args.skip_monitor else run_monitor(session)
    logger.info("Xong: %d phép kiểm, %d dòng giám sát", checks, monitor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
