#!/usr/bin/env python3
"""Chạy nhánh Rule của Detection Engine và sinh cảnh báo ``detector='rule'``.

Ví dụ::

    # Thử trước, không ghi gì
    python scripts/run_rule_engine.py --dry-run

    # Chạy thật trên cửa sổ 7 ngày cuối của dữ liệu
    python scripts/run_rule_engine.py

    # Cửa sổ và mốc thời gian chỉ định
    python scripts/run_rule_engine.py --as-of 2022-09-28T00:00:00Z --window-days 7
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402
from src.detection import rule_engine  # noqa: E402

logger = logging.getLogger("fin07.run_rule_engine")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default=None,
        help="Mốc kết thúc cửa sổ (ISO 8601). Bỏ trống = ngay sau giao dịch mới nhất.",
    )
    parser.add_argument("--window-days", type=int, default=7, choices=(1, 7, 30))
    parser.add_argument(
        "--min-transactions",
        type=int,
        default=5,
        help="Bỏ qua tài khoản có ít giao dịch hơn mức này trong cửa sổ.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Dừng sau khi tạo N cảnh báo.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi Postgres.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None

    with get_session() as session:
        stats = rule_engine.run(
            session,
            as_of=as_of,
            window_days=args.window_days,
            min_transactions=args.min_transactions,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
