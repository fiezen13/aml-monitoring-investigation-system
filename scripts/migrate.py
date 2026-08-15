#!/usr/bin/env python3
"""Áp các file lược đồ trong db/init lên một cơ sở dữ liệu đã có dữ liệu.

Vì sao cần: `db/init/*.sql` chỉ được PostgreSQL chạy khi volume còn rỗng
(docker-entrypoint-initdb.d). Trên máy đã chạy, thêm một file lược đồ mới sẽ
không có tác dụng gì, và cách duy nhất còn lại là `make db-reset` — xoá sạch
dữ liệu. Trên VM production thì đó không phải một lựa chọn.

Script này giữ một bảng `schema_migration` ghi nhận file nào đã áp, rồi chạy
những file còn thiếu theo thứ tự tên, mỗi file trong một transaction.

Lần chạy đầu trên cơ sở dữ liệu cũ: nếu bảng `customer` đã tồn tại thì các
file 001–004 coi như đã áp từ trước (chúng chính là thứ dựng nên bảng đó) và
chỉ được đánh dấu, không chạy lại.

Cách dùng:
    python scripts/migrate.py            # áp các file còn thiếu
    python scripts/migrate.py --status   # chỉ liệt kê, không ghi gì
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

# Chạy trực tiếp thì sys.path[0] là scripts/, không phải gốc repo.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from src.db.session import get_session  # noqa: E402

INIT_DIR = ROOT / "db" / "init"

# Các file dựng nên lược đồ gốc. Nếu cơ sở dữ liệu đã có bảng `customer` thì
# chúng đã chạy rồi — đánh dấu chứ không chạy lại.
BASELINE = {"001_schema.sql", "002_audit_immutability.sql", "004_console_runtime.sql"}

log = logging.getLogger("migrate")


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _ensure_table(session) -> None:
    session.execute(
        text(
            """CREATE TABLE IF NOT EXISTS schema_migration (
                   filename    TEXT        PRIMARY KEY,
                   checksum    TEXT        NOT NULL,
                   applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                   -- baseline = đã tồn tại từ trước khi có script này
                   applied_by  TEXT        NOT NULL DEFAULT 'migrate.py'
               )"""
        )
    )


def _sql_files() -> list[Path]:
    # Chỉ .sql: 003_agent_readonly_role.sh là shell script, do entrypoint của
    # image postgres chạy, không phải việc của script này.
    return sorted(p for p in INIT_DIR.glob("*.sql"))


def _check_agent_role(session) -> bool:
    """Vai trò `fin07_agent` có tồn tại không, và nói to nếu không.

    Vì sao phải kiểm riêng: `db/init/003_agent_readonly_role.sh` là shell
    script, chỉ được chạy bởi entrypoint của image `postgres` khi volume còn
    rỗng. Script này chỉ áp `*.sql`, nên trên MỌI cơ sở dữ liệu không dựng từ
    image đó — Cloud SQL, RDS, một PostgreSQL cài sẵn — file 003 sẽ không bao
    giờ chạy.

    Hệ quả nếu im lặng: schema `agent` không tồn tại, vai trò chỉ đọc không
    tồn tại, và ranh giới "agent không đọc được nhãn" (ND1/RD1, cưỡng chế bằng
    quyền PostgreSQL) biến mất mà không có một dòng lỗi nào. Một ràng buộc an
    toàn mất đi trong im lặng là thứ tệ hơn một ràng buộc chưa từng có: người
    ta tin rằng nó đang bảo vệ mình.

    Trả về True nếu vai trò có mặt.
    """
    exists = session.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fin07_agent')")).scalar()
    if exists:
        return True

    log.warning("")
    log.warning("  ⚠ Vai trò `fin07_agent` KHÔNG tồn tại trên cơ sở dữ liệu này.")
    log.warning("    Cách ly nhãn khỏi agent (ND1/RD1) hiện KHÔNG được cưỡng chế.")
    log.warning("")
    log.warning("    Nguyên nhân: db/init/003_agent_readonly_role.sh là shell script,")
    log.warning("    chỉ chạy khi cơ sở dữ liệu được dựng từ image postgres với volume rỗng.")
    log.warning("")
    log.warning("    Cách áp bằng tay — chính file đó, chạy như shell script:")
    log.warning("      PGHOST=<host> PGPASSWORD=<mật khẩu chủ> \\")
    log.warning("      POSTGRES_USER=fin07 POSTGRES_DB=fin07 \\")
    log.warning("      FIN07_AGENT_DB_PASSWORD=<mật khẩu agent> \\")
    log.warning("        bash db/init/003_agent_readonly_role.sh")
    log.warning("")
    log.warning("    Chi tiết: infra/terraform/README.md mục 5.")
    log.warning("")
    return False


def _adopt_existing_optional_migrations(session, applied: set[str]) -> None:
    """Record migrations whose distinctive objects already exist.

    Older deployments applied 005 through docker-entrypoint before
    ``schema_migration`` tracked it. Replaying that non-idempotent file would
    fail at ``CREATE SCHEMA fc`` and block every later migration.
    """
    probes = {
        "005_financial_city.sql": "SELECT to_regclass('fc.agent_run') IS NOT NULL",
        "006_explainable_investigations.sql": "SELECT to_regclass('public.investigation') IS NOT NULL",
        "007_gemini_agent_runtime.sql": (
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='investigation_agent_run' "
            "AND column_name='prompt_version')"
        ),
        "008_behavior_batch_poc.sql": "SELECT to_regclass('public.detection_result') IS NOT NULL",
        "009_behavior_model_provenance.sql": (
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='behavior_batch' "
            "AND column_name='model_sha256')"
        ),
        "010_bank_geography.sql": "SELECT to_regclass('public.bank') IS NOT NULL",
        "011_remove_behavior_14d.sql": (
            "SELECT NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='behavior_batch_feature_window_check') "
            "OR pg_get_constraintdef((SELECT oid FROM pg_constraint "
            "WHERE conname='behavior_batch_feature_window_check' LIMIT 1)) NOT LIKE '%14d%'"
        ),
        "012_operational_geography_rollup.sql": (
            "SELECT to_regclass('public.operational_country_hub') IS NOT NULL"
        ),
        "013_currency_native_edge_release.sql": (
            "SELECT to_regclass('public.edge_model_release') IS NOT NULL"
        ),
        "014_edge_operational_serving.sql": (
            "SELECT to_regclass('public.edge_country_flow') IS NOT NULL"
        ),
    }
    for filename, probe in probes.items():
        path = INIT_DIR / filename
        if filename in applied or not path.exists():
            continue
        if session.execute(text(probe)).scalar():
            session.execute(
                text(
                    """INSERT INTO schema_migration (filename, checksum, applied_by)
                       VALUES (:f, :c, 'adopted-existing') ON CONFLICT DO NOTHING"""
                ),
                {"f": filename, "c": _checksum(path)},
            )
            applied.add(filename)
            log.info("Nhận %s là đã áp từ object hiện hữu", filename)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Chỉ liệt kê trạng thái, không ghi")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = _sql_files()
    if not files:
        log.error("Không tìm thấy file .sql nào trong %s", INIT_DIR)
        return 1

    with get_session() as session:
        _ensure_table(session)

        applied = {row[0] for row in session.execute(text("SELECT filename FROM schema_migration")).all()}

        # Cơ sở dữ liệu có sẵn từ trước script này: nhận baseline là đã áp.
        if not applied:
            has_customer = session.execute(text("SELECT to_regclass('public.customer') IS NOT NULL")).scalar()
            if has_customer:
                for name in sorted(BASELINE):
                    path = INIT_DIR / name
                    if not path.exists():
                        continue
                    session.execute(
                        text(
                            """INSERT INTO schema_migration (filename, checksum, applied_by)
                               VALUES (:f, :c, 'baseline')
                               ON CONFLICT (filename) DO NOTHING"""
                        ),
                        {"f": name, "c": _checksum(path)},
                    )
                    applied.add(name)
                log.info("Nhận %d file lược đồ gốc là đã áp từ trước", len(applied))

        _adopt_existing_optional_migrations(session, applied)

        pending = [p for p in files if p.name not in applied]

        if args.status:
            for path in files:
                mark = "đã áp " if path.name in applied else "CHỜ ÁP"
                log.info("  %s  %s", mark, path.name)
            has_role = _check_agent_role(session)
            log.info("  %s  003_agent_readonly_role.sh", "đã áp " if has_role else "CHỜ ÁP")
            return 0

        if not pending:
            log.info("Lược đồ đã ở bản mới nhất (%d file).", len(files))
            _check_agent_role(session)
            return 0

        for path in pending:
            log.info("Áp %s …", path.name)
            # Mỗi file một transaction: file hỏng thì không để lại lược đồ dở dang.
            try:
                session.execute(text(path.read_text(encoding="utf-8")))
                session.execute(
                    text("INSERT INTO schema_migration (filename, checksum) VALUES (:f, :c)"),
                    {"f": path.name, "c": _checksum(path)},
                )
                session.commit()
            except Exception:
                session.rollback()
                log.exception("Áp %s thất bại — đã rollback, các file trước vẫn giữ nguyên", path.name)
                return 1
            log.info("  ✓ %s", path.name)

        log.info("Đã áp %d file.", len(pending))
        _check_agent_role(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
