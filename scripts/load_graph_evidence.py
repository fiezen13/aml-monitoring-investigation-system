#!/usr/bin/env python3
"""Nạp bằng chứng bộ phát hiện đồ thị vào PostgreSQL.

Mặc định chỉ nạp mốc thời gian của ảnh chụp đang phục vụ (lấy từ
``behavior_feature_snapshot``) — đó là mốc mà các cảnh báo đang trỏ tới. Dùng
``--all`` để nạp toàn bộ lịch sử.

Ví dụ::

    python scripts/load_graph_evidence.py
    python scripts/load_graph_evidence.py --as-of 2022-09-17T00:00:00Z
    python scripts/load_graph_evidence.py --all
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

from sqlalchemy import text  # noqa: E402

from src.db.session import get_session  # noqa: E402
from src.detection import graph_loader  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=ROOT / graph_loader.DEFAULT_EVIDENCE)
    parser.add_argument("--as-of", default=None, help="Chỉ nạp mốc này (ISO 8601).")
    parser.add_argument("--all", action="store_true", help="Nạp mọi mốc thời gian trong file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    with get_session() as session:
        as_of: datetime | None = None
        if not args.all:
            if args.as_of:
                as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
            else:
                as_of = session.execute(
                    text("SELECT max(as_of_time) FROM behavior_feature_snapshot")
                ).scalar_one_or_none()
                if as_of is None:
                    raise SystemExit(
                        "Chưa có behavior_feature_snapshot nào để suy ra mốc thời gian. "
                        "Chạy load_fusion_release.py trước, hoặc chỉ định --as-of / --all."
                    )
        stats = graph_loader.load(session, path=args.evidence, as_of=as_of)
        stats["as_of"] = as_of.isoformat() if as_of else "all"

    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
