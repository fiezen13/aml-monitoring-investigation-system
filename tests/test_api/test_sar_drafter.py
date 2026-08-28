"""Rào chắn cho phần AI soạn narrative của hồ sơ SAR.

Hồ sơ SAR là tài liệu gửi ra ngoài. Một câu như "tổng khối lượng giao dịch lên
tới hơn 5 tỷ đơn vị tiền tệ" vừa không có đơn vị, vừa là dấu hiệu mô hình đã
cộng gộp nhiều loại tiền — và câu đó đã từng lọt vào một bản PDF thật.
"""

from __future__ import annotations

from src.api.sar_drafter import _hides_currency


def test_bat_cau_ne_don_vi_tien() -> None:
    assert _hides_currency("Tổng khối lượng giao dịch lên tới hơn 5 tỷ đơn vị tiền tệ.")
    assert _hides_currency("Tài khoản đã chuyển đi 3 tỷ đơn vị.")


def test_cau_goi_dung_ten_loai_tien_thi_qua() -> None:
    assert not _hides_currency("Tài khoản nhận 12 068,26 Canadian Dollar từ 2 đối tác.")
    assert not _hides_currency("Dòng tiền ra đạt 5 230 310 869,72 Ruble trong 6 giao dịch.")


def test_khong_bat_nham_don_vi_khong_phai_tien() -> None:
    """"Đơn vị tính là ngày" nói về đơn vị đo, không phải tiền."""
    assert not _hides_currency("Đơn vị tính là ngày.")
