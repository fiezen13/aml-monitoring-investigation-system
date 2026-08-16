#!/usr/bin/env python3
"""Hiệu chỉnh ngưỡng cảnh báo từ nhãn của chuyên viên — khép vòng phản hồi.

Mũi tên "Feedback / learning loop" trong sơ đồ kiến trúc chỉ khép khi có ai đó
**đọc lại** nhãn. Bảng ``review_feedback`` đã lưu mỗi quyết định kèm đúng điểm
mà chuyên viên nhìn thấy lúc ra quyết định; script này dùng cặp (điểm, nhãn) đó
để trả lời một câu vận hành: *ngưỡng nào cho kết quả tốt nhất theo đánh giá của
chính đội rà soát?*

Nó **không tự đổi ngưỡng**. Nó in ra khuyến nghị kèm số liệu để người có thẩm
quyền quyết định — đổi ngưỡng phát hiện là quyết định nghiệp vụ, không phải hệ
quả tự động của một truy vấn.

Nhãn ``INCONCLUSIVE`` bị loại khỏi phép tính: chuyên viên chưa kết luận, gộp
chúng vào nhóm âm sẽ dạy hệ thống rằng mọi việc chưa xử lý xong đều là báo động
giả.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.session import get_session  # noqa: E402

#: Dưới mức này thì mọi khuyến nghị đều là nhiễu. Đặt ở đây để không ai vô tình
#: hiệu chỉnh ngưỡng sản xuất bằng năm cái nhãn.
MIN_LABELS = 30


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", default=None, help="Chỉ xét một nhánh: rule | ml | graph")
    parser.add_argument("--min-labels", type=int, default=MIN_LABELS)
    return parser.parse_args(argv)


def _metrics(pairs: list[tuple[float, int]], threshold: float) -> dict[str, float | int]:
    tp = sum(1 for score, label in pairs if score >= threshold and label == 1)
    fp = sum(1 for score, label in pairs if score >= threshold and label == 0)
    fn = sum(1 for score, label in pairs if score < threshold and label == 1)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": round(threshold, 2),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "flagged": tp + fp,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    where = ["label <> 'INCONCLUSIVE'", "risk_score IS NOT NULL"]
    params: dict[str, str] = {}
    if args.detector:
        where.append("detector = :detector")
        params["detector"] = args.detector

    with get_session() as session:
        rows = (
            session.execute(
                text(f"SELECT risk_score, label, detector FROM review_feedback WHERE {' AND '.join(where)}"),
                params,
            )
            .mappings()
            .all()
        )

    pairs = [(float(r["risk_score"]), 1 if r["label"] == "SUSPICIOUS" else 0) for r in rows]
    positives = sum(label for _, label in pairs)

    result: dict[str, object] = {
        "labels_used": len(pairs),
        "suspicious": positives,
        "not_suspicious": len(pairs) - positives,
        "detector": args.detector or "all",
    }

    if len(pairs) < args.min_labels:
        result["recommendation"] = None
        result["reason"] = (
            f"Chỉ có {len(pairs)} nhãn kết luận được, cần tối thiểu {args.min_labels}. "
            "Chưa đủ để khuyến nghị bất kỳ ngưỡng nào."
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0
    if positives == 0 or positives == len(pairs):
        result["recommendation"] = None
        result["reason"] = "Nhãn chỉ có một lớp; không tính được ngưỡng phân tách."
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0

    sweep = [_metrics(pairs, threshold) for threshold in range(0, 101, 5)]
    best = max(sweep, key=lambda item: (item["f1"], -item["threshold"]))
    result["sweep"] = sweep
    result["recommendation"] = best
    result["reason"] = (
        f"Ngưỡng {best['threshold']} cho F1 cao nhất ({best['f1']}) trên nhãn của chuyên viên. "
        "Đây là khuyến nghị, không phải thay đổi đã áp dụng."
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
