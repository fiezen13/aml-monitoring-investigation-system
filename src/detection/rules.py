"""Bộ luật nghiệp vụ AML — nhánh Rule của Detection Engine.

Đây là các luật **tất định**, không phải mô hình. Chúng tồn tại để trả lời một
câu mà mô hình bất thường không trả lời được: *cảnh báo này vi phạm quy tắc cụ
thể nào*. Chuyên viên đọc được tên luật; không ai đọc được điểm số của Isolation
Forest.

Nguyên tắc:

* **Chỉ viết luật mà dữ liệu chứng minh được.** Ví dụ rõ nhất: luật "lệch hồ sơ
  khách hàng" (T10) KHÔNG có ở đây. Bảng ``customer`` trong repo có 1.461.697
  dòng nhưng chỉ đúng một giá trị ``expected_monthly_volume`` và một
  ``registered_country`` — dữ liệu lấp chỗ do ``ensure_subject`` sinh ra. Viết
  luật trên đó sẽ tạo ra cảnh báo trông có lý mà không có căn cứ.
* **Ngưỡng nằm một chỗ, có tên.** Xem ``RULE_THRESHOLDS``. Đây là tham số vận
  hành, phải để bộ phận tuân thủ hiệu chỉnh, không được rải rác trong SQL.
* **Mỗi luật khai tín hiệu của mình.** Tín hiệu nối thẳng vào danh mục nhóm hành
  vi (``src/investigation/typologies.json``), nên bật một luật là tự động mở
  đường cho nhóm hành vi tương ứng — không phải sửa hai chỗ.
* **Tín hiệu phải phân biệt được.** ``rule_trigger`` trong danh mục là tín hiệu
  bắt buộc *riêng của T01*, không phải cờ chung "có luật nào đó kích hoạt". Nếu
  mọi luật đều phát nó thì T01 thắng mọi lần và ba luật còn lại mất tác dụng
  chọn nhóm hành vi. Chỉ luật chia nhỏ giao dịch được phát tín hiệu này.

Luật không tự chấm điểm rủi ro cuối cùng. Nó phát ra mức đóng góp; việc hợp nhất
là của ``src/fusion``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: Tham số vận hành của bộ luật.
#:
#: KHÔNG phải hằng số nghiệp vụ đã thẩm định. Ngưỡng báo cáo 10.000 lấy theo mức
#: quen thuộc của chuẩn CTR; thị trường khác dùng mức khác. Bộ phận tuân thủ
#: phải rà lại toàn bộ khối này trước khi đưa vào chạy thật.
RULE_THRESHOLDS: dict[str, float] = {
    # --- R01 chia nhỏ giao dịch ---
    #: Ngưỡng phải báo cáo, đơn vị tiền của giao dịch.
    "reporting_threshold": 10_000.0,
    #: Dải "ngay dưới ngưỡng": từ 85% ngưỡng đến sát ngưỡng.
    "structuring_band_floor": 0.85,
    #: Số giao dịch tối thiểu nằm trong dải đó để coi là có chủ đích.
    "structuring_min_count": 3,
    # --- R02 chuyển tiền nhanh ---
    #: Tỷ lệ tiền ra trong vòng 2 giờ sau khi nhận, trên tổng tiền ra.
    "rapid_outflow_ratio": 0.60,
    #: Cần đủ lượng giao dịch để tỷ lệ có ý nghĩa.
    "rapid_min_outgoing": 3,
    # --- R03 phơi nhiễm tài sản mã hoá ---
    #: Tỷ lệ giá trị đi/đến đối tác là VASP.
    "vasp_exposure_ratio": 0.30,
    "vasp_min_transactions": 2,
    # --- R04 dòng tiền xuyên biên giới ---
    "cross_border_ratio": 0.50,
    "cross_border_min_transactions": 5,
}

#: Trọng số của nhánh rule khi hợp nhất điểm. Đặt ở đây để `alert_reason.weight`
#: và tài liệu bàn giao dùng chung một con số.
RULE_WEIGHT = 0.30


@dataclass(frozen=True)
class RuleContext:
    """Quan sát của một tài khoản trong một cửa sổ thời gian.

    Mọi trường đều là số đo lấy trực tiếp từ bảng ``transaction``. Không có
    trường nào là suy đoán, và không có trường nào đến từ mô hình — nhánh rule
    phải giải thích được bằng dữ liệu thô.
    """

    account_key: str
    as_of: datetime
    window_days: int

    outgoing_count: int = 0
    incoming_count: int = 0
    total_outflow: float = 0.0
    total_inflow: float = 0.0

    #: Số giao dịch đi nằm trong dải ngay dưới ngưỡng báo cáo.
    near_threshold_count: int = 0
    #: Số giá trị khác nhau trong nhóm đó — lặp lại nhiều nghĩa là có khuôn mẫu.
    near_threshold_distinct_amounts: int = 0
    #: Khoảng thời gian trải của nhóm đó, tính bằng giờ.
    near_threshold_span_hours: float = 0.0

    #: Tiền ra trong vòng 2 giờ kể từ lần nhận gần nhất.
    rapid_outflow_amount: float = 0.0
    #: Thời gian giữ tiền trung vị, giờ.
    median_dwell_hours: float | None = None

    #: Giá trị và số giao dịch với đối tác là VASP.
    vasp_amount: float = 0.0
    vasp_transaction_count: int = 0

    #: Số giao dịch mà ngân hàng hai đầu khác quốc gia.
    cross_border_count: int = 0
    transaction_count: int = 0

    @property
    def rapid_outflow_ratio(self) -> float:
        return self.rapid_outflow_amount / self.total_outflow if self.total_outflow > 0 else 0.0

    @property
    def vasp_ratio(self) -> float:
        total = self.total_outflow + self.total_inflow
        return self.vasp_amount / total if total > 0 else 0.0

    @property
    def cross_border_ratio(self) -> float:
        return self.cross_border_count / self.transaction_count if self.transaction_count > 0 else 0.0


@dataclass(frozen=True)
class RuleHit:
    """Một luật đã kích hoạt.

    ``contribution`` thang 0–100 để khớp cột ``alert_reason.contribution``.
    ``signals`` là cầu nối sang danh mục nhóm hành vi.
    """

    code: str
    label: str
    contribution: float
    signals: frozenset[str]
    detail: dict[str, float | int | str] = field(default_factory=dict)
    weight: float = RULE_WEIGHT
    #: Luật chính tự nó đủ để mở một cảnh báo. Luật phụ chỉ làm giàu ngữ cảnh.
    is_primary: bool = True


#: Mức đóng góp tối thiểu của một luật đã kích hoạt.
#:
#: Không được để bằng 0. Luật kích hoạt nghĩa là ngưỡng đã bị vượt — đó là một
#: phát hiện, dù ở mức nhẹ nhất. Thang tuyến tính thuần từ 0 khiến trường hợp
#: đúng bằng ngưỡng nhận điểm 0, và cảnh báo nằm đáy hàng đợi trông y như không
#: có gì. Lần chạy đầu trên LI-Small tạo ra 191 cảnh báo điểm 0 đúng vì lý do
#: này.
MIN_CONTRIBUTION = 20.0


def _scale(value: float, floor: float, ceiling: float) -> float:
    """Đưa mức vượt ngưỡng về thang ``MIN_CONTRIBUTION``–100, kẹp hai đầu.

    Mức đóng góp phải tăng theo độ nghiêm trọng, nếu không thì mọi cảnh báo rule
    đều cùng một điểm và thứ tự hàng đợi mất nghĩa.
    """
    if ceiling <= floor:
        return 100.0
    ratio = min(max((value - floor) / (ceiling - floor), 0.0), 1.0)
    return round(MIN_CONTRIBUTION + (100.0 - MIN_CONTRIBUTION) * ratio, 2)


def rule_structuring(ctx: RuleContext) -> RuleHit | None:
    """R01 — chia nhỏ giao dịch để né ngưỡng báo cáo.

    Dấu hiệu không nằm ở một giao dịch đơn lẻ mà ở *khuôn mẫu*: nhiều giao dịch
    cùng đậu sát dưới ngưỡng, giá trị lặp lại, dồn trong thời gian ngắn. Một
    giao dịch 9.900 là bình thường; mười giao dịch 9.900 trong hai ngày thì
    không.
    """
    threshold = RULE_THRESHOLDS["reporting_threshold"]
    minimum = int(RULE_THRESHOLDS["structuring_min_count"])
    if ctx.near_threshold_count < minimum:
        return None

    signals = {"rule_trigger"}
    # Ít giá trị khác nhau trên nhiều giao dịch = số tiền lặp lại.
    if ctx.near_threshold_distinct_amounts and ctx.near_threshold_count >= 2 * ctx.near_threshold_distinct_amounts:
        signals.add("repeated_amounts")
    if 0 < ctx.near_threshold_span_hours <= 48:
        signals.add("short_window")

    return RuleHit(
        code="R01_STRUCTURING",
        label=f"{ctx.near_threshold_count} giao dịch sát dưới ngưỡng báo cáo {threshold:,.0f}",
        contribution=_scale(ctx.near_threshold_count, minimum, minimum * 4),
        signals=frozenset(signals),
        detail={
            "near_threshold_count": ctx.near_threshold_count,
            "distinct_amounts": ctx.near_threshold_distinct_amounts,
            "span_hours": round(ctx.near_threshold_span_hours, 2),
            "reporting_threshold": threshold,
        },
    )


def rule_rapid_movement(ctx: RuleContext) -> RuleHit | None:
    """R02 — tiền vào rồi ra ngay, tài khoản chỉ làm chỗ trung chuyển."""
    ratio_floor = RULE_THRESHOLDS["rapid_outflow_ratio"]
    if ctx.outgoing_count < int(RULE_THRESHOLDS["rapid_min_outgoing"]):
        return None
    if ctx.rapid_outflow_ratio < ratio_floor:
        return None

    signals = {"rapid_outflow"}
    if ctx.median_dwell_hours is not None and ctx.median_dwell_hours <= 2:
        signals.add("short_dwell_time")

    return RuleHit(
        code="R02_RAPID_MOVEMENT",
        label=f"{ctx.rapid_outflow_ratio:.0%} tiền ra rời tài khoản trong 2 giờ sau khi nhận",
        contribution=_scale(ctx.rapid_outflow_ratio, ratio_floor, 1.0),
        signals=frozenset(signals),
        detail={
            "rapid_outflow_ratio": round(ctx.rapid_outflow_ratio, 4),
            "rapid_outflow_amount": round(ctx.rapid_outflow_amount, 2),
            "median_dwell_hours": round(ctx.median_dwell_hours, 2) if ctx.median_dwell_hours is not None else -1,
        },
    )


def rule_vasp_exposure(ctx: RuleContext) -> RuleHit | None:
    """R03 — phần lớn giá trị đi qua tổ chức cung ứng tài sản mã hoá.

    Dựa trên cờ ``bank.is_vasp`` — dữ liệu thật, 1.508 ngân hàng được đánh dấu.
    """
    ratio_floor = RULE_THRESHOLDS["vasp_exposure_ratio"]
    if ctx.vasp_transaction_count < int(RULE_THRESHOLDS["vasp_min_transactions"]):
        return None
    if ctx.vasp_ratio < ratio_floor:
        return None

    signals = {"vasp_link"}
    if ctx.rapid_outflow_ratio >= RULE_THRESHOLDS["rapid_outflow_ratio"]:
        signals.add("rapid_cross_channel_flow")

    return RuleHit(
        code="R03_VASP_EXPOSURE",
        label=f"{ctx.vasp_ratio:.0%} giá trị giao dịch với đối tác là VASP",
        contribution=_scale(ctx.vasp_ratio, ratio_floor, 1.0),
        signals=frozenset(signals),
        detail={
            "vasp_ratio": round(ctx.vasp_ratio, 4),
            "vasp_transaction_count": ctx.vasp_transaction_count,
            "vasp_amount": round(ctx.vasp_amount, 2),
        },
    )


def rule_cross_border(ctx: RuleContext) -> RuleHit | None:
    """R04 — dòng tiền chủ yếu xuyên biên giới.

    Lưu ý về phạm vi: luật này KHÔNG khẳng định "quốc gia rủi ro cao" (T06).
    Muốn khẳng định điều đó phải có danh sách quốc gia được chỉ định — FATF hoặc
    danh sách nội bộ — mà repo chưa có. Ở đây chỉ nêu một dữ kiện kiểm chứng
    được: ngân hàng hai đầu nằm ở hai quốc gia khác nhau.
    """
    ratio_floor = RULE_THRESHOLDS["cross_border_ratio"]
    if ctx.transaction_count < int(RULE_THRESHOLDS["cross_border_min_transactions"]):
        return None
    if ctx.cross_border_ratio < ratio_floor:
        return None

    return RuleHit(
        # Luật phụ: một mình nó KHÔNG mở cảnh báo. Xem ``should_alert``.
        is_primary=False,
        code="R04_CROSS_BORDER_FLOW",
        label=f"{ctx.cross_border_ratio:.0%} giao dịch có ngân hàng hai đầu khác quốc gia",
        contribution=_scale(ctx.cross_border_ratio, ratio_floor, 1.0),
        signals=frozenset({"cross_border_flow"}),
        detail={
            "cross_border_ratio": round(ctx.cross_border_ratio, 4),
            "cross_border_count": ctx.cross_border_count,
            "transaction_count": ctx.transaction_count,
        },
    )


#: Thứ tự cố định để kết quả tất định giữa các lần chạy.
RULES = (
    rule_structuring,
    rule_rapid_movement,
    rule_vasp_exposure,
    rule_cross_border,
)


def evaluate(ctx: RuleContext) -> list[RuleHit]:
    """Chạy toàn bộ bộ luật trên một quan sát."""
    return [hit for rule in RULES if (hit := rule(ctx)) is not None]


def should_alert(hits: list[RuleHit]) -> bool:
    """Có mở cảnh báo cho tập luật này không.

    Cần ít nhất một **luật chính**. Nếu không có rào này, R04 tự mở cảnh báo cho
    27% số tài khoản trong bộ dữ liệu — giao dịch xuyên biên giới là chuyện bình
    thường ở đây, không phải vi phạm. Trong danh mục nhóm hành vi,
    ``cross_border_flow`` cũng chỉ là tín hiệu *hỗ trợ*, không bao giờ tự chọn
    được nhóm nào; một cảnh báo chỉ có R04 sẽ không có phát hiện nào để nói.

    Nó vẫn được giữ trong kết quả để làm giàu ngữ cảnh cho cảnh báo do luật
    chính mở.
    """
    return any(hit.is_primary for hit in hits)


def risk_score(hits: list[RuleHit]) -> float:
    """Điểm rủi ro của nhánh rule, thang 0–100.

    Lấy mức đóng góp cao nhất làm nền rồi cộng thêm phần suy giảm của các luật
    còn lại. Cộng thẳng sẽ khiến bốn luật yếu vượt mặt một luật rất mạnh, mà
    trong rà soát AML thì một vi phạm nghiêm trọng đáng chú ý hơn bốn dấu hiệu
    mờ nhạt.
    """
    if not hits:
        return 0.0
    ordered = sorted((hit.contribution for hit in hits), reverse=True)
    score = ordered[0]
    for index, contribution in enumerate(ordered[1:], start=1):
        score += contribution / (2**index)
    return round(min(score, 100.0), 2)


def signals_of(hits: list[RuleHit]) -> set[str]:
    """Hợp tất cả tín hiệu của các luật đã kích hoạt."""
    signals: set[str] = set()
    for hit in hits:
        signals |= hit.signals
    return signals
