#!/usr/bin/env python3
"""Đóng các cảnh báo chỉ dựa trên luật đã gỡ khỏi bộ luật.

    python -m scripts.close_unverifiable_rule_alerts --dry-run
    python -m scripts.close_unverifiable_rule_alerts

Bối cảnh
--------
``R03_VASP_EXPOSURE`` và ``R04_CROSS_BORDER_FLOW`` đã bị gỡ khỏi
``src/detection/rules.py`` vì chúng đọc thuộc tính **do dự án tự gán** trong
``data/reference/bank_country.csv``, không có trong bộ dữ liệu IBM AML:

* ``is_vasp`` chỉ đánh dấu một họ ngân hàng hư cấu (``Crytpo Bank``).
* 12.857 trên 32.173 ngân hàng có quốc gia do dự án gán chứ không đọc được.

Bộ nhãn của IBM (``LI-Small-Patterns.txt``) gán 117 vụ theo tám mẫu hình đồ thị
— FAN-OUT, STACK, BIPARTITE, RANDOM, SCATTER-GATHER, GATHER-SCATTER, FAN-IN,
CYCLE — không có mẫu nào tương ứng hai luật ấy. Nghĩa là chúng không thể
benchmark hay kiểm chứng được trên bộ dữ liệu này.

Vì sao ĐÓNG chứ không XOÁ
-------------------------
Trong quy trình AML, một cảnh báo đã phát thì không bị xoá; nó được đóng lại kèm
lý do. Xoá đi là giả vờ nó chưa từng tồn tại, và ở đây còn kéo theo sáu phiên
điều tra cùng ba vụ việc đang gắn vào chúng — tức xoá luôn cả dấu vết tác tử đã
chạy. Đóng lại thì hàng đợi phản ánh đúng những gì kiểm chứng được, mà lịch sử
vẫn tra lại được.

Cảnh báo đã đóng biến khỏi mọi màn hình đếm theo ``status <> 'closed'``: hàng
đợi cảnh báo, badge sidebar, và ô "cảnh báo đang mở" trên Tổng quan.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402

logger = logging.getLogger("fin07.close_unverifiable")

#: Mã của các luật đã gỡ. Giữ ở đây chứ không import từ ``rules.py``: sau khi gỡ
#: thì hai mã ấy không còn tồn tại trong mã nguồn, mà dữ liệu cũ vẫn mang chúng.
REMOVED_RULES = ("R03_VASP_EXPOSURE", "R04_CROSS_BORDER_FLOW")

#: Cảnh báo mà **mọi** yếu tố dạng luật đều thuộc nhóm đã gỡ.
#:
#: ``factor_code LIKE 'R0%'`` lọc riêng các yếu tố luật, bỏ qua những dòng
#: ``CTX_*`` — chúng chỉ là số đo ngữ cảnh thêm vào cho đủ ràng buộc NT7, mang
#: ``contribution = 0``, nên không được tính khi xét cảnh báo còn căn cứ hay không.
TARGET_SQL = """
    SELECT a.alert_id
      FROM alert a
      JOIN alert_reason r USING (alert_id)
     WHERE a.detector = 'rule'
       AND a.status <> 'closed'
       AND r.factor_code LIKE 'R0%'
     GROUP BY a.alert_id
    HAVING bool_and(r.factor_code = ANY(:removed))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with get_session() as session:
        params = {"removed": list(REMOVED_RULES)}
        targets = list(session.execute(text(TARGET_SQL), params).scalars())
        logger.info("Cảnh báo chỉ còn căn cứ từ luật đã gỡ: %d", len(targets))

        before = session.execute(text("SELECT count(*) FROM alert WHERE status <> 'closed'")).scalar_one()
        if args.dry_run:
            logger.info("Đang mở trước khi chạy: %d — thử nghiệm, không ghi gì", before)
            return 0
        if not targets:
            logger.info("Không có gì để đóng")
            return 0

        session.execute(
            text("UPDATE alert SET status = 'closed' WHERE alert_id = ANY(:ids)"),
            {"ids": targets},
        )
        after = session.execute(text("SELECT count(*) FROM alert WHERE status <> 'closed'")).scalar_one()
        logger.info("Đã đóng %d cảnh báo. Đang mở: %d → %d", len(targets), before, after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
