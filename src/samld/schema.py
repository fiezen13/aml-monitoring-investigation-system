"""Lược đồ canonical cho nhánh SAML-D và HÀNG RÀO chống rò rỉ nhãn.

SAML-D là dataset tổng hợp về AML ngân hàng có yếu tố xuyên biên giới. File thô
dùng tên cột riêng; ở đây quy về một lược đồ nội bộ ổn định để phần còn lại của
nhánh không phụ thuộc tên cột gốc.

RÒ RỈ NHÃN — quy tắc sống còn
-----------------------------
``Is_laundering`` là NHÃN nhị phân (ground truth). ``Laundering_type`` là NHÃN
typology (ground truth). Cả hai TUYỆT ĐỐI không được nằm trong đặc trưng đầu vào
của model. ``Laundering_type`` chỉ dùng cho đánh giá / phân tích / chọn ca demo
/ (tùy chọn) một bộ phân loại typology huấn luyện RIÊNG — không bao giờ ở
inference của bộ phát hiện.

``EDGE_FEATURE_COLUMNS`` và ``NODE_FEATURE_SOURCES`` được kiểm bằng test tự động
(``tests/test_samld/test_leakage.py``) để chắc chắn không lọt nhãn.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Ánh xạ cột thô SAML-D → tên canonical. Chỉ những cột này được đọc.
RAW_TO_CANONICAL: dict[str, str] = {
    "Time": "time",
    "Date": "date",
    "Sender_account": "sender_account",
    "Receiver_account": "receiver_account",
    "Amount": "amount",
    "Payment_currency": "payment_currency",
    "Received_currency": "received_currency",
    "Sender_bank_location": "sender_country",
    "Receiver_bank_location": "receiver_country",
    "Payment_type": "payment_type",
    "Is_laundering": "label",
    "Laundering_type": "typology",
}

#: Cột NHÃN — không bao giờ được là đặc trưng.
LABEL_COLUMN = "label"
TYPOLOGY_COLUMN = "typology"
FORBIDDEN_IN_FEATURES = frozenset({LABEL_COLUMN, TYPOLOGY_COLUMN, "Is_laundering", "Laundering_type"})

#: Định danh node của đồ thị: TÀI KHOẢN (không phải quốc gia).
SENDER_NODE = "sender_account"
RECEIVER_NODE = "receiver_account"

#: Đặc trưng CẠNH (một giao dịch). Chỉ đặc trưng hợp lệ, KHÔNG có nhãn.
#: Country là thuộc tính ngữ cảnh của cạnh — mã hoá categorical, KHÔNG phải nhãn
#: rủi ro FATF. Không có danh sách quốc gia rủi ro cứng ở bất kỳ đâu.
NUMERIC_EDGE_FEATURES: tuple[str, ...] = (
    "amount_log",  # log1p(amount) chuẩn hoá
    "hour",
    "day_of_week",
    "day_of_month",
    "elapsed_days",  # số ngày kể từ mốc đầu dataset
)
BINARY_EDGE_FEATURES: tuple[str, ...] = (
    "cross_border",  # sender_country != receiver_country — NGỮ CẢNH, không phải nhãn
    "currency_mismatch",  # payment_currency != received_currency
)
CATEGORICAL_EDGE_FEATURES: tuple[str, ...] = (
    "payment_type",
    "payment_currency",
    "received_currency",
    "sender_country",
    "receiver_country",
)

#: Toàn bộ cột dùng để DẪN XUẤT đặc trưng cạnh (trước khi encode). Không gồm nhãn.
EDGE_FEATURE_SOURCE_COLUMNS: tuple[str, ...] = NUMERIC_EDGE_FEATURES + BINARY_EDGE_FEATURES + CATEGORICAL_EDGE_FEATURES


@dataclass(frozen=True)
class CanonicalColumns:
    """Tên cột canonical, gom một chỗ để tránh gõ tay chuỗi rải rác."""

    time = "time"
    date = "date"
    timestamp = "timestamp"
    sender_account = "sender_account"
    receiver_account = "receiver_account"
    amount = "amount"
    payment_currency = "payment_currency"
    received_currency = "received_currency"
    sender_country = "sender_country"
    receiver_country = "receiver_country"
    payment_type = "payment_type"
    label = "label"
    typology = "typology"


COLS = CanonicalColumns()


def assert_no_label_leakage(feature_names: list[str]) -> None:
    """Ném lỗi nếu bất kỳ tên đặc trưng nào trùng cột nhãn.

    Gọi ở mọi nơi dựng ma trận đặc trưng — hàng rào cuối cùng chống rò rỉ.
    """
    leaked = FORBIDDEN_IN_FEATURES.intersection(feature_names)
    if leaked:
        raise ValueError(
            f"RÒ RỈ NHÃN: các cột nhãn {sorted(leaked)} xuất hiện trong đặc trưng đầu vào. "
            "Is_laundering/Laundering_type chỉ được dùng cho đánh giá, không phải đặc trưng."
        )
