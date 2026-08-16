#!/usr/bin/env python3
"""Nạp tên và quốc gia ngân hàng từ `*_accounts.csv` của bộ IBM AML.

    python scripts/load_bank_geography.py --accounts data/raw/ibm-aml/LI-Small_accounts.csv

Cái bẫy quan trọng nhất: hai file của IBM dùng **hai không gian mã ngân hàng
khác nhau**. `*_accounts.csv` có cột `Bank ID` (314693, 311253) còn `*_Trans.csv`
có `From Bank`/`To Bank` (011, 070) — và `account.bank_code` trong cơ sở dữ liệu
lấy theo file giao dịch. Nối hai file bằng `Bank ID` sẽ ra rỗng mà không báo lỗi.

Khoá nối đúng là **số tài khoản**: mọi tài khoản trong file giao dịch đều có mặt
trong file accounts, và số tài khoản gần như duy nhất toàn cục.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from src.db.session import get_session  # noqa: E402
from src.services.bank_geography import (  # noqa: E402
    family_of,
    load_country_geo,
    load_lookup,
    resolve_all,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accounts",
        type=Path,
        default=ROOT / "data/raw/ibm-aml/LI-Small_accounts.csv",
        help="File *_accounts.csv của IBM AML",
    )
    return parser.parse_args(argv)


def account_to_bank_name(accounts_csv: Path) -> dict[str, str]:
    """`Account Number` -> `Bank Name`. Đây là bảng bắc cầu giữa hai file."""
    if not accounts_csv.is_file():
        raise FileNotFoundError(accounts_csv)
    mapping: dict[str, str] = {}
    with accounts_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            number = (row.get("Account Number") or "").strip()
            name = (row.get("Bank Name") or "").strip()
            if number and name:
                mapping[number] = name
    if not mapping:
        raise ValueError(f"Không đọc được cột 'Account Number'/'Bank Name' trong {accounts_csv}")
    return mapping


def refresh_operational_geography(session) -> dict[str, int]:
    """Rebuild currency-native World Monitor rollups for the active edge release."""
    release_id = session.execute(
        text(
            """SELECT release_id FROM edge_model_release
                WHERE status='active' LIMIT 1"""
        )
    ).scalar_one_or_none()
    if release_id is None:
        return {"rollup_hubs": 0, "rollup_flows": 0}
    rollup_schema = session.execute(text("SELECT to_regclass('public.edge_country_flow') IS NOT NULL")).scalar_one()
    if not rollup_schema:
        raise RuntimeError("Thiếu migration 014; chạy `make migrate` rồi nạp geography lại")

    session.execute(text("DELETE FROM edge_country_flow WHERE release_id=:release"), {"release": release_id})
    session.execute(text("DELETE FROM edge_country_hub WHERE release_id=:release"), {"release": release_id})
    session.execute(
        text(
            """
            INSERT INTO edge_country_hub (
              release_id, country_code, entities, inbound, outbound, alerts, risk_score
            )
            WITH acct AS (
              SELECT a.account_key, b.country_code
                FROM account a JOIN bank b ON b.bank_code=a.bank_code
               WHERE b.country_code IS NOT NULL
            ),
            edge AS (
              SELECT af.country_code src, ad.country_code dst
                FROM transaction t
                JOIN transaction_model_score s USING (transaction_id)
                JOIN acct af ON af.account_key=t.from_account_key
                JOIN acct ad ON ad.account_key=t.to_account_key
               WHERE s.release_id=:release
            ),
            outb AS (SELECT src cc, count(*) n FROM edge GROUP BY 1),
            inb  AS (SELECT dst cc, count(*) n FROM edge GROUP BY 1),
            ent  AS (SELECT country_code cc, count(*) n FROM acct GROUP BY 1),
            alr  AS (
              SELECT ac.country_code cc, count(*) n, avg(al.risk_score) r
                FROM alert al JOIN transaction_model_score s ON s.transaction_id=al.transaction_id
                JOIN acct ac ON ac.account_key=al.account_key
               WHERE s.release_id=:release
               GROUP BY 1
            )
            SELECT :batch, ent.cc, ent.n, coalesce(inb.n,0), coalesce(outb.n,0),
                   coalesce(alr.n,0), coalesce(round(alr.r),0)
              FROM ent
              LEFT JOIN inb ON inb.cc=ent.cc
              LEFT JOIN outb ON outb.cc=ent.cc
              LEFT JOIN alr ON alr.cc=ent.cc
            """
        ),
        {"batch": release_id, "release": release_id},
    )
    session.execute(
        text(
            """
            INSERT INTO edge_country_flow (
              release_id, source_country_code, target_country_code, currency,
              channel, txn_count, amount_native, first_seen, last_seen,
              alert_count, risk_score
            )
            WITH acct AS (
              SELECT a.account_key, b.country_code, b.is_vasp
                FROM account a JOIN bank b ON b.bank_code=a.bank_code
               WHERE b.country_code IS NOT NULL
            ),
            edge AS (
              SELECT af.country_code src, ad.country_code dst,
                     CASE WHEN af.is_vasp OR ad.is_vasp THEN 'vasp' ELSE 'bank' END channel,
                     t.amount, t.currency, t.occurred_at, s.triggered, s.model_score
                FROM transaction t
                JOIN transaction_model_score s USING (transaction_id)
                JOIN acct af ON af.account_key=t.from_account_key
                JOIN acct ad ON ad.account_key=t.to_account_key
               WHERE s.release_id=:release AND af.country_code<>ad.country_code
            )
            SELECT :batch, e.src, e.dst, e.currency,
                   e.channel, count(*), sum(e.amount),
                   min(e.occurred_at), max(e.occurred_at),
                   count(*) FILTER (WHERE e.triggered),
                   round((max(e.model_score)*100)::numeric,2)
              FROM edge e
             GROUP BY e.src,e.dst,e.currency,e.channel
            """
        ),
        {"batch": release_id, "release": release_id},
    )
    hubs = int(
        session.execute(
            text("SELECT count(*) FROM edge_country_hub WHERE release_id=:release"), {"release": release_id}
        ).scalar_one()
    )
    flows = int(
        session.execute(
            text("SELECT count(*) FROM edge_country_flow WHERE release_id=:release"), {"release": release_id}
        ).scalar_one()
    )
    return {"rollup_hubs": hubs, "rollup_flows": flows}


def run(accounts_csv: Path) -> dict[str, object]:
    by_account = account_to_bank_name(accounts_csv)
    lookup = load_lookup()
    counters: Counter[str] = Counter()

    with get_session() as session:
        rows = session.execute(text("SELECT DISTINCT bank_code, account_number FROM account")).mappings().all()
        if not rows:
            raise RuntimeError("Bảng account rỗng — nạp giao dịch trước khi chạy script này")

        # Một mã ngân hàng có thể xuất hiện ở nhiều tài khoản; lấy tên chiếm đa
        # số. Trên LI-Small chỉ 2 trên 41.867 mã có nhiều hơn một tên, nên bỏ
        # phiếu là đủ và không cần chính sách phức tạp hơn.
        votes: dict[str, Counter[str]] = {}
        for row in rows:
            name = by_account.get(row["account_number"])
            if name is None:
                counters["account_not_in_master"] += 1
                continue
            votes.setdefault(row["bank_code"], Counter())[family_of(name)] += 1

        chosen = {code: tally.most_common(1)[0][0] for code, tally in votes.items()}
        decisions = resolve_all(set(chosen.values()), lookup)

        params = []
        for bank_code, family in chosen.items():
            if len(votes[bank_code]) > 1:
                counters["bank_code_with_multiple_names"] += 1
            decided = decisions[family]
            counters[f"source_{decided.country_source}"] += 1
            if decided.is_vasp:
                counters["vasp"] += 1
            params.append(
                {
                    "bank_code": bank_code,
                    "bank_name": family,
                    "country_code": decided.country_code,
                    "country_source": decided.country_source,
                    "is_vasp": decided.is_vasp,
                }
            )

        session.execute(
            text(
                """INSERT INTO bank (bank_code, bank_name, country_code, country_source, is_vasp)
                   VALUES (:bank_code, :bank_name, :country_code, :country_source, :is_vasp)
                   ON CONFLICT (bank_code) DO UPDATE SET
                       bank_name      = EXCLUDED.bank_name,
                       country_code   = EXCLUDED.country_code,
                       country_source = EXCLUDED.country_source,
                       is_vasp        = EXCLUDED.is_vasp"""
            ),
            params,
        )

        geo = load_country_geo()
        session.execute(
            text(
                """INSERT INTO country_geo (country_code, name, lat, lon)
                   VALUES (:country_code, :name, :lat, :lon)
                   ON CONFLICT (country_code) DO UPDATE SET
                       name = EXCLUDED.name, lat = EXCLUDED.lat, lon = EXCLUDED.lon"""
            ),
            geo,
        )

        missing = (
            session.execute(
                text(
                    """SELECT DISTINCT b.country_code FROM bank b
                        WHERE b.country_code IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM country_geo g WHERE g.country_code = b.country_code)"""
                )
            )
            .scalars()
            .all()
        )
        covered = session.execute(
            text(
                """SELECT count(*) FILTER (WHERE b.country_code IS NOT NULL)::float
                          / greatest(count(*), 1)
                     FROM account a LEFT JOIN bank b ON b.bank_code = a.bank_code"""
            )
        ).scalar_one()

        rollup = refresh_operational_geography(session)

    return {
        "accounts_csv": str(accounts_csv),
        "banks_written": len(params),
        "countries_written": len(geo),
        "account_coverage": round(float(covered), 4),
        "country_without_coordinates": sorted(missing),
        **rollup,
        **{key: counters[key] for key in sorted(counters)},
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(args.accounts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["country_without_coordinates"]:
        print("CẢNH BÁO: có quốc gia chưa có toạ độ, bản đồ sẽ bỏ sót.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
