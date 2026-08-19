#!/usr/bin/env python3
"""Dựng bản đồ hành lang dòng tiền cho World Monitor từ SAML-D.

    python scripts/build_geo_rollup.py

Vì sao trang World Monitor đang trống
-------------------------------------
Nó đọc ``edge_country_hub`` và ``edge_country_flow``, cả hai đều rỗng, và
``country_geo`` cũng rỗng. Bộ dữ liệu IBM AML không mang quốc gia — quốc gia
phải suy từ tên ngân hàng, và bước ấy chưa từng chạy được.

SAML-D thì có sẵn vị trí ngân hàng của bên gửi và bên nhận trên TỪNG giao dịch.
Đây là dữ liệu địa lý thật của bộ dữ liệu, không phải suy đoán.

Release riêng cho bản đồ
------------------------
``edge_model_release`` đang có một bản ghi ``active`` phục vụ trang tra cứu
giao dịch và chấm điểm cạnh. Chiếm chỗ nó là làm hỏng ba trang khác. Bản rollup
địa lý vì thế mang một ``release_id`` riêng và endpoint tra theo đúng mã ấy.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "REL-GEO-SAMLD-V1"
MAX_FLOWS = 400


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--geo-csv", type=Path, default=ROOT / "data/reference/country_geo.csv")
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


def seed_countries(args: argparse.Namespace) -> int:
    rows = [
        r
        for r in csv.DictReader(
            line for line in args.geo_csv.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
        )
    ]
    values = ", ".join(
        "('{}', '{}', {}, {})".format(r["country_code"], r["name"].replace("'", "''"), r["lat"], r["lon"]) for r in rows
    )
    sql(
        args,
        f"""INSERT INTO country_geo (country_code, name, lat, lon) VALUES {values}
                  ON CONFLICT (country_code) DO UPDATE
                  SET name = EXCLUDED.name, lat = EXCLUDED.lat, lon = EXCLUDED.lon""",
    )
    return len(rows)


# Quốc gia trong SAML-D viết bằng tên thường; bảng rollup dùng mã ISO hai chữ.
ISO_CASE = """CASE {col}
    WHEN 'UK' THEN 'GB' WHEN 'USA' THEN 'US' WHEN 'UAE' THEN 'AE'
    WHEN 'Turkey' THEN 'TR' WHEN 'Switzerland' THEN 'CH' WHEN 'Pakistan' THEN 'PK'
    WHEN 'Nigeria' THEN 'NG' WHEN 'Spain' THEN 'ES' WHEN 'Germany' THEN 'DE'
    WHEN 'Italy' THEN 'IT' WHEN 'France' THEN 'FR' WHEN 'Japan' THEN 'JP'
    WHEN 'Morocco' THEN 'MA' WHEN 'Austria' THEN 'AT' WHEN 'Mexico' THEN 'MX'
    WHEN 'Albania' THEN 'AL' WHEN 'India' THEN 'IN' WHEN 'Netherlands' THEN 'NL'
    ELSE 'ZZ' END"""

RELEASE_SQL = """
INSERT INTO edge_model_release (
    release_id, model_version, dataset, split, model_sha256, scores_sha256,
    source_database_sha256, threshold, transaction_rows, positive_rows,
    triggered_rows, feature_count, benchmark, policy, status, trained_at)
SELECT '{release}', 'geo-rule-saml-d-v1', 'SAML-D', 'test',
       repeat('0', 64), repeat('0', 64), repeat('0', 64), 0.0,
       (SELECT count(*) FROM transaction WHERE source_dataset = 'SAML-D'),
       (SELECT count(*) FROM label.saml_d_truth WHERE is_laundering = 1),
       (SELECT count(*) FROM alert WHERE detector = 'geo_rule'),
       4,
       '{{"note": "Bộ luật địa lý, không huấn luyện. Xem reports/geo-rule/saml_d_v1.json."}}'::jsonb,
       '{{"branch": "geo_rule", "unit": "account_window", "window_days": 7}}'::jsonb,
       'reference', now()
WHERE NOT EXISTS (SELECT 1 FROM edge_model_release WHERE release_id = '{release}');
"""

ROLLUP_SQL = """
DELETE FROM edge_country_flow WHERE release_id = '{release}';
DELETE FROM edge_country_hub  WHERE release_id = '{release}';

-- Hành lang: gộp theo (nguồn, đích, tiền tệ, kênh). alert_count đếm số cảnh báo
-- geo_rule mà tài khoản GỬI của hành lang ấy đang mở — nối bản đồ với hàng đợi.
INSERT INTO edge_country_flow (release_id, source_country_code, target_country_code,
                               currency, channel, txn_count, amount_native,
                               first_seen, last_seen, alert_count, risk_score)
SELECT '{release}', src, dst, currency, channel, txn_count, amount_native,
       first_seen, last_seen, alert_count,
       LEAST(round(100.0 * alert_count / GREATEST(txn_count, 1), 2), 100.00)
FROM (
    SELECT {t_src} AS src, {t_dst} AS dst,
           t.receiving_currency AS currency, t.channel AS channel,
           count(*) AS txn_count, sum(t.amount) AS amount_native,
           min(t.occurred_at) AS first_seen, max(t.occurred_at) AS last_seen,
           count(DISTINCT a.alert_id) AS alert_count
    FROM transaction t
    LEFT JOIN alert a
           ON a.account_key = t.from_account_key AND a.detector = 'geo_rule'
    -- Ràng buộc của bảng chặn hành lang nội địa: bản đồ chỉ vẽ dòng chảy GIỮA
    -- các quốc gia. Lọc ngay tại đây thay vì để ràng buộc ném lỗi.
    WHERE t.source_dataset = 'SAML-D'
      AND t.from_country <> t.to_country
    GROUP BY 1, 2, 3, 4
    ORDER BY count(DISTINCT a.alert_id) DESC, count(*) DESC
    LIMIT {max_flows}
) s;

-- Hub: một dòng mỗi quốc gia.
INSERT INTO edge_country_hub (release_id, country_code, entities, inbound, outbound,
                              alerts, risk_score)
SELECT '{release}', code,
       COALESCE(max(entities), 0), COALESCE(sum(inbound), 0), COALESCE(sum(outbound), 0),
       COALESCE(max(alerts), 0),
       LEAST(round(100.0 * COALESCE(max(alerts), 0)
             / GREATEST(COALESCE(sum(inbound), 0) + COALESCE(sum(outbound), 0), 1), 2), 100.00)
FROM (
    SELECT {p_dst} AS code, 0 AS entities, count(*) AS inbound, 0 AS outbound, 0 AS alerts
    FROM transaction WHERE source_dataset = 'SAML-D' GROUP BY 1
    UNION ALL
    SELECT {p_src}, 0, 0, count(*), 0
    FROM transaction WHERE source_dataset = 'SAML-D' GROUP BY 1
    UNION ALL
    SELECT bank_code, count(*), 0, 0, 0 FROM account WHERE dataset = 'saml_d' GROUP BY 1
    UNION ALL
    SELECT ac.bank_code, 0, 0, 0, count(*)
    FROM alert a JOIN account ac USING (account_key)
    WHERE a.detector = 'geo_rule' GROUP BY 1
) h
WHERE code IN (SELECT country_code FROM country_geo)
GROUP BY 1, 2;
"""


def main() -> int:
    args = parse_args()

    loaded = int(sql(args, "SELECT count(*) FROM transaction WHERE source_dataset='SAML-D'"))
    if loaded == 0:
        print("Chưa có dữ liệu SAML-D.", file=sys.stderr)
        return 1

    n_geo = seed_countries(args)
    print(f"country_geo: {n_geo} quốc gia")

    sql(args, RELEASE_SQL.format(release=RELEASE_ID))

    sql(
        args,
        ROLLUP_SQL.format(
            release=RELEASE_ID,
            max_flows=MAX_FLOWS,
            t_src=ISO_CASE.format(col="t.from_country"),
            t_dst=ISO_CASE.format(col="t.to_country"),
            p_src=ISO_CASE.format(col="from_country"),
            p_dst=ISO_CASE.format(col="to_country"),
        ),
    )

    hubs = int(sql(args, f"SELECT count(*) FROM edge_country_hub WHERE release_id='{RELEASE_ID}'"))
    flows = int(sql(args, f"SELECT count(*) FROM edge_country_flow WHERE release_id='{RELEASE_ID}'"))
    print(f"hub {hubs} quốc gia · hành lang {flows}")
    print("\ntop 6 hành lang theo số cảnh báo:")
    print(
        sql(
            args,
            f"""SELECT '  ' || source_country_code || ' → ' || target_country_code
                        || '  ' || txn_count || ' gd · ' || alert_count || ' cảnh báo'
                        FROM edge_country_flow WHERE release_id='{RELEASE_ID}'
                        ORDER BY alert_count DESC, txn_count DESC LIMIT 6""",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
