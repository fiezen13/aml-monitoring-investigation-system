"""Cảnh báo T03 sinh từ chu trình bộ dò tìm được.

Bài kiểm thử khoá hai thứ mà việc sửa tay rất dễ làm hỏng:

1. **Hằng số phải khớp ràng buộc cơ sở dữ liệu.** ``detector`` và
   ``typology_code`` được nội suy thẳng vào chuỗi SQL, nên một giá trị sai chỉ
   lộ ra khi chạy thật trên máy chủ — lúc đó script đã xoá cảnh báo cũ.
2. **Công thức chấm điểm phải đơn điệu đúng chiều.** Vòng khép nhanh hơn, nhiều
   vòng hơn, vòng ngắn hơn đều phải cho điểm CAO hơn. Đảo dấu một số hạng thì
   hàng đợi vẫn có cảnh báo, vẫn có lý do, chỉ là xếp ngược — không có gì đỏ.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.build_cycle_alerts import (
    CELL_SQL,
    COUNT_SATURATION,
    DATASET,
    DETECTOR,
    LONG_CYCLE_HOPS,
    TYPOLOGY,
    W_COUNT,
    W_SHORT,
    W_SPEED,
    alert_id,
    parse_args,
)

ROOT = Path(__file__).resolve().parents[2]


def _diem(speed_rank: float, cycle_count: int, len_min: int) -> float:
    """Bản Python của công thức trong ``CELL_SQL`` — giữ khớp thủ công.

    ``speed_rank`` là phân vị tốc độ trong lô (1,0 = khép nhanh nhất), vì SQL
    dùng ``percent_rank()`` chứ không phải một mốc giờ cứng.
    """
    s_count = min(1.0, (cycle_count - 1) / COUNT_SATURATION)
    s_short = max(0.0, min(1.0, (LONG_CYCLE_HOPS - len_min) / (LONG_CYCLE_HOPS - 2)))
    return W_SPEED * speed_rank + W_COUNT * s_count + W_SHORT * s_short


# --- Hằng số phải hợp lệ với lược đồ -----------------------------------------


def test_detector_nam_trong_rang_buoc_cua_bang_alert() -> None:
    """``alert_detector_check`` được nới dần qua nhiều migration; lấy bản mới nhất."""
    cho_phep: set[str] = set()
    for sql_file in sorted((ROOT / "db/init").glob("*.sql")):
        for m in re.finditer(r"CHECK \(detector IN \(([^)]*)\)\)", sql_file.read_text(encoding="utf-8")):
            cho_phep = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert DETECTOR in cho_phep, f"{DETECTOR!r} không nằm trong {sorted(cho_phep)}"


def test_typology_khop_bieu_thuc_cua_bang_alert() -> None:
    """Migration 048 nới sang T00–T10; T03 phải lọt."""
    assert re.fullmatch(r"T(0[0-9]|10)", TYPOLOGY)


def test_typology_co_nhan_tieng_viet_trong_tu_vung_nghiep_vu() -> None:
    from src.domain import TYPOLOGY_LABELS

    assert TYPOLOGY in TYPOLOGY_LABELS, "mã không có nhãn thì giao diện đổ mã thô ra màn hình"
    assert "vòng" in TYPOLOGY_LABELS[TYPOLOGY].lower()


def test_dataset_khop_nhan_hien_thi_cua_giao_dien() -> None:
    nhan = (ROOT / "web/src/api/format.ts").read_text(encoding="utf-8")
    assert f"{DATASET}:" in nhan, "bộ dữ liệu thiếu nhãn → hàng đợi hiện chuỗi kỹ thuật"


def test_nhan_detector_da_co_san_khong_can_sua_giao_dien() -> None:
    nhan = (ROOT / "web/src/api/format.ts").read_text(encoding="utf-8")
    assert re.search(rf"^\s+{DETECTOR}: \"", nhan, re.M), f"{DETECTOR!r} chưa có nhãn tiếng Việt"


# --- Mã cảnh báo --------------------------------------------------------------


def test_ma_canh_bao_on_dinh_va_co_tien_to_rieng() -> None:
    a = alert_id("16098:819190A40", "2022-09-29T00:00:00Z")
    assert a == alert_id("16098:819190A40", "2022-09-29T00:00:00Z"), "phải tất định"
    assert a.startswith("ALT-CYC-"), "tiền tố cho biết nhánh nào sinh ra"
    assert a != alert_id("16098:819190A40", "2022-09-30T00:00:00Z")


# --- Công thức chấm điểm ------------------------------------------------------


def test_trong_so_cong_lai_bang_mot() -> None:
    assert W_SPEED + W_COUNT + W_SHORT == pytest.approx(1.0)


def test_diem_luon_nam_trong_khoang_don_vi() -> None:
    for rank, c, ln in [(1.0, 99, 2), (0.0, 1, 13), (0.5, 0, 99), (1.0, 3, 1)]:
        assert 0.0 <= _diem(rank, c, ln) <= 1.0


def test_vong_khep_nhanh_hon_thi_diem_cao_hon() -> None:
    assert _diem(1.0, 1, 2) > _diem(0.5, 1, 2) > _diem(0.0, 1, 2)


def test_nhieu_chu_trinh_hon_thi_diem_cao_hon() -> None:
    assert _diem(0.5, 5, 4) > _diem(0.5, 2, 4) > _diem(0.5, 1, 4)


def test_vong_ngan_hon_thi_diem_cao_hon() -> None:
    assert _diem(0.5, 1, 2) > _diem(0.5, 1, 4) > _diem(0.5, 1, 6)


def test_so_vong_bao_hoa_khong_thuong_vo_han() -> None:
    """Một tài khoản nằm trên 50 vòng không được chiếm trọn đầu hàng đợi."""
    assert _diem(0.5, COUNT_SATURATION + 1, 4) == pytest.approx(_diem(0.5, 50, 4))


def test_toc_do_la_so_hang_nang_nhat() -> None:
    """Tốc độ là số đo DUY NHẤT hiện có biến thiên, nên phải nặng nhất."""
    assert W_SPEED > W_COUNT and W_SPEED > W_SHORT


def test_toc_do_dung_phan_vi_chu_khong_phai_moc_gio_cung() -> None:
    """Bản đầu đặt "nhanh tối đa = 6 giờ" và trung vị thật đúng bằng 6,01 giờ.

    Hậu quả đo được trên bản đang phục vụ: 15 cảnh báo đầu hàng đợi cùng điểm
    0,760, thứ tự ưu tiên rơi về so sánh chuỗi mã tài khoản. Phân vị trong lô
    tự hiệu chuẩn nên luôn phân biệt được, bất kể thang giờ của dữ liệu.
    """
    assert "percent_rank() OVER" in CELL_SQL
    assert "FAST_HOURS" not in CELL_SQL and "MAX_HOURS" not in CELL_SQL


def test_phan_vi_toc_do_luon_phan_biet_duoc_du_moi_vong_deu_nhanh() -> None:
    """Kể cả khi mọi chu trình khép dưới một giờ, thứ hạng vẫn trải đủ."""
    ranks = [i / 9 for i in range(10)]
    diem = [_diem(r, 1, 2) for r in ranks]
    assert len(set(diem)) == len(diem), "điểm bị trùng → hàng đợi mất thứ tự ưu tiên"


# --- Tham số dòng lệnh --------------------------------------------------------


def test_khong_mac_dinh_tro_vao_container_postgres_local() -> None:
    """Máy chủ đang phục vụ có một container postgres RỖNG; API đọc Cloud SQL.

    Vài script nạp cũ mặc định `docker exec fin07-postgres-1 psql -d
    fin07_hi_medium`. Chạy theo chúng thì lệnh kết thúc, in ra thành công, và
    hàng đợi thật không đổi một dòng nào. Script này phải đi theo DATABASE_URL.
    """
    args = parse_args([])
    assert not hasattr(args, "container"), "không được nối bằng docker exec"
    assert args.database_url is None, "mặc định phải lấy từ DATABASE_URL"
    assert args.dry_run is False and args.budget > 0
