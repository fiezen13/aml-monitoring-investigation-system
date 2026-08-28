"""AI soạn thảo narrative cho BÁO CÁO GIAO DỊCH ĐÁNG NGỜ (SAR).

Dùng chung Gemini (GOOGLE_API_KEY) với tầng điều tra / trợ lý, phát cùng bộ
metric observability. Sinh: (1) tóm tắt hành vi nghi vấn, (2) danh sách nhận định
MỖI nhận định kèm mã bằng chứng TRÍCH TỪ tập bằng chứng của vụ.

Rào chắn nghiêm ngặt:
* CHỈ dùng số liệu/sự kiện có trong CONTEXT — không bịa.
* MỖI nhận định phải dẫn >= 1 evidence_id CÓ THẬT trong CONTEXT.evidence; nhận
  định không dẫn được bằng chứng bị loại.
* KHÔNG kết luận "đây là rửa tiền" — chỉ nêu DẤU HIỆU nghi vấn cần rà soát; quyết
  định thuộc con người (NT3).
* Hỏng / chưa cấu hình key / rào chắn không đạt → trả None để caller tự dùng
  template tất định, không làm sập việc tạo SAR.
"""
from __future__ import annotations

import json
import re
from typing import Any

from google.genai import types

from src.api.ai_assistant import _get_client, _record_cost
from src.config import get_settings
from src.observability.metrics import METRICS, attrs

_AGENT = "sar_drafter"

_SYSTEM = (
    "Bạn là chuyên viên tuân thủ AML đang soạn BÁO CÁO GIAO DỊCH ĐÁNG NGỜ (SAR).\n"
    "Từ dữ liệu điều tra trong khối CONTEXT, hãy soạn hai phần:\n"
    "1) 'summary': đoạn tóm tắt hành vi nghi vấn 3–6 câu, khách quan, mạch lạc — nêu chủ thể, "
    "khoảng thời gian, dòng tiền chính, và vì sao đáng ngờ.\n"
    "2) 'findings': danh sách các nhận định; MỖI nhận định gồm 'text' (một câu ngắn, cụ thể) và "
    "'evidence_ids' là các mã bằng chứng lấy TỪ CONTEXT.evidence[].id.\n"
    "RÀO CHẮN BẮT BUỘC:\n"
    "- CHỈ dùng số liệu/sự kiện có trong CONTEXT; TUYỆT ĐỐI không bịa con số, tên, quốc gia, ngày.\n"
    "- MỖI finding phải có ít nhất một evidence_id CÓ THẬT trong CONTEXT.evidence; không bịa mã.\n"
    "- KHÔNG kết luận 'đây là hành vi rửa tiền'; chỉ nêu DẤU HIỆU nghi vấn cần rà soát thêm.\n"
    "- KHÔNG BAO GIỜ cộng gộp các loại tiền khác nhau thành một tổng. Vụ việc có nhiều loại "
    "tiền thì kể riêng từng loại, hoặc chỉ kể loại tiền lớn nhất và nói rõ đó là loại nào.\n"
    "- Mỗi con số tiền phải đi kèm TÊN LOẠI TIỀN ĐẦY ĐỦ đúng như trong CONTEXT (ví dụ 'Canadian "
    "Dollar', 'Ruble'). TUYỆT ĐỐI không viết 'đơn vị tiền tệ', 'đơn vị', hay bỏ trống đơn vị.\n"
    "- KHÔNG trích điểm số nội bộ của mô hình theo thang gốc (ví dụ '1.0 trên thang 0-1'). "
    "Điểm rủi ro chỉ được nêu theo thang 0-100 đúng như màn hình nghiệp vụ, hoặc mô tả bằng lời.\n"
    "- Viết tiếng Việt, giọng báo cáo tuân thủ, KHÔNG markdown, KHÔNG emoji. Không dùng thuật "
    "ngữ tiếng Anh (fan-in/fan-out, structuring, layering) — diễn đạt bằng tiếng Việt.\n"
    "Trả về đúng JSON theo schema, không kèm chữ nào khác."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence_ids"],
            },
        },
    },
    "required": ["summary", "findings"],
}


#: Cách nói né đơn vị tiền — con số mất nghĩa, và thường là dấu hiệu mô hình đã
#: cộng gộp nhiều loại tiền vào làm một.
_VAGUE_CURRENCY = re.compile(r"đơn vị tiền tệ|đơn vị tiền\b|(?<!\w)đơn vị(?!\s*(tiền|tính))", re.I)


def _hides_currency(text: str) -> bool:
    """Câu có nêu số tiền mà không gọi tên loại tiền."""
    return bool(_VAGUE_CURRENCY.search(text))


def draft_sar(context: dict[str, Any]) -> dict[str, Any] | None:
    """Sinh {summary, findings:[{text, evidence_ids}]} từ CONTEXT điều tra.

    Trả None nếu không dùng được (chưa cấu hình key, lỗi Gemini, hoặc rào chắn
    loại hết nhận định) — caller phải tự fallback template tất định.
    """
    settings = get_settings()
    if not settings.google_api_key:
        return None
    valid_ev = {str(e.get("id")) for e in (context.get("evidence") or []) if e.get("id")}
    if not valid_ev:
        return None
    contents = "<CONTEXT>\n" + json.dumps(context, ensure_ascii=False, default=str, sort_keys=True) + "\n</CONTEXT>"
    try:
        resp = _get_client(settings).models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                response_mime_type="application/json",
                response_schema=_SCHEMA,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        data = json.loads(resp.text or "{}")
        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", None)
        out_tok = getattr(usage, "candidates_token_count", None)
        METRICS.gemini_requests.add(1, attrs(agent=_AGENT, model=settings.gemini_model, status="success"))
        if in_tok:
            METRICS.gemini_input_tokens.add(in_tok, attrs(agent=_AGENT, model=settings.gemini_model))
        if out_tok:
            METRICS.gemini_output_tokens.add(out_tok, attrs(agent=_AGENT, model=settings.gemini_model))
        _record_cost(settings, in_tok, out_tok)

        summary = str(data.get("summary") or "").strip()
        findings: list[dict[str, Any]] = []
        for item in data.get("findings") or []:
            text = str(item.get("text") or "").strip()
            # Rào chắn: chỉ giữ evidence_id CÓ THẬT trong tập bằng chứng của vụ.
            ev = [e for e in (item.get("evidence_ids") or []) if str(e) in valid_ev]
            if text and ev:
                findings.append({"text": text, "evidence_ids": ev})
        if not summary or not findings:
            return None
        # Rào chắn tất định cho ĐƠN VỊ TIỀN. Lời nhắc trong prompt là mong đợi,
        # không phải bảo đảm; mà "hơn 5 tỷ đơn vị tiền tệ" thì đã lọt vào một bản
        # PDF gửi ra ngoài. Vi phạm thì bỏ bản AI, caller dùng template tất định.
        if _hides_currency(summary) or any(_hides_currency(f["text"]) for f in findings):
            METRICS.gemini_requests.add(1, attrs(agent=_AGENT, model=settings.gemini_model, status="rejected"))
            return None
        return {"summary": summary, "findings": findings}
    except Exception as exc:  # noqa: BLE001 — trả None, caller fallback template
        METRICS.gemini_requests.add(1, attrs(agent=_AGENT, model=settings.gemini_model, status="failure"))
        METRICS.gemini_errors.add(1, attrs(agent=_AGENT, error_type=type(exc).__name__))
        return None
