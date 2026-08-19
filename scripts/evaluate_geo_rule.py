#!/usr/bin/env python3
"""Chấm điểm bộ luật địa lý theo nhãn đối chứng của SAML-D.

    python scripts/evaluate_geo_rule.py

Một ô ``(tài khoản, ngày)`` được tính là DƯƠNG nếu bất kỳ giao dịch nào của tài
khoản ấy trong cửa sổ nhìn lại mang nhãn rửa tiền. Đây là định nghĩa mức tài
khoản, khớp với cách nhánh MEGA-PNA chấm, nên hai nhánh so được với nhau.

Báo cáo theo NGÂN SÁCH chứ không chỉ một ngưỡng: câu hỏi vận hành là "rà N vụ
mỗi kỳ thì bắt được bao nhiêu", và dãy ngân sách là dãy dùng chung cho mọi
nhánh của dự án.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc  # noqa: UP017
BUDGETS = (100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument("--out", type=Path, default=ROOT / "reports/geo-rule/saml_d_v1.json")
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


TRUTH_SQL = """
DROP TABLE IF EXISTS geo_cell_truth;
CREATE TABLE geo_cell_truth AS
SELECT c.account_key, c.as_of, c.score,
       COALESCE(max(l.is_laundering), 0) AS y,
       -- Phạm vi và mục tiêu của nhánh này là XUYÊN BIÊN GIỚI.
       --
       -- `y` tính mọi giao dịch dương trong cửa sổ, kể cả giao dịch nội địa mà
       -- nhánh này không có nhiệm vụ bắt — chấm bằng nó là bắt bộ luật chịu
       -- trách nhiệm cho việc của nhánh khác. Cấu trúc đồ thị đã do MEGA-PNA
       -- đảm nhiệm trên bộ IBM. `y_xb` mới là mục tiêu thật của nhánh này.
       max(CASE WHEN t.from_country <> t.to_country THEN 1 ELSE 0 END) AS co_xb,
       max(CASE WHEN t.from_country <> t.to_country
                 AND l.is_laundering = 1 THEN 1 ELSE 0 END) AS y_xb
FROM geo_cell c
LEFT JOIN transaction t
       ON t.from_account_key = c.account_key
      AND t.source_dataset = 'SAML-D'
      AND (t.occurred_at AT TIME ZONE 'UTC')::date <= c.as_of
      AND (t.occurred_at AT TIME ZONE 'UTC')::date > c.as_of - {window}
LEFT JOIN label.saml_d_truth l ON l.source_line_number = t.source_line_number
GROUP BY 1, 2, 3;
CREATE INDEX geo_cell_truth_score_idx ON geo_cell_truth (score DESC, account_key, as_of);
"""


def main() -> int:
    args = parse_args()
    print("gắn nhãn đối chứng cho lưới điểm…")
    sql(args, TRUTH_SQL.format(window=args.window_days))

    all_cells = int(sql(args, "SELECT count(*) FROM geo_cell_truth"))
    cells = int(sql(args, "SELECT count(*) FROM geo_cell_truth WHERE co_xb = 1"))
    positives = int(sql(args, "SELECT sum(y_xb) FROM geo_cell_truth"))
    print(f"lưới test: {all_cells:,} ô, trong đó {cells:,} ô có giao dịch xuyên biên giới")
    print(f"mục tiêu : {positives:,} ô có giao dịch xuyên biên giới bị gắn nhãn ({100 * positives / cells:.3f}%)")

    rows = []
    print(f"\n{'ngân sách':>10} {'bắt đúng':>9} {'precision':>10} {'recall':>8} {'nâng':>7}")
    base = positives / cells
    for budget in BUDGETS:
        if budget > cells:
            continue
        caught = int(
            sql(
                args,
                f"""SELECT COALESCE(sum(y_xb), 0) FROM (
                    SELECT y_xb FROM geo_cell_truth WHERE co_xb = 1
                    ORDER BY score DESC, account_key, as_of LIMIT {budget}) s""",
            )
        )
        precision = caught / budget
        recall = caught / positives if positives else 0.0
        rows.append(
            {
                "alerts": budget,
                "caught": caught,
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "lift": round(precision / base, 3) if base else None,
            }
        )
        print(f"{budget:>10,} {caught:>9,} {precision:>10.4f} {recall:>8.4f} {precision / base:>7.2f}×")

    corridors = sql(
        args,
        """SELECT key || '|' || round(lift, 3) || '|' || n
                             FROM geo_weight WHERE kind='corridor' ORDER BY lift DESC LIMIT 10""",
    )
    report = {
        "schema_version": "fin07.geo_rule.benchmark.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": "SAML-D",
        "detector": "geo_rule",
        "unit": "account_window_cross_border",
        "window_days": args.window_days,
        "note": (
            "Bộ luật, không huấn luyện. Trọng số hành lang và hình thức thanh toán đo trên "
            "train+validation rồi áp nguyên lên test. Laundering_type chỉ dùng làm nhãn đối "
            "chứng — nó trùng khớp hoàn toàn với nhãn nên đưa vào đặc trưng là rò rỉ đáp án."
        ),
        "test_cells_all": all_cells,
        "test_cells_cross_border": cells,
        "test_positive_cells_cross_border": positives,
        "test_positive_rate_cross_border": round(positives / cells, 6),
        "operational_budget": rows,
        "top_corridors": [
            {"corridor": part.split("|")[0], "lift": float(part.split("|")[1]), "n": int(part.split("|")[2])}
            for part in corridors.splitlines()
            if part.strip()
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nđã ghi {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
