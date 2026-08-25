"""Lớp DETERMINISTIC hợp nhất: drivers (SHAP) + registry (ngữ nghĩa phục hồi) +
phân phối train (percentile) → danh sách RiskReason có cấu trúc cho UI/AI.

Nguyên tắc (audit §4/§5/§6/§7/§8/§20):
* SHAP dương KHÔNG mặc định là "bất thường". Chỉ nói "cao hơn P{n}" KHI có
  percentile thật; không có thì chỉ nói direction ("làm tăng mức ưu tiên").
* Nhóm phụ thuộc GIAO DỊCH TRƯỚC/SAU chỉ xuất hiện khi đồ thị có chiều đó.
* Đặc trưng dựa trên GIAO DỊCH SAU (successor, DFRWS 131–166) đánh dấu temporal
  `after_transaction` — không phải thông tin có tại thời điểm giao dịch.
* Enrich ở READ-TIME (không re-score): chỉ cần drivers đã lưu + registry + dist.
"""
from __future__ import annotations

import bisect
from functools import lru_cache
from typing import Any

from src.bitcoin_aml.elliptic_registry import registry_by_model_index

# category registry (elliptic_registry) → trình bày nghiệp vụ + chiều đồ thị + temporal.
# side: dùng để (a) chặn khi count=0, (b) highlight đồ thị. temporal: available_at_transaction_time
# | after_transaction. Address-history dựng từ ảnh chụp chuỗi khối → ghi chú snapshot.
_CATEGORY_META: dict[str, dict[str, str]] = {
    "TRANSACTION_INTRINSIC": {"title": "Đặc điểm nội tại của giao dịch", "side": "local", "temporal": "available_at_transaction_time"},
    "INPUT_VALUE_STATS": {"title": "Cách hình thành nguồn tiền đầu vào", "side": "local", "temporal": "available_at_transaction_time"},
    "OUTPUT_VALUE_STATS": {"title": "Cách phân bổ giá trị ở các đầu nhận", "side": "local", "temporal": "available_at_transaction_time"},
    "INPUT_ADDRESS_HISTORY": {"title": "Hoạt động của các địa chỉ gửi tiền", "side": "upstream", "temporal": "available_at_transaction_time"},
    "OUTPUT_ADDRESS_HISTORY": {"title": "Hoạt động của các địa chỉ nhận tiền", "side": "downstream", "temporal": "available_at_transaction_time"},
    "UPSTREAM_TRANSACTION_AGGREGATE": {"title": "Đặc điểm của các giao dịch nguồn", "side": "upstream_tx", "temporal": "available_at_transaction_time"},
    "DOWNSTREAM_TRANSACTION_AGGREGATE": {"title": "Đặc điểm của các giao dịch tiếp theo", "side": "downstream_tx", "temporal": "after_transaction"},
}
# TIME / UNRESOLVED → bỏ khỏi lý do nghiệp vụ.


@lru_cache(maxsize=1)
def _registry() -> dict[int, Any]:
    return registry_by_model_index()


@lru_cache(maxsize=1)
def _name_to_index() -> dict[str, int]:
    """Tên HIỂN THỊ (display_name) → model_index. Vì driver có thể lưu `name`/`label`
    dạng tên hiển thị (script build_elliptic_scored) thay vì 'feature_N' (stream)."""
    return {m.display_name: m.model_index for m in _registry().values() if m.display_name}


def _resolve_index(driver: dict[str, Any]) -> int | None:
    """Suy model_index từ driver, chấp nhận cả 'feature_N'/'timestep' lẫn tên hiển thị."""
    name = str(driver.get("name", ""))
    if name == "timestep":
        return 0
    if name.startswith("feature_"):
        try:
            return int(name.split("_", 1)[1])
        except ValueError:
            pass
    # fallback: khớp theo tên hiển thị (name hoặc label).
    n2i = _name_to_index()
    for key in (driver.get("label"), name):
        if key and key in n2i:
            return n2i[key]
    return None


def _dist_col(model_index: int) -> str:
    """Cột trong feature_distribution.json ứng với model_index (timestep=0)."""
    return "timestep" if model_index == 0 else f"feature_{model_index}"


def _percentile(value: float, pct_map: dict[str, float]) -> float | None:
    if not pct_map:
        return None
    grid = sorted((int(k), v) for k, v in pct_map.items())
    xs = [v for _, v in grid]
    ps = [p for p, _ in grid]
    i = bisect.bisect_left(xs, value)
    if i <= 0:
        return ps[0] / 100.0
    if i >= len(xs):
        return ps[-1] / 100.0
    x0, x1, p0, p1 = xs[i - 1], xs[i], ps[i - 1], ps[i]
    frac = 0.0 if x1 == x0 else (value - x0) / (x1 - x0)
    return (p0 + frac * (p1 - p0)) / 100.0


def _contribution_band(rank: int) -> str:
    return "very_high" if rank == 0 else "high" if rank == 1 else "medium" if rank == 2 else "low"


_BAND_VI = {"very_high": "RẤT MẠNH", "high": "MẠNH", "medium": "VỪA", "low": "THẤP"}


def build_risk_reasons(
    drivers: list[dict[str, Any]],
    graph_in_degree: int,
    graph_out_degree: int,
    distribution: dict[str, dict[str, Any]] | None = None,
    max_reasons: int = 5,
) -> list[dict[str, Any]]:
    """Danh sách RiskReason (đã gộp theo nhóm, chỉ nhóm LÀM TĂNG mức ưu tiên).

    `distribution` là feature_distribution.json (key = tên cột) để lấy percentile;
    None thì reason không có reference (chỉ direction).
    """
    reg = _registry()
    groups: dict[str, dict[str, Any]] = {}
    for d in drivers:
        if not d.get("meaningful") or d.get("label") is None:
            continue
        contribution = float(d.get("contribution", 0.0))
        if contribution <= 0:  # chỉ yếu tố LÀM TĂNG
            continue
        idx = _resolve_index(d)
        if idx is None or idx not in reg:
            continue
        meta = reg[idx]
        cat = meta.category
        cmeta = _CATEGORY_META.get(cat)
        if cmeta is None:  # TIME / UNRESOLVED
            continue
        # Chặn nhóm giao dịch trước/sau khi đồ thị không có chiều đó (§7/§8).
        if cmeta["side"] == "upstream_tx" and graph_in_degree <= 0:
            continue
        if cmeta["side"] == "downstream_tx" and graph_out_degree <= 0:
            continue
        g = groups.setdefault(cat, {"cat": cat, "meta": cmeta, "weight": 0.0, "top": None, "feature_ids": []})
        g["weight"] += abs(contribution)
        g["feature_ids"].append(meta.dfrws_feature)
        if g["top"] is None or abs(contribution) > abs(float(g["top"].get("contribution", 0.0))):
            g["top"] = {**d, "model_index": idx}

    ranked = sorted(groups.values(), key=lambda x: x["weight"], reverse=True)[:max_reasons]
    out: list[dict[str, Any]] = []
    for rank, g in enumerate(ranked):
        cmeta = g["meta"]
        top = g["top"] or {}
        band = _contribution_band(rank)
        # Percentile CHỈ khi có phân phối cho cột đó.
        pct: int | None = None
        if distribution is not None and top.get("model_index") is not None:
            entry = distribution.get(_dist_col(int(top["model_index"]))) or {}
            p = _percentile(float(top.get("value", 0.0)), entry.get("percentiles") or {})
            if p is not None:
                pct = round(p * 100)
        # §9: SHAP dương KHÔNG có nghĩa 'giá trị cao'. Chỉ so sánh khi giá trị nằm ở
        # ĐUÔI RÕ của phân phối tham chiếu (≥90 → cao hơn; ≤10 → thấp hơn). Ở giữa
        # thì KHÔNG khẳng định 'cao/thấp/bất thường' — chỉ direction.
        reference: dict[str, Any] | None = None
        grounded = ""
        if pct is not None and pct >= 90:
            grounded = f" (cao hơn {pct}% giao dịch trong tập tham chiếu)"
            reference = {"population": "training_reference", "percentile": pct}
        elif pct is not None and pct <= 10:
            grounded = f" (thấp hơn {100 - pct}% giao dịch trong tập tham chiếu)"
            reference = {"population": "training_reference", "percentile": pct}
        text = f"{cmeta['title']}{grounded} là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát cho giao dịch này."
        out.append(
            {
                "id": f"rr-{g['cat'].lower()}",
                "category": g["cat"],
                "title": cmeta["title"],
                "side": cmeta["side"],
                "feature_ids": sorted(set(g["feature_ids"])),
                "reference": reference,
                "shap_direction": "increase_risk",
                "contribution": band,
                "contribution_label": _BAND_VI[band],
                "temporal_availability": cmeta["temporal"],
                "after_transaction": cmeta["temporal"] == "after_transaction",
                "investigator_text": text,
            }
        )
    return out
