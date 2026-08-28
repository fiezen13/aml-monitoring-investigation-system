"""Dựng PDF cho Báo cáo Giao dịch Đáng ngờ (SAR).

Bản dựng này theo lối một văn bản báo cáo chính thức: có phần đầu thư (tổ chức
báo cáo — nơi nhận — số hiệu), các mục đánh số La Mã, và khối ký tên ở cuối. Ba
lỗi của bản cũ được sửa tại đây:

* lưới nhãn/giá trị dùng chiều cao dòng CỐ ĐỊNH, nên mã SAR dài bị tràn xuống và
  đè lên nhãn kế tiếp — nay mỗi hàng cao bằng ô cao nhất trong hàng;
* mục "Nhận định" in thẳng mã bằng chứng nội bộ (``EV-…``) vào tài liệu gửi ra
  ngoài — nay in tên nghiệp vụ của bằng chứng;
* tiền của nhiều loại tiền tệ bị cộng dồn thành MỘT con số (Yên + Euro + Rupee),
  vô nghĩa trong một báo cáo — nay tách theo từng loại tiền.

Font: trình dựng PDF mặc định (Helvetica) rớt dấu tiếng Việt (không phủ Latin
Extended Additional). Nhúng DejaVu Sans (assets/fonts) để chữ có dấu hiển thị
đúng. Thuần Python, không phụ thuộc hệ thống.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace

from src.api.sar_graph import draw_case_graph

#: Số NUMERIC của PostgreSQL đi qua chuỗi giữ nguyên phần thập phân (vd
#: "1083674.330000000000000000"). Trong văn bản/bảng nhìn rất rối, nên rút gọn
#: mọi số có ≥3 chữ số thập phân về 2 chữ số + phân tách hàng nghìn bằng dấu cách.
#: Chỉ khớp số THẬP PHÂN DÀI thật sự, không khớp số viết kiểu Việt Nam.
#:
#: Biểu thức cũ (`\d+\.\d{3,}`) đọc "97.103,33" — chín mươi bảy nghìn một trăm
#: linh ba phẩy ba ba — thành "97.103" rồi rút gọn thành "97.10", để lại
#: "97.10,33 USD" ngay trên bản báo cáo chính thức. Hai rào chặn điều đó:
#: phía sau không được là dấu phân cách + chữ số (tức đang ở giữa một số có
#: nhóm hàng nghìn), và phía trước không được là chữ số + dấu chấm.
#: Ngưỡng BỐN chữ số thập phân, không phải ba.
#:
#: "100.000" trong tiếng Việt là một trăm nghìn, và cũng có thể là một số
#: NUMERIC ba chữ số thập phân — hai thứ viết y hệt nhau, không phân biệt được
#: bằng biểu thức. Nhóm hàng nghìn LUÔN đúng ba chữ số, nên lấy bốn làm ngưỡng
#: là bỏ đúng phần mơ hồ ấy: đuôi của NUMERIC thật thì dài hơn nhiều.
_LONG_DECIMAL = re.compile(r"(?<![\d.])\d+\.\d{4,}(?![.,]?\d)")

#: "1 234.56 US Dollar" → phần số và phần tên loại tiền.
#:
#: Lớp ký tự của phần SỐ phải chứa cả dấu tách hàng nghìn. Máy chủ nay trả số
#: tiền đã định dạng ("10 924.92 US Dollar"); nếu biểu thức dừng ở khoảng trắng
#: đầu tiên thì số thành "10" còn "924.92 US Dollar" bị đọc thành tên loại tiền
#: — đúng lỗi đã làm hỏng bảng tổng hợp theo loại tiền của bản PDF.
_AMOUNT_CCY = re.compile(r"^\s*(-?[\d.,\u202f\u00a0 ]+)(.*)$")


def _trim_decimals(text: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        try:
            return f"{float(m.group()):,.2f}".replace(",", " ")
        except ValueError:
            return m.group()

    return _LONG_DECIMAL.sub(_repl, text)


_FONT_DIR = Path(__file__).parent / "assets" / "fonts"
_INK = (23, 27, 34)
_MUTED = (95, 104, 117)
_LINE = (208, 213, 221)
_ACCENT = (17, 62, 122)
_RISK = (176, 42, 42)
_BAND = (238, 242, 247)
_WATERMARK = (232, 234, 238)

#: Tên nghiệp vụ của bằng chứng — GIỮ TRÙNG với web/src/api/format.ts để bản in
#: và màn hình gọi cùng một thứ bằng cùng một tên.
_EVIDENCE_TYPE_LABELS = {
    "RISK_BREAKDOWN": "Cơ sở tính điểm rủi ro",
    "BEHAVIOR_FEATURE": "Dấu hiệu hành vi tài khoản",
    "ANOMALY_EXPLANATION": "Lý do được xem là bất thường",
    "TRANSACTION": "Giao dịch liên quan",
    "TYPOLOGY_MAPPING": "Nhóm hành vi được đối chiếu",
    "GRAPH_PATTERN": "Mô hình luân chuyển tiền",
    "GRAPH_NEIGHBORHOOD": "Quan hệ giao dịch liên quan",
    "RULE_TRIGGER": "Quy tắc cảnh báo đã kích hoạt",
}
_EVIDENCE_SOURCE_TITLES = {
    "detection_engine": "Cơ sở tính điểm rủi ro",
    "rule_engine": "Quy tắc cảnh báo đã kích hoạt",
    "feature_service": "Dấu hiệu hành vi tài khoản",
    "transaction_service": "Giao dịch liên quan",
    "typology_registry": "Nhóm hành vi được đối chiếu",
    "anomaly_explanation_service": "Lý do được xem là bất thường",
    "graph_detector": "Quan hệ giao dịch liên quan",
    "transaction": "Giao dịch liên quan",
}


def evidence_label(item: dict[str, Any]) -> str:
    """Tên đọc được của một bằng chứng (không phải mã ``EV-…`` nội bộ)."""
    kind = str(item.get("type") or "")
    if kind:
        return _EVIDENCE_TYPE_LABELS.get(kind, kind)
    return _EVIDENCE_SOURCE_TITLES.get(str(item.get("source") or ""), "Bằng chứng nghiệp vụ")


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _split_amount(raw: Any) -> tuple[float | None, str, str]:
    """"12345.67 US Dollar" → (12345.67, "12 345.67", "US Dollar")."""
    m = _AMOUNT_CCY.match(str(raw or ""))
    if not m:
        return None, _s(raw), ""
    try:
        number = float(re.sub(r"[\s\u202f\u00a0,]", "", m.group(1)))
    except ValueError:
        return None, _s(raw), ""
    return number, _fmt_money(number), m.group(2).strip()  # phần còn lại là tên loại tiền


def _fmt_dt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    text = str(value)
    # ISO "2023-06-18T20:24:52Z" → "18/06/2023 20:24"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text


def _fmt_date_vn(value: datetime) -> str:
    return f"ngày {value.day:02d} tháng {value.month:02d} năm {value.year}"


#: Giá trị hồ sơ chủ thể, Việt hoá cho BẢN GỬI RA NGOÀI.
#:
#: API cố tình giữ giá trị thô (`organisation`, `medium`) vì mã còn so sánh trên
#: chúng; nhưng hồ sơ gửi cơ quan quản lý thì không được in ra tiếng Anh, và
#: trường nghề nghiệp khi thiếu KYC còn kèm cả TÊN BỘ DỮ LIỆU nội bộ.
_SUBJECT_VI = {
    "organisation": "Tổ chức",
    "individual": "Cá nhân",
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
}


def _subject_value(value: Any) -> str:
    """Một ô trong khối "Đối tượng bị báo cáo", đã Việt hoá."""
    text = _s(value)
    if text.lower().startswith("kyc unavailable"):
        return "Chưa có thông tin KYC"
    return _SUBJECT_VI.get(text.lower(), text)


def _s(value: Any) -> str:
    return "—" if value is None or value == "" else str(value)


class _SarPdf(FPDF):
    """A4, đầu thư ở trang 1 và tiêu đề chạy ở các trang sau."""

    def __init__(self, sar_id: str, *, institution: dict[str, Any], draft: bool) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.sar_id = sar_id
        self.institution = institution
        self.is_draft = draft
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 14, 18)
        self.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))

    # --- khung trang ---

    def header(self) -> None:
        if self.is_draft:
            self._watermark()
        if self.page_no() == 1:
            self._letterhead()
        else:
            self._running_header()

    def _watermark(self) -> None:
        """Dấu chìm "BẢN NHÁP" — để không ai nhầm bản đọc soát với bản chính."""
        self.set_font("DejaVu", "B", 58)
        self.set_text_color(*_WATERMARK)
        with self.rotation(45, x=105, y=150):
            self.text(38, 158, "BẢN NHÁP")
        self.set_text_color(*_INK)

    def _letterhead(self) -> None:
        top = self.get_y()
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(*_INK)
        self.multi_cell(104, 5, str(self.institution.get("name") or ""), align=Align.L,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(*_MUTED)
        self.multi_cell(104, 4.4, str(self.institution.get("unit") or ""), align=Align.L,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        left_bottom = self.get_y()

        self.set_xy(122, top)
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(*(_RISK if self.is_draft else _MUTED))
        self.cell(70, 5, "MẬT — CONFIDENTIAL", align=Align.R)
        self.set_xy(122, top + 5)
        self.set_font("DejaVu", "", 7.2)
        self.set_text_color(*_MUTED)
        self.cell(70, 4, "SỐ HIỆU BÁO CÁO", align=Align.R)
        self.set_xy(122, top + 9)
        self.set_text_color(*_INK)
        self.fit_font(self.sar_id, 70, style="B", size=8.0, floor=6.0)
        self.multi_cell(70, 4.4, self.sar_id, align=Align.R, new_x=XPos.LEFT, new_y=YPos.NEXT)

        self.set_y(max(left_bottom, self.get_y()) + 2)
        self.set_draw_color(*_ACCENT)
        self.set_line_width(0.5)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(4)

    def _running_header(self) -> None:
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, "BÁO CÁO GIAO DỊCH ĐÁNG NGỜ — MẬT", align=Align.L)
        self.cell(0, 5, self.sar_id, align=Align.R)
        self.ln(6)
        self.set_draw_color(*_LINE)
        self.set_line_width(0.2)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(3.5)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_draw_color(*_LINE)
        self.set_line_width(0.2)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(1.2)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*_MUTED)
        note = "Tài liệu chỉ có giá trị khi có đủ chữ ký của người lập và người phê duyệt."
        self.cell(0, 5, note, align=Align.L)
        self.cell(0, 5, f"Trang {self.page_no()}/{{nb}}", align=Align.R)

    # --- khối nội dung ---

    def fit_font(self, text: str, width: float, *, style: str = "", size: float = 9.0, floor: float = 6.8) -> None:
        """Đặt cỡ chữ lớn nhất mà ``text`` vẫn nằm gọn trong ``width``.

        ``multi_cell`` còn trừ lề trong ô (``c_margin`` mỗi bên), nên phải trừ
        phần đó khi đo — nếu không, chuỗi vừa khít vẫn bị bẻ xuống dòng (mã SAR
        dài rơi lại đúng một ký tự ở dòng dưới).
        """
        usable = width - 2 * self.c_margin
        while size > floor:
            self.set_font("DejaVu", style, size)
            if self.get_string_width(text) <= usable:
                return
            size -= 0.5
        self.set_font("DejaVu", style, floor)

    def need(self, height: float) -> None:
        """Sang trang nếu phần còn lại không đủ chỗ cho khối cao ``height``."""
        if self.get_y() + height > self.h - self.b_margin:
            self.add_page()

    def title_block(self, subtitle: str, recipient: str) -> None:
        self.ln(2)
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(*_INK)
        self.multi_cell(0, 8, "BÁO CÁO GIAO DỊCH ĐÁNG NGỜ", align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("DejaVu", "", 9)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 5, subtitle, align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if recipient:
            self.ln(1.5)
            self.set_font("DejaVu", "", 9.5)
            self.set_text_color(*_INK)
            self.multi_cell(0, 5, f"Kính gửi: {recipient}", align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def notice(self, text: str, *, color: tuple[int, int, int]) -> None:
        """Dải thông báo trạng thái tài liệu (bản nháp / mức rủi ro)."""
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("DejaVu", "B", 8.5)
        self.cell(0, 7, f"  {text}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_INK)
        self.ln(3)

    def h_section(self, text: str, *, keep: float = 22) -> None:
        """``keep`` = chiều cao tối thiểu phải còn lại, để tiêu đề mục không bị
        bỏ lại một mình ở cuối trang còn phần thân sang trang sau."""
        self.need(keep)
        self.ln(2.5)
        y = self.get_y()
        self.set_fill_color(*_BAND)
        self.rect(18, y, 174, 7.6, style="F")
        self.set_fill_color(*_ACCENT)
        self.rect(18, y, 1.6, 7.6, style="F")
        self.set_xy(21.5, y + 0.4)
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(*_ACCENT)
        self.cell(0, 6.8, text.upper())
        self.set_y(y + 7.6)
        self.ln(2.5)
        self.set_text_color(*_INK)

    def kv_grid(self, pairs: list[tuple[str, str]], *, columns: int = 2) -> None:
        """Lưới nhãn/giá trị.

        Mỗi hàng cao bằng ô CAO NHẤT trong hàng: giá trị dài (mã SAR, mã tài
        khoản) xuống dòng mà không đè lên nhãn của hàng dưới — lỗi của bản cũ.
        """
        col_w = self.epw / columns
        for i in range(0, len(pairs), columns):
            row = pairs[i : i + columns]
            self.need(16)
            y0 = self.get_y()
            bottoms = []
            for j, (label, value) in enumerate(row):
                x = self.l_margin + j * col_w
                self.set_xy(x, y0)
                self.set_text_color(*_MUTED)
                self.set_font("DejaVu", "", 7.2)
                self.cell(col_w, 3.8, label.upper())
                self.set_xy(x, y0 + 3.8)
                self.set_text_color(*_INK)
                text = _s(value)
                self.fit_font(text, col_w - 5, style="B", size=9.0)
                self.multi_cell(col_w - 5, 4.8, text, align=Align.L, new_x=XPos.LEFT, new_y=YPos.NEXT)
                bottoms.append(self.get_y())
            self.set_y(max(bottoms) + 2.2)

    def paragraph(self, text: str, size: float = 9.5) -> None:
        self.set_font("DejaVu", "", size)
        self.set_text_color(*_INK)
        self.multi_cell(0, 5.2, text, align=Align.J, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def note(self, text: str) -> None:
        self.set_font("DejaVu", "", 7.8)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 4.4, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_INK)


def _currency_totals(transactions: list[dict[str, Any]]) -> "OrderedDict[str, dict[str, float]]":
    """Tổng tiền vào/ra THEO TỪNG LOẠI TIỀN.

    Bản cũ cộng thẳng Yên + Euro + Rupee thành một con số duy nhất; con số đó
    không có ý nghĩa nào và không được đưa vào báo cáo gửi ra ngoài.
    """
    totals: OrderedDict[str, dict[str, float]] = OrderedDict()
    for t in transactions:
        amount, _, ccy = _split_amount(t.get("amount"))
        if amount is None:
            continue
        bucket = totals.setdefault(ccy or "—", {"in": 0.0, "out": 0.0, "n": 0})
        bucket["in" if t.get("direction") == "in" else "out"] += amount
        bucket["n"] += 1
    return OrderedDict(sorted(totals.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"])))


def build_sar_pdf(
    payload: dict[str, Any], *, exported_by: str, exported_at: datetime, draft: bool = False
) -> bytes:
    """Dựng và trả về bytes PDF cho một SAR (payload từ ``_sar_payload``).

    ``draft=True`` (hồ sơ chưa phê duyệt) đóng dấu "BẢN NHÁP" để chuyên viên đọc
    soát trước khi gửi duyệt — không phải bản chính thức.
    """
    institution = payload.get("institution") or {}
    preparer = payload.get("preparer") or {}
    pdf = _SarPdf(str(payload.get("sar_id") or "SAR"), institution=institution, draft=draft)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.title_block(
        "Suspicious Activity Report (SAR)",
        str(institution.get("recipient") or ""),
    )

    if draft:
        pdf.notice(
            "BẢN NHÁP — CHƯA PHÊ DUYỆT · chỉ để đọc soát nội bộ, không có giá trị nộp",
            color=_MUTED,
        )

    risk = _s(payload.get("riskLevel"))
    pdf.notice(f"MỨC RỦI RO: {risk}", color=_RISK if risk == "CAO" else _MUTED)

    # I. Thông tin chung + người lập
    pdf.h_section("I. Thông tin chung về báo cáo")
    pdf.kv_grid(
        [
            ("Số hiệu báo cáo", _s(payload.get("sar_id"))),
            ("Mã vụ việc", _s(payload.get("case_id"))),
            ("Mã cảnh báo", _s(payload.get("alert_id"))),
            ("Loại nghi vấn", _s(payload.get("suspicionType"))),
            ("Trạng thái hồ sơ", "Bản nháp — chưa phê duyệt" if draft else "Đã phê duyệt"),
            ("Ngày lập báo cáo", _fmt_dt(preparer.get("preparedAt") or exported_at)),
        ]
    )
    pdf.ln(1)
    pdf.need(30)
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 5.5, "Người lập báo cáo", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)
    if preparer.get("name"):
        pdf.kv_grid(
            [
                ("Họ và tên", _s(preparer.get("name"))),
                ("Chức danh", _s(preparer.get("title"))),
                ("Đơn vị công tác", _s(preparer.get("department"))),
                ("Điện thoại liên hệ", _s(preparer.get("phone"))),
                ("Thư điện tử", _s(preparer.get("email"))),
                ("Người xuất bản in này", exported_by),
            ]
        )
    else:
        pdf.note(
            "Chưa khai thông tin người lập báo cáo. Người lập cần điền họ tên, chức danh và "
            "đầu mối liên hệ tại màn hình soạn báo cáo trước khi gửi phê duyệt."
        )

    # II. Đối tượng
    subject = payload.get("subject") or {}
    pdf.h_section("II. Đối tượng bị báo cáo")
    pdf.kv_grid(
        [
            ("Mã khách hàng", _s(subject.get("customerId"))),
            ("Tài khoản", _s(subject.get("accountKey"))),
            ("Loại khách hàng", _subject_value(subject.get("customerType"))),
            ("Nghề nghiệp / ngành nghề", _subject_value(subject.get("occupation"))),
            ("Xếp hạng rủi ro nội bộ", _subject_value(subject.get("riskRating"))),
            ("Ngày thiết lập quan hệ", _fmt_dt(subject.get("onboardingDate"))),
        ]
    )

    # III. Tóm tắt nghi vấn
    pdf.h_section("III. Tóm tắt hành vi nghi vấn")
    summary = _trim_decimals(_s(payload.get("behaviourSummary"))) or "Chưa có tóm tắt."
    pdf.paragraph(summary)

    txs = payload.get("relatedTransactions") or []
    totals = _currency_totals(txs)
    if totals:
        pdf.ln(1)
        pdf.need(18 + 5.6 * (len(totals) + 1))
        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(0, 5.5, f"Dòng tiền trong {len(txs)} giao dịch gần nhất", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)
        pdf.set_font("DejaVu", "", 8.5)
        pdf.set_fill_color(250, 251, 253)
        with pdf.table(
            col_widths=(56, 26, 46, 46),
            text_align=("LEFT", "CENTER", "RIGHT", "RIGHT"),
            headings_style=FontFace(emphasis="BOLD", color=_INK, fill_color=_BAND),
            cell_fill_mode="EVEN_ROWS",
            line_height=5.4,
            first_row_as_headings=True,
            borders_layout="MINIMAL",
        ) as table:
            head = table.row()
            for h in ("Loại tiền", "Số giao dịch", "Tổng tiền vào", "Tổng tiền ra"):
                head.cell(h)
            for ccy, agg in totals.items():
                r = table.row()
                r.cell(ccy)
                r.cell(str(int(agg["n"])))
                r.cell(_fmt_money(agg["in"]))
                r.cell(_fmt_money(agg["out"]))
        pdf.ln(1)
        pdf.note(
            "Tổng hợp theo từng loại tiền tệ; không quy đổi và không cộng gộp các loại tiền khác nhau."
        )

    # IV. Nhận định & bằng chứng
    statements = payload.get("statements") or []
    labels = {str(e.get("id")): evidence_label(e) for e in (payload.get("evidence") or [])}
    pdf.h_section("IV. Nhận định và bằng chứng")
    if not statements:
        pdf.paragraph("Chưa có nhận định nào được lập.")
    for idx, st in enumerate(statements, start=1):
        pdf.need(18)
        pdf.set_font("DejaVu", "", 9.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(
            0,
            5.2,
            f"{idx}. {_trim_decimals(_s(st.get('text')))}",
            align=Align.J,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        # Tên nghiệp vụ của bằng chứng — KHÔNG in mã nội bộ ``EV-…`` ra tài liệu.
        names = list(dict.fromkeys(labels.get(str(e), "Bằng chứng nghiệp vụ") for e in (st.get("evidenceIds") or [])))
        pdf.note(f"Căn cứ: {'; '.join(names) if names else 'chưa gắn bằng chứng'}")
        pdf.ln(1.5)

    # V. Giao dịch liên quan
    pdf.h_section("V. Giao dịch liên quan")
    if not txs:
        pdf.paragraph("Không có giao dịch đính kèm.")
    else:
        subject_key = str((payload.get("network") or {}).get("subject") or "")
        shown = txs[:15]
        pdf.need(14 + 5.4 * (len(shown) + 1))
        pdf.set_font("DejaVu", "", 7.8)
        pdf.set_text_color(*_INK)
        # Bảng dùng màu tô hiện hành cho hàng xen kẽ; dải mức rủi ro ở trên để
        # lại màu đỏ, nên phải đặt lại thành xám rất nhạt.
        pdf.set_fill_color(250, 251, 253)
        with pdf.table(
            col_widths=(22, 29, 12, 34, 18, 59),
            text_align=("LEFT", "LEFT", "CENTER", "RIGHT", "LEFT", "LEFT"),
            headings_style=FontFace(emphasis="BOLD", color=_INK, fill_color=_BAND),
            cell_fill_mode="EVEN_ROWS",
            line_height=5.2,
            first_row_as_headings=True,
            borders_layout="MINIMAL",
        ) as table:
            head = table.row()
            for h in ("Mã giao dịch", "Thời điểm", "Chiều", "Số tiền", "Loại tiền", "Tài khoản đối ứng"):
                head.cell(h)
            for t in shown:
                incoming = t.get("direction") == "in"
                _, amount, ccy = _split_amount(t.get("amount"))
                counterparty = t.get("from_account_key") if incoming else t.get("to_account_key")
                if str(counterparty) == subject_key:
                    counterparty = t.get("to_account_key") if incoming else t.get("from_account_key")
                r = table.row()
                r.cell(_s(t.get("transaction_id")))
                r.cell(_fmt_dt(t.get("time")))
                r.cell("Vào" if incoming else "Ra")
                r.cell(amount)
                r.cell(ccy or "—")
                r.cell(_s(counterparty))
        pdf.ln(1)
        note = f"Chủ thể của các giao dịch trên là tài khoản {subject_key}."
        if len(txs) > 15:
            note += f" Còn {len(txs) - 15} giao dịch khác trong hồ sơ điều tra đầy đủ."
        pdf.note(note)

    # VI. Sơ đồ quan hệ giao dịch
    network = payload.get("network") or {}
    pdf.h_section("VI. Sơ đồ quan hệ giao dịch", keep=92)
    net_nodes = network.get("nodes") or []
    if len(net_nodes) < 2:
        pdf.paragraph("Không đủ quan hệ để dựng sơ đồ cho vụ này.")
    else:
        graph_h = 78.0
        pdf.need(graph_h + 8)
        graph_y = pdf.get_y()
        draw_case_graph(
            pdf,
            str(network.get("subject") or ""),
            [str(n) for n in net_nodes],
            list(network.get("edges") or []),
            x=pdf.l_margin,
            y=graph_y,
            w=pdf.epw,
            h=graph_h,
        )
        pdf.set_y(graph_y + graph_h + 2)
        pdf.note("Điểm giữa là tài khoản bị báo cáo; các điểm xung quanh là tài khoản đối ứng.")

    # VII. Ý kiến phê duyệt
    approval = payload.get("approval")
    pdf.h_section("VII. Ý kiến phê duyệt")
    if not approval:
        pdf.paragraph("Hồ sơ chưa có ý kiến phê duyệt.")
    else:
        decision_map = {"approved": "ĐỒNG Ý BÁO CÁO", "rejected": "KHÔNG BÁO CÁO", "more_info": "YÊU CẦU BỔ SUNG"}
        pdf.kv_grid(
            [
                ("Kết luận", decision_map.get(approval.get("decision"), _s(approval.get("decision")))),
                ("Người phê duyệt", _s(approval.get("decided_by"))),
                ("Thời điểm trình duyệt", _fmt_dt(approval.get("requested_at"))),
                ("Thời điểm phê duyệt", _fmt_dt(approval.get("decided_at"))),
            ]
        )
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, 5, f"Ý kiến: {_s(approval.get('reason'))}", align=Align.J, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # VIII. Phương pháp & giới hạn — minh bạch về cách dựng báo cáo.
    pdf.h_section("VIII. Phương pháp và giới hạn")
    pdf.paragraph(
        "Báo cáo do chuyên viên lập với hỗ trợ của trợ lý AI: phần tóm tắt và các nhận định được soạn từ "
        "kết quả điều tra và chỉ trích dẫn bằng chứng có thật của vụ; chuyên viên đã rà soát và chịu trách "
        "nhiệm nội dung. Mức rủi ro do bộ phát hiện chấm điểm, là tín hiệu hỗ trợ rà soát — KHÔNG phải xác "
        "suất rửa tiền. Đây là báo cáo nghi vấn để cơ quan có thẩm quyền xem xét, không phải kết luận về hành "
        "vi phạm tội. Số liệu giao dịch lấy trực tiếp từ sổ giao dịch; sơ đồ quan hệ dựng từ các giao dịch "
        "gần nhất của chủ thể."
    )

    _signature_block(pdf, preparer=preparer, approval=approval, exported_at=exported_at)
    return bytes(pdf.output())


def _signature_block(
    pdf: _SarPdf, *, preparer: dict[str, Any], approval: dict[str, Any] | None, exported_at: datetime
) -> None:
    """Khối ký tên cuối văn bản — phần bản cũ thiếu hẳn."""
    pdf.need(58)
    pdf.ln(6)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 5, _fmt_date_vn(exported_at), align=Align.R, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    approved = bool(approval) and approval.get("decision") == "approved"
    columns = [
        ("NGƯỜI LẬP BÁO CÁO", _s(preparer.get("name")) if preparer.get("name") else "", _s(preparer.get("title"))),
        (
            "NGƯỜI PHÊ DUYỆT",
            _s(approval.get("decided_by")) if approved else "",
            "Quản lý phụ trách" if approved else "",
        ),
    ]
    y0 = pdf.get_y()
    col_w = pdf.epw / len(columns)
    for j, (role, name, title) in enumerate(columns):
        x = pdf.l_margin + j * col_w
        pdf.set_xy(x, y0)
        pdf.set_font("DejaVu", "B", 9)
        pdf.set_text_color(*_INK)
        pdf.cell(col_w, 5, role, align=Align.C)
        pdf.set_xy(x, y0 + 5)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.cell(col_w, 4.5, "(Ký, ghi rõ họ tên)", align=Align.C)
        pdf.set_xy(x, y0 + 28)
        pdf.set_font("DejaVu", "B", 9.5)
        pdf.set_text_color(*_INK)
        pdf.cell(col_w, 5, name if name != "—" else "", align=Align.C)
        pdf.set_xy(x, y0 + 33)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.cell(col_w, 4.5, title if title != "—" else "", align=Align.C)
    pdf.set_y(y0 + 40)
