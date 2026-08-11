"""Sinh biểu đồ EDA từ kết quả JSON của hai script profiling.

Không đọc lại file dữ liệu gốc — chỉ đọc `artifacts/eda/*.json`. Nghĩa là
chạy lại rất nhanh, và biểu đồ luôn khớp với con số trong tài liệu vì cùng
một nguồn.

Chạy:
    python scripts/eda/plot_eda.py \
        --transactions artifacts/eda/li_small_transactions.json \
        --patterns artifacts/eda/li_small_patterns.json \
        --outdir docs/ml/figures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

# Bảng màu: xanh mực cho dữ liệu bình thường, đỏ gạch cho cảnh báo/nhãn dương,
# xám cho nền. Đủ tương phản khi in đen trắng.
INK = "#1f3d5c"
ALERT = "#a8342a"
MUTED = "#8a95a1"
GRID = "#dfe4ea"
SAFE = "#2f6b4f"

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.edgecolor": "#c3cad3",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "figure.dpi": 160,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
    }
)


def _finish(fig: plt.Figure, path: Path, note: str | None = None) -> None:
    if note:
        fig.text(0.5, -0.02, note, ha="center", va="top", fontsize=7.5, color=MUTED)
    fig.savefig(path)
    plt.close(fig)
    print(f"  {path}")


def fig_daily(data: dict[str, Any], outdir: Path) -> None:
    """Khối lượng và nhãn dương theo ngày — biểu đồ quyết định cách chia tập."""
    rows = data["nhan_theo_ngay"]
    days = [r["ngay"][5:] for r in rows]
    volume = [r["tong_giao_dich"] for r in rows]
    laundering = [r["laundering"] for r in rows]
    x = range(len(days))

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"height_ratios": [1, 1], "hspace": 0.18}
    )

    top.bar(x, volume, color=INK, width=0.68)
    top.set_ylabel("Giao dịch")
    top.set_title("Khối lượng giao dịch theo ngày — 99,997% nằm trong 10 ngày đầu", loc="left")
    top.set_yscale("log")
    top.axvspan(9.5, len(days) - 0.5, color=ALERT, alpha=0.08)
    top.annotate(
        "7 ngày cuối: 223 giao dịch\n(đuôi kịch bản đang hoàn tất)",
        xy=(13, 60),
        xytext=(11.2, 9000),
        fontsize=8,
        color=ALERT,
        ha="center",
        arrowprops={"arrowstyle": "->", "color": ALERT, "lw": 0.9},
    )

    bottom.bar(x, laundering, color=ALERT, width=0.68)
    bottom.set_ylabel("Dòng laundering")
    bottom.set_title("Nhãn dương theo ngày", loc="left")
    bottom.axvspan(9.5, len(days) - 0.5, color=ALERT, alpha=0.08)
    bottom.set_xticks(list(x))
    bottom.set_xticklabels(days, rotation=45, ha="right", fontsize=7.5)

    # Mốc cắt nếu chia 60/20/20 theo lịch trên span 16,6 ngày.
    for pos, label in ((9.95, "mốc 60%"), (12.9, "mốc 80%")):
        for ax in (top, bottom):
            ax.axvline(pos, color=MUTED, ls="--", lw=1)
        bottom.text(
            pos,
            bottom.get_ylim()[1] * 0.92,
            label,
            fontsize=7.5,
            color=MUTED,
            ha="center",
            va="top",
            bbox={"fc": "white", "ec": "none", "pad": 1.5},
        )

    _finish(
        fig,
        outdir / "01_phan_bo_theo_ngay.png",
        "Chia 60/20/20 theo lịch để lại tập TEST đúng 50 giao dịch và 31 dòng laundering.",
    )


def fig_hours(data: dict[str, Any], outdir: Path) -> None:
    """Giờ trong ngày — artifact 00:00."""
    dist = data["gio_trong_ngay"]["phan_bo"]
    hours = [d["gio"] for d in dist]
    share = [d["ti_le_pct"] for d in dist]
    expected = data["gio_trong_ngay"]["ky_vong_neu_deu_pct"]
    colors = [ALERT if h == "00" else INK for h in hours]

    fig, ax = plt.subplots(figsize=(9, 3.1))
    ax.bar(hours, share, color=colors, width=0.72)
    ax.axhline(expected, color=MUTED, ls="--", lw=1.1)
    ax.text(23.4, expected + 0.18, f"kỳ vọng nếu đều: {expected}%", fontsize=8, color=MUTED, ha="right")
    ax.annotate(
        "12,55% — artifact của bộ sinh:\ngiao dịch không có giờ rơi về 00:00",
        xy=(0, 12.4),
        xytext=(3.1, 10.6),
        fontsize=8,
        color=ALERT,
        arrowprops={"arrowstyle": "->", "color": ALERT, "lw": 0.9},
    )
    ax.set_ylabel("Tỉ lệ giao dịch (%)")
    ax.set_xlabel("Giờ trong ngày")
    ax.set_title("Giờ 01–23 phẳng trong khoảng 0,04 điểm phần trăm — chỉ giờ 00 lệch", loc="left")
    ax.set_ylim(0, 13.6)
    _finish(
        fig,
        outdir / "02_gio_trong_ngay.png",
        "Kết luận: cấm mọi đặc trưng theo giờ trong ngày. Hiệu hai mốc thời gian thì vẫn dùng được.",
    )


def fig_channel(data: dict[str, Any], outdir: Path) -> None:
    """Lift theo kênh thanh toán."""
    rows = sorted(data["kenh_thanh_toan"], key=lambda r: r["lift"] or 0)
    names = [r["gia_tri"] for r in rows]
    lifts = [r["lift"] or 0 for r in rows]
    colors = [ALERT if lift >= 3 else (SAFE if lift < 1.5 else "#c98a1e") for lift in lifts]

    fig, (left, right) = plt.subplots(1, 2, figsize=(9.4, 3.2), gridspec_kw={"wspace": 0.32})

    left.barh(names, lifts, color=colors, height=0.62)
    left.axvline(1.0, color=MUTED, lw=1)
    left.axvline(3.0, color=ALERT, ls="--", lw=1.1)
    left.text(3.08, 0.1, "ngưỡng cấm 3×", fontsize=7.5, color=ALERT, rotation=90, va="bottom")
    for i, lift in enumerate(lifts):
        left.text(
            lift + 0.12,
            i,
            f"{lift:g}×",
            va="center",
            fontsize=8,
            color=ALERT if lift >= 3 else INK,
            fontweight="bold" if lift >= 3 else "normal",
        )
    left.set_xlim(0, 7.4)
    left.set_xlabel("Lift so với tỉ lệ nền")
    left.set_title("Kênh thanh toán × nhãn", loc="left")

    share_file = [r["ti_le_toan_file_pct"] for r in rows]
    share_laund = [r["ti_le_trong_laundering_pct"] for r in rows]
    y = range(len(names))
    right.barh([i + 0.2 for i in y], share_file, height=0.36, color=MUTED, label="trong toàn file")
    right.barh([i - 0.2 for i in y], share_laund, height=0.36, color=ALERT, label="trong dòng laundering")
    right.set_yticks(list(y))
    right.set_yticklabels(names)
    right.set_xlabel("Tỉ lệ (%)")
    right.set_title("ACH: 11,5% toàn file nhưng 73,2% dòng laundering", loc="left")
    right.legend(fontsize=7.5, frameon=False, loc="lower right")

    _finish(
        fig,
        outdir / "03_kenh_thanh_toan.png",
        "Wire và Reinvestment không chứa một dòng laundering nào. Payment Format bị cấm làm đặc trưng.",
    )


def fig_amounts(data: dict[str, Any], outdir: Path) -> None:
    """Số tiền: toàn bộ so với laundering, và độ trải theo tiền tệ."""
    overall = data["so_tien"]["toan_bo_mau"]
    laund = data["so_tien"]["chi_dong_laundering"]
    labels = ["p25", "p50", "p75", "p95"]

    fig, (left, right) = plt.subplots(1, 2, figsize=(9.4, 3.3), gridspec_kw={"wspace": 0.3})

    idx = range(len(labels))
    left.plot(idx, [overall[k] for k in labels], "o-", color=MUTED, lw=2, ms=6, label="toàn bộ giao dịch")
    left.plot(idx, [laund[k] for k in labels], "o-", color=ALERT, lw=2, ms=6, label="chỉ dòng laundering")
    left.set_yscale("log")
    left.set_xticks(list(idx))
    left.set_xticklabels(labels)
    left.set_ylabel("Số tiền (thang log)")
    left.set_title("Laundering nằm ở khúc giữa, tránh cả hai đầu", loc="left")
    left.legend(fontsize=8, frameon=False)
    left.annotate(
        "p50 gấp 1,9×",
        xy=(1, laund["p50"]),
        xytext=(1.15, laund["p50"] * 3.2),
        fontsize=8,
        color=ALERT,
        arrowprops={"arrowstyle": "->", "color": ALERT, "lw": 0.9},
    )
    left.annotate(
        "nhưng p95 lại thấp hơn",
        xy=(3, laund["p95"]),
        xytext=(1.6, laund["p95"] * 0.06),
        fontsize=8,
        color=ALERT,
        arrowprops={"arrowstyle": "->", "color": ALERT, "lw": 0.9},
    )

    by_cur = data["so_tien"]["theo_tien_te"]
    curs = list(by_cur)
    med = [by_cur[c]["p50"] for c in curs]
    order = sorted(range(len(curs)), key=lambda i: med[i])
    right.barh([curs[i] for i in order], [med[i] for i in order], color=INK, height=0.6)
    right.set_xscale("log")
    right.set_xlabel("Trung vị số tiền (thang log)")
    right.set_title("Trải 6 bậc độ lớn giữa các đơn vị tiền tệ", loc="left")
    for pos, i in enumerate(order):
        right.text(med[i] * 1.35, pos, f"{med[i]:,.2f}".replace(",", "."), va="center", fontsize=7.5, color=INK)
    right.set_xlim(right.get_xlim()[0], right.get_xlim()[1] * 12)

    _finish(
        fig,
        outdir / "04_so_tien.png",
        "Bắt buộc chuẩn hoá số tiền trong từng đơn vị tiền tệ trước mọi phép tổng hoặc so sánh.",
    )


def fig_degree(data: dict[str, Any], outdir: Path) -> None:
    """Phân bố bậc và ngưỡng loại hub."""
    deg = data["bac"]["tong"]
    total = data["quy_mo"]["so_tai_khoan"]
    points = [
        ("p25", deg["p25"]),
        ("p50", deg["p50"]),
        ("p75", deg["p75"]),
        ("p95", deg["p95"]),
        ("p99", deg["p99"]),
        ("max", deg["max"]),
    ]

    fig, (left, right) = plt.subplots(1, 2, figsize=(9.4, 3.2), gridspec_kw={"wspace": 0.3})

    left.plot(range(len(points)), [v for _, v in points], "o-", color=INK, lw=2, ms=6)
    left.set_yscale("log")
    left.set_xticks(range(len(points)))
    left.set_xticklabels([k for k, _ in points])
    left.set_ylabel("Bậc tổng (thang log)")
    left.set_title("Phân bố bậc đứt gãy rất rõ ở đuôi", loc="left")
    left.axhline(1000, color=ALERT, ls="--", lw=1.1)
    left.text(0.05, 1250, "ngưỡng loại hub = 1.000", fontsize=8, color=ALERT)
    left.annotate(
        f"max = {deg['max']:,}".replace(",", "."),
        xy=(5, deg["max"]),
        xytext=(3.1, deg["max"] * 0.25),
        fontsize=8,
        color=ALERT,
        arrowprops={"arrowstyle": "->", "color": ALERT, "lw": 0.9},
    )

    buckets = [
        ("bậc ≥ 1.000\n(hub — loại bỏ)", data["bac"]["so_tai_khoan_bac_>=1000"], ALERT),
        ("bậc ≥ 100", data["bac"]["so_tai_khoan_bac_>=100"], "#c98a1e"),
        ("bậc ≥ 20\n(đủ lịch sử để tự so sánh)", data["bac"]["so_tai_khoan_bac_>=20"], SAFE),
        ("toàn bộ tài khoản", total, MUTED),
    ]
    right.barh([b[0] for b in buckets], [b[1] for b in buckets], color=[b[2] for b in buckets], height=0.6)
    right.set_xscale("log")
    right.set_xlabel("Số tài khoản (thang log)")
    right.set_title("Chỉ 15 tài khoản vượt ngưỡng hub", loc="left")
    for i, (_, value, _) in enumerate(buckets):
        right.text(
            value * 1.4,
            i,
            f"{value:,}".replace(",", ".") + f"  ({100 * value / total:.1f}%)",
            va="center",
            fontsize=7.5,
            color=INK,
        )
    right.set_xlim(right.get_xlim()[0], right.get_xlim()[1] * 40)

    _finish(
        fig,
        outdir / "05_phan_bo_bac.png",
        "33,7% tài khoản có bậc ≥ 20 — đó là phạm vi của nhánh tự-so-sánh; phần còn lại đi nhánh so-với-nhóm.",
    )


def fig_typology(patterns: dict[str, Any], outdir: Path) -> None:
    """Typology của IBM và ánh xạ sang danh mục T01-T10."""
    mapping = {
        "STACK": "T02",
        "BIPARTITE": "T02",
        "CYCLE": "T03",
        "FAN-IN": "T04",
        "FAN-OUT": "T04",
        "SCATTER-GATHER": "T04",
        "GATHER-SCATTER": "T04",
        "RANDOM": "—",
    }
    palette = {"T02": "#3a6ea5", "T03": "#2f6b4f", "T04": "#7a5aa3", "—": MUTED}
    items = sorted(patterns["typology"].items(), key=lambda kv: kv[1]["so_instance"])
    names = [k for k, _ in items]
    counts = [v["so_instance"] for _, v in items]
    colors = [palette[mapping[n]] for n in names]

    fig, (left, right) = plt.subplots(1, 2, figsize=(9.4, 3.4), gridspec_kw={"wspace": 0.36})

    left.barh(names, counts, color=colors, height=0.62)
    for i, (name, count) in enumerate(zip(names, counts, strict=True)):
        left.text(count + 0.4, i, f"{count} → {mapping[name]}", va="center", fontsize=8, color=INK)
    left.set_xlim(0, max(counts) * 1.5)
    left.set_xlabel("Số instance")
    left.set_title("8 typology của IBM", loc="left")
    left.legend(
        handles=[Patch(color=c, label=t) for t, c in palette.items()],
        fontsize=7.5,
        frameon=False,
        loc="lower right",
        ncols=2,
    )

    targets = ["T01", "T02", "T03", "T04", "T05"]
    totals = {"T01": 0, "T02": 0, "T03": 0, "T04": 0, "T05": 0}
    for name, meta in patterns["typology"].items():
        target = mapping[name]
        if target in totals:
            totals[target] += meta["so_instance"]
    bar_colors = [ALERT if totals[t] == 0 else palette.get(t, INK) for t in targets]
    right.bar(targets, [totals[t] for t in targets], color=bar_colors, width=0.62)
    for i, t in enumerate(targets):
        label = "KHÔNG CÓ" if totals[t] == 0 else str(totals[t])
        right.text(
            i,
            totals[t] + 1.5,
            label,
            ha="center",
            fontsize=8,
            color=ALERT if totals[t] == 0 else INK,
            fontweight="bold" if totals[t] == 0 else "normal",
        )
    right.set_ylabel("Số instance có ground truth")
    right.set_title("Cam kết BUS-001 §7 phủ T01–T05", loc="left")
    right.set_ylim(0, max(totals.values()) * 1.42)
    right.text(
        2.0,
        max(totals.values()) * 1.30,
        "T01 và T05 không có instance nào — structuring là mẫu hình\n"
        "theo NGƯỠNG, không phải mẫu hình ĐỒ THỊ nên IBM không sinh",
        fontsize=7.5,
        color=ALERT,
        ha="center",
        va="top",
    )

    _finish(
        fig,
        outdir / "06_typology.png",
        "T01 không có instance nào; T05 phải dẫn xuất từ thời gian lưu tiền trong STACK và CYCLE.",
    )


def fig_split(data: dict[str, Any], outdir: Path) -> None:
    """So sánh hai cách chia tập."""
    rows = data["nhan_theo_ngay"]
    total_txn = sum(r["tong_giao_dich"] for r in rows)
    total_laund = sum(r["laundering"] for r in rows)

    time_split = [("TRAIN", 6_923_826, 3_431), ("VALIDATION", 173, 103), ("TEST", 50, 31)]
    net_split = [("TRAIN", 0.70), ("VALIDATION", 0.10), ("TEST", 0.10), ("HIDDEN", 0.10)]

    fig, (left, right) = plt.subplots(1, 2, figsize=(9.4, 3.3), gridspec_kw={"wspace": 0.3})

    names = [s[0] for s in time_split]
    left.bar(names, [s[2] for s in time_split], color=[INK, INK, ALERT], width=0.6)
    left.set_yscale("log")
    left.set_ylabel("Dòng laundering (thang log)")
    left.set_title("Chia theo THỜI GIAN 60/20/20 — không dùng được", loc="left")
    for i, s in enumerate(time_split):
        left.text(
            i,
            s[2] * 1.35,
            f"{s[2]:,}".replace(",", ".") + f"\n({100 * s[2] / total_laund:.1f}%)",
            ha="center",
            fontsize=8,
            color=ALERT if s[0] == "TEST" else INK,
        )
    left.set_ylim(10, total_laund * 4)

    names2 = [s[0] for s in net_split]
    values2 = [int(total_laund * s[1]) for s in net_split]
    right.bar(names2, values2, color=[INK, INK, SAFE, SAFE], width=0.6)
    right.set_ylabel("Dòng laundering (ước tính)")
    right.set_title("Chia theo MẠNG LƯỚI + THỰC THỂ 70/10/10/10", loc="left")
    for i, v in enumerate(values2):
        right.text(i, v + total_laund * 0.02, f"~{v:,}".replace(",", "."), ha="center", fontsize=8, color=INK)
    right.set_ylim(0, total_laund * 0.86)

    _finish(
        fig,
        outdir / "07_chia_tap.png",
        f"Tổng {total_laund:,} dòng laundering trên {total_txn:,} giao dịch.".replace(",", "."),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--transactions", required=True, type=Path)
    parser.add_argument("--patterns", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()

    trans = json.loads(args.transactions.read_text(encoding="utf-8"))
    patterns = json.loads(args.patterns.read_text(encoding="utf-8"))
    args.outdir.mkdir(parents=True, exist_ok=True)

    print("Sinh biểu đồ:")
    fig_daily(trans, args.outdir)
    fig_hours(trans, args.outdir)
    fig_channel(trans, args.outdir)
    fig_amounts(trans, args.outdir)
    fig_degree(trans, args.outdir)
    fig_typology(patterns, args.outdir)
    fig_split(trans, args.outdir)


if __name__ == "__main__":
    main()
