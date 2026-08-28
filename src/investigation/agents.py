from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation import consistency
from src.investigation.llm import GeminiCallResult, GeminiService
from src.investigation.prompts import get_prompt
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import (
    Claim,
    EvidenceEnvelope,
    EvidenceType,
    Explanation,
    RiskDriver,
    SupervisorPlan,
    ToolDecision,
    ValidationIssue,
    ValidationResult,
)
from src.investigation.tools import InvestigationTools


def _claim_id() -> str:
    return f"CLM-{uuid.uuid4().hex[:16]}"


# Feature names stay verbatim in claim text for traceability; the gloss is what
# a reviewer actually reads.
FEATURE_LABELS_VI = {
    "txn_count": "số giao dịch",
    "incoming_count": "số giao dịch nhận",
    "outgoing_count": "số giao dịch chuyển đi",
    "active_days": "số ngày có phát sinh",
    "txn_per_active_day": "số giao dịch mỗi ngày hoạt động",
    "total_inflow": "tổng tiền vào",
    "total_outflow": "tổng tiền ra",
    "net_flow": "dòng tiền ròng",
    "outflow_inflow_ratio": "tỉ lệ tiền ra trên tiền vào",
    "rapid_outflow_ratio": "tỉ lệ chuyển đi trong vòng 2 giờ sau khi nhận",
    "median_dwell_time": "thời gian giữ tiền trung vị",
    "unique_in_counterparties": "số đối tác chuyển đến",
    "unique_out_counterparties": "số đối tác nhận tiền",
    "new_counterparty_ratio": "tỉ lệ đối tác chưa từng giao dịch",
    "median_amount": "số tiền trung vị",
    "p90_amount": "số tiền phân vị 90",
    "amount_std": "độ lệch chuẩn số tiền",
    "repeated_amount_ratio": "tỉ lệ số tiền lặp lại",
    "median_inter_txn_gap": "khoảng cách trung vị giữa hai giao dịch",
    "p10_inter_txn_gap": "khoảng cách ngắn nhất giữa hai giao dịch",
}


def _amount(value: float) -> str:
    """Số tiền có phân tách hàng nghìn bằng DẤU CÁCH mảnh.

    "30752077.04" là một dãy chín chữ số không ai đọc được bằng mắt; chuyên viên
    phải đếm từng cụm mới biết là ba mươi triệu hay ba trăm triệu. Dấu cách mảnh
    (U+202F) tách cụm mà không tạo ký tự nào có thể bị đọc thành dấu thập phân.

    Bộ kiểm số của tác tử phản biện chuẩn hoá lại dấu cách này trước khi so khớp
    (xem ``_normalise_numbers``), nên câu vẫn tự kiểm chứng được.
    """
    return f"{float(value):,.2f}".replace(",", THIN_SPACE)


#: Kênh thanh toán → tiếng Việt.
#:
#: Hai bộ dữ liệu ghi cùng một khái niệm theo hai kiểu (`CREDIT_CARD` với IBM,
#: `Credit card` với SAML-D), và cả hai đều là mã thô. Câu dữ kiện đọc lên phải
#: là tiếng Việt: "qua kênh thẻ tín dụng", không phải "qua kênh CREDIT_CARD".
_CHANNEL_VI = {
    "cheque": "séc",
    "ach": "chuyển khoản ACH",
    "creditcard": "thẻ tín dụng",
    "debitcard": "thẻ ghi nợ",
    "crossborder": "chuyển tiền quốc tế",
    "cash": "tiền mặt",
    "cashwithdrawal": "rút tiền mặt",
    "cashdeposit": "nộp tiền mặt",
    "wire": "điện chuyển tiền",
    "bitcoin": "Bitcoin",
}


def _channel(value: Any) -> str:
    """Tên kênh thanh toán để ĐỌC. Mã lạ thì trả nguyên văn, không đoán."""
    raw = str(value or "").strip()
    if not raw:
        return "không rõ"
    return _CHANNEL_VI.get(re.sub(r"[\s_-]", "", raw).lower(), raw)


def _day(value: Any) -> str:
    """Ngày viết theo lối Việt Nam (dd/mm/yyyy).

    "2022-09-16" là định dạng máy. Bộ kiểm số nhận ra dạng dd/mm/yyyy và quy về
    ISO trước khi đối chiếu với bằng chứng (xem ``_mask_identifiers``).
    """
    iso = str(value)[:10]
    parts = iso.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return iso


#: Dấu cách mảnh dùng để tách hàng nghìn. Không phải dấu cách thường: dấu cách
#: thường bị các bước chuẩn hoá chuỗi khác gộp mất, và khi ấy "30 752 077" biến
#: thành ba số rời.
THIN_SPACE = "\u202f"

# Screening thresholds for reading a typology signal off the observed window.
# They decide wording only — never the risk score, which stays the detector's.
FAN_COUNTERPARTIES = 5
RAPID_OUTFLOW_PERCENT = 50.0
SHORT_DWELL_HOURS = 24.0
REPEATED_AMOUNT_RATIO = 0.3
RETAINED_OUTFLOW_RATIO = 0.5


def _signal_measurements(grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> dict[str, str]:
    """Số đo và ngưỡng đứng sau mỗi tín hiệu, viết cho người đọc.

    Câu "không thấy phân tán ra nhiều đích" là một khẳng định trần trụi: chuyên
    viên nhìn thấy hai đối tác nhận tiền trong sổ giao dịch liền đọc thành mâu
    thuẫn, và tác tử phản biện cũng vậy — quan sát được trên hồ sơ thật, nó nêu
    CONTRADICTION đúng vì lý do đó. Kèm phép đo thì câu ấy thành một phép đo có
    ngưỡng, kiểm chứng được, chứ không phải lời phủ nhận.
    """
    measurements: dict[str, str] = {}

    # Phép đo của nhánh địa lý không phụ thuộc cửa sổ đặc trưng, nên đứng riêng:
    # một tài khoản có cửa sổ rỗng vẫn nói được nó đi hành lang nào.
    for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
        geo = item.payload.get("geo_context")
        if not geo or not geo.get("from_country"):
            continue
        corridor = f"{geo['from_country']} → {geo['to_country']}"
        if geo.get("cross_border"):
            lift = geo.get("lift_vs_cross_border")
            measurements["cross_border_flow"] = f"hành lang {corridor}"
            measurements["jurisdiction_signal"] = (
                # Dấu thập phân thống nhất với mọi số đo khác trong cùng câu ("12.1 giờ").
                f"hành lang {corridor}, gấp {float(lift):.1f} lần mức nền xuyên biên giới, ngưỡng ≥ 1.0"
                if lift
                else f"hành lang {corridor}"
            )
        else:
            measurements["cross_border_flow"] = f"toàn bộ nội địa {geo['from_country']}"
            measurements["jurisdiction_signal"] = f"không có hành lang ra nước ngoài, đậm nhất là {corridor}"

    behavior = grouped.get(EvidenceType.BEHAVIOR_FEATURE, [])
    observed = next((item.payload["observed"] for item in behavior if item.payload.get("observed")), None)
    if not observed:
        return measurements
    dwell = observed.get("median_dwell_hours")
    # Cửa sổ nhiều loại tiền thì MỌI tỉ lệ tính trên số tiền đều vô nghĩa.
    #
    # Đo được trên bản thật: câu tóm tắt vừa nói "không cộng gộp thành một tổng"
    # xong đã ghi ngay "nhận 4 932.33 rồi chuyển đi 4 694.59 — 95% số tiền nhận
    # được đã đi tiếp" — mà hai con số ấy chính là USD cộng EUR. Một đoạn tự
    # phủ định chính nó. Phép đo theo SỐ LƯỢNG (đối tác, giao dịch) và theo THỜI
    # GIAN không phụ thuộc loại tiền nên vẫn giữ.
    single_currency = bool(observed.get("currency"))
    measurements |= {
        "fan_in": f"{observed['unique_in_counterparties']} đối tác gửi, ngưỡng ≥ {FAN_COUNTERPARTIES}",
        "fan_out": f"{observed['unique_out_counterparties']} đối tác nhận, ngưỡng ≥ {FAN_COUNTERPARTIES}",
        "new_counterparties": f"{observed['new_counterparties']} đối tác mới, ngưỡng > 0",
    }
    if single_currency:
        measurements["rapid_outflow"] = (
            f"{observed['rapid_outflow_percent']:.0f}% tiền ra đi nhanh, ngưỡng ≥ {RAPID_OUTFLOW_PERCENT:.0f}%"
        )
    if dwell is not None:
        measurements["short_dwell_time"] = f"tiền nằm lại trung vị {dwell:.1f} giờ, ngưỡng ≤ {SHORT_DWELL_HOURS:.0f}"
        measurements["short_duration"] = measurements["short_dwell_time"]
    if observed["inflow_amount"] > 0 and single_currency:
        share = observed["outflow_amount"] / observed["inflow_amount"]
        measurements["value_retention"] = (
            f"chuyển đi {share:.0%} số nhận vào, ngưỡng giữ lại < {RETAINED_OUTFLOW_RATIO:.0%}"
        )

    # --- Các tín hiệu còn lại: cũng phải có SỐ ĐO, không chỉ có tên ---
    #
    # Trước đây chỉ 9 tín hiệu trên có phép đo; những tín hiệu định nghĩa nên
    # T01/T02/T03 (chia nhỏ dưới ngưỡng, trung chuyển, khép vòng) thì không, nên
    # bản giải thích của các nhóm ấy chỉ nói "khớp dấu hiệu" mà không nói khớp ở
    # mức nào — đúng chỗ chuyên viên cần con số nhất.
    window = observed.get("window_days")
    if window:
        total_txn = int(observed["incoming_count"]) + int(observed["outgoing_count"])
        measurements["short_window"] = f"{total_txn} giao dịch dồn trong {int(window)} ngày"
    features = next((item.payload.get("features") or {} for item in reversed(behavior)), {})
    repeated = features.get("repeated_amount_ratio")
    if repeated is not None:
        measurements["repeated_amounts"] = (
            f"{float(repeated):.0%} giao dịch lặp lại cùng mức tiền, ngưỡng ≥ {REPEATED_AMOUNT_RATIO:.0%}"
        )
    if observed["inflow_amount"] > 0 and observed["outflow_amount"] > 0 and single_currency:
        # Khoá RIÊNG, không gán vào `network_flow`.
        #
        # `network_flow` là tín hiệu của bộ phát hiện ĐỒ THỊ. Mượn khoá ấy cho
        # một phép đo tính từ đặc trưng hành vi thì câu trạng thái đọc thành mâu
        # thuẫn: "chưa đạt ngưỡng tiền đi qua tài khoản trung gian (94% số tiền
        # chỉ đi qua tài khoản)". Đây là phép đo phụ, chỉ dùng cho câu nhấn mạnh.
        # Tỉ lệ là PHẦN CỦA SỐ NHẬN ĐƯỢC đã chuyển đi tiếp, chặn trên ở 100%.
        #
        # Lấy thẳng outflow/inflow cho ra "811% số tiền chỉ đi qua tài khoản" khi
        # tài khoản chuyển đi nhiều hơn số nhận trong cửa sổ (tiền vào từ trước
        # cửa sổ). Không có nghĩa nào cho một tỉ lệ đi qua vượt 100%.
        forwarded = min(observed["outflow_amount"], observed["inflow_amount"]) / observed["inflow_amount"]
        # Chú thích NGẮN: phép đo này còn được nhét vào danh sách dấu hiệu đã
        # khớp, vốn đã nằm trong ngoặc — một mệnh đề dài nữa thành ngoặc ba tầng.
        extra = " (chênh do tiền vào trước cửa sổ)" if observed["outflow_amount"] > observed["inflow_amount"] else ""
        # Số tiền LUÔN đi kèm loại tiền. Một con số trần không nói được nó là
        # bốn nghìn đô hay bốn nghìn yên — hai thứ lệch nhau hai bậc độ lớn.
        # Nhánh này chỉ chạy khi cửa sổ dùng một loại tiền, nên nêu được đích danh.
        unit = f" {observed['currency']}"
        measurements["pass_through"] = (
            f"nhận {_amount(observed['inflow_amount'])}{unit} rồi chuyển đi "
            f"{_amount(observed['outflow_amount'])}{unit} — {forwarded:.0%} số tiền nhận được đã đi tiếp{extra}"
        )
    return measurements


def _graph_measurements(grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> dict[str, str]:
    """Số đo lấy từ bằng chứng đồ thị (mẫu hình, số tài khoản trong mẫu hình)."""
    measurements: dict[str, str] = {}
    for item in grouped.get(EvidenceType.GRAPH_PATTERN, []):
        pattern = str(item.payload.get("pattern") or "")
        if not pattern:
            continue
        accounts = len(item.payload.get("accounts", []) or [])
        if "CYCLE" in pattern.upper():
            measurements["directed_cycle"] = f"vòng tiền khép kín qua {accounts} tài khoản"
        measurements.setdefault("network_flow", f"mẫu hình {pattern} nối {accounts} tài khoản")
    return measurements


#: Mỗi kiểu hành vi có MỘT chiều đo quyết định nó — và chuyên viên đọc bản giải
#: thích là để biết chiều ấy đo ra bao nhiêu.
#:
#: Trước đây mọi nhóm hành vi đều được kể bằng cùng một khuôn: liệt kê tên các
#: dấu hiệu đã khớp, không kèm số. "Khớp 3 trong 3 dấu hiệu" đúng nhưng rỗng —
#: với nhóm luân chuyển nhanh thì phải thấy tiền nằm lại BAO LÂU, với nhóm gom
#: toả thì phải thấy BAO NHIÊU nguồn và BAO NHIÊU đích, với nhóm chia nhỏ thì
#: phải thấy NGƯỠNG là bao nhiêu và các giao dịch nằm dưới nó thế nào.
#:
#: `angle` là chiều đo, `signals` là thứ tự nêu số — đặt tín hiệu định nghĩa
#: nhóm lên trước.
_TYPOLOGY_FOCUS: dict[str, dict[str, Any]] = {
    "T01": {
        "angle": "cách chia nhỏ so với ngưỡng phải báo cáo",
        "signals": ["rule_trigger", "repeated_amounts", "short_window"],
    },
    "T02": {
        "angle": "vai trò trung chuyển — tiền đi qua chứ không nằm lại",
        # `pass_through` và `value_retention` nói cùng một tỉ lệ bằng hai cách;
        # chỉ giữ một để câu nhấn mạnh không lặp số.
        "signals": ["pass_through", "network_flow", "rapid_outflow", "new_counterparties"],
    },
    "T03": {
        "angle": "đường đi khép vòng của dòng tiền",
        "signals": ["directed_cycle", "short_duration", "value_retention"],
    },
    "T04": {
        "angle": "số lượng nguồn dồn vào và số đích toả ra",
        "signals": ["fan_in", "fan_out", "short_dwell_time"],
    },
    "T05": {
        "angle": "tốc độ — tiền nằm lại bao lâu trước khi rời đi",
        "signals": ["rapid_outflow", "short_dwell_time"],
    },
    "T06": {
        "angle": "hành lang địa lý mà tiền đi qua",
        "signals": ["jurisdiction_signal", "cross_border_flow"],
    },
    "T07": {"angle": "độ lệch giữa hành vi và hồ sơ khách hàng", "signals": ["identity_mismatch", "shared_device"]},
    "T09": {"angle": "chênh lệch giá trị trong chứng từ thương mại", "signals": ["trade_value_mismatch"]},
    "T10": {
        "angle": "mức lệch so với hồ sơ và quy mô thường thấy",
        "signals": ["profile_deviation", "volume_deviation"],
    },
}


def _focus_clause(code: str, measurements: dict[str, str]) -> str:
    """Câu NHẤN MẠNH đúng chiều đo của nhóm hành vi, kèm mọi số đo đã có.

    Nêu số đo của MỌI tín hiệu thuộc chiều ấy, không chỉ tín hiệu đã khớp: câu
    ngay trước đó đã nói rõ cái nào khớp, cái nào chưa đạt ngưỡng, cái nào chưa
    kiểm tra được. Một phép đo vẫn là một phép đo — với nhóm trung chuyển, tỉ lệ
    tiền đi qua tài khoản là con số chuyên viên cần thấy, kể cả khi bộ phát hiện
    đồ thị chưa xác nhận mẫu hình.
    """
    focus = _TYPOLOGY_FOCUS.get(code)
    if not focus:
        return ""
    # Bỏ phép đo TRÙNG hoặc BỊ BAO HÀM trong phép đo đứng trước.
    #
    # Hai tín hiệu của cùng một nhóm hay dựng câu từ cùng một con số — nhóm địa
    # lý là ví dụ rõ nhất: "hành lang UK → Morocco, gấp 2,0 lần mức nền" và
    # "hành lang UK → Morocco". In cả hai thì câu nhấn mạnh tự lặp lại chính nó.
    kept: list[str] = []
    for name in focus["signals"]:
        measure = measurements.get(name)
        if not measure or any(measure in earlier or earlier in measure for earlier in kept):
            continue
        kept.append(measure)
    if not kept:
        return f"Với kiểu này, điều quyết định là {focus['angle']}."
    numbers = "; ".join(kept)
    return f"Với kiểu này, điều quyết định là {focus['angle']} — đo được: {numbers}."


#: Tín hiệu tính từ khoảng thời gian giữa lúc nhận và lúc chuyển đi.
_DWELL_SIGNALS = {"short_dwell_time", "short_duration", "value_retention"}


def _transaction_corridor(grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> dict[str, Any] | None:
    """Suy HÀNH LANG QUỐC GIA từ chính sổ giao dịch (source_country/destination_country).

    Dùng khi nhánh địa lý không nạp được ``geo_context`` (ô chấm điểm geo_cell lỗi
    join theo ngày/múi giờ): quốc gia hai đầu VẪN nằm trong bằng chứng giao dịch,
    nên vẫn nêu được tên vùng tài phán thay vì bỏ trống hoặc nói sai là "không do
    bộ luật địa lý sinh ra". Lấy hành lang xuyên biên giới xuất hiện nhiều nhất.
    """
    counts: dict[tuple[str, str], int] = {}
    for item in grouped.get(EvidenceType.TRANSACTION, []):
        for record in item.payload.get("items", []):
            src, dst = record.get("source_country"), record.get("destination_country")
            if src and dst and src != dst:
                counts[(src, dst)] = counts.get((src, dst), 0) + 1
    if not counts:
        return None
    (src, dst), n = max(counts.items(), key=lambda kv: kv[1])
    return {"from_country": src, "to_country": dst, "cross_border": True, "txn_count": n}


def _absent_reason(name: str, grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> str | None:
    """Vì sao một tín hiệu không đo được, khi lý do là thứ nói ra được."""
    behavior = grouped.get(EvidenceType.BEHAVIOR_FEATURE, [])
    observed = next((item.payload["observed"] for item in behavior if item.payload.get("observed")), None)
    if name in _DWELL_SIGNALS and observed is not None and not observed["incoming_count"]:
        return "cửa sổ không có giao dịch tiền vào nào, nên không có khoảng cách giữa lúc nhận và lúc chuyển đi để đo"
    if name in _DWELL_SIGNALS and observed is not None and not observed["outgoing_count"]:
        return (
            "tiền vào còn nằm nguyên trong tài khoản đến hết cửa sổ, chưa có lần chuyển đi nào để đo thời gian giữ tiền"
        )
    if name in _DWELL_SIGNALS and observed is not None and observed.get("median_dwell_hours") is None:
        # Có cả tiền vào lẫn tiền ra mà vẫn không đo được: mọi lần chuyển đi đều
        # xảy ra TRƯỚC lần nhận gần nhất, nên không ghép được cặp nhận–chuyển nào.
        # Nói đúng điều đó thay vì "thiếu bằng chứng" — không lệnh truy vấn nào
        # bổ sung được thứ vốn không tồn tại trong dòng thời gian của tài khoản.
        return (
            "không ghép được cặp nhận–chuyển nào trong cửa sổ (các lần chuyển đi đều xảy ra trước lần "
            "nhận), nên chưa có thời gian giữ tiền để đo"
        )
    if name in _DWELL_SIGNALS and observed is None:
        return "chưa có đặc trưng hành vi của tài khoản trong cửa sổ"
    if name in {"network_flow", "directed_cycle"} and not grouped.get(EvidenceType.GRAPH_PATTERN):
        return "chưa tra cứu bộ phát hiện đồ thị cho tài khoản này"
    if name in {"jurisdiction_signal", "cross_border_flow"}:
        corridor = _transaction_corridor(grouped)
        if corridor:
            return (
                f"quan sát được dòng tiền qua hành lang {corridor['from_country']} → {corridor['to_country']} "
                "trong sổ giao dịch, nhưng chưa nạp được ô chấm điểm địa lý để xác nhận mức rủi ro pháp vực"
            )
        return "chưa nạp được chi tiết hành lang quốc gia cho cảnh báo này (cần kiểm tra dữ liệu địa lý)"
    if name in {"profile_deviation", "volume_deviation"}:
        return "chưa có kết quả mô hình bất thường cho tài khoản này"
    return None


def _observed_signals(grouped: dict[EvidenceType, list[EvidenceEnvelope]]) -> dict[str, bool]:
    """Which typology signals the collected evidence can actually speak to.

    A signal absent from the returned mapping is one this evidence set cannot
    check — reported as unchecked rather than silently treated as negative.
    """
    signals: dict[str, bool] = {}

    behavior = grouped.get(EvidenceType.BEHAVIOR_FEATURE, [])
    observed = next((item.payload["observed"] for item in behavior if item.payload.get("observed")), None)
    if observed and (observed["incoming_count"] or observed["outgoing_count"]):
        features = behavior[-1].payload.get("features", {})
        dwell = observed.get("median_dwell_hours")
        signals["rapid_outflow"] = observed["rapid_outflow_percent"] >= RAPID_OUTFLOW_PERCENT
        signals["new_counterparties"] = observed["new_counterparties"] > 0
        signals["fan_in"] = observed["unique_in_counterparties"] >= FAN_COUNTERPARTIES
        signals["fan_out"] = observed["unique_out_counterparties"] >= FAN_COUNTERPARTIES
        signals["repeated_amounts"] = float(features.get("repeated_amount_ratio", 0)) >= REPEATED_AMOUNT_RATIO
        if dwell is not None:
            signals["short_dwell_time"] = dwell <= SHORT_DWELL_HOURS
            signals["short_duration"] = signals["short_dwell_time"]
        if observed["inflow_amount"] > 0:
            signals["value_retention"] = observed["outflow_amount"] < RETAINED_OUTFLOW_RATIO * observed["inflow_amount"]
            # Tiền vào rồi phần lớn đi tiếp — bằng chứng TRỰC TIẾP của vai trò
            # trung chuyển, đo ngay trên sổ giao dịch của chính tài khoản. Mẫu
            # hình đồ thị chứng minh vai trò trong MẠNG LƯỚI, nhưng nhãn thì gắn
            # cho MỘT tài khoản nên phép đo cấp tài khoản mới chứng minh được nó.
            signals["pass_through"] = observed["outflow_amount"] >= RETAINED_OUTFLOW_RATIO * observed["inflow_amount"]

    # Gộp bằng OR trên toàn bộ bằng chứng đồ thị, không ghi đè theo dòng cuối.
    #
    # Một phiên có thể vừa có dòng "đã tra, không thấy" vừa có một mẫu hình thật
    # (bộ dò ghi theo nhiều mốc). Bản trước gán đè nên dòng nào đứng cuối danh
    # sách thì dòng ấy quyết định — một mẫu hình CYCLE có thật bị một dòng rỗng
    # xoá mất chỉ vì thứ tự trả về.
    graph_items = grouped.get(EvidenceType.GRAPH_PATTERN, [])
    if graph_items:
        patterns = [str(item.payload.get("pattern") or "").upper() for item in graph_items]
        # Có mặt trong dict = ĐÃ KIỂM TRA. Giá trị False = kiểm tra rồi, âm tính.
        signals["network_flow"] = any(patterns)
        signals["directed_cycle"] = any("CYCLE" in pattern for pattern in patterns)

    # Hai tín hiệu của nhóm T06, suy từ chính thứ làm cảnh báo địa lý nổ.
    #
    # Trước đây không nhánh nào sinh ra chúng, nên cả 5.004 cảnh báo geo_rule
    # đều kết luận "chưa kiểm tra được dấu hiệu vùng tài phán, dòng tiền xuyên
    # biên giới vì thiếu bằng chứng tương ứng" — trong khi dữ kiện ngay phía
    # trên đã ghi rõ hành lang UK→UAE. Tác tử phản biện bắt mâu thuẫn ấy và
    # đánh trượt, nên **không một cảnh báo địa lý nào** từng chạy xong.
    for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
        geo = item.payload.get("geo_context")
        if not geo:
            continue
        signals["cross_border_flow"] = bool(geo.get("cross_border"))
        # Ngưỡng theo mẫu số ĐÚNG của nhánh này: giao dịch xuyên biên giới.
        # So với mẫu số toàn bộ giao dịch thì mọi hành lang quốc tế đều "cao
        # hơn mức nền", vì bản thân việc ra khỏi biên giới đã hiếm.
        lift = geo.get("lift_vs_cross_border")
        signals["jurisdiction_signal"] = bool(geo.get("cross_border")) and float(lift or 0) >= 1.0

    # Giao dịch xuyên biên giới có thật trong sổ, độc lập với ô chấm điểm.
    for item in grouped.get(EvidenceType.TRANSACTION, []):
        for record in item.payload.get("items", []):
            src, dst = record.get("source_country"), record.get("destination_country")
            if src and dst:
                signals["cross_border_flow"] = signals.get("cross_border_flow", False) or src != dst

    # Nhánh địa lý (T06) yêu cầu jurisdiction_signal, nhưng nó chỉ tính được từ
    # geo_context — thứ có thể thiếu khi ô chấm điểm địa lý lỗi join theo ngày. Nếu
    # sổ giao dịch đã cho thấy hành lang xuyên biên giới thì coi như ĐÃ kiểm tra
    # được dấu hiệu vùng tài phán (nêu tên vùng ở narrative), thay vì báo "chưa
    # kiểm tra được" trong khi hành lang đã hiện rõ trong bằng chứng.
    if "jurisdiction_signal" not in signals and _transaction_corridor(grouped) is not None:
        signals["jurisdiction_signal"] = True
        signals["cross_border_flow"] = True

    for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
        signals["rule_trigger"] = bool(item.payload.get("triggered_rules"))

    for item in grouped.get(EvidenceType.ANOMALY_EXPLANATION, []):
        if not item.payload.get("available", True):
            continue
        deviating = any(
            abs(float(feature["reference_percentile"]) - 50.0) >= 10.0
            for feature in item.payload.get("top_anomalous_features", [])
        )
        signals["profile_deviation"] = deviating
        signals["volume_deviation"] = deviating

    return signals


def _corridor_claim(geo: dict[str, Any], evidence_id: str) -> Claim:
    """Một câu nói rõ hành lang, mức rủi ro, VÀ mức nền dùng để so.

    "Rủi ro gấp 5,1 lần mức nền" là câu chuyên viên không kiểm chứng được: mức
    nền nào? Đo trên tập nào? Câu này trả lời cả ba — tỉ lệ nhãn của chính hành
    lang, số giao dịch đã quan sát để ra tỉ lệ ấy, và hai mẫu số kèm bội số
    tương ứng.

    Hai mẫu số đều được nêu vì chúng cho hai con số rất khác nhau (5,1 lần so
    với 1,7 lần cho UK→UAE) và cả hai đều đúng trong phạm vi của mình. Điểm rủi
    ro của cảnh báo tính theo mẫu số thứ nhất; mẫu số thứ hai mới là mức so sánh
    hợp lý cho một nhánh chỉ xét giao dịch xuyên biên giới, nên nó đứng sau cùng
    và được gọi tên rõ ràng.
    """
    src, dst = geo["from_country"], geo["to_country"]
    if not geo.get("cross_border"):
        return Claim(
            claim_id=_claim_id(),
            claim=(
                f"Hành lang đậm nhất trong cửa sổ là {src} → {dst}, tức giao dịch nội địa {src}; "
                "cảnh báo này không dựa trên yếu tố xuyên biên giới."
            ),
            claim_type="FACT",
            evidence_refs=[evidence_id],
            confidence=1.0,
        )
    # Mọi con số dưới đây đọc thẳng từ payload, không tự tính lại và không chèn
    # dấu phân cách hàng nghìn: "27.372" trong tiếng Việt là hai mươi bảy nghìn,
    # nhưng bộ đối chiếu số đọc nó thành 27,372 và câu bị đánh trượt vì con số
    # ấy không có trong bằng chứng nào.
    parts = [f"Hành lang tiền tệ đậm nhất trong cửa sổ là {src} → {dst}"]
    rate_pct = geo.get("corridor_label_percent")
    support = geo.get("corridor_transactions")
    if rate_pct is not None and support:
        parts.append(
            f"trên {support} giao dịch {src} → {dst} trong dữ liệu tham chiếu có {rate_pct}% bị gắn nhãn nghi ngờ"
        )
    cross = geo.get("lift_vs_cross_border")
    base_cross_pct = geo.get("baseline_cross_border_percent")
    if cross and base_cross_pct is not None:
        parts.append(f"cao gấp {cross:.1f} lần mức trung bình của giao dịch xuyên biên giới ({base_cross_pct}%)")
    all_lift = geo.get("lift_vs_all")
    base_all_pct = geo.get("baseline_all_percent")
    if all_lift and base_all_pct is not None:
        parts.append(
            f"và gấp {all_lift:.1f} lần nếu so với toàn bộ giao dịch kể cả nội địa ({base_all_pct}%) — "
            "đây là mẫu số mà điểm rủi ro của cảnh báo đang dùng"
        )
    # Tách làm hai câu.
    #
    # Nối cả bốn mệnh đề bằng dấu phẩy cho ra một câu ba trăm ký tự với năm con
    # số — đúng nhưng không ai đọc hết. Câu đầu nói hành lang nào và tỉ lệ bao
    # nhiêu; câu sau nói tỉ lệ ấy cao hơn mức nền bao nhiêu lần.
    head = ", ".join(parts[:2]) + "."
    tail = (" " + ", ".join(parts[2:]).capitalize() + ".") if len(parts) > 2 else ""
    return Claim(
        claim_id=_claim_id(),
        claim=head + tail,
        claim_type="FACT",
        evidence_refs=[evidence_id],
        confidence=1.0,
    )


#: Ngưỡng đọc hình dạng dòng tiền. Đặt tên rời ra để câu văn và phép đo không
#: bao giờ lệch nhau, và để sửa ngưỡng là sửa một chỗ.
#: MỘT định nghĩa "nhiều" cho cả trang, lấy đúng ngưỡng của tín hiệu.
#:
#: Trước đây văn xuôi dùng ngưỡng riêng (3) còn phần đối chiếu dấu hiệu dùng
#: `FAN_COUNTERPARTIES` (5). Hậu quả đọc thấy ngay trên màn hình: câu tóm tắt
#: viết "nhiều nguồn nộp vào" rồi ba dòng sau ghi "chưa đạt ngưỡng nhiều nguồn
#: dồn vào (3 đối tác gửi, ngưỡng ≥ 5)". Cùng một trang, hai nghĩa của một chữ.
_MANY_SOURCES = FAN_COUNTERPARTIES
_MANY_DESTINATIONS = FAN_COUNTERPARTIES
_FEW = 2  # bao nhiêu trở xuống thì gọi là "rất ít"


#: Thứ tự đọc của phần DỮ KIỆN, từ việc tài khoản đã làm tới cách hệ chấm điểm.
#:
#: Bản trước xếp theo thứ tự CODE chạy: điểm rủi ro và các yếu tố chấm điểm nằm
#: trên cùng, hành vi thật nằm dưới. Người mở một cảnh báo cần biết "tài khoản
#: này đã làm gì với tiền" trước, còn "hệ thống cộng điểm thế nào" là thứ đọc
#: sau khi đã hiểu câu chuyện.
_FACT_ORDER: tuple[tuple[int, str], ...] = (
    (10, "Trong khoảng "),           # dòng tiền của cả cửa sổ
    (20, "được chuyển đi trong vòng"),  # tốc độ
    (21, "Thời gian giữ tiền"),
    (30, "chưa từng giao dịch với tài khoản này"),  # đối tác mới
    (40, "Ngày "),                   # từng giao dịch dẫn chứng
    (50, "So với các tài khoản hoạt động"),  # đặc trưng hành vi
    (55, "Bộ phát hiện đồ thị"),
    (60, "hành lang"),
)

#: Dữ kiện thuộc về cách CHẤM ĐIỂM — đúng nhưng không phải câu chuyện, nên xuống cuối.
_SCORING_FACT = ("Hệ thống chấm mức rủi ro", "đóng góp", "vượt ngưỡng cảnh báo", "bị gắn cờ")


def _order_facts(facts: list[str]) -> list[str]:
    """Xếp dữ kiện theo MẠCH ĐỌC, giữ nguyên thứ tự trong cùng một nhóm."""

    def rank(fact: str) -> int:
        for priority, marker in _FACT_ORDER:
            if marker in fact:
                return priority
        if any(marker in fact for marker in _SCORING_FACT):
            return 90
        return 70

    return [fact for _, fact in sorted(enumerate(facts), key=lambda pair: (rank(pair[1]), pair[0]))]


def _side(amount: float, count: int, parties: int, unit: str, *, verb: str) -> str:
    """Một vế dòng tiền; vế rỗng thì nói "không", đừng viết "0.00 USD từ 0 đối tác".

    "tài khoản nhận 0.00 US Dollar từ 0 đối tác" là cách máy nói. Người viết
    "tài khoản không nhận giao dịch nào".
    """
    if count == 0:
        return f"không {verb} giao dịch nào"
    preposition = "từ" if verb == "nhận" else "tới"
    return f"{verb} {_amount(amount)}{unit} {preposition} {parties} đối tác"


def _percent(value: float, *, of_nonzero: bool = False) -> str:
    """Tỉ lệ viết cho người đọc, không bao giờ làm một lượng khác 0 thành "0%".

    "332.79 UK pounds được chuyển đi trong vòng 2 giờ, chiếm 0% tổng tiền ra" là
    một câu tự mâu thuẫn: có tiền đi mà tỉ lệ bằng không.

    ``of_nonzero`` là khi NƠI GỌI đã biết lượng gốc khác 0. Cần cờ này vì tỉ lệ
    được làm tròn hai chữ số ngay từ nguồn: một lượng rất nhỏ so với tổng cho ra
    đúng 0.0, và khi ấy chỉ nhìn con số thì không phân biệt được "không có đồng
    nào" với "có nhưng chưa tới 0,005%".
    """
    if value < 0.5 and (of_nonzero or value > 0):
        return "dưới 1"
    return f"{value:.0f}"


def _absence_wording(label: str) -> str:
    """"0 giao dịch tiền mặt" → "Kỳ chấm điểm không ghi nhận giao dịch tiền mặt".

    Phải nêu rõ PHẠM VI. Yếu tố chấm điểm đo trên cửa sổ của ô chấm điểm, còn sổ
    giao dịch đính kèm là các dòng gần nhất — hai khoảng khác nhau. Viết trống
    thành "Không có giao dịch tiền mặt" là một khẳng định tuyệt đối, và khi sổ
    giao dịch có đúng một dòng rút tiền mặt thì bản giải thích tự mâu thuẫn;
    tác tử phản biện bắt đúng lỗi đó rồi đánh trượt cả phiên.
    """
    if label.startswith("0 "):
        return "Kỳ chấm điểm không ghi nhận " + label[2:]
    return label


def _label_already_states(label: str, contribution: float) -> bool:
    """True nếu nhãn yếu tố đã nói ra chính con số đóng góp ấy.

    "Giao dịch rủi ro nhất trong kỳ đạt 92 điểm rủi ro — yếu tố này đóng góp
    91.76 điểm vào mức rủi ro" là một câu nói hai lần cùng một việc: chuyên viên
    đọc hai con số gần bằng nhau rồi phải tự hỏi chúng khác nhau chỗ nào. Khi
    nhãn đã chứa con số ấy (sai lệch dưới một điểm), phần đuôi là thừa.
    """
    return any(abs(float(number) - contribution) < 1.0 for number in _CLAIM_NUMBER_RE.findall(label))


def _money_shape(observed: dict[str, Any]) -> str | None:
    """Hình dạng dòng tiền, viết bằng tiếng người.

    Đây là câu mà chuyên viên rà soát cần đọc đầu tiên và hiện đang thiếu hẳn.
    Bản giải thích cũ kể đủ số liệu — nhận bao nhiêu, chuyển bao nhiêu, mấy đối
    tác — rồi dừng, để người đọc tự ghép lại thành một câu chuyện. Một người mở
    ba trăm cảnh báo mỗi ngày không có thời gian làm việc đó.

    Chỉ dùng con số CÓ SẴN trong ``observed``. Mọi so sánh suy ra (gấp mấy lần)
    đều viết bằng chữ, không viết bằng số: bộ đối chiếu của tác tử phản biện
    kiểm từng con số trong câu với bằng chứng, và một tỉ lệ tự tính sẽ bị đánh
    trượt là bịa đặt — đúng theo luật, dù nội dung không sai.

    Câu trả về luôn là NGHI VẤN, không phải kết luận. Hình dạng dòng tiền giống
    một kịch bản rửa tiền không có nghĩa là nó là rửa tiền; rất nhiều doanh
    nghiệp thu hộ có đúng hình phễu này.
    """
    ins = observed["unique_in_counterparties"]
    outs = observed["unique_out_counterparties"]
    inflow = float(observed["inflow_amount"])
    outflow = float(observed["outflow_amount"])
    fast = float(observed["rapid_outflow_percent"])

    if inflow > 0 and outflow == 0:
        return (
            "Tài khoản chỉ nhận tiền rồi giữ lại — trong khoảng quan sát không có lần chuyển đi nào. "
            "Cần xem tiền có tiếp tục đi ra sau mốc này không."
        )
    if outflow > 0 and inflow == 0:
        return (
            "Tài khoản chỉ chuyển tiền đi, không nhận đồng nào trong khoảng quan sát — nguồn tiền nằm "
            "trước khoảng này, nên chưa nhìn thấy được tiền từ đâu tới."
        )
    if ins >= _MANY_SOURCES and outs == 1:
        return (
            f"Hình phễu: tiền chảy vào từ {ins} tài khoản khác nhau rồi dồn hết về đúng 1 tài khoản. "
            f"Đây là dáng của một điểm gom tiền — {ins} nơi nộp vào, một nơi hưởng."
        )
    if ins >= _MANY_SOURCES and outs <= _FEW:
        return (
            f"Tiền chảy vào từ {ins} tài khoản khác nhau rồi dồn về {outs} tài khoản. Dáng gom tiền: "
            f"{ins} nơi nộp vào, chỉ {outs} nơi nhận."
        )
    if ins <= _FEW and outs >= _MANY_DESTINATIONS:
        return (
            f"Tiền vào từ {ins} tài khoản rồi chia nhỏ toả ra {outs} tài khoản khác nhau. Dáng phát tán: "
            f"{ins} nơi vào, {outs} nơi ra — kiểu chia nhỏ để khó lần theo."
        )
    if fast >= RAPID_OUTFLOW_PERCENT and outflow > 0 and observed.get("currency"):
        return (
            f"Tài khoản gần như không giữ tiền: {_percent(fast)}% số tiền ra rời đi trong vòng "
            f"{observed['rapid_window_hours']} giờ kể từ lúc nhận. Dáng trung chuyển — tiền chỉ đi ngang qua."
        )
    if outflow > inflow and outs <= _FEW and outs > 0 and observed.get("currency"):
        return (
            f"Số tiền chuyển đi ({_amount(outflow)} {observed['currency']}) lớn hơn hẳn số nhận vào "
            f"({_amount(inflow)} {observed['currency']}) trong cùng "
            f"khoảng quan sát, và chảy về {outs} tài khoản. Phần lớn nguồn tiền đã có từ trước khoảng này — "
            "cần mở rộng mốc thời gian để thấy tiền từ đâu tới."
        )
    return None


def _summary(
    alert: dict[str, Any],
    drivers: list[RiskDriver],
    grouped: dict[EvidenceType, list[EvidenceEnvelope]],
    typologies: list[str],
    missing: list[str],
    focus: str = "",
) -> str:
    """Kể hành vi, không kể đường ống.

    Người đọc màn hình này là chuyên viên tuân thủ, không phải kỹ sư. Tên mô
    hình ("MEGA-PNA"), tên nhánh và mã nhóm hành vi ("T02") không giúp họ quyết
    định gì: biết cũng không hiểu, mà không biết cũng không sao. Thứ họ cần là
    tài khoản đã làm gì với tiền, và vì sao chỗ đó đáng nghi.

    Xuất xứ kỹ thuật không bị xoá — nó nằm nguyên ở bảng phân rã điểm rủi ro và
    sổ bằng chứng, nơi kiểm toán viên tìm đến. Chỉ là nó không được chiếm chỗ
    của câu đầu tiên.
    """

    # Cùng một quy tắc chọn cửa sổ với phần dữ kiện bên dưới — cửa sổ rộng nhất.
    # Lấy "cái đầu tiên" ở đây và "cái rộng nhất" ở kia là cách chắc chắn để câu
    # tóm tắt nói một đằng còn danh sách dữ kiện nói một nẻo.
    _behavior = [item for item in grouped.get(EvidenceType.BEHAVIOR_FEATURE, []) if item.payload.get("observed")]
    observed = (
        max(_behavior, key=lambda item: int(item.payload["observed"].get("window_days") or 0)).payload["observed"]
        if _behavior
        else None
    )
    if not observed or not (observed["incoming_count"] or observed["outgoing_count"]):
        # Cửa sổ đặc trưng rỗng KHÔNG có nghĩa là tài khoản không có giao dịch.
        #
        # Đây là mâu thuẫn mà chuyên viên nhìn thấy đầu tiên và mất niềm tin ngay:
        # câu mở đầu nói "không có giao dịch nào của tài khoản", còn phần DỮ KIỆN
        # ngay bên dưới liệt kê ba giao dịch có ngày, có số tiền, có mã. Hai phần
        # đọc từ hai nguồn khác nhau — một bên là cửa sổ đặc trưng, một bên là sổ
        # giao dịch — và chỉ phần đầu bị rỗng.
        #
        # Nói đúng phạm vi: rỗng trong CỬA SỔ, và nếu sổ giao dịch có dòng thì
        # nêu luôn khoảng thời gian thật của chúng để chuyên viên biết phải nhìn
        # đi đâu.
        ledger = [
            record for item in grouped.get(EvidenceType.TRANSACTION, []) for record in item.payload.get("items", [])
        ]
        if ledger:
            stamps = sorted(record["timestamp"] for record in ledger)
            headline = (
                f"Trong khoảng thời gian hệ thống dùng để tính các chỉ số hành vi, tài khoản không phát sinh "
                f"giao dịch nào, nên mọi chỉ số đều bằng 0. Nhưng sổ giao dịch của tài khoản có "
                f"{len(ledger)} giao dịch, từ {_day(stamps[0])} đến {_day(stamps[-1])} — hãy đọc hành vi ở "
                "phần danh sách giao dịch bên dưới."
            )
        else:
            headline = (
                "Tính đến mốc rà soát, tài khoản không có giao dịch nào — cả ở chỉ số hành vi lẫn sổ giao "
                "dịch — nên chưa mô tả được tài khoản này đã làm gì."
            )
    else:
        window_text = f"{_day(observed['window_start'])}–{_day(observed['window_end'])}"
        if observed.get("currency"):
            unit = f" {observed['currency']}"
            received = _side(
                observed["inflow_amount"], observed["incoming_count"],
                observed["unique_in_counterparties"], unit, verb="nhận",
            )
            sent = _side(
                observed["outflow_amount"], observed["outgoing_count"],
                observed["unique_out_counterparties"], unit, verb="chuyển đi",
            )
            headline = f"Trong cửa sổ 30 ngày ({window_text}), tài khoản {received} và {sent}."
        else:
            # Cửa sổ có NHIỀU LOẠI TIỀN thì không có tổng nào để nêu.
            #
            # Cộng đô-la với yên rồi in ra một con số trần không đơn vị là một
            # phép tính vô nghĩa — đó chính là câu "nhận 30 752 077.04 từ 2 đối
            # tác" đã lọt lên màn hình thật. Ở đây kể bằng SỐ GIAO DỊCH và SỐ ĐỐI
            # TÁC (cộng được), còn số tiền để ở từng dòng giao dịch bên dưới,
            # nơi mỗi số đi kèm đúng loại tiền của nó.
            headline = (
                f"Trong cửa sổ 30 ngày ({window_text}), tài khoản nhận {observed['incoming_count']} giao dịch "
                f"từ {observed['unique_in_counterparties']} đối tác và chuyển đi {observed['outgoing_count']} "
                f"giao dịch tới {observed['unique_out_counterparties']} đối tác. Các giao dịch thuộc nhiều loại "
                "tiền khác nhau nên không cộng gộp thành một tổng; số tiền của từng giao dịch nêu ở phần dữ kiện."
            )
        # Câu quan trọng nhất của cả bản giải thích: rốt cuộc tài khoản này đang
        # làm gì với tiền. Đứng ngay sau con số, trước mọi thứ khác.
        shape = _money_shape(observed)
        if shape:
            headline += f" {shape}"

    tail = f" Kiểu hành vi đối chiếu: {', '.join(typologies)}." if typologies else ""
    # Nêu NGAY chiều đo quyết định của kiểu hành vi ấy, kèm số.
    #
    # Câu tóm tắt cũ dừng ở tên kiểu ("Kiểu hành vi đối chiếu: Luân chuyển tiền
    # tốc độ cao") — người đọc phải lần xuống mục nhận định mới biết nhanh là
    # nhanh bao nhiêu. Số quan trọng nhất phải nằm ở đoạn đầu.
    if focus:
        tail += f" {focus}"
    if missing:
        tail += " Bản giải thích còn một số chỗ chưa đủ dữ liệu, nêu ở mục bên dưới."
    return f"{headline}{tail} Đây là nhận định của hệ thống để hỗ trợ rà soát; kết luận thuộc về chuyên viên."


def _evidence_by_type(evidence: list[EvidenceEnvelope]) -> dict[EvidenceType, list[EvidenceEnvelope]]:
    grouped: dict[EvidenceType, list[EvidenceEnvelope]] = {}
    for item in evidence:
        grouped.setdefault(item.type, []).append(item)
    return grouped


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _string_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _string_values(nested)


def _mask_identifiers(claim: str, cited: list[EvidenceEnvelope]) -> str:
    """Blank out identifiers before harvesting numbers from claim text.

    An account key like ``070:10042B660`` contains a digit run the number
    regex happily reads as ``70``, which no payload holds numerically — so a
    correctly sourced claim would be flagged unsupported purely for naming the
    counterparty a reviewer needs to see. Identifiers are matched against the
    cited evidence first, longest one wins, so only text the evidence itself
    contains is removed.
    """
    # Chỉ xoá định danh, tuyệt đối không xoá SỐ.
    #
    # ``next_cursor`` của trang giao dịch là chuỗi ``"50"``. Bản trước coi nó là
    # một định danh và xoá mọi chuỗi "50" trong câu, nên số tiền ``5016.80`` bị
    # cắt thành `` 16.80``. Bộ quét số sau đó tìm 16,8 trong bằng chứng, không
    # thấy, và đánh trượt một câu hoàn toàn đúng — cả bốn dòng giao dịch của hồ
    # sơ. Đây là nguyên nhân UNSUPPORTED_CLAIM nhiều nhất đo được trên 163 phiên.
    #
    # Định danh luôn có ký tự không phải chữ số (``001:A``, ``EV-abc123``,
    # ``AE:4598413445``); một token toàn chữ số thì hoặc là số cần kiểm chứng,
    # hoặc là thứ vô hại để lại.
    # Chuẩn hoá dấu tách hàng nghìn ở CẢ HAI PHÍA.
    #
    # Câu được bỏ dấu cách mảnh trước khi so khớp (bên dưới). Nếu bằng chứng vẫn
    # giữ dấu ấy thì chuỗi hai bên không còn bằng nhau: nhãn "Tổng 9 294 trên các
    # giao dịch bị gắn cờ" nằm nguyên trong bằng chứng nhưng không che được câu
    # đã chuẩn hoá thành "Tổng 9294 …", và con số 9294 bị đòi bằng chứng số học —
    # thứ không tồn tại vì nó chỉ sống trong chuỗi nhãn. Đo trên bản chạy lại
    # 27/08/2026: lỗi này đánh trượt 100% số phiên của hai lô liên tiếp.
    tokens = {
        variant
        for item in cited
        for token in _string_values(item.payload)
        if len(token) > 1 and not token.replace(".", "").replace(",", "").isdigit()
        for variant in (token, token.replace(THIN_SPACE, ""))
    }
    # Bỏ dấu tách hàng nghìn TRƯỚC khi so khớp: "30 752 077.04" phải quay về
    # đúng con số nằm trong bằng chứng, nếu không mỗi cụm thành một số lạ.
    claim = claim.replace(THIN_SPACE, "")
    # Mô hình diễn đạt lại thường thay dấu cách mảnh bằng DẤU CÁCH THƯỜNG.
    #
    # Khi ấy "5 155.25" bị đọc thành hai số 5 và 155,25 — không số nào có trong
    # bằng chứng, và một câu hoàn toàn đúng bị đánh trượt. Chỉ gộp khi bên phải
    # đúng ba chữ số, tức là một nhóm hàng nghìn, để không dính vào "2 giao dịch".
    claim = _GROUPING_SPACE_RE.sub("", claim)
    # Ngày viết theo lối Việt Nam quy về ISO rồi mới đối chiếu. Không có bước này
    # thì "16/09/2022" bị đọc thành ba con số 16, 9, 2022 mà bằng chứng không có.
    claim = _VN_DATE_RE.sub(lambda m: _iso_if_cited(m, tokens), claim)
    for token in sorted(tokens, key=len, reverse=True):
        claim = claim.replace(token, " ")
    return claim


#: Dấu cách ĐỨNG GIỮA hai nhóm chữ số của một số có phân tách hàng nghìn.
_GROUPING_SPACE_RE = re.compile(r"(?<=\d)[ \u00a0](?=\d{3}(?!\d))")

#: Ngày dd/mm/yyyy trong câu diễn giải.
_VN_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _iso_if_cited(match: re.Match[str], cited_tokens: set[str]) -> str:
    """Đổi dd/mm/yyyy thành ISO nếu bằng chứng có ngày đó; không thì giữ nguyên.

    Giữ nguyên khi không khớp là có chủ ý: một ngày KHÔNG có trong bằng chứng
    phải rơi xuống bộ kiểm số và bị nêu, chứ không được lặng lẽ biến mất.
    """
    day, month, year = match.groups()
    iso = f"{year}-{month}-{day}"
    return iso if any(iso in token for token in cited_tokens) else match.group(0)


#: Số liệu trong câu diễn giải, dùng để đối chiếu với bằng chứng đã trích dẫn.
#:
#: Dấu trừ phải nằm *trong* token. Bản trước chặn dấu trừ ở lookbehind, nên với
#: ``-16.466031`` bộ quét bỏ qua ``16.466031`` rồi lại bắt được ``466031`` — phần
#: thập phân bị cắt rời thành một số nguyên không tồn tại trong bằng chứng nào,
#: và mọi câu có số âm đều bị đánh trượt UNSUPPORTED_CLAIM.
#:
#: Ba rào, mỗi rào chặn một kiểu đọc sai:
#:
#: * ``(?<![\w.-])`` — chữ số đứng ngay sau dấu chấm luôn là phần thập phân của
#:   một số khác, không bao giờ là số độc lập. Đây là rào sửa lỗi trên. Gạch
#:   ngang giữ nguyên để ``2022-09-01`` không rã thành ``2022`` và ``-09``.
#: * ``-?`` — dấu trừ nằm *trong* token, nên số âm được đọc trọn vẹn. Rào
#:   lookbehind ở trên đã lo việc phân biệt dấu trừ trong câu văn với gạch nối
#:   trong định danh.
#: * ``(?![\w-])`` — cố tình KHÔNG chặn dấu chấm ở đây: nhóm ``(?:\.\d+)?`` đã
#:   ăn hết phần thập phân rồi, nên dấu chấm còn lại chỉ có thể là dấu kết câu.
#:   Chặn nó sẽ làm mọi số đứng cuối câu không bao giờ được kiểm chứng.
#:
#: Định danh (mã tài khoản, mã bằng chứng) đã được ``_mask_identifiers`` xoá
#: trước khi quét.
_CLAIM_NUMBER_RE = re.compile(r"(?<![\w.-])-?\d+(?:\.\d+)?(?![\w-])")

#: Định danh nghiệp vụ xuất hiện trong câu diễn giải: khoá tài khoản (``070:10042B660``)
#: và mã có tiền tố (``EV-…``, ``ALT-…``, ``CASE-…``, ``INV-…``). Số giao dịch thuần
#: chữ số KHÔNG nằm ở đây — bộ kiểm số đã phủ chúng.
_IDENTIFIER_RE = re.compile(r"\b(?:[0-9A-Za-z]{1,20}:[0-9A-Za-z]{2,20}|(?:EV|ALT|CASE|SAR|INV|APR)-[0-9A-Za-z-]{4,})\b")


_EVIDENCE_ID_RE = re.compile(r"\bEV-[A-Za-z0-9_]{3,}\b")
_TRUNCATION_RE = re.compile(
    r"cắt ngắn|cắt bớt|truncat|phân trang|trang tiếp theo|chỉ hiển thị|chỉ trích xuất", re.IGNORECASE
)
#: "giao dịch", "transaction" — để chỉ bác bỏ khiếu nại đang nói về giao dịch,
#: không phải mọi khiếu nại tình cờ có một dãy số dài.
_TRANSACTION_WORD_RE = re.compile(r"giao dịch|transaction", re.IGNORECASE)
#: Mã giao dịch của bộ dữ liệu dài 7 chữ số trở lên; ngưỡng này giữ cho số tiền
#: và năm tháng không bị nhầm thành mã.
_LONG_NUMBER_RE = re.compile(r"(?<![\w.])\d{7,}(?![\w.])")
_DENIES_EXISTENCE_RE = re.compile(
    r"không tồn tại|không có trong|không nằm trong|thiếu trong|does not exist|not present|absent",
    re.IGNORECASE,
)
#: Nhận định ĐANG ĐẾM giao dịch: "15 giao dịch xuyên biên giới", "nhận qua 4
#: giao dịch", "3 giao dịch rút tiền mặt". Một phép đếm không bao giờ nằm sẵn
#: trong payload bằng chứng — nó được suy ra bằng cách đếm các dòng — nên bộ
#: kiểm tất định luôn báo nó là số bịa. Điều đó chỉ chấp nhận được khi bằng
#: chứng ĐẦY ĐỦ; khi sổ giao dịch bị cắt ở 50 dòng thì phép đếm không thể kiểm
#: chứng được bằng cả hai phía, và đứng trên nó là buộc tội bịa đặt oan.
_TRANSACTION_COUNT_RE = re.compile(
    r"\d+\s+giao dịch|\d+\s+transactions?|số lượng giao dịch|qua \d+ giao dịch",
    re.IGNORECASE,
)


def _transaction_facts(evidence: list[EvidenceEnvelope]) -> dict[str, Any]:
    """Đếm sổ giao dịch BẰNG CODE để tác tử phản biện khỏi phải tự đếm.

    Trả về đúng những phép đếm mà tranh cãi hay nổ ra: tổng số dòng, số giao
    dịch xuyên biên giới, và phân bố theo quốc gia đích. Kèm cờ ``truncated``:
    thiếu nó thì một con số đúng-trên-phần-đọc-được lại bị đọc thành tổng thật.
    """
    rows: list[dict[str, Any]] = []
    truncated = False
    for item in evidence:
        if item.type is not EvidenceType.TRANSACTION:
            continue
        payload = item.payload or {}
        truncated = truncated or bool(payload.get("truncated"))
        for row in payload.get("items") or []:
            if isinstance(row, dict):
                rows.append(row)

    if not rows:
        return {"available": False, "note": "Chưa thu sổ giao dịch nào cho phiên này."}

    by_destination: dict[str, int] = {}
    cross_border = 0
    for row in rows:
        src, dst = row.get("source_country"), row.get("destination_country")
        if dst:
            by_destination[dst] = by_destination.get(dst, 0) + 1
        if src and dst and src != dst:
            cross_border += 1

    return {
        "available": True,
        "transactions_in_evidence": len(rows),
        "cross_border_transactions": cross_border,
        "transactions_by_destination_country": dict(
            sorted(by_destination.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "ledger_truncated": truncated,
        "how_to_use": (
            "Đây là phép đếm do hệ thống tính trên chính sổ giao dịch đã thu, không phải "
            "do mô hình đếm. Dùng nó làm chuẩn khi đối chiếu các con số trong nhận định; "
            "đừng tự đếm lại trong khối dữ liệu không tin cậy. Nếu ledger_truncated là "
            "true thì mọi phép đếm chỉ đúng trên phần đã đọc được, và một nhận định lệch "
            "so với nó KHÔNG phải là bịa đặt."
        ),
    }


def _is_counting_claim(issue: Any) -> bool:
    """Khiếu nại này có đang tranh cãi về một PHÉP ĐẾM giao dịch không?

    Xét cả ``claim`` lẫn ``detail``: bộ kiểm tất định để phép đếm ở ``claim``
    ("15 giao dịch xuyên biên giới") còn phần ``detail`` chỉ ghi con số trần
    ("Các con số [15.0] không có trong bằng chứng"), trong khi tác tử phản biện
    thì ngược lại. Bỏ sót một trong hai vế là bỏ sót đúng một nửa số trường hợp.
    """
    return bool(
        _TRANSACTION_COUNT_RE.search(getattr(issue, "claim", "") or "")
        or _TRANSACTION_COUNT_RE.search(getattr(issue, "detail", "") or "")
    )


def _numeric_values(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        yield float(value)
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _numeric_values(nested)
    elif isinstance(value, list):
        yield float(len(value))
        for nested in value:
            yield from _numeric_values(nested)


class InvestigationSupervisorAgent:
    name = "investigation_supervisor"

    def __init__(self, service: GeminiService, investigation_id: str):
        self.service = service
        self.investigation_id = investigation_id

    async def plan(
        self,
        *,
        alert: dict[str, Any],
        evidence: list[EvidenceEnvelope],
        validation: ValidationResult | None = None,
    ) -> GeminiCallResult[SupervisorPlan]:
        baseline = self._deterministic_plan(alert=alert, evidence=evidence, validation=validation)
        prompt = get_prompt(self.name)
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context={
                "alert": alert,
                "evidence_collected": [
                    item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content
                ],
                "open_validation": validation.model_dump(mode="json") if validation else None,
                "allow_listed_tool_catalog": InvestigationTools.tool_catalog(),
                "deterministic_safety_candidate": baseline.model_dump(mode="json"),
            },
            untrusted_data=[item.payload for item in evidence if item.is_untrusted_content],
            response_schema=SupervisorPlan,
            fallback_response=baseline,
        )
        # The deterministic baseline is a floor, not a suggestion. A model-authored
        # plan that skips the behaviour and transaction tools leaves the explanation
        # with nothing to describe, so the alert comes back to the reviewer saying
        # only that it scored highly. Baseline decisions run first and keep their
        # slots; the model may add to them, never remove.
        plan = result.output
        decisions = list(baseline.decisions)
        seen = {decision.tool for decision in decisions}
        for decision in plan.decisions:
            if decision.tool not in seen:
                decisions.append(decision)
                seen.add(decision.tool)
        plan = plan.model_copy(update={"decisions": decisions[: get_settings().max_tool_calls]})
        return GeminiCallResult(output=plan, metadata=result.metadata)

    def _deterministic_plan(
        self,
        *,
        alert: dict[str, Any],
        evidence: list[EvidenceEnvelope],
        validation: ValidationResult | None = None,
    ) -> SupervisorPlan:
        """Prioritize detector-specific evidence with a closed tool vocabulary."""
        grouped = _evidence_by_type(evidence)
        decisions: list[ToolDecision] = []
        open_questions: list[str] = []

        if EvidenceType.RISK_BREAKDOWN not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetRiskBreakdown",
                    arguments={"alert_id": alert["alert_id"]},
                    short_rationale="Lấy điểm chính thức và nhánh phát hiện hiện có trước.",
                )
            )

        detector = alert["detector"]
        if detector == "graph":
            if EvidenceType.GRAPH_PATTERN not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetGraphEvidence",
                        arguments={"alert_id": alert["alert_id"]},
                        short_rationale="Đồ thị là nhánh chính; cần bằng chứng có cấu trúc do bộ phát hiện tạo ra.",
                    )
                )
            if EvidenceType.GRAPH_NEIGHBORHOOD not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetGraphNeighborhood",
                        arguments={"account_key": alert["account_key"], "hops": 1, "time_window": "7d"},
                        short_rationale="Thu thập ngữ cảnh giới hạn một chặng mà không yêu cầu mô hình tự duyệt đồ thị.",
                    )
                )
            open_questions.append("Cần có mẫu hình từ bộ phát hiện đồ thị và các cạnh giao dịch tương ứng.")
        elif detector == "ml":
            if EvidenceType.BEHAVIOR_FEATURE not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetAccountBehavior",
                        arguments={"account_key": alert["account_key"], "window": "7d"},
                        short_rationale="Nhánh bất thường cần giá trị đặc trưng nguồn trước khi tạo bản giải thích.",
                    )
                )
            if EvidenceType.ANOMALY_EXPLANATION not in grouped:
                decisions.append(
                    ToolDecision(
                        tool="GetAnomalyExplanation",
                        arguments={"alert_id": alert["alert_id"], "account_key": alert["account_key"], "window": "7d"},
                        short_rationale="Thu thập mức đóng góp sai lệch đặc trưng được tính tất định cho điểm Isolation Forest.",
                    )
                )
        else:
            if EvidenceType.RULE_TRIGGER not in grouped:
                open_questions.append("Kết quả phát hiện còn thiếu chi tiết luật đã kích hoạt.")

        if EvidenceType.TRANSACTION not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetTransactions",
                    arguments={"account_key": alert["account_key"], "limit": 50},
                    short_rationale="Thu thập tập giao dịch nguồn có giới hạn để đối chiếu bối cảnh cảnh báo.",
                )
            )
        if EvidenceType.TYPOLOGY_MAPPING not in grouped:
            decisions.append(
                ToolDecision(
                    tool="GetTypology",
                    arguments={"typology_code": alert["typology_code"]},
                    short_rationale="Đối chiếu nhóm hành vi qua danh mục có phiên bản, không dựa vào kiến thức của lời nhắc.",
                )
            )

        if validation and validation.status == "FAIL":
            for issue in validation.issues:
                if (
                    issue.required_tool
                    and issue.required_tool
                    in {
                        "GetRiskBreakdown",
                        "GetAccountBehavior",
                        "GetTransactions",
                        "GetGraphEvidence",
                        "GetGraphNeighborhood",
                        "GetTypology",
                        "GetAnomalyExplanation",
                    }
                    and all(decision.tool != issue.required_tool for decision in decisions)
                ):
                    # The deterministic workflow never lets critic inject raw
                    # arguments. It derives safe arguments per tool.
                    safe_arguments = {
                        "GetGraphEvidence": {"alert_id": alert["alert_id"]},
                        "GetTransactions": {"account_key": alert["account_key"], "limit": 50},
                        "GetAccountBehavior": {"account_key": alert["account_key"], "window": "7d"},
                        "GetAnomalyExplanation": {
                            "alert_id": alert["alert_id"],
                            "account_key": alert["account_key"],
                            "window": "7d",
                        },
                        "GetTypology": {"typology_code": alert["typology_code"]},
                    }.get(issue.required_tool)
                    if safe_arguments:
                        decisions.append(
                            ToolDecision(
                                tool=issue.required_tool,
                                arguments=safe_arguments,
                                short_rationale=f"Tác tử phản biện yêu cầu bằng chứng được hỗ trợ: {issue.type}.",
                            )
                        )
        settings = get_settings()
        return SupervisorPlan(
            decisions=decisions[: settings.max_tool_calls],
            open_questions=open_questions,
            evidence_sufficient=not decisions and not open_questions,
        )


class ExplanationAgent:
    name = "explanation_agent"

    def __init__(self, service: GeminiService, investigation_id: str):
        self.service = service
        self.investigation_id = investigation_id

    async def explain(self, alert: dict[str, Any], evidence: list[EvidenceEnvelope]) -> GeminiCallResult[Explanation]:
        deterministic = self._deterministic(alert, evidence)
        prompt = get_prompt(self.name)
        # Chiều đo quyết định của nhóm hành vi này, kèm số đo đã tính sẵn.
        #
        # Không đưa vào thì mô hình viết cùng một khuôn cho mọi nhóm: liệt kê
        # tên dấu hiệu đã khớp mà không nói khớp ở mức nào. Số ở đây do CODE
        # tính từ bằng chứng, mô hình chỉ việc nêu đúng thứ tự.
        grouped_evidence = _evidence_by_type(evidence)
        measurements = _signal_measurements(grouped_evidence) | _graph_measurements(grouped_evidence)
        matched_signals = [name for name, ok in _observed_signals(grouped_evidence).items() if ok]
        trusted = {
            "alert": alert,
            "evidence": [item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content],
            "deterministic_candidate": deterministic.model_dump(mode="json"),
            "typology_focus": [
                {
                    "typology_code": item.payload["typology_code"],
                    "typology_name": item.payload.get("name_vi") or item.payload.get("name"),
                    "dimension": _TYPOLOGY_FOCUS.get(item.payload["typology_code"], {}).get("angle", ""),
                    "measurements": [
                        {"signal": name, "measured": measurements[name]}
                        for name in _TYPOLOGY_FOCUS.get(item.payload["typology_code"], {}).get("signals", [])
                        if name in measurements
                    ],
                    "matched_signals": [
                        name
                        for name in _TYPOLOGY_FOCUS.get(item.payload["typology_code"], {}).get("signals", [])
                        if name in matched_signals
                    ],
                }
                for item in grouped_evidence.get(EvidenceType.TYPOLOGY_MAPPING, [])
            ],
        }
        untrusted = [item.payload for item in evidence if item.is_untrusted_content]
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context=trusted,
            untrusted_data=untrusted,
            response_schema=Explanation,
            fallback_response=deterministic,
            sanitize=self._drop_uncited_facts,
        )
        # The deterministic candidate is sourced by construction: every fact in
        # it was built from a payload it cites. A model response that paraphrases
        # it and loses the citations is not an improvement — the uncited facts
        # get dropped and the reviewer is left with less than the pipeline
        # already knew. The model earns the output by carrying more sourced
        # facts than the floor, not by rewording it.
        sourced = sum(1 for claim in result.output.claims if claim.claim_type == "FACT")
        floor = sum(1 for claim in deterministic.claims if claim.claim_type == "FACT")
        if sourced < floor:
            return GeminiCallResult(output=deterministic, metadata=result.metadata)
        return result

    #: Mã nội bộ của nhánh phát hiện → tên nghiệp vụ. Cùng bảng với
    #: RISK_COMPONENT_LABELS ở web/src/api/format.ts.
    _BRANCH_WORDS = {
        "mega_pna": "mô hình phân tích mạng lưới giao dịch",
        "geo_rule": "bộ luật địa lý",
        "anomaly": "mô hình phát hiện bất thường",
        "rule": "bộ luật nghiệp vụ",
    }

    @classmethod
    def _scrub_prose(cls, text_value: str) -> str:
        """Xoá mã nội bộ và mẫu số N/100 khỏi câu chữ MÔ HÌNH tự viết.

        Sửa khuôn mẫu tất định là chưa đủ: Gemini viết phần tóm tắt bằng lời của
        nó, và nó CHÉP mã nội bộ từ ngữ cảnh được đưa vào. Đo trên 30 phiên
        thật, bản tóm tắt ra câu "dựa trên mô hình phân tích mạng lưới giao dịch
        (mega_pna) với mức điểm rủi ro tối đa là 100/100" — vừa lộ mã nhánh vừa
        dính lại đúng mẫu số đã bỏ.

        Đây là bộ lọc TẤT ĐỊNH chứ không phải một câu nhắc trong prompt: mô hình
        đã chứng minh là không giữ được lời hứa loại này, nên chặn ở đầu ra.
        """
        cleaned = re.sub(r"\s*\((?:mega_pna|geo_rule|anomaly|rule|ml|graph)\)", "", text_value)
        for code, label in cls._BRANCH_WORDS.items():
            cleaned = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w-])", label, cleaned)
        # "100/100" → "100 điểm": mẫu số viết bằng số bị bộ kiểm tất định đòi
        # bằng chứng riêng, và cảnh báo 57 điểm không có số 100 nào để khớp.
        cleaned = re.sub(r"(?<![\d/])(\d{1,3})/100(?![\d/])", r"\1 điểm", cleaned)
        # Câu vốn đã có chữ "điểm" trước con số thì phép thay trên đẻ ra "điểm 57
        # điểm". Gộp lại thay vì để một câu lặp chữ ra màn hình.
        cleaned = re.sub(r"điểm\s+(\d{1,3})\s+điểm", r"điểm \1", cleaned)
        return cleaned

    @classmethod
    def _scrub_tree(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls._scrub_prose(value)
        if isinstance(value, list):
            return [cls._scrub_tree(v) for v in value]
        if isinstance(value, dict):
            # `source` là KHOÁ MÁY (tra nhãn hiển thị), không phải câu chữ —
            # đổi nó sẽ làm hỏng phép tra ở cả API lẫn giao diện.
            return {k: (v if k == "source" else cls._scrub_tree(v)) for k, v in value.items()}
        return value

    @staticmethod
    def _drop_uncited_facts(parsed: Any) -> Any:
        """Refuse the offending claim, not the whole investigation.

        A FACT without ``evidence_refs`` is exactly what this system is built
        to reject, but the rejection used to happen at schema validation, which
        discards every well-sourced claim in the same response and fails the
        run. Dropping the single claim keeps that guarantee and leaves the rest
        for the critic to audit. The removal is stated in the output, so a
        reviewer sees that the model asserted something it could not source.
        """
        if not isinstance(parsed, dict):
            return parsed
        parsed = ExplanationAgent._scrub_tree(parsed)
        if not isinstance(parsed.get("claims"), list):
            return parsed
        kept = [
            claim
            for claim in parsed["claims"]
            if not (isinstance(claim, dict) and claim.get("claim_type") == "FACT" and not claim.get("evidence_refs"))
        ]
        dropped = len(parsed["claims"]) - len(kept)
        if not dropped:
            return parsed
        note = (
            f"Đã loại {dropped} nhận định loại DỮ KIỆN do không trích dẫn bằng chứng nào. "
            "Nội dung bị loại không được đưa vào bản giải thích."
        )
        return {**parsed, "claims": kept, "missing_information": [*(parsed.get("missing_information") or []), note]}

    @staticmethod
    def _deterministic(alert: dict[str, Any], evidence: list[EvidenceEnvelope]) -> Explanation:
        grouped = _evidence_by_type(evidence)
        # Thiếu phân rã điểm thì viết bản giải thích RÚT GỌN, không ném lỗi.
        #
        # Bản cũ tra thẳng vào dict và ném KeyError khi công cụ GetRiskBreakdown
        # thất bại — làm hỏng cả phiên điều tra, người rà soát nhận được "FAILED"
        # thay vì một bản giải thích thiếu một phần. Chứng cứ khác vẫn dùng được.
        risk_items = grouped.get(EvidenceType.RISK_BREAKDOWN) or []
        risk_ev = risk_items[-1] if risk_items else None
        breakdown = risk_ev.payload if risk_ev else {}
        drivers: list[RiskDriver] = []
        claims: list[Claim] = []
        if risk_ev is not None:
            claims.append(
                Claim(
                    claim_id=_claim_id(),
                    # Thang 0-100, KHÔNG phải 0-1 ba chữ số thập phân: "1.000"
                    # đọc trong tiếng Việt là "một nghìn", và bộ đối chiếu số của
                    # tác tử phản biện cũng đọc đúng như vậy. Cột `risk_score`
                    # trên bảng cảnh báo và trang Chi tiết đều đã dùng thang 100.
                    #
                    # Thang viết BẰNG CHỮ ("một trăm"), không viết "X/100": bộ
                    # kiểm tất định rút MỌI chữ số trong câu rồi đòi mỗi số phải
                    # có mặt trong bằng chứng. Mẫu số 100 viết bằng số sẽ bị đòi
                    # bằng chứng cho riêng nó, và với cảnh báo 57 điểm thì không
                    # có số 100 nào để khớp — cả phiên trượt vì một mẫu số. Cùng
                    # luật với `flow_shape` ở trên.
                    claim=(
                        f"Hệ thống chấm mức rủi ro {float(breakdown['final_risk_score_100']):.0f} điểm "
                        f"trên thang một trăm cho cảnh báo {alert['alert_id']} (càng cao càng đáng chú ý)."
                    ),
                    claim_type="FACT",
                    evidence_refs=[risk_ev.evidence_id],
                    confidence=1.0,
                )
            )
        facts = [claim.claim for claim in claims]
        inferences: list[str] = []
        missing: list[str] = []
        typologies: list[str] = []
        typology_names: list[str] = []

        for source, component in (breakdown.get("components") or {}).items():
            if component["available"]:
                branch = {
                    "anomaly": "Mô hình phát hiện bất thường",
                    "rule": "Bộ luật nghiệp vụ",
                    "graph": "Bộ phát hiện đồ thị mạng lưới",
                    # Tên kiến trúc ("MEGA-PNA") không đi vào bản giải thích đọc
                    # cho chuyên viên: các nhánh khác đều gọi theo VIỆC chúng làm.
                    "mega_pna": "Mô hình phân tích mạng lưới giao dịch",
                    "geo_rule": "Bộ luật địa lý",
                }.get(source, source)
                reason = f"{branch} là nhánh sinh ra cảnh báo này và là nguồn điểm chính thức."
                if source == "geo_rule":
                    _corr = _transaction_corridor(grouped)
                    if _corr:
                        reason = (
                            f"Bộ luật địa lý sinh ra cảnh báo này: giao dịch qua hành lang "
                            f"{_corr['from_country']} → {_corr['to_country']}, với {_corr['to_country']} "
                            f"là vùng tài phán bị xếp mức rủi ro cao theo chính sách."
                        )
                drivers.append(
                    RiskDriver(
                        source=source,
                        score=component["score"],
                        weight=component["weight"],
                        contribution=component["contribution"],
                        reason=reason,
                        evidence_refs=[risk_ev.evidence_id] if risk_ev else [],
                    )
                )

        corridor_named = False
        for item in grouped.get(EvidenceType.RULE_TRIGGER, []):
            geo = item.payload.get("geo_context") or {}
            if geo.get("from_country") and geo.get("to_country"):
                claims.append(_corridor_claim(geo, item.evidence_id))
                facts.append(claims[-1].claim)
                corridor_named = True
            for rule in item.payload.get("triggered_rules", []):
                # Hành lang đã được câu riêng ở trên kể đủ cả hai mẫu số; nhắc
                # lại nhãn thô ở đây chỉ tạo hai con số khác nhau cho cùng một
                # hành lang trên cùng một màn hình.
                if geo and rule["factor_code"] == "GEO_CORRIDOR":
                    continue
                claim = Claim(
                    claim_id=_claim_id(),
                    # Nhãn, không phải mã. "GEO_FX" không nói gì với chuyên viên;
                    # "3 giao dịch đổi loại tiền" thì có.
                    # Yếu tố BỐI CẢNH (đóng góp và trọng số đều 0) mô tả tình
                    # huống chứ không chấm điểm. Dán "đóng góp 0.00 điểm" vào
                    # sau nó khiến bản giải thích tự phủ định chính mình: nêu ra
                    # một dữ kiện rồi bảo dữ kiện ấy không đóng góp gì.
                    claim=(
                        # "0 giao dịch tiền mặt." đứng một mình đọc như một dòng
                        # rác. Cùng thông tin ấy, viết là "Không có giao dịch
                        # tiền mặt" thì thành một câu tiếng Việt bình thường.
                        f"{_absence_wording(rule.get('factor_label') or rule['factor_code'])}"
                        + (
                            "."
                            # Điều kiện chỉ xét ĐÓNG GÓP, không xét trọng số nữa.
                            #
                            # Bản trước đòi cả hai bằng 0, nên yếu tố geo_rule như
                            # GEO_CASH (trọng số 0,30 nhưng đóng góp 0,00 khi tài
                            # khoản không có giao dịch tiền mặt) vẫn in ra "0 giao
                            # dịch tiền mặt — yếu tố này đóng góp 0.00 điểm". Đo
                            # trên 30 phiên thật: 15 bản giải thích dính câu này.
                            # Đóng góp bằng 0 thì câu "đóng góp 0.00" là thừa và
                            # tự phủ định, bất kể trọng số bao nhiêu.
                            if float(rule["contribution"]) == 0
                            or _label_already_states(rule.get("factor_label") or "", float(rule["contribution"]))
                            else f" — yếu tố này đóng góp {float(rule['contribution']):.2f} điểm vào mức rủi ro."
                        )
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(claim)
                facts.append(claim.claim)

        # Fallback nêu tên HÀNH LANG khi nhánh địa lý không nạp được geo_context:
        # quốc gia hai đầu vẫn nằm trong sổ giao dịch, nên vẫn nói được vùng tài
        # phán rủi ro cao là nước nào thay vì bỏ trống.
        if not corridor_named:
            _corr = _transaction_corridor(grouped)
            if _corr:
                _tx_ev = next(iter(grouped.get(EvidenceType.TRANSACTION, [])), None)
                _corr_claim = Claim(
                    claim_id=_claim_id(),
                    # NÓI RÕ PHẠM VI: đây là hành lang đọc từ SỔ GIAO DỊCH đính
                    # kèm, không phải hành lang đã làm cảnh báo nổ.
                    #
                    # Hai thứ khác nhau và có thể khác quốc gia: ô chấm điểm địa
                    # lý xét một cửa sổ riêng, còn sổ giao dịch ở đây chỉ là các
                    # dòng gần nhất. Gọi chung một tên thì bản giải thích tự mâu
                    # thuẫn với phần phân rã điểm — tác tử phản biện bắt đúng lỗi
                    # ấy và đánh trượt, và đó là nguyên nhân phần lớn phiên điều
                    # tra nhánh địa lý không chạy xong (đo 27/08/2026).
                    claim=(
                        f"Trong sổ giao dịch đính kèm, hành lang xuyên biên giới xuất hiện nhiều nhất là "
                        f"{_corr['from_country']} → {_corr['to_country']} ({_corr['txn_count']} giao dịch). "
                        "Đây là quan sát trên các giao dịch gần nhất, không phải hành lang mà bộ luật địa lý "
                        "dùng để chấm điểm cảnh báo — hai phạm vi có thể khác nhau."
                    ),
                    claim_type="FACT",
                    evidence_refs=[_tx_ev.evidence_id] if _tx_ev else [],
                    confidence=1.0,
                )
                claims.append(_corr_claim)
                facts.append(_corr_claim.claim)

        # MỘT cửa sổ hành vi thôi, cửa sổ rộng nhất.
        #
        # Tác tử điều phối hay gọi GetAccountBehavior nhiều lần với cửa sổ khác
        # nhau, nên bản giải thích in ra hai câu "Trong cửa sổ quan sát từ … tài
        # khoản nhận …" với hai khoảng thời gian và hai con số khác hẳn nhau.
        # Người rà soát đọc thành mâu thuẫn — và không có cách nào biết câu nào
        # là câu để dựa vào. Câu tóm tắt cũng chỉ nói về một cửa sổ, nên hai
        # phần còn lệch nhau nữa.
        behavior_items = [
            item for item in grouped.get(EvidenceType.BEHAVIOR_FEATURE, []) if item.payload.get("observed")
        ]
        if behavior_items:
            behavior_items = [
                max(behavior_items, key=lambda item: int(item.payload["observed"].get("window_days") or 0))
            ]
        for item in behavior_items:
            observed = item.payload.get("observed")
            if not observed:
                continue
            window = f"từ {_day(observed['window_start'])} đến {_day(observed['window_end'])}"
            unit = f" {observed['currency']}" if observed.get("currency") else ""

            if not observed["incoming_count"] and not observed["outgoing_count"]:
                missing.append(
                    f"Khoảng thời gian quan sát {window} không có giao dịch nào của tài khoản này, "
                    "nên mọi chỉ số hành vi đều bằng 0 và chưa nói lên được điều gì."
                )
                continue

            if observed.get("currency"):
                flow_text = (
                    f"Trong khoảng {window}, tài khoản nhận {_amount(observed['inflow_amount'])}{unit} "
                    f"qua {observed['incoming_count']} giao dịch từ {observed['unique_in_counterparties']} đối tác, "
                    f"và chuyển đi {_amount(observed['outflow_amount'])}{unit} qua {observed['outgoing_count']} "
                    f"giao dịch tới {observed['unique_out_counterparties']} đối tác, "
                    f"trải trên {observed['active_days']} ngày có phát sinh. Đây là tổng của toàn bộ giao dịch "
                    "trong khoảng, không phải của vài giao dịch nêu bên dưới."
                )
            else:
                flow_text = (
                    f"Trong khoảng {window}, tài khoản nhận {observed['incoming_count']} giao dịch từ "
                    f"{observed['unique_in_counterparties']} đối tác và chuyển đi {observed['outgoing_count']} "
                    f"giao dịch tới {observed['unique_out_counterparties']} đối tác, trải trên "
                    f"{observed['active_days']} ngày có phát sinh. Các giao dịch thuộc nhiều loại tiền khác nhau "
                    "nên không cộng gộp thành một tổng."
                )
            flow = Claim(
                claim_id=_claim_id(),
                claim=flow_text,
                claim_type="FACT",
                evidence_refs=[item.evidence_id],
                confidence=1.0,
            )
            claims.append(flow)
            facts.append(flow.claim)

            # Chỉ nêu tỉ lệ tiền ra đi nhanh khi cửa sổ dùng MỘT loại tiền; còn
            # lại vẫn nêu thời gian giữ tiền vì thời gian không phụ thuộc loại tiền.
            if observed["rapid_outflow_amount"] > 0 and observed.get("currency"):
                dwell = observed.get("median_dwell_hours")
                # MỘT cách làm tròn cho một số đo.
                #
                # Câu tóm tắt in "1.2 giờ" còn dữ kiện in "1.25 giờ" — cùng một
                # phép đo, hai con số. Người đọc không biết mình đang nhìn hai
                # thứ khác nhau hay một thứ bị ghi sai, và mất tin ở cả hai.
                dwell_text = (
                    f" Thời gian giữ tiền trung vị giữa lúc nhận và lần chuyển đi kế tiếp là "
                    f"{float(dwell):.1f} giờ."
                    if dwell is not None
                    else ""
                )
                rapid = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"{_amount(observed['rapid_outflow_amount'])}{unit} được chuyển đi trong vòng "
                        f"{observed['rapid_window_hours']} giờ sau khi nhận, chiếm "
                        f"{_percent(float(observed['rapid_outflow_percent']), of_nonzero=True)}% "
                        "tổng tiền ra của cửa sổ."
                        f"{dwell_text}"
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(rapid)
                facts.append(rapid.claim)

            if observed["new_counterparties"] > 0:
                fresh = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"{observed['new_counterparties']} trong số các đối tác của khoảng này chưa từng giao dịch "
                        "với tài khoản này trước đó."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(fresh)
                facts.append(fresh.claim)

        for item in grouped.get(EvidenceType.ANOMALY_EXPLANATION, []):
            if not item.payload.get("available", True):
                missing.append(
                    "Không có kết quả Isolation Forest cho tài khoản này nên chưa quy được điểm bất thường "
                    "về đặc trưng cụ thể."
                )
                continue
            informative = [
                feature
                for feature in item.payload.get("top_anomalous_features", [])
                if abs(float(feature["reference_percentile"]) - 50.0) >= 10.0
            ]
            if not informative:
                missing.append(
                    "Các đặc trưng của tài khoản không lệch khỏi trung vị nhóm tài khoản cùng cửa sổ, "
                    "nên chưa quy được điểm bất thường về đặc trưng cụ thể."
                )
                continue
            for feature in informative[:3]:
                name = feature["feature"]
                label = FEATURE_LABELS_VI.get(name, name)
                percentile = float(feature["reference_percentile"])
                side = "cao hơn" if percentile >= 50 else "thấp hơn"
                claim = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"So với các tài khoản hoạt động trong cùng cửa sổ, {label} ({name}) của tài khoản ở mức "
                        f"{feature['value']}, nằm tại phân vị {feature['reference_percentile']} — {side} mức "
                        "trung vị của nhóm đối chiếu."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=0.95,
                )
                claims.append(claim)
                facts.append(claim.claim)

        graph_items = grouped.get(EvidenceType.GRAPH_PATTERN, [])
        if alert["detector"] == "graph" and not graph_items:
            missing.append(
                "Chưa có bằng chứng có cấu trúc từ bộ phát hiện đồ thị; không khẳng định mẫu hình đồ thị nào."
            )
        for item in graph_items:
            pattern = item.payload.get("pattern")
            if not pattern:
                continue
            claim = Claim(
                claim_id=_claim_id(),
                claim=f"Bộ phát hiện đồ thị ghi nhận mẫu hình {pattern} liên quan đến {len(item.payload.get('accounts', []))} tài khoản.",
                claim_type="FACT",
                evidence_refs=[item.evidence_id],
                confidence=1.0,
            )
            claims.append(claim)
            facts.append(claim.claim)

        # Hành lang của cảnh báo, dùng để chọn giao dịch dẫn chứng bên dưới.
        corridor_geo = next(
            (
                rule_item.payload["geo_context"]
                for rule_item in grouped.get(EvidenceType.RULE_TRIGGER, [])
                if rule_item.payload.get("geo_context")
            ),
            None,
        )
        # Một tập giao dịch thôi — tập ĐẦY ĐỦ nhất.
        #
        # Tác tử điều phối gọi GetTransactions nhiều lần (bộ đếm "agent repeated
        # identical tool call" bắt được điều này), mỗi lần sinh một bằng chứng
        # riêng chứa gần như cùng những dòng ấy. Duyệt hết thì cùng một giao dịch
        # được kể hai, ba lần trong danh sách dữ kiện — nhìn như tài khoản
        # chuyển 30.101,17 Euro bốn lần trong khi thực tế là hai.
        transaction_items = grouped.get(EvidenceType.TRANSACTION, [])
        if transaction_items:
            transaction_items = [max(transaction_items, key=lambda item: len(item.payload.get("items", [])))]
        for item in transaction_items:
            records = item.payload.get("items", [])
            if not records:
                missing.append("Không lấy được giao dịch nào của tài khoản tính đến thời điểm rà soát.")
                continue

            account = alert["account_key"]
            # Lấy giao dịch lớn nhất của CẢ HAI CHIỀU, không phải ba dòng lớn
            # nhất nói chung.
            #
            # Sổ giao dịch trả về 50 dòng mới nhất, và với tài khoản chuyển đi
            # nhiều thì cả 50 dòng đều là tiền ra. Bản giải thích khi ấy nói
            # "nhận 54.154 từ 2 đối tác" mà không dẫn nổi một giao dịch nhận
            # nào — tác tử phản biện bắt đúng lỗi đó.
            outs = [r for r in records if r["source"] == account]
            ins = [r for r in records if r["source"] != account]

            def by_amount(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return sorted(rows, key=lambda row: float(row["amount"]), reverse=True)

            chosen = by_amount(ins)[:2] + by_amount(outs)[:2]

            # Với cảnh báo hành lang, "giao dịch lớn nhất" là tiêu chí sai.
            #
            # Đo trên một cảnh báo UK→UAE có thật: cả ba giao dịch được chọn đều
            # là UK→UK. Bản giải thích vì thế nói về hành lang UAE ở phần lý do
            # rồi dẫn chứng bằng ba giao dịch nội địa — không dẫn nổi một giao
            # dịch nào của chính hành lang bị cảnh báo. Chuyên viên đọc xong
            # không có gì để mở ra xem.
            #
            # Thứ tự ưu tiên: giao dịch mà bộ luật chấm điểm, rồi giao dịch đúng
            # hành lang ấy, rồi giao dịch xuyên biên giới bất kỳ. Giao dịch lớn
            # nhất vẫn được giữ ở cuối để không mất bối cảnh quy mô.
            driving = str(corridor_geo.get("driving_transaction_id") or "") if corridor_geo else ""
            if corridor_geo and corridor_geo.get("cross_border"):
                src_c, dst_c = corridor_geo["from_country"], corridor_geo["to_country"]

                def rank(row: dict[str, Any]) -> tuple[int, float]:
                    on_corridor = row.get("source_country") == src_c and row.get("destination_country") == dst_c
                    crosses = (
                        row.get("source_country")
                        and row.get("destination_country")
                        and row["source_country"] != row["destination_country"]
                    )
                    if str(row["transaction_id"]) == driving:
                        tier = 0
                    elif on_corridor:
                        tier = 1
                    elif crosses:
                        tier = 2
                    else:
                        tier = 3
                    return (tier, -float(row["amount"]))

                ordered = sorted(records, key=rank)
                chosen = ordered[:3]
                # Vẫn giữ một giao dịch của chiều còn lại: một tài khoản chỉ
                # được kể chiều tiền ra thì không nhìn ra tiền từ đâu tới.
                sides = {r["source"] == account for r in chosen}
                if len(sides) == 1:
                    other = outs if not next(iter(sides)) else ins
                    chosen += by_amount(other)[:1]

            seen_ids: set[str] = set()
            for record in by_amount(chosen):
                if str(record["transaction_id"]) in seen_ids:
                    continue
                seen_ids.add(str(record["transaction_id"]))
                outgoing = record["source"] == account
                direction = "chuyển" if outgoing else "nhận"
                counterparty = record["destination"] if outgoing else record["source"]
                preposition = "tới" if outgoing else "từ"
                # Hành lang quốc gia, khi bộ dữ liệu có. Với một cảnh báo địa lý
                # thì đây CHÍNH là lý do nó nổ; thiếu nó thì câu dữ kiện kể đúng
                # số tiền mà không kể được điều quan trọng nhất.
                src_c = record.get("source_country")
                dst_c = record.get("destination_country")
                corridor = ""
                if src_c and dst_c:
                    corridor = f", hành lang {src_c} → {dst_c}" if src_c != dst_c else f", nội địa {src_c}"
                claim = Claim(
                    claim_id=_claim_id(),
                    claim=(
                        f"Ngày {_day(record['timestamp'])}, tài khoản {direction} "
                        f"{_amount(record['amount'])} {record['currency']} {preposition} {counterparty} "
                        f"qua kênh {_channel(record['payment_format'])}{corridor} "
                        f"(mã giao dịch {record['transaction_id']})."
                    ),
                    claim_type="FACT",
                    evidence_refs=[item.evidence_id],
                    confidence=1.0,
                )
                claims.append(claim)
                facts.append(claim.claim)

            if item.payload.get("truncated"):
                missing.append(
                    f"Chỉ trích xuất được {len(records)} giao dịch đầu tiên; tài khoản còn giao dịch chưa được "
                    "đưa vào bằng chứng, cần truy vấn thêm trang tiếp theo trước khi kết luận."
                )

        signals = _observed_signals(grouped)
        measurements = _signal_measurements(grouped) | _graph_measurements(grouped)
        focus_lines: list[str] = []
        for item in grouped.get(EvidenceType.TYPOLOGY_MAPPING, []):
            code = item.payload["typology_code"]
            typologies.append(code)
            # Câu tóm tắt nhận TÊN, không nhận mã. "T02" không nói gì với chuyên
            # viên tuân thủ; "Mạng lưới tài khoản trung chuyển" thì nói đủ. Mã
            # vẫn nằm trong trường `typologies` của bản giải thích cho kiểm toán
            # và cho các màn hình lọc theo nhóm.
            typology_names.append(item.payload.get("name_vi") or item.payload.get("name") or code)
            expected = [*item.payload.get("required_signals", []), *item.payload.get("supporting_signals", [])]
            matched = [name for name in expected if signals.get(name)]
            absent = [name for name in expected if name not in signals]
            unmatched = [name for name in expected if signals.get(name) is False]

            # Chuyên viên đọc màn hình bằng tiếng Việt: mã tín hiệu thô như
            # ``fan_in`` không nói lên điều gì, nên luôn dịch trước khi ghép câu.
            labels = item.payload.get("signal_labels_vi") or {}

            def _vi(names: list[str], _labels: dict[str, str] = labels, *, with_measure: bool = False) -> str:
                parts = []
                for name in names:
                    label = _labels.get(name, name)
                    measure = measurements.get(name) if with_measure else None
                    parts.append(f"{label} ({measure})" if measure else label)
                return ", ".join(parts)

            if matched:
                # Kèm SỐ ĐO cho dấu hiệu đã khớp, không chỉ tên.
                #
                # "khớp 3 trong 3 dấu hiệu (nhiều nguồn dồn vào, phân tán ra
                # nhiều đích, tiền nằm lại rất ngắn)" đúng nhưng rỗng: chuyên
                # viên vẫn không biết bao nhiêu nguồn, bao nhiêu đích, nằm lại
                # bao lâu. Ngưỡng đi kèm để họ tự thấy nó vượt bao xa.
                ordered_matched = sorted(
                    matched,
                    key=lambda name: (
                        _TYPOLOGY_FOCUS.get(code, {}).get("signals", []).index(name)
                        if name in _TYPOLOGY_FOCUS.get(code, {}).get("signals", [])
                        else len(expected)
                    ),
                )
                # Dùng gạch ngang thay ngoặc: bản trước ghép "nhãn (số đo)" rồi
                # bọc cả danh sách trong một cặp ngoặc nữa, mà số đo lại có chú
                # thích trong ngoặc — thành ba tầng ngoặc trong một câu.
                status = (
                    f"khớp {len(matched)} trong {len(expected)} dấu hiệu đặc trưng của kiểu này: "
                    + "; ".join(
                        f"{labels.get(name, name)} — {measurements[name]}"
                        if measurements.get(name)
                        else labels.get(name, name)
                        for name in ordered_matched
                    )
                )
            else:
                status = "chưa khớp dấu hiệu đặc trưng nào của kiểu này"
            if unmatched:
                # Ba trạng thái, ba câu khác nhau — chuyên viên hành động khác
                # nhau với mỗi trạng thái:
                #
                #   khớp              → có căn cứ, đọc tiếp phần dữ kiện
                #   đo được, dưới ngưỡng → đã có số, kết luận là "không đạt"
                #   tra rồi, không có  → loại giả thuyết này, khỏi tìm nữa
                #   chưa tra được      → còn việc phải làm
                #
                # Bản trước gộp hai trạng thái giữa vào cùng một câu "chưa đạt
                # ngưỡng", nên một tín hiệu nhị phân như "tiền đi qua tài khoản
                # trung gian" bị mô tả như thể nó có ngưỡng để đạt.
                measured = [name for name in unmatched if measurements.get(name)]
                checked = [name for name in unmatched if not measurements.get(name)]
                if measured:
                    status += f"; chưa đạt ngưỡng {_vi(measured, with_measure=True)}"
                if checked:
                    status += f"; đã tra cứu nhưng không thấy {_vi(checked)}"
            if absent:
                # Nói rõ VÌ SAO không đo được, khi biết được lý do.
                #
                # "Thiếu bằng chứng tương ứng" là câu đúng nhưng vô dụng: chuyên
                # viên không biết phải đi lấy gì. Với các tín hiệu tính theo thời
                # gian giữ tiền, lý do gần như luôn là tài khoản không có tiền
                # vào trong cửa sổ — không có lúc nhận thì không có khoảng cách
                # giữa nhận và chuyển đi để đo, và không lệnh truy vấn nào sửa
                # được điều đó.
                reasons = {name: _absent_reason(name, grouped) for name in absent}
                explained = [name for name in absent if reasons[name]]
                plain = [name for name in absent if not reasons[name]]
                for name in explained:
                    status += f"; chưa kiểm tra được {_vi([name])} — {reasons[name]}"
                if plain:
                    status += f"; chưa kiểm tra được {_vi(plain)} vì thiếu bằng chứng tương ứng"

            name = item.payload.get("name_vi") or item.payload["name"]
            description = item.payload.get("description_vi") or item.payload.get("description", "")

            # Nhóm "chưa đối chiếu được" KHÔNG có dấu hiệu nào để đối chiếu.
            #
            # Chạy khuôn chung cho nó sẽ ra câu "khớp 0 trong 0 dấu hiệu đặc
            # trưng của kiểu này" — vô nghĩa. Ở đây phải nói rõ hai điều: chưa
            # chứng minh được mẫu hình nào, và căn cứ THẬT của cảnh báo nằm ở
            # điểm rủi ro cùng các yếu tố đóng góp phía trên, không phải ở nhãn.
            if not expected:
                unmatched_note = (
                    "Hành vi quan sát được chưa đủ dấu hiệu của bất kỳ nhóm hành vi nào trong danh mục, "
                    "nên chưa đối chiếu được mẫu hình có tên. Căn cứ của cảnh báo là mức rủi ro và các "
                    "yếu tố đóng góp nêu ở trên; việc đối chiếu nhóm hành vi vẫn còn để ngỏ và cần "
                    "chuyên viên xem xét thêm bằng ngữ cảnh khách hàng."
                )
                inferences.append(unmatched_note)
                claims.append(
                    Claim(
                        claim_id=_claim_id(),
                        claim=unmatched_note,
                        claim_type="INFERENCE",
                        evidence_refs=[item.evidence_id, *([risk_ev.evidence_id] if risk_ev else [])],
                        confidence=0.5,
                    )
                )
                continue

            # Câu nhấn mạnh CHỈ đứng ở phần tóm tắt.
            #
            # Trước đây in cả ở tóm tắt lẫn cuối nhận định: cùng một câu dài xuất
            # hiện hai lần trong một màn hình. Phần nhận định đã kèm số đo ngay
            # sau từng dấu hiệu nên không mất thông tin nào.
            focus_clause = _focus_clause(code, measurements)
            if focus_clause:
                focus_lines.append(focus_clause)
            inference = (
                f"Đối chiếu với kiểu hành vi \u201c{name}\u201d — {description.rstrip('.').lower()} — "
                f"thì hành vi quan sát được {status}. "
                "Đây là nhận định phục vụ điều tra, không phải kết luận về hành vi rửa tiền."
            )
            inferences.append(inference)
            claims.append(
                Claim(
                    claim_id=_claim_id(),
                    claim=inference,
                    claim_type="INFERENCE",
                    evidence_refs=[item.evidence_id, *([risk_ev.evidence_id] if risk_ev else [])],
                    confidence=0.7 if matched else 0.5,
                )
            )

        # Nhãn "chưa đối chiếu được" mà KHÔNG có bằng chứng nhóm hành vi nào thì
        # vòng lặp trên không chạy, và bản giải thích im lặng về chuyện ấy. Người
        # đọc chỉ thấy số liệu dòng tiền rồi tự hỏi vì sao cảnh báo tồn tại.
        if not typologies and str(alert.get("typology_code") or "") == "T00":
            unmatched_note = (
                "Hành vi quan sát được chưa đủ dấu hiệu của bất kỳ nhóm hành vi nào trong danh mục, "
                "nên chưa đối chiếu được mẫu hình có tên. Căn cứ của cảnh báo là mức rủi ro và các "
                "yếu tố đóng góp nêu ở trên; việc đối chiếu nhóm hành vi vẫn còn để ngỏ và cần "
                "chuyên viên xem xét thêm bằng ngữ cảnh khách hàng."
            )
            inferences.append(unmatched_note)
            if risk_ev is not None:
                claims.append(
                    Claim(
                        claim_id=_claim_id(),
                        claim=unmatched_note,
                        claim_type="INFERENCE",
                        evidence_refs=[risk_ev.evidence_id],
                        confidence=0.5,
                    )
                )

        # Two evidence items of the same type raise the same gap twice.
        missing = list(dict.fromkeys(missing))
        summary = _summary(alert, drivers, grouped, typology_names, missing, focus=" ".join(focus_lines))
        # Không đề xuất "ESCALATE_TO_L2" nữa: nó đã bị bỏ khỏi lựa chọn của
        # người rà soát, nên gợi ý ấy sẽ trỏ tới một nút không tồn tại. Bằng
        # chứng đủ mà cảnh báo vẫn đứng thì bước kế tiếp thật sự trong hệ này
        # là cân nhắc lập hồ sơ nghi vấn.
        action = "REQUEST_MORE_INFORMATION" if missing else "REVIEW_FOR_SAR_STR"
        return Explanation(
            summary=summary,
            risk_drivers=drivers,
            claims=claims,
            # `claims` giữ nguyên thứ tự sinh ra (vết kiểm toán); chỉ phần HIỂN
            # THỊ được xếp lại theo mạch đọc.
            facts=_order_facts(facts),
            inferences=inferences,
            missing_information=missing,
            typologies=typologies,
            confidence=0.75 if missing else 0.9,
            recommended_action=action,
            requires_human_review=True,
        )


class EvidenceCriticAgent:
    name = "evidence_critic"

    def __init__(self, session: Session, service: GeminiService, investigation_id: str):
        self.session = session
        self.service = service
        self.investigation_id = investigation_id
        self.repository = InvestigationRepository(session)

    async def validate(
        self, explanation: Explanation, evidence: list[EvidenceEnvelope]
    ) -> GeminiCallResult[ValidationResult]:
        deterministic = self._deterministic_validate(explanation, evidence)
        prompt = get_prompt(self.name)
        result = await self.service.generate_structured(
            investigation_id=self.investigation_id,
            agent_name=self.name,
            prompt_version=prompt.version,
            system_instruction=prompt.system_instruction,
            trusted_context={
                "explanation": explanation.model_dump(mode="json"),
                "evidence": [item.model_dump(mode="json") for item in evidence if not item.is_untrusted_content],
                # Mục lục của MỌI chứng cứ, kể cả chứng cứ không tin cậy. Không có
                # nó, tác tử phản biện thấy dữ liệu giao dịch trong khối untrusted
                # nhưng không biết mã chứng cứ nào phủ dữ liệu ấy, nên kết luận
                # "mã không tồn tại" và đánh trượt mọi khẳng định về giao dịch —
                # tức là mọi hồ sơ, kể từ khi GetTransactions thành bắt buộc.
                # Chỉ đưa mã, loại và nguồn: nội dung do người dùng nhập vẫn nằm
                # nguyên trong khối untrusted, không rò sang khối tin cậy.
                # Kèm cả mã giao dịch mà mỗi chứng cứ phủ. Không có chúng, tác
                # tử phản biện thấy giao dịch 26005546 trong khối untrusted, tra
                # mục lục không thấy, rồi kết luận "giao dịch không có trong
                # danh mục evidence_index" và đánh trượt — nguyên nhân
                # UNSUPPORTED_CLAIM nhiều thứ hai đo được. Mã giao dịch do hệ
                # thống sinh, không phải nội dung người dùng nhập, nên đưa sang
                # khối tin cậy không mở đường tiêm lệnh.
                "evidence_index": [
                    {
                        "evidence_id": item.evidence_id,
                        "type": item.type.value,
                        "source": item.source,
                        "transaction_ids": item.integrity.source_record_ids
                        if item.type == EvidenceType.TRANSACTION
                        else [],
                    }
                    for item in evidence
                ],
                "risk_breakdown": [item.payload for item in evidence if item.type == EvidenceType.RISK_BREAKDOWN],
                # PHÉP ĐẾM DO CODE LÀM, không để tác tử tự đếm.
                #
                # Sổ giao dịch nằm trong khối KHÔNG TIN CẬY, nên trước đây tác tử
                # phản biện phải tự đếm ở đó — và nó đếm không ổn định: trên cùng
                # một hồ sơ, vòng 2 nói "17 giao dịch tới Morocco", vòng 3 nói
                # "chỉ có 12". Ba con số cho cùng một câu hỏi thì không thể hội
                # tụ, và một nhận định đúng vẫn bị đánh trượt.
                #
                # Đây là cùng những dòng ấy, đếm bằng Python, đặt trong khối TIN
                # CẬY. Tác tử không còn phải đếm — chỉ đối chiếu.
                "transaction_facts": _transaction_facts(evidence),
                "deterministic_backend_validation": deterministic.model_dump(mode="json"),
                "allow_listed_tools": sorted(InvestigationTools.ALLOWED),
            },
            untrusted_data=[item.payload for item in evidence if item.is_untrusted_content],
            response_schema=ValidationResult,
            fallback_response=deterministic,
        )
        gemini = result.output
        # Bộ kiểm tất định đi thẳng vào danh sách, KHÔNG qua `_is_refuted` — nó
        # là nửa đáng tin, không nên bị các luật bác bỏ nới lỏng. Ngoại lệ duy
        # nhất: phép đếm giao dịch trên một sổ đã tự khai là bị cắt. Ở đó chính
        # bộ kiểm cũng không có đủ dữ liệu để kết luận, nên giữ lại khiếu nại là
        # buộc tội bịa đặt trong khi không ai kiểm chứng được.
        truncated = any(_TRUNCATION_RE.search(note) for note in explanation.missing_information)
        det_kept, det_excused = [], 0
        for issue in deterministic.issues:
            if truncated and _is_counting_claim(issue):
                det_excused += 1
                continue
            det_kept.append(issue)
        if det_excused:
            self.repository.add_trace(
                self.investigation_id,
                agent=self.name,
                event_type="CRITIC_OBJECTION_REFUTED",
                rationale=(
                    f"Đã bỏ qua {det_excused} khiếu nại của bộ kiểm tất định về phép đếm giao dịch: "
                    "bản giải thích đã tự khai sổ giao dịch bị cắt ngắn, nên phép đếm không kiểm "
                    "chứng được bằng bằng chứng hiện có."
                ),
            )
        issues = list(det_kept)
        seen = {issue.model_dump_json() for issue in issues}
        refuted = 0
        for issue in gemini.issues:
            if self._is_refuted(issue, explanation, evidence):
                refuted += 1
                continue
            serialized = issue.model_dump_json()
            if serialized not in seen:
                issues.append(issue)
                seen.add(serialized)
        if refuted:
            self.repository.add_trace(
                self.investigation_id,
                agent=self.name,
                # KHÔNG phải VALIDATION_PASS: vòng lặp này vẫn có thể FAIL vì lỗi
                # khác. Đây chỉ là việc loại bớt khiếu nại mà sổ bằng chứng bác bỏ.
                event_type="CRITIC_OBJECTION_REFUTED",
                rationale=(
                    f"Đã bỏ qua {refuted} vấn đề do tác tử phản biện Gemini nêu: sổ bằng chứng cho thấy "
                    "các tham chiếu bị coi là thiếu đều tồn tại."
                ),
            )
        if gemini.status == "FAIL" and not gemini.issues:
            issues.append(
                ValidationIssue(
                    type="OTHER",
                    claim="Kết quả của tác tử phản biện Gemini",
                    detail="Tác tử phản biện Gemini trả về trạng thái không đạt nhưng không nêu vấn đề có cấu trúc.",
                )
            )
        status = "FAIL" if issues else "PASS"
        combined = ValidationResult(
            status=status,
            confidence=min(deterministic.confidence, gemini.confidence),
            issues=issues,
            missing_evidence=list(dict.fromkeys([*deterministic.missing_evidence, *gemini.missing_evidence])),
            unsupported_claims=list(dict.fromkeys([*deterministic.unsupported_claims, *gemini.unsupported_claims])),
            next_action="BUILD_CASE_PACKAGE" if status == "PASS" else "RETURN_TO_INVESTIGATION",
        )
        return GeminiCallResult(output=combined, metadata=result.metadata)

    @staticmethod
    def _is_refuted(issue: ValidationIssue, explanation: Explanation, evidence: list[EvidenceEnvelope]) -> bool:
        """Drop a critic objection the evidence ledger positively disproves.

        The critic may only ever be a second opinion on top of the ledger. Left
        unchecked, one hallucinated "this evidence ID does not exist" fails an
        investigation whose citations are all present and verified, and the
        reviewer is told there is no explanation at all. Only MISSING_EVIDENCE
        is refutable this way, and only when every reference on the named claim
        resolves — a genuine gap still fails the run.
        """
        known = {item.evidence_id for item in evidence}

        # Hạn chế mà bản giải thích ĐÃ TỰ KHAI thì không phải khiếm khuyết.
        #
        # Sổ giao dịch bị cắt ở 50 dòng là giới hạn phân trang đã biết, và bản
        # giải thích ghi nó ở mục "thông tin còn thiếu". Tác tử phản biện nêu
        # lại đúng điều đó rồi đánh trượt cả phiên là đếm hai lần một hạn chế đã
        # công bố — chuyên viên mở ra thấy "KHÔNG ĐẠT" mà không có lỗi nào thật.
        if _TRUNCATION_RE.search(issue.detail or "") and any(
            _TRUNCATION_RE.search(note) for note in explanation.missing_information
        ):
            return True

        # Cùng lý lẽ, nhưng cho trường hợp khiếu nại KHÔNG tự nhắc tới việc cắt
        # ngắn — vốn là đa số.
        #
        # Đo trên một hồ sơ thật: bản giải thích tự khai "Chỉ trích xuất được 50
        # giao dịch đầu tiên", rồi nói "15 giao dịch xuyên biên giới". Tác tử
        # phản biện đếm trên đúng 50 dòng ấy và phản đối — vòng 2 bảo "có 17",
        # vòng 3 bảo "chỉ có 12". Ba con số cho cùng một câu hỏi, vì cả ba đều
        # đếm trên một sổ đã bị cắt. Luật bên trên không cứu được vì lời phản đối
        # chỉ nói "chỉ có 12 giao dịch tới Morocco", không có chữ nào về cắt ngắn.
        #
        # Khi bản giải thích ĐÃ TỰ KHAI sổ bị cắt, một phép đếm giao dịch là thứ
        # KHÔNG BÊN NÀO kiểm chứng được. Đứng trên nó để đánh trượt là buộc tội
        # bịa đặt trong khi cả hai phía cùng mù. Hạn chế đã công bố ở mục "thông
        # tin còn thiếu" là chỗ chuyên viên đọc để tự trừ hao.
        if _is_counting_claim(issue) and any(
            _TRUNCATION_RE.search(note) for note in explanation.missing_information
        ):
            return True

        # Cáo buộc "mã chứng cứ này không tồn tại" là mệnh đề về sổ bằng chứng,
        # và sổ bằng chứng là bên nói lời cuối. Tác tử phản biện đôi khi phát
        # biểu nó dưới nhãn UNSUPPORTED_CLAIM thay vì MISSING_EVIDENCE; xét theo
        # nội dung chứ không theo nhãn, nếu không cùng một lỗi lại lọt lưới chỉ
        # vì được gọi tên khác.
        cited_in_detail = set(_EVIDENCE_ID_RE.findall(issue.detail or ""))
        if cited_in_detail and _DENIES_EXISTENCE_RE.search(issue.detail or ""):
            # Chỉ bác bỏ khi MỌI mã bị nêu đều có thật. Còn một mã thiếu thật
            # thì khiếu nại vẫn đứng vững và phiên vẫn phải trượt.
            if cited_in_detail <= known:
                return True

        # Cùng lập luận, cho MÃ GIAO DỊCH. Tác tử phản biện hay viết "giao dịch
        # 26005546 không có trong danh mục evidence_index" khi mã ấy nằm đầy đủ
        # trong sổ. Sổ bằng chứng vẫn là bên nói lời cuối, bất kể mã ấy là mã
        # chứng cứ hay mã giao dịch.
        denies = _DENIES_EXISTENCE_RE.search(issue.detail or "")
        if denies and _TRANSACTION_WORD_RE.search(issue.detail or ""):
            known_transactions = {str(reference) for item in evidence for reference in item.integrity.source_record_ids}
            cited_ids = set(_LONG_NUMBER_RE.findall(issue.detail or ""))
            if cited_ids and cited_ids <= known_transactions:
                return True

        if issue.type != "MISSING_EVIDENCE":
            return False
        if issue.evidence_ref and issue.evidence_ref not in known:
            return False
        return any(
            claim.claim == issue.claim and claim.evidence_refs and all(ref in known for ref in claim.evidence_refs)
            for claim in explanation.claims
        )

    def _deterministic_validate(self, explanation: Explanation, evidence: list[EvidenceEnvelope]) -> ValidationResult:
        by_id = {item.evidence_id: item for item in evidence}
        issues: list[ValidationIssue] = []

        # Nhất quán LOGIC: câu có dẫn nguồn, số có thật, nhưng ghép lại thì vô lý.
        # Bộ kiểm token không thấy loại lỗi này — xem src/investigation/consistency.py.
        account_key = next((item.account_key for item in evidence if item.account_key), "")
        # Khử trùng lặp trước khi kiểm: bản giải thích tất định đặt CÙNG một câu
        # vào cả `claims` lẫn `facts`, nên không khử thì mỗi mâu thuẫn bị báo hai
        # lần và vòng sửa lỗi tưởng có gấp đôi vấn đề phải sửa.
        for contradiction in consistency.check(
            list(dict.fromkeys([claim.claim for claim in explanation.claims] + list(explanation.facts))),
            evidence,
            account_key=account_key,
            fan_threshold=FAN_COUNTERPARTIES,
        ):
            issues.append(
                ValidationIssue(
                    type="CONTRADICTION",
                    claim=contradiction.claim,
                    detail=f"[{contradiction.rule}] {contradiction.detail}",
                )
            )

        for claim in explanation.claims:
            missing_refs = [reference for reference in claim.evidence_refs if reference not in by_id]
            if missing_refs or (claim.claim_type == "FACT" and not claim.evidence_refs):
                issues.append(
                    ValidationIssue(
                        type="MISSING_EVIDENCE",
                        claim=claim.claim,
                        evidence_ref=missing_refs[0] if missing_refs else None,
                        detail="Nhận định không liên kết được với bằng chứng trong sổ điều tra này.",
                    )
                )
                continue
            cited = [by_id[reference] for reference in claim.evidence_refs]
            lower = claim.claim.lower()
            if claim.claim_type == "FACT":
                cited_numbers = [number for item in cited for number in _numeric_values(item.payload)]
                claim_numbers = _CLAIM_NUMBER_RE.findall(_mask_identifiers(claim.claim, cited))
                # Dung sai bằng nửa đơn vị của chữ số cuối cùng ĐƯỢC VIẾT RA —
                # áp cho cả số nguyên. Trước đây số có thập phân được nới theo
                # chữ số cuối còn số nguyên bị ép khớp tuyệt đối, nên viết
                # "104324" cho số liệu 104324,50 bị coi là bịa. Làm tròn tới
                # đơn vị là cách viết bình thường của một bản tường trình.
                unsupported_numbers = [
                    float(number)
                    for number in claim_numbers
                    if not any(
                        abs(float(number) - cited_number) <= 0.5 * 10 ** -len(number.partition(".")[2]) + 1e-9
                        for cited_number in cited_numbers
                    )
                ]
                if unsupported_numbers:
                    issues.append(
                        ValidationIssue(
                            type="UNSUPPORTED_CLAIM",
                            claim=claim.claim,
                            detail=(f"Các con số {unsupported_numbers} không có trong bằng chứng được trích dẫn."),
                        )
                    )
                # Định danh cũng phải NEO vào bằng chứng, không chỉ con số.
                #
                # Bộ kiểm số một mình không đủ: một mã tài khoản bịa mà phần chữ
                # số tình cờ trùng số nào đó trong bằng chứng sẽ lọt, và người
                # đọc nhận một đối tác không tồn tại trong hồ sơ. Đây là phép
                # kiểm quy kết ở mức định danh (Rashkin và cộng sự 2021).
                cited_strings = {value for item in cited for value in _string_values(item.payload)}
                invented = [
                    token
                    for token in set(_IDENTIFIER_RE.findall(claim.claim))
                    if token not in cited_strings
                ]
                if invented:
                    issues.append(
                        ValidationIssue(
                            type="UNSUPPORTED_CLAIM",
                            claim=claim.claim,
                            detail=(
                                f"Định danh {sorted(invented)} không có trong bằng chứng được trích dẫn — "
                                "không dẫn được tài khoản hay giao dịch không tồn tại trong hồ sơ."
                            ),
                        )
                    )
            if "money laundering" in lower and claim.claim_type == "FACT":
                issues.append(
                    ValidationIssue(
                        type="UNSUPPORTED_CLAIM",
                        claim=claim.claim,
                        detail="Tác tử không được trình bày kết luận rửa tiền như một dữ kiện.",
                    )
                )
            if ("cycle" in lower or "graph detector" in lower or "graph pattern" in lower) and not any(
                item.type == EvidenceType.GRAPH_PATTERN and item.source == "graph_detector" for item in cited
            ):
                issues.append(
                    ValidationIssue(
                        type="UNSUPPORTED_CLAIM",
                        claim=claim.claim,
                        required_tool="GetGraphEvidence",
                        detail="Nhận định về đồ thị cần bằng chứng có cấu trúc từ bộ phát hiện đồ thị.",
                    )
                )
            if re.search(r"\bT(?:0[1-9]|10)\b", claim.claim) and not any(
                item.type == EvidenceType.TYPOLOGY_MAPPING for item in cited
            ):
                issues.append(
                    ValidationIssue(
                        type="INVALID_TYPOLOGY",
                        claim=claim.claim,
                        required_tool="GetTypology",
                        detail="Diễn giải nhóm hành vi phải trích dẫn ánh xạ trong danh mục.",
                    )
                )

        for driver in explanation.risk_drivers:
            expected = round(driver.score * driver.weight, 6)
            if abs(driver.contribution - expected) > 1e-6:
                issues.append(
                    ValidationIssue(
                        type="INVALID_SCORE_CONTRIBUTION",
                        claim=f"{driver.source} contribution {driver.contribution}",
                        evidence_ref=driver.evidence_refs[0] if driver.evidence_refs else None,
                        detail=f"Expected score × weight = {expected}.",
                    )
                )
            risk_sources = [
                by_id[reference]
                for reference in driver.evidence_refs
                if reference in by_id and by_id[reference].type == EvidenceType.RISK_BREAKDOWN
            ]
            component = risk_sources[0].payload.get("components", {}).get(driver.source) if risk_sources else None
            if not component or any(
                abs(float(component[field]) - getattr(driver, field)) > 1e-6
                for field in ("score", "weight", "contribution")
            ):
                issues.append(
                    ValidationIssue(
                        type="INVALID_SCORE_CONTRIBUTION",
                        claim=f"{driver.source} risk driver",
                        evidence_ref=driver.evidence_refs[0] if driver.evidence_refs else None,
                        detail="Giá trị yếu tố rủi ro không khớp chi tiết từ Bộ máy phát hiện được trích dẫn.",
                    )
                )

        for item in evidence:
            if item.type != EvidenceType.TRANSACTION:
                continue
            for record in item.payload.get("items", []):
                row = (
                    self.session.execute(
                        text(
                            """SELECT occurred_at, from_account_key, to_account_key, amount, currency, channel
                                 FROM transaction WHERE transaction_id = :id"""
                        ),
                        {"id": int(record["transaction_id"])},
                    )
                    .mappings()
                    .first()
                )
                if not row or any(
                    [
                        row["from_account_key"] != record["source"],
                        row["to_account_key"] != record["destination"],
                        float(row["amount"]) != float(record["amount"]),
                        row["currency"] != record["currency"],
                        row["channel"] != record["payment_format"],
                        row["occurred_at"].isoformat() != str(record["timestamp"]).replace("Z", "+00:00"),
                    ]
                ):
                    issues.append(
                        ValidationIssue(
                            type="MISSING_SOURCE_RECORD",
                            claim=f"Transaction {record['transaction_id']}",
                            evidence_ref=item.evidence_id,
                            required_tool="GetTransactions",
                            detail="Bằng chứng giao dịch không khớp bản ghi trong cơ sở dữ liệu nguồn.",
                        )
                    )

        for item in evidence:
            if item.type != EvidenceType.GRAPH_PATTERN:
                continue
            for edge in item.payload.get("edges", []):
                row = (
                    self.session.execute(
                        text(
                            """SELECT from_account_key, to_account_key FROM transaction
                                 WHERE transaction_id = :id"""
                        ),
                        {"id": int(edge["transaction_id"])},
                    )
                    .mappings()
                    .first()
                )
                if not row or row["from_account_key"] != edge["from"] or row["to_account_key"] != edge["to"]:
                    issues.append(
                        ValidationIssue(
                            type="MISSING_SOURCE_RECORD",
                            claim=f"Graph edge transaction {edge['transaction_id']}",
                            evidence_ref=item.evidence_id,
                            required_tool="GetGraphEvidence",
                            detail="Cạnh từ bộ phát hiện đồ thị không khớp giao dịch nguồn.",
                        )
                    )

        # A graph-detector alert without its detector evidence is a critical
        # gap even if the explanation correctly abstains from claiming a pattern.
        risk_items = [item for item in evidence if item.type == EvidenceType.RISK_BREAKDOWN]
        graph_primary = any(item.payload.get("components", {}).get("graph", {}).get("available") for item in risk_items)
        if graph_primary and not any(item.type == EvidenceType.GRAPH_PATTERN for item in evidence):
            issues.append(
                ValidationIssue(
                    type="MISSING_EVIDENCE",
                    claim="Primary graph detector signal",
                    required_tool="GetGraphEvidence",
                    detail="Có điểm đồ thị nhưng chưa có bằng chứng có cấu trúc về mẫu hình/cạnh tương ứng.",
                )
            )

        status = "FAIL" if issues else "PASS"
        return ValidationResult(
            status=status,
            confidence=0.98 if not issues else 0.9,
            issues=issues,
            missing_evidence=[issue.detail for issue in issues if issue.type == "MISSING_EVIDENCE"],
            unsupported_claims=[issue.claim for issue in issues if issue.type == "UNSUPPORTED_CLAIM"],
            next_action="BUILD_CASE_PACKAGE" if status == "PASS" else "RETURN_TO_INVESTIGATION",
        )
