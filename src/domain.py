"""Từ vựng nghiệp vụ dùng chung giữa API và worker.

Đặt ở một chỗ vì hai tiến trình phải đồng ý với nhau về cùng một máy trạng
thái. Trước đây worker biết chuỗi trạng thái còn API thì không, nên giao
diện không có cách nào hiển thị vụ việc đang ở đâu trong quy trình.

Nguồn: FIN-07-ARC-001 Hình 4 (máy trạng thái), FIN-07-BUS-001 (typology).
"""

# Nhãn typology T01–T10 dùng chung cho alert/case từ LI-Small.
TYPOLOGY_LABELS: dict[str, str] = {
    "T01": "Chia nhỏ giao dịch dưới ngưỡng báo cáo",
    "T02": "Tài khoản trung chuyển trong mạng lưới",
    "T03": "Giao dịch vòng quay lại chủ thể ban đầu",
    "T04": "Gom vào và toả ra bất thường",
    "T05": "Luân chuyển tốc độ cao",
    "T06": "Giao dịch với vùng tài phán rủi ro cao",
    "T07": "Sử dụng tài khoản người khác đứng tên",
    "T08": "Dòng tiền gắn tài sản ảo",
    "T09": "Thương mại quốc tế khai khống giá trị",
    "T10": "Dòng tiền không tương xứng hồ sơ khách hàng",
}


def typology_label(code: str) -> str:
    return TYPOLOGY_LABELS.get(code, code)


# Chuỗi điều tra tuyến tính: mỗi bước là một lần worker chạy. Dừng ở
# ChoNguoiPheDuyet — đó là điểm bàn giao cho con người. Không có cung nào từ
# đây đi thẳng tới XuatHoSo bằng máy: NT3 đòi một quyết định có người ký tên,
# và cung đó nằm ở tầng phê duyệt, không nằm trong vòng lặp tự động.
INVESTIGATION_CHAIN: tuple[str, ...] = (
    "TiepNhanCanhBao",
    "TruyHoiBangChung",
    "PhanTichDoThi",
    "DoiChieuTrungPhatPEP",
    "TinhToanBangCongCu",
    "LapLuanGanTypology",
    "SoanHoSoNghiVan",
    "KiemChungBangChung",
    "ChoNguoiPheDuyet",
)

# Trạng thái kết thúc, đạt được bằng quyết định của con người chứ không phải
# bằng bước tiếp theo của máy.
TERMINAL_STATES: frozenset[str] = frozenset({"XuatHoSo", "DongKhongBaoCao", "DieuTraBoSung"})

CASE_STATE_LABELS: dict[str, str] = {
    "TiepNhanCanhBao": "Tiếp nhận cảnh báo",
    "TruyHoiBangChung": "Truy hồi bằng chứng",
    "PhanTichDoThi": "Phân tích đồ thị",
    "DoiChieuTrungPhatPEP": "Đối chiếu trừng phạt / PEP",
    "TinhToanBangCongCu": "Tính toán bằng công cụ",
    "LapLuanGanTypology": "Lập luận gán typology",
    "SoanHoSoNghiVan": "Soạn hồ sơ nghi vấn",
    "KiemChungBangChung": "Kiểm chứng bằng chứng",
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
