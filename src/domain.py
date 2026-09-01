"""Từ vựng nghiệp vụ dùng chung giữa API và worker.

Đặt ở một chỗ vì hai tiến trình phải đồng ý với nhau về cùng một máy trạng
thái. Trước đây worker biết chuỗi trạng thái còn API thì không, nên giao
diện không có cách nào hiển thị vụ việc đang ở đâu trong quy trình.

Nguồn: FIN-07-ARC-001 Hình 4 (máy trạng thái), FIN-07-BUS-001 (typology).
"""

# Nhãn typology T01–T10 dùng chung cho alert/case từ LI-Small.
TYPOLOGY_LABELS: dict[str, str] = {
    # Cảnh báo có căn cứ (điểm rủi ro + yếu tố đóng góp) nhưng hành vi quan sát
    # được chưa khớp mẫu hình có tên nào. Nói thẳng còn hơn gán bừa một nhóm.
    "T00": "Rủi ro theo mô hình — chưa khớp nhóm hành vi có tên",
    "T01": "Chia nhỏ giao dịch dưới ngưỡng báo cáo",
    "T02": "Tài khoản trung chuyển trong mạng lưới",
    "T03": "Giao dịch vòng quay lại chủ thể ban đầu",
    "T04": "Gom vào và toả ra bất thường",
    "T05": "Luân chuyển tốc độ cao",
    "T06": "Giao dịch với vùng tài phán rủi ro cao",
    "T07": "Sử dụng tài khoản người khác đứng tên",
    # T08 (Dòng tiền gắn tài sản ảo) đã gỡ: luật R03_VASP_EXPOSURE — nguồn duy
    # nhất sinh T08 — đọc cờ is_vasp do dự án tự bịa nên đã bỏ; không detector
    # nào còn phát T08. Giữ khoảng trống thay vì tái dùng mã cho nghĩa khác.
    "T09": "Thương mại quốc tế khai khống giá trị",
    "T10": "Dòng tiền không tương xứng hồ sơ khách hàng",
}


def typology_label(code: str) -> str:
    return TYPOLOGY_LABELS.get(code, code)


# Chuỗi vụ việc, rút còn những bước THẬT SỰ có người đẩy.
#
# Sáu bước cũ (TruyHoiBangChung, PhanTichDoThi, DoiChieuTrungPhatPEP,
# TinhToanBangCongCu, LapLuanGanTypology, KiemChungBangChung) đã gỡ ngày
# 27/08/2026: lối vào duy nhất của chúng là `POST /cases/{id}/investigate`, một
# endpoint không giao diện nào gọi. Chúng chưa từng có một vụ nào đi qua (đo
# trên production: 0 vụ, 0 dòng nhật ký) nhưng vẫn hiện trong nhật ký kiểm toán
# như những giai đoạn đã xảy ra — mô tả một quy trình không tồn tại.
#
# Hai bước còn lại là hai bước có người bấm thật: chuyên viên soạn hồ sơ, rồi
# nộp lên chờ duyệt. Chuỗi dừng ở ChoNguoiPheDuyet vì bước sau đó đòi một quyết
# định có người ký tên, nằm ở tầng phê duyệt chứ không phải vòng lặp tự động.
INVESTIGATION_CHAIN: tuple[str, ...] = (
    "TiepNhanCanhBao",
    "SoanHoSoNghiVan",
    "ChoNguoiPheDuyet",
)

# Trạng thái kết thúc, đạt được bằng quyết định của con người chứ không phải
# bằng bước tiếp theo của máy.
TERMINAL_STATES: frozenset[str] = frozenset({"XuatHoSo", "DongKhongBaoCao", "DieuTraBoSung"})

CASE_STATE_LABELS: dict[str, str] = {
    "TiepNhanCanhBao": "Tiếp nhận cảnh báo",
    "SoanHoSoNghiVan": "Soạn hồ sơ nghi vấn",
    "ChoNguoiPheDuyet": "Chờ người phê duyệt",
    "DieuTraBoSung": "Điều tra bổ sung",
    "XuatHoSo": "Xuất hồ sơ",
    "DongKhongBaoCao": "Đóng, không báo cáo",
}


def state_label(state: str) -> str:
    return CASE_STATE_LABELS.get(state, state)


def next_state(current: str) -> str | None:
    """Bước hợp lệ kế tiếp trên chuỗi điều tra, hoặc None nếu đã hết.

    Trả None ở ChoNguoiPheDuyet và ở mọi trạng thái kết thúc — cả hai đều
    cần con người quyết định, không phải một lượt chạy của worker.
    """
    try:
        index = INVESTIGATION_CHAIN.index(current)
    except ValueError:
        return None
    if index + 1 >= len(INVESTIGATION_CHAIN):
        return None
    return INVESTIGATION_CHAIN[index + 1]
