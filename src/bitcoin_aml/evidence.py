"""Interpretable Investigation Evidence Layer cho nhánh Bitcoin (Elliptic).

Chạy SONG SONG Random Forest, KHÔNG thay và KHÔNG retrain model. Mục tiêu: trả
lời câu hỏi nghiệp vụ mà SHAP trên đặc trưng ẩn danh không trả lời được — tiền
đi từ đâu, đi tiếp đâu, gần ca bất hợp pháp đã biết tới mức nào, có cấu trúc đồ
thị đáng chú ý không.

Ba lớp GIỮ RIÊNG, tuyệt đối không gộp thành một điểm:
  * MODEL RISK          — P(illicit) của RF (ở module khác).
  * INVESTIGATION EVIDENCE — bằng chứng đồ thị tính SAU suy luận (module này).
  * MODEL EXPLAINABILITY  — chất lượng giải thích SHAP (ở explain.py).

Chống rò nhãn (label leakage): bằng chứng đồ thị dùng nhãn thật của LÁNG GIỀNG
chỉ để HIỂN THỊ ngữ cảnh điều tra — KHÔNG bao giờ được đưa ngược vào đặc trưng
của RF. Module này không chạm tới predictor; nó nhận đồ thị + nhãn đã có sẵn.

Không bịa nghĩa: không gọi cấu trúc đồ thị là "đã rửa tiền". Fan-in/fan-out… chỉ
là "cấu trúc quan sát được" (observed structure), không phải kết luận tội phạm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Ngưỡng cấu trúc (chỉnh được, không phải nhãn ground-truth) -------------
FAN_MIN_DEGREE = 5  # bậc tối thiểu để gọi là gom/toả
FAN_RATIO = 2.0  # một chiều phải lớn hơn chiều kia bấy nhiêu lần
GATHER_SCATTER_MIN = 5  # vừa nhiều vào vừa nhiều ra
CHAIN_MIN_LEN = 4  # số giao dịch liên tiếp tối thiểu để gọi là chuỗi dài
MODEL_HIGH_RISK_PROB = 0.5  # ngưỡng coi một láng giềng ĐÃ CHẤM là rủi ro cao

# --- Giới hạn duyệt đồ thị (không traverse vô hạn) --------------------------
MAX_HOP = 2  # phạm vi tổng hợp vùng lân cận
NEAREST_SEARCH_HOP = 3  # phạm vi tìm hop gần nhất tới ca bất hợp pháp
NODE_BUDGET = 600  # trần số nút duyệt cho mỗi giao dịch (an toàn với nút hub)
CHAIN_MAX_LEN = 8  # trần độ dài chuỗi truy theo


@dataclass(frozen=True)
class GraphMaps:
    """Chỉ mục kề + nhãn, dựng MỘT LẦN rồi tra nhiều lần (không dựng lại mỗi tx)."""

    succ: dict[str, list[str]]
    pred: dict[str, list[str]]
    known_illicit: set[str]  # nhãn THẬT illicit (Elliptic ground truth)
    known_licit: set[str]  # nhãn THẬT licit
    model_risk: dict[str, float]  # tx đã chấm → P(illicit); chỉ tập test có
    model_high_risk_set: set[str]  # tx đã chấm có P(illicit) ≥ ngưỡng (tính sẵn 1 lần)

    @classmethod
    def build(
        cls,
        succ: dict[str, list[str]],
        pred: dict[str, list[str]],
        known_illicit: set[str],
        known_licit: set[str],
        model_risk: dict[str, float],
    ) -> GraphMaps:
        high = {t for t, p in model_risk.items() if p >= MODEL_HIGH_RISK_PROB}
        return cls(succ, pred, known_illicit, known_licit, model_risk, high)


def status_of(tx: str, maps: GraphMaps) -> str:
    """Trạng thái một giao dịch, PHÂN BIỆT ground-truth với model-prediction.

    Ground truth luôn thắng model prediction khi hiển thị: một nút vừa có nhãn
    thật illicit vừa được model chấm thì gọi là KNOWN_ILLICIT.
    """
    if tx in maps.known_illicit:
        return "KNOWN_ILLICIT"
    if tx in maps.known_licit:
        return "KNOWN_LICIT"
    prob = maps.model_risk.get(tx)
    if prob is None:
        return "UNKNOWN"
    return "MODEL_HIGH_RISK" if prob >= MODEL_HIGH_RISK_PROB else "MODEL_LOW_RISK"


def _bfs_layers(start: str, adj: dict[str, list[str]], max_hop: int) -> list[set[str]]:
    """Các lớp theo hop (1..max_hop) theo MỘT hướng, có trần số nút.

    Trả về danh sách tập nút ở đúng từng hop (không gồm start). Dừng khi vượt
    NODE_BUDGET để an toàn với nút bậc lớn.
    """
    visited = {start}
    frontier = {start}
    layers: list[set[str]] = []
    budget = NODE_BUDGET
    for _ in range(max_hop):
        nxt: set[str] = set()
        for node in frontier:
            for nb in adj.get(node, ()):  # noqa: SIM118
                if nb not in visited:
                    visited.add(nb)
                    nxt.add(nb)
                    budget -= 1
                    if budget <= 0:
                        break
            if budget <= 0:
                break
        layers.append(nxt)
        frontier = nxt
        if not nxt or budget <= 0:
            break
    while len(layers) < max_hop:
        layers.append(set())
    return layers


def _breakdown(nodes: set[str], maps: GraphMaps) -> dict[str, int]:
    counts = {"total": len(nodes), "known_illicit": 0, "known_licit": 0, "model_high_risk": 0, "unknown": 0}
    for tx in nodes:
        st = status_of(tx, maps)
        if st == "KNOWN_ILLICIT":
            counts["known_illicit"] += 1
        elif st == "KNOWN_LICIT":
            counts["known_licit"] += 1
        elif st == "MODEL_HIGH_RISK":
            counts["model_high_risk"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _nearest_hop(up_layers: list[set[str]], down_layers: list[set[str]], target_set: set[str]) -> int | None:
    """Hop nhỏ nhất (cả thượng lẫn hạ nguồn) tới một tập nút, hoặc None nếu ngoài phạm vi."""
    for hop in range(max(len(up_layers), len(down_layers))):
        up = up_layers[hop] if hop < len(up_layers) else set()
        down = down_layers[hop] if hop < len(down_layers) else set()
        if (up | down) & target_set:
            return hop + 1
    return None


def _linear_chain_length(start: str, succ: dict[str, list[str]], pred: dict[str, list[str]]) -> int:
    """Độ dài chuỗi truyền-thẳng hạ nguồn: các nút trung gian có in≈out≈1.

    Đếm số giao dịch liên tiếp mà tiền "đi thẳng qua" (một vào, một ra). Có trần
    để không đi vô hạn khi gặp vòng.
    """
    length = 1
    node = start
    seen = {start}
    while length < CHAIN_MAX_LEN:
        outs = succ.get(node, [])
        if len(outs) != 1:
            break
        nxt = outs[0]
        if nxt in seen or len(pred.get(nxt, [])) != 1:
            break
        seen.add(nxt)
        node = nxt
        length += 1
    return length


def detect_topology(in_degree: int, out_degree: int, chain_len: int) -> list[dict[str, Any]]:
    """Cấu trúc đồ thị QUAN SÁT ĐƯỢC (rule tất định). KHÔNG phải nhãn tội phạm.

    Mọi mẫu đều đóng khung 'structural' — chỉ mô tả hình dạng luồng, không kết
    luận rửa tiền. Ngưỡng ở hằng số module (chỉnh được).
    """
    patterns: list[dict[str, Any]] = []
    if in_degree >= GATHER_SCATTER_MIN and out_degree >= GATHER_SCATTER_MIN:
        patterns.append(
            {
                "type": "GATHER_SCATTER",
                "confidence": "STRUCTURAL",
                "evidence": {"in_degree": in_degree, "out_degree": out_degree},
            }
        )
    else:
        if in_degree >= FAN_MIN_DEGREE and in_degree > FAN_RATIO * max(out_degree, 1):
            patterns.append(
                {
                    "type": "FAN_IN",
                    "confidence": "STRUCTURAL",
                    "evidence": {"in_degree": in_degree, "out_degree": out_degree},
                }
            )
        if out_degree >= FAN_MIN_DEGREE and out_degree > FAN_RATIO * max(in_degree, 1):
            patterns.append(
                {
                    "type": "FAN_OUT",
                    "confidence": "STRUCTURAL",
                    "evidence": {"in_degree": in_degree, "out_degree": out_degree},
                }
            )
    if chain_len >= CHAIN_MIN_LEN:
        patterns.append({"type": "LINEAR_CHAIN", "confidence": "STRUCTURAL", "evidence": {"chain_length": chain_len}})
    return patterns


def evidence_strength(ev: dict[str, Any]) -> str:
    """Xếp hạng SỨC MẠNH BẰNG CHỨNG ĐIỀU TRA (tất định) — TÁCH khỏi điểm rủi ro.

    KHÔNG cộng thành xác suất AML. STRONG đòi hỏi phơi nhiễm ground-truth thật;
    MODERATE cho ca gần ground-truth vài hop hoặc nhiều láng giềng model rủi ro
    hoặc có cấu trúc rõ; WEAK cho tín hiệu nhẹ; NONE khi vùng lân cận sạch/rời rạc.
    """
    gt = ev["ground_truth_exposure"]
    mr = ev["model_risk_context"]
    two = ev["neighborhood"]["two_hop"]
    topo = ev["topology"]["observed_patterns"]

    if gt["direct_known_illicit_total"] > 0 or two["known_illicit"] >= 2:
        return "STRONG"
    if (
        (gt["nearest_known_illicit_hop"] is not None)
        or mr["direct_high_risk_total"] >= 2
        or two["model_high_risk"] >= 2
        or bool(topo)
    ):
        return "MODERATE"
    if mr["direct_high_risk_total"] >= 1 or two["model_high_risk"] >= 1:
        return "WEAK"
    return "NONE"


def build_graph_evidence(tx_id: str, maps: GraphMaps) -> dict[str, Any]:
    """Đối tượng bằng chứng đồ thị có cấu trúc cho MỘT giao dịch (§20).

    Tất cả tính SAU suy luận, từ đồ thị + nhãn có sẵn — không đầu vào nào của RF.
    """
    up_direct = list(dict.fromkeys(maps.pred.get(tx_id, [])))  # thượng nguồn (tiền tới từ)
    down_direct = list(dict.fromkeys(maps.succ.get(tx_id, [])))  # hạ nguồn (tiền đi tới)
    in_degree, out_degree = len(up_direct), len(down_direct)

    # Duyệt tới NEAREST_SEARCH_HOP MỘT LẦN mỗi hướng rồi tái dùng (thay vì duyệt
    # lại cho từng phép tìm hop) — giữ chi phí thấp trên 16k giao dịch.
    up_layers = _bfs_layers(tx_id, maps.pred, NEAREST_SEARCH_HOP)
    down_layers = _bfs_layers(tx_id, maps.succ, NEAREST_SEARCH_HOP)

    def direct_status_count(nodes: list[str], statuses: set[str]) -> int:
        return sum(1 for n in nodes if status_of(n, maps) in statuses)

    # Vùng lân cận theo hop (gộp hai hướng, không trùng start).
    one_hop = up_layers[0] | down_layers[0]
    two_hop = one_hop | up_layers[1] | down_layers[1]

    # Phân phối rủi ro MODEL của láng giềng ĐÃ CHẤM (không trộn ground truth).
    neigh_probs = [maps.model_risk[n] for n in one_hop if n in maps.model_risk]
    high_risk_neighbours = sum(1 for p in neigh_probs if p >= MODEL_HIGH_RISK_PROB)

    chain_len = _linear_chain_length(tx_id, maps.succ, maps.pred)

    evidence = {
        "transaction_id": tx_id,
        "direct_context": {
            "upstream_count": in_degree,
            "downstream_count": out_degree,
            "total": len(one_hop),
        },
        "ground_truth_exposure": {
            "direct_known_illicit_upstream": direct_status_count(up_direct, {"KNOWN_ILLICIT"}),
            "direct_known_illicit_downstream": direct_status_count(down_direct, {"KNOWN_ILLICIT"}),
            "direct_known_illicit_total": direct_status_count(up_direct + down_direct, {"KNOWN_ILLICIT"}),
            "nearest_known_illicit_hop": _nearest_hop(up_layers, down_layers, maps.known_illicit),
        },
        "model_risk_context": {
            "direct_high_risk_upstream": direct_status_count(up_direct, {"MODEL_HIGH_RISK"}),
            "direct_high_risk_downstream": direct_status_count(down_direct, {"MODEL_HIGH_RISK"}),
            "direct_high_risk_total": direct_status_count(up_direct + down_direct, {"MODEL_HIGH_RISK"}),
            "nearest_model_high_risk_hop": _nearest_hop(up_layers, down_layers, maps.model_high_risk_set),
            "mean_neighbor_risk": round(sum(neigh_probs) / len(neigh_probs), 4) if neigh_probs else None,
            "max_neighbor_risk": round(max(neigh_probs), 4) if neigh_probs else None,
            "high_risk_neighbor_count": high_risk_neighbours,
        },
        "neighborhood": {
            "one_hop": _breakdown(one_hop, maps),
            "two_hop": _breakdown(two_hop, maps),
        },
        "topology": {
            "in_degree": in_degree,
            "out_degree": out_degree,
            "total_degree": in_degree + out_degree,
            "max_linear_chain": chain_len,
            "observed_patterns": detect_topology(in_degree, out_degree, chain_len),
        },
    }
    evidence["two_hop_known_illicit"] = evidence["neighborhood"]["two_hop"]["known_illicit"]
    evidence["strength"] = evidence_strength(evidence)
    return evidence


# --- Diễn giải TẤT ĐỊNH từ bằng chứng (trước Agent) -------------------------
# Mỗi lý do mang BADGE nguồn để chuyên viên biết căn cứ đến từ đâu:
#   GROUND_TRUTH · GRAPH · MODEL · PREDICTION · TEMPORAL
_TOPOLOGY_WORDING: dict[str, str] = {
    "FAN_IN": "Quan sát thấy cấu trúc gom luồng: nhiều giao dịch đi vào một điểm.",
    "FAN_OUT": "Quan sát thấy cấu trúc phân tán: một nguồn toả ra nhiều giao dịch kế tiếp.",
    "GATHER_SCATTER": "Quan sát thấy cấu trúc gom-rồi-toả: vừa nhiều luồng vào vừa nhiều luồng ra.",
    "LINEAR_CHAIN": "Dòng giao dịch đi thẳng qua nhiều giao dịch liên tiếp.",
}


def evidence_reasons(ev: dict[str, Any], model_prob: float, explain_quality: str) -> list[dict[str, Any]]:
    """Danh sách lý do TẤT ĐỊNH, ưu tiên bằng chứng điều tra mạnh trước tín hiệu
    ẩn danh. Chỉ sinh lý do khi điều kiện THỰC SỰ đúng (không thẻ giả).

    Thứ tự ưu tiên (§25): phơi nhiễm illicit trực tiếp > lân cận rủi ro > láng
    giềng model rủi ro > cấu trúc đồ thị > tín hiệu ẩn danh của model.
    """
    gt = ev["ground_truth_exposure"]
    mr = ev["model_risk_context"]
    two = ev["neighborhood"]["two_hop"]
    topo = ev["topology"]
    out: list[dict[str, Any]] = []

    if gt["direct_known_illicit_total"] > 0:
        out.append(
            {
                "priority": 1,
                "badges": ["GROUND_TRUTH", "GRAPH"],
                "title": "Kết nối trực tiếp với giao dịch bất hợp pháp đã biết",
                "text": (
                    f"{gt['direct_known_illicit_total']} giao dịch nối trực tiếp mang NHÃN THẬT illicit trong "
                    f"Elliptic ({gt['direct_known_illicit_upstream']} thượng nguồn, "
                    f"{gt['direct_known_illicit_downstream']} hạ nguồn). Khoảng cách: 1 hop."
                ),
            }
        )
    elif gt["nearest_known_illicit_hop"] is not None:
        out.append(
            {
                "priority": 2,
                "badges": ["GROUND_TRUTH", "GRAPH"],
                "title": "Có giao dịch bất hợp pháp đã biết ở gần",
                "text": f"Trong phạm vi {gt['nearest_known_illicit_hop']} hop có giao dịch mang nhãn thật illicit.",
            }
        )

    if two["known_illicit"] + two["model_high_risk"] >= 2:
        out.append(
            {
                "priority": 3,
                "badges": ["GRAPH"],
                "title": "Vùng lân cận có mức rủi ro cao",
                "text": (
                    f"Trong 2 hop có {two['known_illicit']} giao dịch nhãn thật illicit và "
                    f"{two['model_high_risk']} giao dịch model dự đoán rủi ro cao."
                ),
            }
        )
    elif mr["direct_high_risk_total"] > 0:
        out.append(
            {
                "priority": 4,
                "badges": ["PREDICTION", "GRAPH"],
                "title": "Láng giềng bị model dự đoán rủi ro cao",
                "text": (
                    f"{mr['direct_high_risk_total']} láng giềng trực tiếp bị MODEL DỰ ĐOÁN rủi ro cao "
                    "(chưa phải nhãn thật — cần xác minh)."
                ),
            }
        )

    for p in topo["observed_patterns"]:
        out.append(
            {
                "priority": 5,
                "badges": ["GRAPH"],
                "title": "Cấu trúc đồ thị quan sát được",
                "text": (
                    f"{_TOPOLOGY_WORDING.get(p['type'], 'Cấu trúc đồ thị đáng chú ý.')} "
                    f"(vào {topo['in_degree']} · ra {topo['out_degree']}"
                    + (f" · chuỗi {topo['max_linear_chain']} bước" if p["type"] == "LINEAR_CHAIN" else "")
                    + ")."
                ),
            }
        )

    # Luôn có: tín hiệu model, nhưng ĐỨNG SAU bằng chứng đồ thị nếu có.
    out.append(
        {
            "priority": 6,
            "badges": ["MODEL"],
            "title": "Tín hiệu nội bộ của mô hình",
            "text": (
                f"Random Forest chấm {round(model_prob * 100)}% khả năng bất hợp pháp; phần lớn đóng góp SHAP đến "
                f"từ đặc trưng Elliptic ẩn danh (chất lượng giải thích: {explain_quality})."
            ),
        }
    )

    out.sort(key=lambda r: r["priority"])
    return out[:5]


def recommended_steps(ev: dict[str, Any]) -> list[str]:
    """Gợi ý điều tra sinh TỪ bằng chứng thật (không checklist chung chung)."""
    gt = ev["ground_truth_exposure"]
    mr = ev["model_risk_context"]
    topo = ev["topology"]
    steps: list[str] = []
    if gt["direct_known_illicit_total"] > 0:
        steps.append("Rà soát đường nối trực tiếp tới giao dịch bất hợp pháp đã biết.")
    elif gt["nearest_known_illicit_hop"] is not None:
        steps.append(f"Mở rộng đồ thị tới {gt['nearest_known_illicit_hop']} hop để xem đường tới ca illicit đã biết.")
    else:
        steps.append("Mở rộng đồ thị 2 hop lên thượng nguồn và xuống hạ nguồn.")
    if mr["direct_high_risk_total"] > 0:
        steps.append("Xác minh các láng giềng bị model dự đoán rủi ro cao (chưa có nhãn thật).")
    types = {p["type"] for p in topo["observed_patterns"]}
    if "FAN_OUT" in types or "GATHER_SCATTER" in types:
        steps.append("Theo dõi luồng phân tán hạ nguồn (nhiều giao dịch nhận tiền).")
    if "FAN_IN" in types or "GATHER_SCATTER" in types:
        steps.append("Kiểm tra các nguồn gom tiền ở thượng nguồn.")
    if "LINEAR_CHAIN" in types:
        steps.append(f"Truy theo chuỗi hạ nguồn {topo['max_linear_chain']} giao dịch liên tiếp.")
    steps.append("Đối chiếu thông tin ví/thực thể nếu có nguồn ngoài — Elliptic ẩn danh nên không cung cấp.")
    return steps
