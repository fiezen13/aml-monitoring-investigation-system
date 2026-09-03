#!/usr/bin/env python3
"""Sinh cảnh báo T03 (giao dịch vòng) từ chu trình bộ dò đã tìm được.

    python scripts/build_cycle_alerts.py --dry-run
    python scripts/build_cycle_alerts.py --budget 2000

Vì sao cần script này
---------------------
Bộ dò chu trình đã chạy ở quy mô thật (``reports/graph-detector/cycle_v1.json``:
15.513 chu trình trên lõi 5.458.781 cạnh), và ``scripts/write_cycle_evidence.py``
đã ghi kết quả vào ``graph_detector_evidence``. Nhưng bảng ấy chỉ được đọc bởi
công cụ ``GetGraphEvidence`` KHI đã có phiên điều tra — nó không tự sinh cảnh
báo. Hệ quả đo được trên bản đang phục vụ: 14.267 cảnh báo, **không một cảnh báo
T03 nào**, dù mã dò, kiểm thử và báo cáo đánh giá đều đã có.

Script này là mắt xích còn thiếu: bằng chứng chu trình → hàng đợi của chuyên viên.

Chấm điểm theo cái gì
---------------------
Bộ dò không trả về điểm — nó trả về "có chu trình hay không". Ba số đo dưới đây
là thứ QUAN SÁT ĐƯỢC từ chính chu trình, không phải trọng số đặt tay:

* **Tốc độ khép vòng** — tiền quay về càng nhanh càng đáng ngờ.
* **Số chu trình đi qua tài khoản** — nằm trên một vòng có thể là trùng hợp;
  nằm trên nhiều vòng thì không.
* **Độ ngắn của vòng** — vòng 2 chặng là quan hệ khép kín trực tiếp; vòng dài
  có thể là dòng tiền thương mại bình thường đi vòng.

Tốc độ dùng PHÂN VỊ THỰC NGHIỆM trong chính lô đang chấm, không phải một mốc
giờ đặt cứng. Bản đầu tiên đặt "nhanh tối đa = 6 giờ" rồi đo lại trên dữ liệu
thật: trung vị đúng bằng 6,01 giờ và giá trị lớn nhất chỉ 28,98 giờ — mốc cứng
ấy làm phẳng đúng nửa dưới, cho 15 cảnh báo đầu hàng đợi cùng một điểm 0,760.
Phân vị thì tự hiệu chuẩn theo dữ liệu có thật, nên luôn phân biệt được.

Hai số đo còn lại HIỆN KHÔNG BIẾN THIÊN trên bằng chứng đang có: cả 72 tài
khoản đều nằm trên đúng một vòng, và 71/72 vòng dài 2 chặng. Giữ chúng lại với
trọng số nhỏ để khi bộ dò chạy ở dải độ dài rộng hơn thì chúng có tác dụng
ngay — nhưng nói thẳng ở đây rằng lúc này chúng không đóng góp gì, thay vì để
người đọc tưởng điểm số cân ba yếu tố.

Điểm thô CHỈ dùng để xếp hạng — ``risk_score`` cuối cùng đi theo THỨ HẠNG,
giống nhánh luật địa lý, vì để nhiều cảnh báo cùng điểm 100 thì hàng đợi mất
thứ tự ưu tiên.

Không bịa nhãn
--------------
``HI-Medium_Patterns.txt`` của IBM là đáp án dùng để chấm điểm. Script này chỉ
đọc ``graph_detector_evidence`` — thứ bộ dò tự tìm ra. Recall của bộ dò là
0,2273 và 6.234 đỉnh đã bị bỏ vì quá dày; cảnh báo sinh ra ở đây thừa hưởng
đúng giới hạn đó, không hơn.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402

DETECTOR = "graph"
TYPOLOGY = "T03"
DATASET = "ibm_hi_medium"

#: Trọng số ba số đo. Tổng bằng 1 để điểm thô nằm trong [0,1]. Tốc độ nặng nhất
#: vì nó là số đo duy nhất hiện có biến thiên — xem phần "Chấm điểm theo cái gì".
W_SPEED, W_COUNT, W_SHORT = 0.7, 0.2, 0.1

#: Số vòng bão hoà ở đây: nằm trên 5 vòng đã đủ nói lên vấn đề, hơn nữa không
#: thêm thông tin và sẽ để một tài khoản chiếm trọn đầu hàng đợi.
COUNT_SATURATION = 5

#: Vòng dài từ ngần này chặng trở lên thì coi như không còn là tín hiệu "khép
#: kín trực tiếp". Bộ dò `graph_cycle_v1` phát hiện độ dài 2–6.
LONG_CYCLE_HOPS = 6


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--budget", type=int, default=2000, help="số cảnh báo tối đa mở ra")
    p.add_argument("--dry-run", action="store_true")
    # Đi theo DATABASE_URL, KHÔNG phải `docker exec psql` vào container local.
    #
    # Trên máy chủ đang phục vụ có một container `fin07-postgres-1` mang database
    # `fin07_hi_medium` — và nó RỖNG (0 giao dịch, 0 cảnh báo). API đọc Cloud SQL.
    # Vài script nạp cũ mặc định trỏ vào container ấy; chạy theo chúng thì lệnh
    # kết thúc, in ra thành công, và không có gì đổi trên hàng đợi thật.
    p.add_argument("--database-url", default=None, help="mặc định lấy từ DATABASE_URL")
    return p.parse_args(argv)


def _psycopg_url(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL phải trỏ tới PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def connect(args: argparse.Namespace) -> psycopg.Connection:
    return psycopg.connect(_psycopg_url(args.database_url or get_settings().database_url))


def sql(conn: psycopg.Connection, statement: str) -> str:
    """Chạy câu lệnh; trả các ô của cột đầu, mỗi dòng một ô."""
    with conn.cursor() as cur:
        cur.execute(statement)  # type: ignore[arg-type]
        if cur.description is None:
            return ""
        return "\n".join(str(r[0]) for r in cur.fetchall())


def alert_id(account_key: str, as_of: str) -> str:
    digest = hashlib.sha256(f"cycle|{account_key}|{as_of}".encode()).hexdigest()[:16]
    return f"ALT-CYC-{digest}"


#: Gom bằng chứng chu trình về mức (tài khoản, mốc mới nhất).
#:
#: Một tài khoản có thể nằm trên nhiều chu trình ở nhiều mốc khác nhau. Chuyên
#: viên cần MỘT vụ cho tài khoản ấy, mang theo cả bức tranh, chứ không phải một
#: vụ cho mỗi vòng — nếu không thì một tài khoản nằm trên 12 vòng sẽ chiếm 12
#: dòng đầu hàng đợi và đẩy mọi tài khoản khác xuống.
CELL_SQL = """
DROP TABLE IF EXISTS cycle_cell;
CREATE TEMP TABLE cycle_cell AS
WITH ev AS (
    SELECT account_key,
           as_of_time,
           (payload ->> 'cycle_length')::int          AS cycle_length,
           (payload ->> 'duration_hours')::numeric    AS duration_hours,
           payload -> 'edges'                         AS edges
    FROM graph_detector_evidence
    WHERE pattern = 'CYCLE'
),
agg AS (
    SELECT account_key,
           max(as_of_time)                       AS as_of,
           count(*)                              AS cycle_count,
           min(cycle_length)                     AS len_min,
           max(cycle_length)                     AS len_max,
           min(duration_hours)                   AS hours_min,
           sum(jsonb_array_length(edges))        AS edge_total
    FROM ev
    GROUP BY account_key
)
SELECT a.*,
       -- Phân vị thực nghiệm TRONG LÔ: vòng khép nhanh nhất = 1,0, chậm nhất = 0,0.
       -- Tự hiệu chuẩn nên không phụ thuộc thang giờ của lần chạy nào.
       percent_rank() OVER (ORDER BY a.hours_min DESC)::numeric              AS s_speed,
       -- Một vòng = 0; bão hoà ở COUNT_SATURATION vòng.
       LEAST(1.0, (a.cycle_count - 1)::numeric / {count_sat})                AS s_count,
       -- Vòng 2 chặng = 1,0; từ LONG_CYCLE_HOPS chặng trở lên = 0.
       GREATEST(0.0, LEAST(1.0,
           ({long_hops} - a.len_min)::numeric / ({long_hops} - 2)))          AS s_short
FROM agg a;

ALTER TABLE cycle_cell ADD COLUMN score numeric;
UPDATE cycle_cell SET score =
    {w_speed} * s_speed + {w_count} * s_count + {w_short} * s_short;
"""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    conn = connect(args)
    conn.autocommit = False

    have = sql(conn, "SELECT count(*) FROM graph_detector_evidence WHERE pattern='CYCLE'")
    if have == "0":
        print(
            "graph_detector_evidence chưa có dòng CYCLE nào.\n"
            "Chạy trước: scripts/detect_cycles_core.py rồi scripts/write_cycle_evidence.py",
            file=sys.stderr,
        )
        return 1
    print(f"[1/4] {int(have):,} dòng bằng chứng CYCLE trong kho")

    sql(
        conn,
        CELL_SQL.format(
            count_sat=COUNT_SATURATION,
            long_hops=LONG_CYCLE_HOPS,
            w_speed=W_SPEED,
            w_count=W_COUNT,
            w_short=W_SHORT,
        ),  # fmt: skip
    )
    cells = int(sql(conn, "SELECT count(*) FROM cycle_cell"))
    print(f"[2/4] Gom về {cells:,} tài khoản nằm trên ít nhất một chu trình")

    if args.dry_run:
        print(
            sql(
                conn,
                """SELECT account_key || '  ' || cycle_count || ' vòng  ngắn nhất '
                          || len_min || ' chặng  khép sau ' || round(hours_min, 1)
                          || 'h  điểm ' || round(score, 3)
                   FROM cycle_cell ORDER BY score DESC LIMIT 15""",
            )
        )
        print("(dry-run — không ghi cảnh báo)")
        conn.rollback()
        return 0

    # Xoá lý do trước, rồi chỉ xoá cảnh báo CHƯA có phiên điều tra nào trỏ vào.
    # Cảnh báo đã điều tra được giữ và cập nhật tại chỗ qua ON CONFLICT: lịch sử
    # điều tra là bằng chứng, không phải thứ dọn đi cho tiện.
    sql(
        conn,
        f"""DELETE FROM alert_reason WHERE alert_id IN
            (SELECT alert_id FROM alert WHERE detector='{DETECTOR}' AND typology_code='{TYPOLOGY}')""",
    )
    sql(
        conn,
        f"""DELETE FROM alert WHERE detector='{DETECTOR}' AND typology_code='{TYPOLOGY}'
            AND alert_id NOT IN (SELECT alert_id FROM investigation)""",
    )

    # risk_score đi theo THỨ HẠNG, trải 100 → 60 trên ngân sách, giống nhánh địa lý.
    sql(
        conn,
        f"""
        WITH top AS (
            SELECT *, row_number() OVER (ORDER BY score DESC, account_key, as_of) AS rnk
            FROM cycle_cell ORDER BY score DESC, account_key, as_of LIMIT {args.budget}
        )
        INSERT INTO alert (alert_id, account_key, typology_code, detector,
                           risk_score, status, created_at, dataset)
        SELECT 'ALT-CYC-' || substr(md5('cycle|' || account_key || '|' || as_of), 1, 16),
               account_key, '{TYPOLOGY}', '{DETECTOR}',
               round((100.0 - 40.0 * (rnk - 1)::numeric / {args.budget})::numeric, 2),
               'open', as_of, '{DATASET}'
        FROM top
        ON CONFLICT (alert_id) DO UPDATE
           SET risk_score = EXCLUDED.risk_score, typology_code = EXCLUDED.typology_code
        """,
    )
    made = int(sql(conn, f"SELECT count(*) FROM alert WHERE detector='{DETECTOR}' AND typology_code='{TYPOLOGY}'"))
    print(f"[3/4] {made:,} cảnh báo T03 trong hàng đợi")

    # Bốn dòng lý do. NT7 đòi tối thiểu ba yếu tố có giá trị số.
    #
    # Dấu tách nghìn là DẤU CÁCH MẢNH (U+202F), không phải dấu phẩy: "9,258" đọc
    # trong tiếng Việt là chín phẩy hai năm tám, và bộ đối chiếu số của tác tử
    # phản biện cũng đọc như vậy. Không viết "X/100" — bộ kiểm chứng rút mọi chữ
    # số trong câu rồi đòi bằng chứng cho từng số, kể cả mẫu số.
    sql(
        conn,
        f"""
        WITH a AS (
            SELECT al.alert_id, c.*
            FROM alert al JOIN cycle_cell c ON c.account_key = al.account_key
            WHERE al.detector='{DETECTOR}' AND al.typology_code='{TYPOLOGY}'
        )
        INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
        SELECT alert_id, 'CYC_SPEED',
               'Tiền quay về tài khoản sau ' || round(hours_min, 1) || ' giờ',
               round(100.0 * s_speed, 2), {W_SPEED} FROM a
        UNION ALL
        SELECT alert_id, 'CYC_COUNT',
               cycle_count || ' chu trình dòng tiền khép kín đi qua tài khoản này',
               round(100.0 * s_count, 2), {W_COUNT} FROM a
        UNION ALL
        SELECT alert_id, 'CYC_SHORT',
               'Chu trình ngắn nhất đi qua ' || len_min || ' tài khoản rồi quay lại',
               round(100.0 * s_short, 2), {W_SHORT} FROM a
        UNION ALL
        SELECT alert_id, 'CYC_EDGES',
               replace(to_char(edge_total, 'FM999G999G999'), ',', U&'\\202F')
               || ' giao dịch tạo nên các chu trình này',
               0.00, 0.00 FROM a
        ON CONFLICT (alert_id, factor_code) DO NOTHING
        """,
    )
    n = sql(
        conn,
        f"""SELECT count(*) FROM alert_reason r JOIN alert al USING (alert_id)
                      WHERE al.detector='{DETECTOR}' AND al.typology_code='{TYPOLOGY}'""",
    )
    print(f"[4/4] {int(n):,} dòng lý do (mỗi cảnh báo 4 yếu tố)")
    conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
