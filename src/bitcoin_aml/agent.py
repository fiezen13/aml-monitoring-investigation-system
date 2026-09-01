"""Lớp trình bày Gemini cho nhánh Bitcoin — DIỄN ĐẠT structured evidence, KHÔNG bịa.

Structured evidence (RF + TreeSHAP + registry phục hồi + graph) là NGUỒN SỰ THẬT;
agent chỉ chuyển sang tiếng Việt dễ đọc. Rào chắn §37 nằm trong system prompt +
schema có kiểm soát. Không cho model tự nghĩ lý do từ mỗi điểm số.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

AGENT = "bitcoin_explainer"
PROMPT_VERSION = "btc-explain-v1-vi"

SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý AML tóm tắt kết quả mô hình cho chuyên viên điều tra, bằng tiếng Việt.\n"
    "CHỈ dùng dữ kiện trong evidence được cung cấp. TUYỆT ĐỐI không thêm thông tin ngoài.\n\n"
    "ĐƯỢC PHÉP: tóm tắt bằng chứng đặc trưng của model; dịch tên đặc trưng ĐÃ PHỤC HỒI sang "
    "diễn đạt dễ hiểu; tóm tắt ngữ cảnh đồ thị; gợi ý bước điều tra tiếp.\n"
    "KHÔNG ĐƯỢC: bịa nghĩa cho đặc trưng UNRESOLVED; khẳng định chắc chắn là rửa tiền; nói "
    "mixer/darknet/ransomware/typology khi không có bằng chứng; nhầm 'model dự đoán' với 'nhãn "
    "thật'; biến giá trị SHAP thành phần trăm xác suất/nguyên nhân; hiển thị giá trị chuẩn hoá "
    "như số BTC thô.\n"
    "Luôn đóng khung: 'mô hình đánh giá…', 'có liên kết…', 'dữ liệu cho thấy…'. Nhấn mạnh đây là "
    "tín hiệu để ƯU TIÊN RÀ SOÁT, không phải kết luận.\n\n"
    "NGÔN NGỮ: viết cho CHUYÊN VIÊN AML ngân hàng, KHÔNG biết ML. TUYỆT ĐỐI KHÔNG dùng các từ: "
    "'SHAP', 'percentile', 'feature', 'Random Forest', 'ground truth', 'nhãn thật', 'Elliptic', "
    "'z-score', 'dataset', 'chuẩn hoá', 'model risk', 'benchmark'. Dịch đặc trưng sang khái niệm "
    "nghiệp vụ: hoạt động của địa chỉ gửi/nhận tiền, cấu trúc đầu ra, cách phân bổ giá trị, đặc điểm "
    "giao dịch trước/sau.\n"
    "RÀO CHẮN SO SÁNH (rất quan trọng): CHỈ nói một yếu tố 'cao hơn X% giao dịch tham chiếu' hoặc "
    "'khác biệt so với thông thường' KHI dữ kiện có 'percentile'/'reference'. NẾU KHÔNG có mốc so "
    "sánh, TUYỆT ĐỐI KHÔNG dùng 'bất thường', 'khác đáng kể', 'cao hơn thông thường', 'hiếm gặp' — "
    "chỉ được nói yếu tố đó 'là một trong những điểm khiến hệ thống tăng mức ưu tiên rà soát'. "
    "KHÔNG nhắc hoạt động 'giao dịch tiếp theo/hạ nguồn' nếu downstream=0; KHÔNG nhắc 'giao dịch "
    "trước/thượng nguồn' nếu upstream=0."
)


class BitcoinAgentExplanation(BaseModel):
    summary: str = Field(description="2-3 câu: vì sao giao dịch cần rà soát, đóng khung nghi vấn")
    key_reasons: list[str] = Field(default_factory=list, description="3-4 gạch đầu dòng từ đặc trưng/đồ thị")
    next_steps: list[str] = Field(default_factory=list, description="Bước điều tra tiếp, từ bằng chứng thật")
    caveat: str = Field(description="Giới hạn: không kết luận rửa tiền; đặc trưng chuẩn hoá; benchmark có leakage")


def build_agent_input(row: dict[str, Any]) -> dict[str, Any]:
    """Dựng structured input (§36) từ một dòng bitcoin_scored_tx đã chấm."""
    ge = row.get("graph_evidence") or {}
    drivers = row.get("drivers") or []
    top = [
        {
            "display_name": d.get("label") or d.get("name"),
            "semantic_status": "RECOVERED_AND_VALIDATED" if d.get("meaningful") else "UNRESOLVED",
            "shap_value": round(float(d.get("contribution", 0.0)), 4),
            "direction": "INCREASE_RISK" if float(d.get("contribution", 0.0)) > 0 else "DECREASE_RISK",
            "standardized_value": round(float(d.get("value", 0.0)), 4),
        }
        for d in drivers[:5]
    ]
    gt = ge.get("ground_truth_exposure", {})
    return {
        "transaction": {"id": row.get("tx_id"), "timestep": row.get("timestep")},
        "model": {"illicit_probability": row.get("illicit_prob"), "risk_level": row.get("risk_level")},
        "model_explanation": {
            "quality": row.get("explanation_quality"),
            "top_features": top,
            "note": "Giá trị đặc trưng đã CHUẨN HOÁ (z-score); SHAP là đóng góp vào dự đoán, không phải % nhân quả.",
        },
        "graph_evidence": {
            "direct_upstream": (ge.get("direct_context") or {}).get("upstream_count"),
            "direct_downstream": (ge.get("direct_context") or {}).get("downstream_count"),
            "direct_known_illicit": gt.get("direct_known_illicit_total"),
            "nearest_known_illicit_hop": gt.get("nearest_known_illicit_hop"),
            "strength": ge.get("strength"),
            "observed_patterns": [p.get("type") for p in (ge.get("topology") or {}).get("observed_patterns", [])],
        },
        "limitations": [
            "Bộ Elliptic: nhãn 'illicit' rộng hơn 'rửa tiền'.",
            "15/166 đặc trưng chưa giải nghĩa (giữ ẩn danh).",
            "Benchmark có leakage (DFRWS 2026) — không phải tổng quát thực tế.",
        ],
    }


async def explain(service: Any, row: dict[str, Any]) -> BitcoinAgentExplanation:
    fallback = BitcoinAgentExplanation(
        summary=row.get("headline", "Giao dịch cần rà soát."),
        key_reasons=[],
        next_steps=list(row.get("recommended_steps") or []),
        caveat="Tín hiệu thống kê để ưu tiên rà soát, không phải kết luận.",
    )
    result = await service.generate_structured(
        investigation_id=f"BTC-{row.get('tx_id')}",
        agent_name=AGENT,
        prompt_version=PROMPT_VERSION,
        system_instruction=SYSTEM_INSTRUCTION,
        trusted_context=build_agent_input(row),
        untrusted_data=[],
        response_schema=BitcoinAgentExplanation,
        fallback_response=fallback,
    )
    return result.output
