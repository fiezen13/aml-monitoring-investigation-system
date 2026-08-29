"""Vẽ đồ thị mạng lưới của vụ TRỰC TIẾP vào PDF bằng primitive của fpdf.

Không dùng matplotlib (chỉ có ở môi trường dev): tự tính bố cục hình sao (chủ thể
ở giữa, đối tác quanh vòng) rồi vẽ đường (line) + nút (ellipse) + nhãn. Đầu ra là
đồ thị vector, sắc nét, tự chứa — hợp với luồng xuất PDF từ server.
"""

from __future__ import annotations

import math
from typing import Any

_INK = (17, 24, 39)
_MUTED = (107, 114, 128)
_PRIMARY = (0, 150, 136)
_RISK = (220, 38, 38)
_EDGE = (150, 160, 172)
_EDGE_RISK = (220, 38, 38)


def _short(account: str) -> str:
    s = str(account or "")
    return s if len(s) <= 14 else s[:12] + "…"


def draw_case_graph(
    pdf: Any,
    subject: str,
    nodes: list[str],
    edges: list[dict[str, Any]],
    *,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    """Vẽ đồ thị vào vùng (x, y, w, h) tính bằng mm.

    ``nodes`` là danh sách account_key (đã gồm chủ thể). ``edges`` là các dict
    ``{"from","to","suspicious"}``. Bố cục: chủ thể ở giữa, các đối tác chia đều
    trên vòng tròn. Cạnh nghi vấn vẽ đỏ, còn lại xám.
    """
    others = [n for n in nodes if n != subject]
    if not others:
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.set_xy(x, y + h / 2)
        pdf.cell(w, 5, "Không đủ quan hệ để dựng mạng lưới.", align="C")
        return

    cx, cy = x + w / 2, y + h / 2
    # Bố trí trên ELLIP dẹt chứ không phải vòng tròn: vùng vẽ rộng gấp đôi chiều
    # cao, nên vòng tròn dồn các đối tác vào đỉnh và đáy — chỗ duy nhất phải đặt
    # nhãn chồng lên nhau. Ellip đẩy phần lớn đối tác ra hai bên, nơi nhãn nằm
    # ngang cạnh nút và không đụng nhau, chừa đỉnh/đáy cho vài nút thưa.
    rx = max(w / 2 - 26, 20.0)
    ry = max(h / 2 - 16, 14.0)
    pos: dict[str, tuple[float, float]] = {subject: (cx, cy)}
    # Nhãn đặt trên một vòng RỘNG HƠN vòng nút và so le trong/ngoài: khi vụ có
    # nhiều đối tác, nhãn đặt sát nút sẽ chồng lên nhau và không đọc được.
    label_pos: dict[str, tuple[float, float]] = {}
    angle: dict[str, float] = {}
    n = len(others)
    for i, node in enumerate(others):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        angle[node] = ang
        pos[node] = (cx + rx * math.cos(ang), cy + ry * math.sin(ang))
        gap = 5.0 if i % 2 == 0 else 9.5
        label_pos[node] = (cx + (rx + gap) * math.cos(ang), cy + (ry + gap) * math.sin(ang))

    # --- Cạnh (vẽ trước để nút nằm trên) ---
    pdf.set_line_width(0.3)
    for e in edges:
        a, b = pos.get(e.get("from")), pos.get(e.get("to"))
        if not a or not b:
            continue
        pdf.set_draw_color(*(_EDGE_RISK if e.get("suspicious") else _EDGE))
        pdf.line(a[0], a[1], b[0], b[1])

    # --- Nút + nhãn ---
    pdf.set_font("DejaVu", "", 6.5)
    for node, (nx, ny) in pos.items():
        is_subject = node == subject
        r = 3.4 if is_subject else 2.4
        pdf.set_draw_color(*(_PRIMARY if is_subject else _MUTED))
        pdf.set_fill_color(*(_PRIMARY if is_subject else (232, 236, 241)))
        pdf.set_line_width(0.5 if is_subject else 0.3)
        pdf.ellipse(nx - r, ny - r, 2 * r, 2 * r, style="FD")
        pdf.set_text_color(*(_INK if not is_subject else _INK))
        label = _short(node)
        tw = pdf.get_string_width(label)
        # Chủ thể: nhãn ngay dưới nút. Đối tác: đặt HẲN RA NGOÀI theo hướng nan
        # hoa — bên phải thì nhãn nằm bên phải nút, bên trái thì nằm bên trái —
        # để nhãn không đè lên chính nút của mình như bản cũ.
        if is_subject:
            lx0, ly = nx - tw / 2, ny + r + 2.4
        else:
            ang = angle[node]
            _, ly = label_pos[node]
            if abs(math.cos(ang)) < 0.12:  # đúng đỉnh hoặc đúng đáy vòng tròn
                lx0 = nx - tw / 2
                ly = ly - 3.2 if math.sin(ang) < 0 else ly + 0.4
            elif math.cos(ang) > 0:
                lx0, ly = nx + r + 1.5, ly - 1.6
            else:
                lx0, ly = nx - r - 1.5 - tw, ly - 1.6
        lx0 = min(max(lx0, x), x + w - tw - 1)
        pdf.set_xy(lx0 - 1, ly)
        pdf.cell(tw + 2, 3, label, align="C")

    # Chú giải nhỏ dưới đồ thị.
    pdf.set_font("DejaVu", "", 7)
    pdf.set_text_color(*_MUTED)
    pdf.set_xy(x, y + h - 4)
    pdf.cell(0, 4, "● Chủ thể (xanh) · ○ Đối tác · đường đỏ = giao dịch đáng ngờ")
