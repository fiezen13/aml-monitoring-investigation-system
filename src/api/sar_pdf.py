"""Dựng PDF cho Báo cáo Giao dịch Đáng ngờ (SAR).

Trước đây ``POST /sars/{id}/export`` chỉ đổi trạng thái + ghi audit rồi trả một
tên file GIẢ; không có file thật để nộp. Module này dựng PDF thật từ payload của
``_sar_payload`` — cùng dữ liệu mà giao diện đang hiển thị, nên PDF khớp màn hình.

Font: trình dựng PDF mặc định (Helvetica) rớt dấu tiếng Việt (không phủ Latin
Extended Additional). Nhúng DejaVu Sans (assets/fonts) để chữ có dấu hiển thị
đúng. Thuần Python, không phụ thuộc hệ thống.
"""

from __future__ import annotations

import re
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
_LONG_DECIMAL = re.compile(r"\d+\.\d{3,}")


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
_BAND = (241, 244, 248)


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


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


def _s(value: Any) -> str:
    return "—" if value is None or value == "" else str(value)


class _SarPdf(FPDF):
    """A4, có header/footer riêng cho hồ sơ mật."""

    def __init__(self, sar_id: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.sar_id = sar_id
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)
        self.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))

    def header(self) -> None:
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 6, "FIN-07 · Velrix — MẬT / CONFIDENTIAL", align=Align.L)
        self.cell(0, 6, self.sar_id, align=Align.R)
        self.ln(7)
        self.set_draw_color(*_LINE)
        self.set_line_width(0.2)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(*_LINE)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(1)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*_MUTED)
        note = "Tài liệu tạo tự động — chỉ có giá trị khi kèm phê duyệt và chữ ký người chịu trách nhiệm."
        self.cell(0, 5, note, align=Align.L)
        self.cell(0, 5, f"Trang {self.page_no()}/{{nb}}", align=Align.R)

    # --- khối nội dung ---

    def h_section(self, text: str) -> None:
        if self.get_y() > 250:
            self.add_page()
        self.ln(2)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*_ACCENT)
        self.cell(0, 7, text)
        self.ln(8)
        self.set_text_color(*_INK)

    def kv_grid(self, pairs: list[tuple[str, str]]) -> None:
        """Lưới nhãn/giá trị hai cột."""
        self.set_font("DejaVu", "", 9)
        col_w = 89.0
        for i in range(0, len(pairs), 2):
            row = pairs[i : i + 2]
            y0 = self.get_y()
            for j, (label, value) in enumerate(row):
                x = 16 + j * col_w
                self.set_xy(x, y0)
                self.set_text_color(*_MUTED)
                self.set_font("DejaVu", "", 7.5)
                self.cell(col_w, 4, label.upper())
                self.set_xy(x, y0 + 4)
                self.set_text_color(*_INK)
                self.set_font("DejaVu", "B", 9.5)
                self.multi_cell(col_w - 4, 5, _s(value), align=Align.L)
            self.set_y(y0 + 11)

    def paragraph(self, text: str, size: float = 9.5) -> None:
        self.set_font("DejaVu", "", size)
        self.set_text_color(*_INK)
        self.multi_cell(0, 5.2, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)


def build_sar_pdf(payload: dict[str, Any], *, exported_by: str, exported_at: datetime) -> bytes:
    """Dựng và trả về bytes PDF cho một SAR (payload từ ``_sar_payload``)."""
    pdf = _SarPdf(payload.get("sar_id", "SAR"))
    pdf.alias_nb_pages()
    pdf.add_page()

    # Tiêu đề
    pdf.set_font("DejaVu", "B", 17)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 9, "BÁO CÁO GIAO DỊCH ĐÁNG NGỜ")
    pdf.ln(9)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, "Suspicious Activity Report (SAR)")
    pdf.ln(8)

    # Dải mức rủi ro
    risk = _s(payload.get("riskLevel"))
    pdf.set_fill_color(*(_RISK if risk == "CAO" else _MUTED))
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 8)
    pdf.cell(pdf.get_string_width(f"  MỨC RỦI RO: {risk}  ") + 2, 6, f"  MỨC RỦI RO: {risk}  ", fill=True)
    pdf.ln(10)

    pdf.kv_grid(
        [
            ("Mã SAR", _s(payload.get("sar_id"))),
            ("Mã vụ việc", _s(payload.get("case_id"))),
            ("Mã cảnh báo", _s(payload.get("alert_id"))),
            ("Loại nghi vấn", _s(payload.get("suspicionType"))),
            ("Trạng thái hồ sơ", _s(payload.get("status"))),
            ("Người lập (đã gửi)", _s(payload.get("submittedBy"))),
            ("Người xuất báo cáo", exported_by),
            ("Thời điểm xuất", exported_at.strftime("%d/%m/%Y %H:%M")),
        ]
    )

    # 1. Đối tượng
    subject = payload.get("subject") or {}
    pdf.h_section("1. Đối tượng bị báo cáo")
    pdf.kv_grid(
        [
            ("Mã khách hàng", _s(subject.get("customerId"))),
            ("Tài khoản", _s(subject.get("accountKey"))),
            ("Loại khách hàng", _s(subject.get("customerType"))),
            ("Nghề nghiệp", _s(subject.get("occupation"))),
            ("Xếp hạng rủi ro nội bộ", _s(subject.get("riskRating"))),
            ("Ngày thiết lập quan hệ", _fmt_dt(subject.get("onboardingDate"))),
        ]
    )

    # 2. Tóm tắt nghi vấn
    pdf.h_section("2. Tóm tắt hành vi nghi vấn")
    summary = _trim_decimals(_s(payload.get("behaviourSummary"))) or "Chưa có tóm tắt."
    pdf.paragraph(summary)
    pdf.ln(1)
    pdf.kv_grid(
        [
            ("Tổng tiền vào (mẫu)", _fmt_money(payload.get("inflow"))),
            ("Tổng tiền ra (mẫu)", _fmt_money(payload.get("outflow"))),
        ]
    )

    # 3. Nhận định & bằng chứng
    statements = payload.get("statements") or []
    pdf.h_section("3. Nhận định và bằng chứng")
    if not statements:
        pdf.paragraph("Chưa có nhận định nào được lập.")
    for idx, st in enumerate(statements, start=1):
        pdf.set_font("DejaVu", "B", 9.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, 5.2, f"{idx}. {_trim_decimals(_s(st.get('text')))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        refs = ", ".join(st.get("evidenceIds") or []) or "— (chưa gắn bằng chứng)"
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 4.6, f"Bằng chứng: {refs}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)

    # 4. Giao dịch liên quan
    txs = payload.get("relatedTransactions") or []
    pdf.h_section("4. Giao dịch liên quan")
    if not txs:
        pdf.paragraph("Không có giao dịch đính kèm.")
    else:
        pdf.set_font("DejaVu", "", 8)
        headings = ("Mã giao dịch", "Thời điểm", "Chiều", "Số tiền", "Từ → Đến")
        widths = (32, 30, 14, 34, 68)
        pdf.set_text_color(*_INK)
        # Màu tô của tài liệu đang là đỏ (dải mức rủi ro ở trên). Bảng dùng màu
        # tô hiện hành cho các hàng xen kẽ, nên phải đặt lại thành xám nhạt.
        pdf.set_fill_color(247, 249, 251)
        with pdf.table(
            col_widths=widths,
            text_align=("LEFT", "LEFT", "CENTER", "RIGHT", "LEFT"),
            headings_style=FontFace(emphasis="BOLD", color=_INK, fill_color=_BAND),
            cell_fill_mode="EVEN_ROWS",
            line_height=5.2,
            first_row_as_headings=True,
            borders_layout="MINIMAL",
        ) as table:
            head = table.row()
            for h in headings:
                head.cell(h)
            for t in txs[:15]:
                direction = "Vào" if t.get("direction") == "in" else "Ra"
                flow = f"{_s(t.get('from_account_key'))[:16]} → {_s(t.get('to_account_key'))[:16]}"
                r = table.row()
                r.cell(_s(t.get("transaction_id")))
                r.cell(_fmt_dt(t.get("time")))
                r.cell(direction)
                r.cell(_trim_decimals(_s(t.get("amount"))))
                r.cell(flow)
        if len(txs) > 15:
            pdf.ln(1)
            pdf.set_font("DejaVu", "", 7.5)
            pdf.set_text_color(*_MUTED)
            pdf.cell(0, 4, f"… và {len(txs) - 15} giao dịch khác (xem hồ sơ điều tra đầy đủ).")
            pdf.ln(5)

    # 5. Đồ thị mạng lưới của vụ
    network = payload.get("network") or {}
    pdf.h_section("5. Đồ thị mạng lưới của vụ")
    net_nodes = network.get("nodes") or []
    if len(net_nodes) < 2:
        pdf.paragraph("Không đủ quan hệ để dựng mạng lưới cho vụ này.")
    else:
        graph_h = 88.0
        if pdf.get_y() + graph_h > pdf.h - pdf.b_margin:
            pdf.add_page()
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
        pdf.set_y(graph_y + graph_h + 3)

    # 6. Phê duyệt
    approval = payload.get("approval")
    pdf.h_section("6. Phê duyệt")
    if not approval:
        pdf.paragraph("Hồ sơ chưa có bản ghi phê duyệt.")
    else:
        decision_map = {"approved": "ĐÃ PHÊ DUYỆT", "rejected": "TỪ CHỐI", "more_info": "YÊU CẦU BỔ SUNG"}
        pdf.kv_grid(
            [
                ("Quyết định", decision_map.get(approval.get("decision"), _s(approval.get("decision")))),
                ("Người quyết định", _s(approval.get("decided_by"))),
                ("Thời điểm yêu cầu", _fmt_dt(approval.get("requested_at"))),
                ("Thời điểm quyết định", _fmt_dt(approval.get("decided_at"))),
            ]
        )
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 5, f"Lý do: {_s(approval.get('reason'))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # 7. Phương pháp & giới hạn — minh bạch về cách dựng báo cáo.
    pdf.h_section("7. Phương pháp & giới hạn")
    pdf.paragraph(
        "Báo cáo do chuyên viên lập với hỗ trợ của trợ lý AI: phần tóm tắt và các nhận định được soạn từ "
        "kết quả điều tra và chỉ trích dẫn bằng chứng có thật của vụ; chuyên viên đã rà soát và chịu trách "
        "nhiệm nội dung. Mức rủi ro do bộ phát hiện chấm điểm, là tín hiệu hỗ trợ rà soát — KHÔNG phải xác "
        "suất rửa tiền. Đây là báo cáo nghi vấn để cơ quan có thẩm quyền xem xét, không phải kết luận về hành "
        "vi phạm tội. Số liệu giao dịch lấy trực tiếp từ sổ giao dịch; đồ thị mạng lưới dựng từ các giao dịch "
        "gần nhất của chủ thể."
    )

    return bytes(pdf.output())
