"""Gán một ít vụ việc cho analyst demo (U-006) để MINH HOẠ phạm vi dữ liệu.

Nền dữ liệu tải vào để trống cột ``aml_case.assigned_to``. Khi đó vai trò phạm
vi ASSIGNED (analyst) — vốn được thực thi đúng ở máy chủ (danh sách + chi tiết
vụ việc) — không có gì để hiển thị, nên KHÔNG thể minh hoạ đường đi "analyst chỉ
thấy vụ việc của mình". Script này gán N vụ việc rủi ro cao nhất cho một analyst
để đường đi tích cực có thể demo/kiểm thử; đường đi tiêu cực (analyst KHÔNG mở
được vụ việc của người khác) vẫn được bảo đảm bởi phân quyền cấp-bản-ghi.

Đây là DỮ LIỆU MINH HOẠ có thật (gán vụ việc thật cho người dùng thật), không
phải số liệu bịa. Idempotent: chạy lại chỉ giữ đúng N vụ được gán.

    python scripts/seed_demo_case_assignments.py --analyst U-006 --count 6
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from src.db.session import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyst", default="U-006", help="user_id của analyst nhận vụ việc")
    parser.add_argument("--count", type=int, default=6, help="số vụ việc rủi ro cao nhất để gán")
    args = parser.parse_args()

    with get_session() as session:
        user = (
            session.execute(
                text("SELECT user_id, role FROM app_user WHERE user_id = :id"),
                {"id": args.analyst},
            )
            .mappings()
            .first()
        )
        if user is None:
            raise SystemExit(f"Không tìm thấy người dùng {args.analyst}")
        if user["role"] != "analyst":
            raise SystemExit(f"{args.analyst} không phải analyst (role={user['role']})")

        # Idempotent: gỡ gán cũ của người này trước, rồi gán lại đúng N vụ.
        session.execute(
            text("UPDATE aml_case SET assigned_to = NULL WHERE assigned_to = :id"),
            {"id": args.analyst},
        )
        session.execute(
            text(
                """UPDATE aml_case SET assigned_to = :id
                    WHERE case_id IN (
                        SELECT case_id FROM aml_case
                         WHERE assigned_to IS NULL
                         ORDER BY risk_score DESC, created_at DESC
                         LIMIT :n)"""
            ),
            {"id": args.analyst, "n": args.count},
        )
        total = session.execute(
            text("SELECT count(*) FROM aml_case WHERE assigned_to = :id"),
            {"id": args.analyst},
        ).scalar_one()
    print(f"Đã gán {total} vụ việc cho {args.analyst}.")


if __name__ == "__main__":
    main()
