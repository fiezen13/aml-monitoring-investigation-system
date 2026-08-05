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

        pending = [p for p in files if p.name not in applied]

        if args.status:
            for path in files:
                mark = "đã áp " if path.name in applied else "CHỜ ÁP"
                log.info("  %s  %s", mark, path.name)
            return 0

        if not pending:
            log.info("Lược đồ đã ở bản mới nhất (%d file).", len(files))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
