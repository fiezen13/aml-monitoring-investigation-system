"""MEGA-PNA phụ thuộc torch và torch-geometric — không cài trong CI.

Hai thư viện ấy nặng gần một gigabyte và chỉ phục vụ một nhánh mô hình đồ thị
ngoại tuyến; bắt mỗi lượt CI tải chúng về sẽ kéo dài mọi pull request vì một
phần mã mà thay đổi hằng ngày không đụng tới.

Nên bỏ qua cả thư mục khi thiếu thư viện, thay vì để pytest hỏng ở bước thu
thập. Trên máy có cài đủ thì bộ test vẫn chạy bình thường — đó là chỗ nhánh
MEGA-PNA thực sự được kiểm chứng.
"""

from importlib.util import find_spec

_AVAILABLE = find_spec("torch") is not None and find_spec("torch_geometric") is not None

collect_ignore_glob = [] if _AVAILABLE else ["test_*.py"]
