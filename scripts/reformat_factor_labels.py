"""Định dạng lại số trong nhãn yếu tố đóng góp của cảnh báo.

``scripts/build_mega_pna_alerts.py`` từng ghi nhãn dạng "Tổng 13696 trên các giao
dịch bị gắn cờ" — số để trần vì lúc ấy bộ đối chiếu số của tác tử phản biện chưa
biết bỏ dấu phân cách trước khi so khớp. Nay nó biết (xem ``_mask_identifiers``),
nên nhãn có thể tách hàng nghìn cho người đọc mà vẫn tự kiểm chứng được.

Chạy::

    python scripts/reformat_factor_labels.py            # chỉ báo cáo
    python scripts/reformat_factor_labels.py --apply    # ghi thật
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402
from src.investigation.agents import THIN_SPACE  # noqa: E402

#: Số nguyên từ bốn chữ số trở lên, chưa có dấu tách.
_BARE_NUMBER = re.compile(r"(?<![\d .,])(\d{4,})(?![\d .,])")


def group_thousands(label: str) -> str:
    """Chèn dấu cách mảnh vào mọi số nguyên dài trong nhãn."""
    return _BARE_NUMBER.sub(lambda m: f"{int(m.group(1)):,}".replace(",", THIN_SPACE), label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Ghi thật; mặc định chỉ báo cáo")
    parser.add_argument("--batch", type=int, default=2000)
    args = parser.parse_args(argv)

    changed = 0
    with get_session() as session:
        rows = session.execute(
            text(r"""SELECT alert_id, factor_code, factor_label FROM alert_reason
                      WHERE factor_label ~ '(^|[^0-9 .,])[0-9]{4,}([^0-9 .,]|$)'""")
        ).all()
    print(f"{len(rows)} nhãn có số chưa tách hàng nghìn")
    updates = []
    for alert_id, factor_code, label in rows:
        new_label = group_thousands(label)
        if new_label != label:
            updates.append({"a": alert_id, "f": factor_code, "l": new_label})
            if changed < 3:
                print(f"  {label[:70]}\n  → {new_label[:70]}")
            changed += 1

    if args.apply and updates:
        for start in range(0, len(updates), args.batch):
            with get_session() as session:
                session.execute(
                    text("UPDATE alert_reason SET factor_label = :l WHERE alert_id = :a AND factor_code = :f"),
                    updates[start : start + args.batch],
                )
            print(f"  ... {min(start + args.batch, len(updates))}/{len(updates)}")
    print(f"\n{changed} nhãn cần đổi" + ("" if args.apply else " (chưa ghi — thêm --apply)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
