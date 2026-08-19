#!/usr/bin/env python3
"""Bộ luật địa lý trên SAML-D — nhánh World Monitor.

    python scripts/build_geo_rule_alerts.py --dry-run
    python scripts/build_geo_rule_alerts.py --budget 5000

Vì sao là luật chứ không phải mô hình
-------------------------------------
SAML-D mang sẵn ``Laundering_type``, và cột ấy TRÙNG KHỚP HOÀN TOÀN với nhãn:
mọi giá trị ``Normal_*`` đều là 0, mọi giá trị còn lại đều là 1. Đưa nó vào đặc
trưng thì mô hình đọc được đáp án — đó là lý do bản notebook tham khảo báo
AUC = 1,0. Ở đây nó chỉ được dùng làm nhãn đối chứng khi chấm điểm.

Phần còn lại của bộ dữ liệu không có đặc trưng nào đủ mạnh để một mô hình vượt
được luật: đo trên mức tài khoản-ngày, tín hiệu mạnh nhất là hành lang quốc gia
với mức nâng 6,3 lần. Luật đọc được, giải thích được, và không cần GPU.

Trọng số lấy từ dữ liệu, không đặt tay
--------------------------------------
Mức rủi ro của mỗi hành lang và mỗi hình thức thanh toán được đo trên phần
TRAIN và VALIDATION, rồi áp nguyên lên TEST. Đo trên chính phần đem báo cáo là
tự chấm bài của mình.

Số tiền bị loại khỏi điểm
-------------------------
Tỉ lệ dương theo thập phân vị số tiền KHÔNG đơn điệu — thập phân vị 1 là
0,144%, thập phân vị 2 là 0,028%, thập phân vị 4 là 0,191%. Một số hạng theo
số tiền vì thế chỉ thêm nhiễu; bản thử đầu tiên có nó cho ra kết quả tệ hơn
chọn ngẫu nhiên.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATASET = "saml_d"
DETECTOR = "geo_rule"
TYPOLOGY = "T06"  # Liên quan vùng tài phán rủi ro cao — tín hiệu jurisdiction_signal
MIN_SUPPORT = 2000  # số giao dịch tối thiểu để một hành lang được tính trọng số
RISKY_LIFT = 4.4  # từ mức nâng này trở lên thì coi là hành lang rủi ro cao
K_CAP = 6  # gộp mọi ô từ 6 giao dịch hành lang rủi ro trở lên vào một nhóm
BUCKET_MIN = 200  # nhóm ít hơn ngần này ô thì tỉ lệ không đáng tin, bỏ qua

FACTORS = {
    "GEO_CORRIDOR": "Hành lang quốc gia rủi ro cao nhất trong cửa sổ",
    "GEO_COUNTRIES": "Số quốc gia đối tác khác nhau",
    "GEO_CASH": "Giao dịch tiền mặt",
    "GEO_FX": "Giao dịch có đổi loại tiền",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--budget", type=int, default=5000)
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
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


def alert_id(account_key: str, as_of: str) -> str:
    digest = hashlib.sha256(f"{DETECTOR}|{account_key}|{as_of}".encode()).hexdigest()[:16]
    return f"ALT-GEO-{digest}"


# Lưới điểm: mỗi ô là (tài khoản, ngày có phát sinh) với cửa sổ nhìn lại N ngày.
# Cùng đơn vị với nhánh MEGA-PNA, để hai nhánh so được với nhau.
CELLS_SQL = """
DROP TABLE IF EXISTS geo_weight;
CREATE TABLE geo_weight AS
WITH labelled AS (
    SELECT t.from_country, t.to_country, t.channel,
           (t.currency <> t.receiving_currency) AS fx,
           l.is_laundering
    FROM transaction t
    JOIN label.saml_d_truth l ON l.source_line_number = t.source_line_number
    WHERE t.source_dataset = 'SAML-D' AND t.dataset_split IN ('train', 'validation')
),
base AS (SELECT avg(is_laundering::numeric) AS rate FROM labelled)
SELECT 'corridor' AS kind,
       from_country || '→' || to_country AS key,
       count(*) AS n,
       avg(is_laundering::numeric) / (SELECT rate FROM base) AS lift
FROM labelled GROUP BY 1, 2 HAVING count(*) >= {min_support}
UNION ALL
SELECT 'channel', channel, count(*),
       avg(is_laundering::numeric) / (SELECT rate FROM base)
FROM labelled GROUP BY 1, 2 HAVING count(*) >= {min_support}
UNION ALL
SELECT 'fx', CASE WHEN fx THEN 'yes' ELSE 'no' END, count(*),
       avg(is_laundering::numeric) / (SELECT rate FROM base)
FROM labelled GROUP BY 1, 2 HAVING count(*) >= {min_support}
-- Hai dòng 'baseline' giữ MẪU SỐ, không phải mức nâng: cột ``lift`` ở đây là
-- tỉ lệ nhãn tuyệt đối. Không có chúng thì câu "gấp 5,1 lần mức nền" trên màn
-- hình không nói được mức nền là gì, và chuyên viên không kiểm chứng được.
-- 'all' là mẫu số dùng để chấm điểm; 'cross_border' là mẫu số so sánh đúng
-- cho một nhánh chỉ xét giao dịch xuyên biên giới. Bản giải thích nêu cả hai.
UNION ALL
SELECT 'baseline', 'all', count(*), avg(is_laundering::numeric) FROM labelled
UNION ALL
SELECT 'baseline', 'cross_border', count(*), avg(is_laundering::numeric)
FROM labelled WHERE from_country <> to_country;

DROP TABLE IF EXISTS geo_cell;
CREATE TABLE geo_cell AS
WITH days AS (
    SELECT DISTINCT from_account_key AS account_key, (occurred_at AT TIME ZONE 'UTC')::date AS as_of
    FROM transaction WHERE source_dataset = 'SAML-D' AND dataset_split = 'test'
),
win AS (
    SELECT d.account_key, d.as_of,
           t.to_country, t.channel, t.transaction_id, t.amount,
           (t.currency <> t.receiving_currency) AS fx,
           t.from_country || '→' || t.to_country AS corridor
    FROM days d
    JOIN transaction t
      ON t.from_account_key = d.account_key
     AND t.source_dataset = 'SAML-D'
     AND (t.occurred_at AT TIME ZONE 'UTC')::date <= d.as_of
     AND (t.occurred_at AT TIME ZONE 'UTC')::date > d.as_of - {window}
)
SELECT w.account_key, w.as_of,
       count(*) AS txn_count,
       count(DISTINCT w.to_country) AS country_count,
       sum(CASE WHEN w.channel IN ('Cash Deposit', 'Cash Withdrawal') THEN 1 ELSE 0 END) AS cash_count,
       sum(CASE WHEN w.fx THEN 1 ELSE 0 END) AS fx_count,
       max(COALESCE(cw.lift, 1.0)) AS corridor_lift,
       (array_agg(w.corridor ORDER BY COALESCE(cw.lift, 1.0) DESC, w.corridor))[1] AS top_corridor,
       max(COALESCE(ch.lift, 1.0)) AS channel_lift,
       (array_agg(w.transaction_id ORDER BY w.amount DESC))[1] AS top_transaction_id
FROM win w
LEFT JOIN geo_weight cw ON cw.kind = 'corridor' AND cw.key = w.corridor
LEFT JOIN geo_weight ch ON ch.kind = 'channel'  AND ch.key = w.channel
GROUP BY 1, 2;

-- Trọng số theo SỐ giao dịch trên hành lang rủi ro, đo trên train+validation.
--
-- Quan hệ này KHÔNG đơn điệu, và đó là lý do bản chấm đầu tiên cho kết quả kém.
-- Càng nhiều giao dịch trên hành lang rủi ro thì càng đáng ngờ — nhưng chỉ tới
-- một mức. Vượt qua mức ấy thì tài khoản là doanh nghiệp xuyên biên giới làm ăn
-- thật, và tỉ lệ dương rơi trở lại gần mức nền. Một thang điểm tăng đều theo
-- khối lượng sẽ đẩy đúng nhóm doanh nghiệp ấy lên đầu hàng đợi.
--
-- Trọng số lấy từ chính dữ liệu chứ không đặt tay, và lấy trên train+validation
-- rồi áp nguyên lên test — rút vùng đỉnh từ test là tự chấm bài của mình.
DROP TABLE IF EXISTS geo_bucket;
CREATE TABLE geo_bucket AS
WITH risky AS (SELECT key FROM geo_weight WHERE kind = 'corridor' AND lift >= {risky_lift}),
days AS (
    SELECT DISTINCT from_account_key AS account_key, (occurred_at AT TIME ZONE 'UTC')::date AS as_of
    FROM transaction
    WHERE source_dataset = 'SAML-D' AND dataset_split IN ('train', 'validation')
),
cells AS (
    SELECT d.account_key, d.as_of,
           count(*) FILTER (WHERE (t.from_country || '→' || t.to_country) IN (SELECT key FROM risky)) AS k,
           max(CASE WHEN t.from_country <> t.to_country AND l.is_laundering = 1 THEN 1 ELSE 0 END) AS y
    FROM days d
    JOIN transaction t
      ON t.from_account_key = d.account_key AND t.source_dataset = 'SAML-D'
     AND (t.occurred_at AT TIME ZONE 'UTC')::date <= d.as_of
     AND (t.occurred_at AT TIME ZONE 'UTC')::date > d.as_of - {window}
    LEFT JOIN label.saml_d_truth l ON l.source_line_number = t.source_line_number
    GROUP BY 1, 2
)
SELECT LEAST(k, {k_cap}) AS bucket, count(*) AS n, sum(y) AS pos,
       avg(y::numeric) AS rate
FROM cells GROUP BY 1 HAVING count(*) >= {bucket_min};

ALTER TABLE geo_cell ADD COLUMN k integer;
UPDATE geo_cell c SET k = COALESCE(x.k, 0) FROM (
    SELECT d.account_key, d.as_of,
           count(*) FILTER (WHERE (t.from_country || '→' || t.to_country)
                            IN (SELECT key FROM geo_weight
                                 WHERE kind = 'corridor' AND lift >= {risky_lift})) AS k
    FROM (SELECT DISTINCT account_key, as_of FROM geo_cell) d
    JOIN transaction t
      ON t.from_account_key = d.account_key AND t.source_dataset = 'SAML-D'
     AND (t.occurred_at AT TIME ZONE 'UTC')::date <= d.as_of
     AND (t.occurred_at AT TIME ZONE 'UTC')::date > d.as_of - {window}
    GROUP BY 1, 2
) x WHERE x.account_key = c.account_key AND x.as_of = c.as_of;

ALTER TABLE geo_cell ADD COLUMN score numeric;
UPDATE geo_cell c SET score =
      COALESCE((SELECT rate FROM geo_bucket b WHERE b.bucket = LEAST(c.k, {k_cap})), 0) * 1000.0
    + c.corridor_lift * 3.0
    + c.channel_lift * 1.5
    + LEAST(c.fx_count, 10) * 0.10;
CREATE INDEX geo_cell_score_idx ON geo_cell (score DESC);
"""


def main() -> int:
    args = parse_args()

    loaded = int(sql(args, "SELECT count(*) FROM transaction WHERE source_dataset='SAML-D'"))
    if loaded == 0:
        print("Chưa có dữ liệu SAML-D. Chạy scripts/load_saml_d.py trước.", file=sys.stderr)
        return 1
    print(f"giao dịch SAML-D đã nạp: {loaded:,}")

    print("đo trọng số hành lang trên train+validation…")
    sql(
        args,
        CELLS_SQL.format(
            min_support=MIN_SUPPORT,
            window=args.window_days,
            risky_lift=RISKY_LIFT,
            k_cap=K_CAP,
            bucket_min=BUCKET_MIN,
        ),
    )

    cells = int(sql(args, "SELECT count(*) FROM geo_cell"))
    print(f"lưới điểm trên tập test: {cells:,} ô")
    print("\ntop 8 hành lang theo mức nâng:")
    print(
        sql(
            args,
            """SELECT '  ' || key || '  ×' || round(lift, 2) || '  (n=' || n || ')'
                       FROM geo_weight WHERE kind='corridor' ORDER BY lift DESC LIMIT 8""",
        )
    )

    if args.dry_run:
        print("\n--dry-run: không ghi cảnh báo")
        return 0

    print(f"\nsinh {args.budget:,} cảnh báo…")
    sql(args, f"DELETE FROM alert_reason WHERE alert_id IN (SELECT alert_id FROM alert WHERE detector='{DETECTOR}')")
    # Chỉ xoá cảnh báo CHƯA có phiên điều tra nào trỏ vào.
    #
    # `investigation.alert_id` là khoá ngoại: xoá thẳng theo detector hỏng ngay
    # khi đã có một phiên điều tra chạy, và script dừng giữa chừng — cảnh báo cũ
    # còn nguyên mà bảng lý do thì đã bị xoá sạch, đúng trạng thái vừa gặp.
    # Cảnh báo đã điều tra được giữ và cập nhật tại chỗ qua ON CONFLICT; lịch sử
    # điều tra là bằng chứng, không phải thứ dọn đi cho tiện.
    sql(
        args,
        f"""DELETE FROM alert WHERE detector='{DETECTOR}'
                    AND alert_id NOT IN (SELECT alert_id FROM investigation)""",
    )

    # risk_score đi theo THỨ HẠNG chứ không phải điểm thô. Nhánh MEGA-PNA để cả
    # 5.000 cảnh báo cùng điểm 100 và hàng đợi mất hẳn thứ tự ưu tiên; đừng lặp lại.
    sql(
        args,
        f"""
        WITH top AS (
            SELECT *, row_number() OVER (ORDER BY score DESC, account_key, as_of) AS rnk
            FROM geo_cell ORDER BY score DESC, account_key, as_of LIMIT {args.budget}
        )
        INSERT INTO alert (alert_id, account_key, transaction_id, typology_code, detector,
                           risk_score, status, created_at, dataset)
        SELECT 'ALT-GEO-' || substr(md5('{DETECTOR}|' || account_key || '|' || as_of), 1, 16),
               account_key, top_transaction_id, '{TYPOLOGY}', '{DETECTOR}',
               round((100.0 - 40.0 * (rnk - 1)::numeric / {args.budget})::numeric, 2),
               'open', as_of::timestamptz, '{DATASET}'
        FROM top
        ON CONFLICT (alert_id) DO UPDATE
           SET risk_score = EXCLUDED.risk_score,
               transaction_id = EXCLUDED.transaction_id,
               typology_code = EXCLUDED.typology_code
    """,
    )

    sql(
        args,
        f"""
        -- Lý do sinh cho MỌI cảnh báo geo_rule còn trong bảng, không chỉ nhóm
        -- top vừa chọn. Cảnh báo được giữ lại vì đã có phiên điều tra vẫn nằm
        -- trong hàng đợi; bỏ sót nó là để lại một cảnh báo không có yếu tố đóng
        -- góp nào, vi phạm NT7 — mỗi điểm rủi ro phải kèm tối thiểu ba yếu tố.
        WITH a AS (
            SELECT al.alert_id, c.*
            FROM alert al
            JOIN geo_cell c
              ON al.alert_id = 'ALT-GEO-' || substr(md5('{DETECTOR}|' || c.account_key || '|' || c.as_of), 1, 16)
            WHERE al.detector = '{DETECTOR}'
        )
        INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
        SELECT alert_id, 'GEO_CORRIDOR',
               'Hành lang ' || top_corridor || ' — rủi ro gấp ' || round(corridor_lift, 1) || ' lần mức nền',
               LEAST(round(corridor_lift * 12.0, 2), 100.00), 1.00 FROM a
        UNION ALL
        SELECT alert_id, 'GEO_COUNTRIES',
               country_count || ' quốc gia đối tác trong khoảng ' || {args.window_days} || ' ngày',
               LEAST(round(country_count * 8.0, 2), 100.00), 0.60 FROM a
        UNION ALL
        SELECT alert_id, 'GEO_CASH', cash_count || ' giao dịch tiền mặt',
               LEAST(round(cash_count * 6.0, 2), 100.00), 0.30 FROM a
        UNION ALL
        SELECT alert_id, 'GEO_FX', fx_count || ' giao dịch đổi loại tiền',
               LEAST(round(fx_count * 5.0, 2), 100.00), 0.30 FROM a
    """,
    )

    n_alert = int(sql(args, f"SELECT count(*) FROM alert WHERE detector='{DETECTOR}'"))
    n_reason = int(
        sql(
            args,
            f"""SELECT count(*) FROM alert_reason r
                                 JOIN alert a USING (alert_id) WHERE a.detector='{DETECTOR}'""",
        )
    )
    spread = sql(
        args,
        f"""SELECT count(DISTINCT risk_score) || ' giá trị risk_score khác nhau, từ '
                           || min(risk_score) || ' tới ' || max(risk_score)
                           FROM alert WHERE detector='{DETECTOR}'""",
    )
    print(f"  cảnh báo {n_alert:,} · dòng lý do {n_reason:,}")
    print(f"  {spread}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
