"""Kiểm tính nhất quán LOGIC của bản giải thích với số liệu đo được.

Vì sao cần lớp này
------------------
Bộ kiểm sẵn có bắt hai loại lỗi: câu không dẫn bằng chứng, và con số không có
trong bằng chứng được dẫn. Cả hai đều là kiểm ở mức TOKEN. Chúng không bắt được
loại lỗi khó chịu nhất với người đọc: câu có dẫn nguồn, số nào cũng có thật,
nhưng ghép lại thì vô lý —

* "tài khoản không nhận đồng nào" trong khi số liệu ghi tiền vào 41.000;
* "chuyển 8.433 tới 002:B" trong khi chính giao dịch được dẫn là tiền VÀO;
* "giao dịch lớn nhất là 9.930" trong khi sổ có dòng 906.270;
* "nhiều nguồn dồn vào" trong khi chỉ đo được 2 đối tác gửi.

Đây là lỗi quy kết (attribution) chứ không phải lỗi trích dẫn: câu được gán cho
một bằng chứng không chống đỡ được nó. Rashkin và cộng sự (2021, "Measuring
Attribution in Natural Language Generation Models") gọi đó là phần quan trọng
nhất của việc đánh giá văn bản có dẫn nguồn; Min và cộng sự (2023, "FActScore")
cho thấy cách bắt hiệu quả là tách câu thành các mệnh đề nguyên tử rồi kiểm từng
mệnh đề với nguồn, thay vì chấm điểm cả đoạn.

Module này làm đúng vậy nhưng TẤT ĐỊNH: mỗi luật là một mệnh đề nguyên tử đối
chiếu thẳng với ô số liệu tương ứng. Không gọi mô hình, nên không có chuyện bộ
kiểm cũng bịa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Câu phủ định dòng tiền — "không nhận", "không có tiền vào"...
_NO_INFLOW = re.compile(
    r"không\s+(hề\s+)?(nhận|có)\s+(được\s+)?(đồng\s+nào|tiền\s+vào|khoản\s+(tiền\s+)?nào\s+vào|giao dịch\s+vào)"
    r"|không\s+phát sinh\s+(giao dịch\s+)?(tiền\s+)?vào",
    re.I,
)
_NO_OUTFLOW = re.compile(
    r"không\s+(hề\s+)?(chuyển|có)\s+(đi\s+)?(đồng\s+nào|tiền\s+ra|lần\s+chuyển\s+đi\s+nào|giao dịch\s+ra)"
    r"|không\s+phát sinh\s+(giao dịch\s+)?(tiền\s+)?ra",
    re.I,
)

#: Từ chỉ chiều của một giao dịch cụ thể.
_SENT = re.compile(r"\b(chuyển|gửi|chi|trả)\s+(đi\s+)?[\d.,]", re.I)
_RECEIVED = re.compile(r"\bnhận\s+(được\s+)?[\d.,]", re.I)

#: Câu khẳng định một cực trị.
_SUPERLATIVE = re.compile(r"\b(lớn nhất|cao nhất|nhiều nhất|đắt nhất)\b", re.I)

#: Khẳng định "nhiều nguồn/nhiều đích" — phải có số đo đỡ lưng.
_MANY_SOURCES_CLAIM = re.compile(r"nhiều\s+(nguồn|tài khoản)\s+(dồn|chuyển|gửi)\s*(vào|tiền vào)?", re.I)
_MANY_DESTINATIONS_CLAIM = re.compile(r"(phân tán|toả|tỏa|chia nhỏ)\s+(ra\s+)?nhiều\s+(đích|tài khoản)", re.I)

#: Số trong câu, cùng luật với bộ kiểm số của tác tử phản biện.
_NUMBER = re.compile(r"(?<![\w.-])-?\d+(?:\.\d+)?(?![\w-])")


@dataclass(frozen=True)
class ConsistencyIssue:
    """Một mâu thuẫn giữa câu chữ và số liệu đo được."""

    rule: str
    claim: str
    detail: str


def _observed(evidence: list[Any]) -> dict[str, Any] | None:
    """Ô số liệu hành vi rộng nhất trong tập bằng chứng (cùng lựa chọn với `_summary`)."""
    windows = [
        item.payload["observed"]
        for item in evidence
        if getattr(item, "type", None) is not None
        and str(getattr(item.type, "value", item.type)) == "BEHAVIOR_FEATURE"
        and isinstance(item.payload, dict)
        and item.payload.get("observed")
    ]
    if not windows:
        return None
    return max(windows, key=lambda observed: int(observed.get("window_days") or 0))


def _transactions(evidence: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in evidence:
        if str(getattr(item.type, "value", getattr(item, "type", ""))) != "TRANSACTION":
            continue
        if isinstance(item.payload, dict):
            records.extend(item.payload.get("items", []) or [])
    return records


def check(
    claims: list[str],
    evidence: list[Any],
    *,
    account_key: str,
    fan_threshold: int,
) -> list[ConsistencyIssue]:
    """Đối chiếu từng câu với số liệu đo được; trả về các mâu thuẫn tìm thấy."""
    observed = _observed(evidence)
    records = _transactions(evidence)
    issues: list[ConsistencyIssue] = []

    for claim in claims:
        issues.extend(_check_flow_direction(claim, observed))
        issues.extend(_check_transaction_direction(claim, records, account_key))
        issues.extend(_check_superlative(claim, records))
        issues.extend(_check_fan_claims(claim, observed, fan_threshold))
    return issues


def _check_flow_direction(claim: str, observed: dict[str, Any] | None) -> list[ConsistencyIssue]:
    """Câu phủ định một chiều dòng tiền trong khi số liệu ghi có chiều đó."""
    if not observed:
        return []
    found: list[ConsistencyIssue] = []
    inflow = float(observed.get("inflow_amount") or 0)
    outflow = float(observed.get("outflow_amount") or 0)
    if _NO_INFLOW.search(claim) and inflow > 0:
        found.append(
            ConsistencyIssue(
                rule="FLOW_CONTRADICTION",
                claim=claim,
                detail=f"Câu nói tài khoản không nhận tiền, nhưng cửa sổ ghi nhận tiền vào {inflow}.",
            )
        )
    if _NO_OUTFLOW.search(claim) and outflow > 0:
        found.append(
            ConsistencyIssue(
                rule="FLOW_CONTRADICTION",
                claim=claim,
                detail=f"Câu nói tài khoản không chuyển tiền đi, nhưng cửa sổ ghi nhận tiền ra {outflow}.",
            )
        )
    return found


def _check_transaction_direction(claim: str, records: list[dict[str, Any]], account_key: str) -> list[ConsistencyIssue]:
    """Câu kể sai CHIỀU của đúng giao dịch mà nó dẫn.

    Đây là lỗi đọc ngược hay gặp nhất: sổ giao dịch ghi ``source``/``destination``
    theo tài khoản đối ứng, và mô hình đọc nhầm thành chiều của chủ thể.
    """
    found: list[ConsistencyIssue] = []
    for record in records:
        tx_id = str(record.get("transaction_id") or "")
        if not tx_id or tx_id not in claim:
            continue
        is_outgoing = str(record.get("source")) == account_key
        if is_outgoing and _RECEIVED.search(claim) and not _SENT.search(claim):
            found.append(
                ConsistencyIssue(
                    rule="DIRECTION_MISMATCH",
                    claim=claim,
                    detail=f"Giao dịch {tx_id} là tiền RA khỏi tài khoản, nhưng câu kể là tiền nhận vào.",
                )
            )
        if not is_outgoing and _SENT.search(claim) and not _RECEIVED.search(claim):
            found.append(
                ConsistencyIssue(
                    rule="DIRECTION_MISMATCH",
                    claim=claim,
                    detail=f"Giao dịch {tx_id} là tiền VÀO tài khoản, nhưng câu kể là tiền chuyển đi.",
                )
            )
    return found


def _check_superlative(claim: str, records: list[dict[str, Any]]) -> list[ConsistencyIssue]:
    """Câu khẳng định "lớn nhất" mà sổ giao dịch có dòng lớn hơn.

    Chỉ xét khi câu có nêu một con số khớp với một giao dịch trong sổ — nếu
    không có mốc để so thì im lặng, đừng đoán.
    """
    if not _SUPERLATIVE.search(claim) or not records:
        return []
    amounts = [float(r["amount"]) for r in records if r.get("amount") is not None]
    if not amounts:
        return []
    largest = max(amounts)
    stated = [float(n) for n in _NUMBER.findall(claim)]
    matched = [value for value in stated if any(abs(value - amount) <= 0.5 for amount in amounts)]
    if matched and max(matched) < largest - 0.5:
        return [
            ConsistencyIssue(
                rule="SUPERLATIVE_UNSUPPORTED",
                claim=claim,
                detail=f"Câu gọi {max(matched)} là lớn nhất, nhưng sổ giao dịch có dòng {largest}.",
            )
        ]
    return []


def _check_fan_claims(claim: str, observed: dict[str, Any] | None, fan_threshold: int) -> list[ConsistencyIssue]:
    """Khẳng định "nhiều nguồn"/"nhiều đích" trong khi số đo dưới ngưỡng.

    Đây là mâu thuẫn mà người dùng nhìn thấy trên màn hình thật: câu chữ nói gom
    từ nhiều nguồn, còn số đo ngay bên cạnh ghi 2 đối tác gửi.
    """
    if not observed:
        return []
    found: list[ConsistencyIssue] = []
    sources = int(observed.get("unique_in_counterparties") or 0)
    destinations = int(observed.get("unique_out_counterparties") or 0)
    if _MANY_SOURCES_CLAIM.search(claim) and sources < fan_threshold:
        found.append(
            ConsistencyIssue(
                rule="THRESHOLD_CONTRADICTION",
                claim=claim,
                detail=(
                    f"Câu khẳng định nhiều nguồn dồn vào, nhưng cửa sổ chỉ đo được {sources} đối tác gửi "
                    f"(ngưỡng ≥ {fan_threshold})."
                ),
            )
        )
    if _MANY_DESTINATIONS_CLAIM.search(claim) and destinations < fan_threshold:
        found.append(
            ConsistencyIssue(
                rule="THRESHOLD_CONTRADICTION",
                claim=claim,
                detail=(
                    f"Câu khẳng định phân tán ra nhiều đích, nhưng cửa sổ chỉ đo được {destinations} đối tác "
                    f"nhận (ngưỡng ≥ {fan_threshold})."
                ),
            )
        )
    return found
