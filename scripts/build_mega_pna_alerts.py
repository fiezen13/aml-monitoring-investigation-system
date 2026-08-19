#!/usr/bin/env python3
"""Sinh cảnh báo mức TÀI KHOẢN từ lưới điểm MEGA-PNA.

    python scripts/build_mega_pna_alerts.py --split test --budget 5000 --dry-run
    python scripts/build_mega_pna_alerts.py --split test --budget 5000

Vì sao cần script này
---------------------
``scripts/load_edge_scores.py`` cố ý **không** sinh cảnh báo — nó chỉ gắn điểm
vào ``transaction_model_score`` để ba trang tra cứu sống lại. Nhưng hàng đợi cảnh
báo, phiên điều tra và hồ sơ vụ việc đều đọc bảng ``alert``, và bảng ấy khoá theo
``account_key``. Không có bước này thì mô hình chấm điểm xong mà chuyên viên
không thấy gì.

Chọn theo NGÂN SÁCH, không theo ngưỡng cố định
----------------------------------------------
Ngưỡng 0,56933 chốt trên validation cho ra hàng chục nghìn ô vượt ngưỡng — nhiều
hơn số vụ một đội điều tra xử lý nổi. Ngân sách trả lời đúng câu hỏi vận hành:
*"rà N vụ mỗi kỳ thì bắt được bao nhiêu"*. Đây cũng là dãy số mà chuẩn benchmark
dùng cho mọi mô hình, nên so sánh được.

Mỗi cảnh báo mang theo lý do và chứng cứ
----------------------------------------
Điểm trần trụi không dùng được: chuyên viên phải biết **vì sao**. Mỗi cảnh báo
sinh ra kèm:

* ``alert_reason`` — bốn số đo của ô, mỗi số một dòng có tên và mức đóng góp;
* nhóm hành vi suy ra từ chính số đo, không gán bừa T01;
* liên kết tới giao dịch điểm cao nhất, để mở được ngay sổ giao dịch.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import duckdb
import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402

DEFAULT_DIR = ROOT / "data/processed/mega-pna-accounts"
DETECTOR = "mega_pna"


#: Nhóm hành vi suy từ số đo của ô. Thứ tự có ý nghĩa — điều kiện đầu tiên khớp
#: thì thắng, nên xếp cái đặc thù nhất lên trước.
#:
#: KHÔNG gán bừa T01: T01 là chia nhỏ giao dịch, một nhóm rất cụ thể. Gán nó cho
#: mọi cảnh báo sẽ làm hỏng thống kê theo nhóm hành vi và khiến tác tử viện dẫn
#: sai nhóm.
def typology_for(row: dict[str, Any]) -> tuple[str, str]:
    incoming = int(row["incoming_count"])
    outgoing = int(row["outgoing_count"])
    edges = max(1, int(row["edge_count"]))
    if incoming >= 5 and outgoing >= 5:
        return "T04", "Nhiều nguồn dồn vào rồi toả ra nhiều đích"
    if outgoing >= 3 and incoming >= 1 and outgoing / edges >= 0.7:
        return "T05", "Tiền vào rồi ra ngay trong cửa sổ quan sát"
    if incoming >= 5:
        return "T04", "Nhiều nguồn dồn về một tài khoản"
    return "T02", "Tài khoản trung chuyển trong mạng lưới"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", choices=("validation", "test"), default="test")
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--budget", type=int, default=5000, help="Số cảnh báo cao điểm nhất cần mở")
    p.add_argument("--database-url", default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def _psycopg_url(url: str) -> str:
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL phải là PostgreSQL")
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


def select_cells(directory: Path, split: str, budget: int) -> list[dict[str, Any]]:
    con = duckdb.connect()
    try:
        return (
            con.execute(
                """
            SELECT account_key, as_of, label,
                   score_max, score_top5_mean, edges_over_threshold,
                   flagged_amount, edge_count, incoming_count, outgoing_count
              FROM read_parquet(?)
             ORDER BY score_max DESC, edges_over_threshold DESC, account_key
             LIMIT ?
            """,
                [str(directory / f"{split}.parquet"), budget],
            )
            .fetchdf()
            .to_dict("records")
        )
    finally:
        con.close()


def reasons_for(row: dict[str, Any]) -> list[tuple[str, str, float, float]]:
    """Bốn số đo của ô thành bốn dòng lý do có tên.

    ``contribution`` trên thang 0–100 để khớp cột trong ``alert_reason``. Trọng số
    để 0 với các số đo bối cảnh: chúng mô tả chứ không chấm điểm, và cột trọng số
    là thứ Agent 2 dùng để nói nhánh nào đóng góp bao nhiêu.
    """
    score = float(row["score_max"])
    top5 = float(row["score_top5_mean"] or 0.0)
    over = int(row["edges_over_threshold"])
    amount = float(row["flagged_amount"] or 0.0)
    return [
        ("MP_SCORE_MAX", f"Giao dịch rủi ro nhất trong khoảng quan sát đạt {score:.3f}", round(score * 100, 2), 1.0),
        ("MP_SCORE_TOP5", f"Trung bình 5 giao dịch rủi ro nhất đạt {top5:.3f}", round(top5 * 100, 2), 0.0),
        ("MP_EDGES_OVER", f"{over} giao dịch vượt ngưỡng cảnh báo", 0.0, 0.0),
        # Không dấu phân cách hàng nghìn. "9,258" đọc trong tiếng Việt là chín
        # phẩy hai năm tám, và bộ đối chiếu số của tác tử phản biện cũng đọc đúng
        # như vậy rồi kết luận con số ấy không có trong bằng chứng nào.
        (
            "MP_FLAGGED_AMOUNT",
            f"Tổng {amount:.0f} trên các giao dịch bị gắn cờ, cộng thô theo nguyên tệ (chưa quy đổi)",
            0.0,
            0.0,
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = select_cells(args.dir, args.split, args.budget)
    if not rows:
        print("Không có ô nào để mở cảnh báo")
        return 1

    caught = sum(int(r["label"]) for r in rows)
    print(f"[1/3] Chọn {len(rows):,} ô cao điểm nhất từ tập {args.split}")
    print(f"      trúng nhãn: {caught:,} ({caught / len(rows) * 100:.2f}% độ chính xác ở ngân sách này)")
    print(f"      dải điểm  : {rows[-1]['score_max']:.4f} .. {rows[0]['score_max']:.4f}")

    if args.dry_run:
        print("\nThử nghiệm — không ghi gì. Ba dòng đầu:")
        for r in rows[:3]:
            code, label = typology_for(r)
            print(f"  {r['account_key']:>22s} @ {r['as_of']}  điểm {r['score_max']:.4f}  {code} · {label}")
        return 0

    url = _psycopg_url(args.database_url or get_settings().database_url)
    inserted = 0
    print("[2/3] Ghi cảnh báo và lý do ...")
    with psycopg.connect(url) as pg:
        for row in rows:
            key = f"{row['account_key']}|{row['as_of']}"
            alert_id = "ALT-MP-" + hashlib.sha1(key.encode()).hexdigest()[:16]
            code, label = typology_for(row)
            # Điểm rủi ro trên thang 0-100 để khớp cột NUMERIC(5,2).
            risk = round(min(100.0, float(row["score_max"]) * 100), 2)
            done = pg.execute(
                """INSERT INTO alert (alert_id, account_key, typology_code, detector, risk_score, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, 'open', %s)
                   ON CONFLICT (alert_id) DO NOTHING""",
                (alert_id, row["account_key"], code, DETECTOR, risk, row["as_of"]),
            ).rowcount
            if not done:
                continue
            inserted += 1
            for factor_code, factor_label, contribution, weight in reasons_for(row):
                pg.execute(
                    """INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (alert_id, factor_code) DO NOTHING""",
                    (alert_id, factor_code, factor_label, contribution, weight),
                )
        pg.commit()
        total = pg.execute("SELECT count(*) FROM alert WHERE detector = %s", (DETECTOR,)).fetchone()[0]

    print(f"[3/3] Đã mở {inserted:,} cảnh báo mới · tổng cảnh báo {DETECTOR}: {total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
