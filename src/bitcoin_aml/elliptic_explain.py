"""Explanation engine cho RF trên Original Elliptic — semantic + percentile.

Kết hợp: TreeSHAP per-instance (đóng góp có dấu) + registry ngữ nghĩa PHỤC HỒI
(DFRWS 2026) + phân phối TRAIN (percentile). Ưu tiên đặc trưng ĐÃ PHỤC HỒI; đặc
trưng UNRESOLVED vẫn hiển thị nhưng gắn rõ "chưa giải nghĩa" — KHÔNG bịa.

Nguyên tắc (§8, §12, §20): giá trị đã chuẩn hoá → hiển thị standardized value +
percentile, KHÔNG giả làm raw BTC. SHAP giải thích HÀNH VI MODEL, không chứng
minh typology AML.
"""

from __future__ import annotations

import bisect
from typing import Any

from src.bitcoin_aml.elliptic_registry import registry_by_model_index


def _percentile(value: float, pct_map: dict[str, float]) -> float:
    """Xấp xỉ percentile của value theo các mốc đã lưu (1,5,10,25,50,75,90,95,99)."""
    grid = sorted((int(k), v) for k, v in pct_map.items())
    xs = [v for _, v in grid]
    ps = [p for p, _ in grid]
    i = bisect.bisect_left(xs, value)
    if i <= 0:
        return ps[0] / 100.0
    if i >= len(xs):
        return ps[-1] / 100.0
    # nội suy tuyến tính giữa hai mốc
    x0, x1, p0, p1 = xs[i - 1], xs[i], ps[i - 1], ps[i]
    frac = 0.0 if x1 == x0 else (value - x0) / (x1 - x0)
    return (p0 + frac * (p1 - p0)) / 100.0


def top_reasons(
    feature_values: list[float],
    shap_values: list[float],
    distribution: dict[str, dict[str, Any]],
    feature_cols: list[str],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Top-k đặc trưng theo |SHAP|, kèm tên phục hồi + percentile train + hướng.

    ``feature_cols`` là thứ tự cột model (timestep, feature_1..165) — khớp
    distribution keys. Registry map theo model_index (0-based).
    """
    reg = registry_by_model_index()
    order = sorted(range(len(shap_values)), key=lambda i: abs(shap_values[i]), reverse=True)[:top_k]
    out: list[dict[str, Any]] = []
    for i in order:
        meta = reg[i]
        col = feature_cols[i]
        pct = _percentile(feature_values[i], distribution[col]["percentiles"]) if col in distribution else None
        out.append(
            {
                "model_index": i,
                "dfrws_feature": meta.dfrws_feature,
                "display_name": meta.display_name,
                "category": meta.category,
                "semantic_status": meta.semantic_status,
                "official_elliptic_semantic": meta.official_elliptic_semantic,
                "source": meta.source,
                "standardized_value": round(float(feature_values[i]), 4),
                "value_representation": meta.value_representation,
                "training_percentile": round(pct, 4) if pct is not None else None,
                "shap_value": round(float(shap_values[i]), 5),
                "direction": "INCREASE_RISK" if shap_values[i] > 0 else "DECREASE_RISK",
            }
        )
    return out
