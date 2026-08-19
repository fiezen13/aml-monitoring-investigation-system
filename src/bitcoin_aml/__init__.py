"""Nhánh phát hiện rửa tiền Bitcoin trên bộ dữ liệu Elliptic++.

Nhánh này ĐỘC LẬP hoàn toàn với hai nhánh còn lại (IBM HI-Medium, SAML-D). Không
gộp giao dịch, không hợp nhất điểm, không đưa vào một classifier chung — mỗi
nhánh đánh giá riêng và tác tử nhận từng kết quả dưới dạng bằng chứng có cấu
trúc. Xem docs ``src/bitcoin_aml/README.md``.

Tham chiếu: Youssef Elmougy, Ling Liu, "Demystifying Fraudulent Transactions and
Illicit Nodes in the Bitcoin Network for Financial Forensics", ACM SIGKDD 2023,
DOI 10.1145/3580305.3599803. Repo: https://github.com/git-disl/EllipticPlusPlus
"""

from src.bitcoin_aml.config import BitcoinAmlConfig, get_bitcoin_config

__all__ = ["BitcoinAmlConfig", "get_bitcoin_config"]
