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
    radius = min(w, h) / 2 - 12
    pos: dict[str, tuple[float, float]] = {subject: (cx, cy)}
    n = len(others)
    for i, node in enumerate(others):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        pos[node] = (cx + radius * math.cos(ang), cy + radius * math.sin(ang))

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
        # Nhãn chủ thể đặt dưới nút; đối tác đặt phía ngoài để đỡ chồng.
        ly = ny + r + 1.2 if ny >= cy else ny - r - 3.4
        pdf.set_xy(nx - tw / 2 - 1, ly)
        pdf.cell(tw + 2, 3, label, align="C")

    # Chú giải nhỏ dưới đồ thị.
    pdf.set_font("DejaVu", "", 7)
    pdf.set_text_color(*_MUTED)
    pdf.set_xy(x, y + h - 4)
    pdf.cell(0, 4, "● Chủ thể (xanh) · ○ Đối tác · đường đỏ = giao dịch đáng ngờ")
