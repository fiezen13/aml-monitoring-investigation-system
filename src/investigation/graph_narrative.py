"""Đọc hộ chuyên viên một vùng đồ thị dòng tiền.

Vì sao cần
----------
Màn hình đồ thị vẽ đúng nhưng không giải thích gì. Chuyên viên nhìn vào một mớ
đỉnh và mũi tên rồi phải tự trả lời: tiền vào từ đâu, đi đâu, ai đứng giữa, vì
sao chỗ này đáng nghi, và nên nhìn vào đâu trước. Không ai làm được việc đó
trong vài phút, nên cả màn hình trở thành trang trí.

Hai tầng, cố ý tách rời
-----------------------
1. ``read_neighbourhood`` — đo tất định trên cơ sở dữ liệu. Mọi con số trong
   bản kể đều sinh ra ở đây, không ở đâu khác.
2. ``narrate`` — nhờ mô hình diễn đạt lại phần đo ấy thành tiếng Việt dễ đọc.
   Mô hình **không** được cấp quyền tra dữ liệu và không thấy gì ngoài phần đo,
   nên nó không có chỗ nào để bịa ra một con số.

Mô hình hỏng, mạng đứt, hết hạn mức — bản kể vẫn có, vì tầng 1 tự dựng được một
bản đầy đủ làm phương án dự phòng. Màn hình không bao giờ trống.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.llm import GeminiService, get_gemini_service
from src.investigation.prompts import get_prompt

logger = logging.getLogger("fin07.graph_narrative")

#: Số đối tác liệt kê đích danh trong bản kể. Nhiều hơn thì câu văn thành danh
#: sách, và chuyên viên vẫn phải tự chọn — đúng việc mà bản kể sinh ra để tránh.
TOP_N = 4
#: Bao nhiêu đối tác trở lên thì gọi là "nhiều nguồn" / "toả rộng". Cùng ngưỡng
#: với phần diễn giải cảnh báo, để hai màn hình không mô tả một tài khoản bằng
#: hai từ khác nhau.
MANY = 3
WIDE = 5


class GraphNarrative(BaseModel):
    """Bốn câu trả lời mà một người nhìn đồ thị cần, không hơn."""

    flow_in: str = Field(default="", max_length=1200)
    flow_out: str = Field(default="", max_length=1200)
    why_suspicious: list[str] = Field(default_factory=list, max_length=4)
    how_to_read: list[str] = Field(default_factory=list, max_length=4)


_NEIGHBOURS_SQL = """
    SELECT to_account_key AS counterparty, 'out' AS direction,
           count(*) AS n, sum(amount) AS total, max(currency) AS currency
      FROM transaction
     WHERE from_account_key = :account AND occurred_at > :start AND occurred_at <= :as_of
     GROUP BY 1
    UNION ALL
    SELECT from_account_key, 'in', count(*), sum(amount), max(currency)
      FROM transaction
     WHERE to_account_key = :account AND occurred_at > :start AND occurred_at <= :as_of
     GROUP BY 1
"""

#: Tài khoản nhận tiền từ tâm rồi chuyển tiếp cho người khác — chặng giữa của
#: dòng tiền. Đây chính là thứ chuyên viên gọi là "trung gian", và là thứ nhìn
#: vào hình không thấy được: trên màn hình nó chỉ là một đỉnh như mọi đỉnh khác.
_INTERMEDIARY_SQL = """
    WITH forwarded AS (
        SELECT t2.from_account_key AS middle, t2.to_account_key AS onward,
               count(*) AS n, sum(t2.amount) AS total
          FROM transaction t2
         WHERE t2.from_account_key = ANY(:neighbours)
           AND t2.to_account_key <> :account
           AND t2.occurred_at > :start AND t2.occurred_at <= :as_of
         GROUP BY 1, 2
    )
    SELECT middle, count(DISTINCT onward) AS onward_count,
           sum(n) AS onward_transactions, sum(total) AS onward_amount
      FROM forwarded GROUP BY 1 ORDER BY sum(total) DESC LIMIT :limit
"""


def read_neighbourhood(session: Session, account_key: str, *, as_of: datetime, window_days: int = 30) -> dict[str, Any]:
    """Đo vùng lân cận một tài khoản. Không suy diễn, không làm tròn ẩn.

    Trả về đúng những gì đếm được: ai gửi vào, ai nhận ra, ai đứng giữa, và có
    vòng khép kín nào đi qua tài khoản này không.
    """
    start = as_of - timedelta(days=window_days)
    params = {"account": account_key, "start": start, "as_of": as_of}
    rows = [dict(row) for row in session.execute(text(_NEIGHBOURS_SQL), params).mappings()]

    incoming = sorted(
        (row for row in rows if row["direction"] == "in"), key=lambda row: float(row["total"]), reverse=True
    )
    outgoing = sorted(
        (row for row in rows if row["direction"] == "out"), key=lambda row: float(row["total"]), reverse=True
    )

    def shape(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "account_key": row["counterparty"],
            "transactions": int(row["n"]),
            "amount": round(float(row["total"]), 2),
            "currency": row["currency"],
        }

    neighbours = [row["counterparty"] for row in outgoing]
    intermediaries: list[dict[str, Any]] = []
    if neighbours:
        intermediaries = [
            {
                "account_key": row["middle"],
                "onward_accounts": int(row["onward_count"]),
                "onward_transactions": int(row["onward_transactions"]),
                "onward_amount": round(float(row["onward_amount"]), 2),
            }
            for row in session.execute(
                text(_INTERMEDIARY_SQL), {**params, "neighbours": neighbours, "limit": TOP_N}
            ).mappings()
        ]

    cycles = [
        {
            "length": int(row["payload"].get("cycle_length") or 0),
            "accounts": list(row["payload"].get("accounts") or []),
            "duration_hours": row["payload"].get("duration_hours"),
        }
        for row in session.execute(
            text(
                """SELECT payload FROM graph_detector_evidence
                    WHERE account_key = :account AND pattern = 'CYCLE'
                    ORDER BY as_of_time DESC LIMIT 3"""
            ),
            {"account": account_key},
        ).mappings()
    ]

    inflow = round(sum(float(row["total"]) for row in incoming), 2)
    outflow = round(sum(float(row["total"]) for row in outgoing), 2)
    return {
        "account_key": account_key,
        "window_start": start.isoformat(),
        "window_end": as_of.isoformat(),
        "window_days": window_days,
        "currency": (incoming or outgoing or [{}])[0].get("currency"),
        "inflow_amount": inflow,
        "outflow_amount": outflow,
        "incoming_transactions": sum(int(row["n"]) for row in incoming),
        "outgoing_transactions": sum(int(row["n"]) for row in outgoing),
        "unique_senders": len(incoming),
        "unique_receivers": len(outgoing),
        "top_senders": [shape(row) for row in incoming[:TOP_N]],
        "top_receivers": [shape(row) for row in outgoing[:TOP_N]],
        "intermediaries": intermediaries,
        "cycles": cycles,
    }


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def fallback_narrative(reading: dict[str, Any]) -> GraphNarrative:
    """Bản kể dựng thẳng từ phần đo, không cần mô hình.

    Vừa là phương án dự phòng khi gọi mô hình hỏng, vừa là mức sàn chất lượng:
    bản do mô hình viết mà tệ hơn bản này thì không đáng dùng.
    """
    unit = f" {reading['currency']}" if reading.get("currency") else ""
    senders, receivers = reading["unique_senders"], reading["unique_receivers"]

    if senders:
        names = ", ".join(item["account_key"] for item in reading["top_senders"])
        flow_in = (
            f"Tiền vào: {_money(reading['inflow_amount'])}{unit} qua "
            f"{reading['incoming_transactions']} giao dịch, từ {senders} tài khoản. "
            f"Gửi nhiều nhất: {names}."
        )
    else:
        flow_in = "Không có tiền vào trong khoảng thời gian này — mọi mũi tên đều là tiền đi ra."

    if receivers:
        names = ", ".join(item["account_key"] for item in reading["top_receivers"])
        flow_out = (
            f"Tiền ra: {_money(reading['outflow_amount'])}{unit} qua "
            f"{reading['outgoing_transactions']} giao dịch, tới {receivers} tài khoản. "
            f"Nhận nhiều nhất: {names}."
        )
    else:
        flow_out = "Không có tiền đi ra trong khoảng thời gian này — tài khoản chỉ nhận rồi giữ lại."

    if reading["intermediaries"]:
        middle = reading["intermediaries"][0]
        flow_out += (
            f" Tiền không dừng ở đó: {middle['account_key']} nhận rồi chuyển tiếp "
            f"{_money(middle['onward_amount'])} cho {middle['onward_accounts']} tài khoản khác."
        )

    why: list[str] = []
    if senders >= MANY and receivers == 1:
        why.append(
            f"Hình phễu: {senders} tài khoản nộp tiền vào, rồi toàn bộ dồn về đúng 1 tài khoản. "
            "Đây là dáng của một điểm gom tiền."
        )
    elif senders <= 2 and receivers >= WIDE:
        why.append(
            f"Hình toả: tiền vào từ {senders} tài khoản rồi chia nhỏ ra {receivers} tài khoản khác nhau — "
            "kiểu chia nhỏ để khó lần theo."
        )
    if reading["intermediaries"]:
        why.append(
            f"Có {len(reading['intermediaries'])} tài khoản đứng giữa: nhận tiền từ tài khoản này rồi "
            "chuyển tiếp đi nơi khác chứ không giữ lại."
        )
    if reading["cycles"]:
        cycle = reading["cycles"][0]
        why.append(
            f"Tiền chạy vòng: có đường đi khép kín qua {cycle['length']} tài khoản rồi quay về chỗ xuất phát. "
            "Tiền quay lại nơi nó đi ra là điều hiếm gặp trong hoạt động bình thường."
        )
    if reading["outflow_amount"] > reading["inflow_amount"] and reading["inflow_amount"] > 0:
        why.append(
            f"Chuyển đi ({_money(reading['outflow_amount'])}) nhiều hơn nhận vào "
            f"({_money(reading['inflow_amount'])}) trong cùng khoảng — phần lớn nguồn tiền có từ trước, "
            "chưa nhìn thấy trên hình."
        )
    if not why:
        why.append("Chưa thấy hình dạng bất thường nào trong vùng đang vẽ; cảnh báo dựa trên căn cứ khác.")

    how = [
        f"Bắt đầu từ đỉnh {reading['account_key']} ở giữa — đây là tài khoản bị cảnh báo.",
        "Mũi tên chỉ VÀO đỉnh đó là tiền nhận; mũi tên chỉ RA là tiền chuyển đi. Cạnh càng đậm, tiền càng lớn.",
    ]
    if reading["top_receivers"]:
        how.append(
            f"Bấm vào {reading['top_receivers'][0]['account_key']} — đây là nơi nhận nhiều tiền nhất, "
            "và là đầu mối đáng lần theo nhất."
        )
    if reading["cycles"]:
        how.append("Mở tab Chu trình để thấy đường tiền khép kín được tô riêng.")
    return GraphNarrative(flow_in=flow_in, flow_out=flow_out, why_suspicious=why[:4], how_to_read=how[:4])


async def narrate(reading: dict[str, Any], *, service: GeminiService | None = None) -> tuple[GraphNarrative, str]:
    """Diễn đạt phần đo thành tiếng Việt. Trả về (bản kể, nguồn sinh ra nó)."""
    fallback = fallback_narrative(reading)
    settings = get_settings()
    owns = service is None
    try:
        service = service or get_gemini_service(settings)
        prompt = get_prompt("graph_narrator")
        result = await service.generate_structured(
            investigation_id=f"GRAPH-{reading['account_key']}",
            agent_name="graph_narrator",
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            # Toàn bộ ngữ cảnh là phần đo. Mô hình không có đường nào chạm tới
            # cơ sở dữ liệu, nên nó chỉ có thể diễn đạt lại, không thể bịa thêm.
            # Kèm luôn bản dự phòng làm mức sàn. Không có nó, mô hình hay bỏ
            # rơi đúng câu quan trọng nhất — quan sát được: nó tả đủ số tiền và
            # số giao dịch nhưng đánh rơi "hình phễu", tức là đánh rơi lý do cả
            # màn hình này tồn tại.
            trusted_context={"reading": reading, "baseline": fallback.model_dump(mode="json")},
            untrusted_data=[],
            response_schema=GraphNarrative,
            fallback_response=fallback,
        )
        narrative = result.output
        if not narrative.flow_in and not narrative.flow_out:
            return fallback, "deterministic"
        return narrative, "gemini"
    except Exception:  # noqa: BLE001 — màn hình không được trống vì một lần gọi hỏng
        logger.warning("graph narrative fell back to the deterministic reading", exc_info=True)
        return fallback, "deterministic"
    finally:
        if owns and service is not None:
            await service.close()
