"""Nhánh phát hiện rửa tiền Bitcoin trên bộ dữ liệu Elliptic gốc.

Nhánh này ĐỘC LẬP hoàn toàn với hai nhánh còn lại (IBM HI-Medium, SAML-D). Không
gộp giao dịch, không hợp nhất điểm, không đưa vào một classifier chung — mỗi
nhánh đánh giá riêng và tác tử nhận từng kết quả dưới dạng bằng chứng có cấu
trúc.

Phục vụ (serving): bảng ``bitcoin_scored_tx`` do ``scripts/build_elliptic_scored.py``
nạp từ tập Elliptic gốc (``data/raw/elliptic/``) + mô hình Random Forest
trong ``data/models/bitcoin_elliptic/``. Giải thích on-demand dùng
``src/bitcoin_aml/agent.py``; ngữ nghĩa đặc trưng phục hồi 151/166 nằm ở
``elliptic_registry.py`` (nguồn DFRWS 2026 companion). Không import ở đây để tránh
kéo phụ thuộc nặng vào lúc nạp gói — dùng chỗ nào import trực tiếp chỗ đó.

Tham chiếu tập dữ liệu: Weber et al., "Anti-Money Laundering in Bitcoin",
KDD 2019 (Elliptic). Ngữ nghĩa phục hồi: Šafář et al., DFRWS EU 2026
(nesfit/DeanonymizedEllipticBitcoinDataset).
"""
