# FIN-07 — Kế hoạch triển khai MEGA-PNA

Kế hoạch dựng lại nhánh dự đoán chính của FIN-07 theo đúng giao thức của bài
báo, dùng MEGA-PNA làm model chủ lực.

## Vì sao chọn MEGA-PNA

Kết quả đã công bố, F1 lớp thiểu số, trên đúng bộ dữ liệu mình dùng:

| Model | HI-Small | HI-Medium | LI-Small | LI-Medium |
|---|---|---|---|---|
| Multi-GIN | 64,79 | 58,92 | 26,88 | 16,30 |
| Multi-PNA | 68,16 | 66,48 | 33,07 | 36,07 |
| MEGA-GIN | 70,83 | 68,83 | 43,66 | 39,03 |
| **MEGA-PNA** | **74,01 ± 1,55** | **78,26 ± 0,11** | **45,07 ± 2,26** | **49,40 ± 0,54** |

Đối chiếu các hướng khác trên HI-Medium: LightGBM + GFP 59,48 — PNA thường
59,71 — FraudGT 62,3 — mô hình cây của FIN-07 hiện tại ~68.

MEGA-PNA hơn phương án tốt thứ hai khoảng 9 điểm, và độ lệch chuẩn trên
HI-Medium chỉ 0,11 — rất ổn định, nên dễ biết mình thiết lập đúng hay sai.

Nguồn: Bilgi và cộng sự, *Multigraph Message Passing with Bi-Directional
Multi-Edge Aggregations* ([arXiv:2412.00241](https://arxiv.org/abs/2412.00241)),
mã nguồn tại [github.com/hcagri/MEGA-GNN](https://github.com/hcagri/MEGA-GNN).

## Vai trò trong kiến trúc

MEGA-PNA **không thay thế** những gì đã có. Mỗi lớp làm đúng việc nó mạnh nhất:

| Lớp | Thành phần | Chỉ số đánh giá |
|---|---|---|
| Dự đoán chính | **MEGA-PNA** | PR-AUC, recall/precision tại ngân sách |
| Dự đoán bổ trợ | GFP + XGBoost | So sánh và hợp nhất |
| Bằng chứng | Rule Engine + Graph Detector | **Tỷ lệ cảnh báo gắn được typology** |
| Novelty | Isolation Forest | **Số ca bắt thêm mà lớp dự đoán bỏ qua** |

Không chấm lớp bằng chứng bằng F1. Graph Detector bắn rộng là **ưu điểm** ở vai
trò giải thích, dù precision của nó rất thấp khi coi là bộ phân loại.

---

## Giai đoạn 0 — Chốt hợp đồng dữ liệu

Dùng `format_kaggle_files.py` của họ, **không sửa gì**.

```bash
python format_kaggle_files.py /path/to/HI-Small_Trans.csv
```

Đầu ra là `formatted_transactions.csv` với 10 cột:

```
EdgeID, from_id, to_id, Timestamp, Amount Sent, Sent Currency,
Amount Received, Received Currency, Payment Format, Is Laundering
```

### Bốn khác biệt so với đường ống FIN-07 hiện tại

| | Bài báo | FIN-07 hiện tại |
|---|---|---|
| Giao dịch tự chuyển | Giữ | Loại (2,56 triệu = 8%) |
| Số 0 đầu mã ngân hàng | Giữ nguyên | Bỏ đi |
| Loại tiền | Giữ nguyên, mã tiền tệ là đặc trưng | Quy đổi hết về USD |
| Payment Format | Dùng làm đặc trưng | Dùng (nhưng EDA nhóm cấm) |

**Quyết định: tách làm hai đường.**

- **Đường học thuật** — theo đúng bài báo, để so sánh được
- **Đường sản xuất** — giữ tiền xử lý của FIN-07, vì có lý do nghiệp vụ

Hai con số khác nhau là bình thường, miễn ghi rõ con số nào thuộc đường nào.

### Riêng Payment Format

EDA của nhóm cấm đặc trưng này (`docs/ml/FIN-07-ML-002` §5.4). Đo lại trên
HI-Medium: lift **7,55×**, 87,25% ca rửa tiền đi qua ACH, kênh WIRE không có
ca nào.

Không bỏ nó ở đường học thuật (bài báo có dùng), nhưng **bắt buộc chạy thêm một
lượt bỏ nó** để biết model đang vay bao nhiêu. Nếu bỏ đi mà điểm sập thì model
chủ yếu đang học "giao dịch này là ACH", không phải học rửa tiền.

---

## Giai đoạn 1 — Tái lập trên bộ nhỏ (CỔNG CHẶN)

**Đây là bước quan trọng nhất và hay bị bỏ qua nhất.**

Mục tiêu không phải điểm cao, mà là **chứng minh thiết lập đúng**. Không tái lập
được con số đã công bố trên bộ nhỏ thì mọi con số trên bộ lớn đều không kiểm
chứng được.

### Dữ liệu cần

| Bộ | Trạng thái | Mục tiêu |
|---|---|---|
| LI-Small | **Đã có** trong repo | 45,07 ± 2,26 |
| HI-Small | **Cần tải** (~450 MB) | 74,01 ± 1,55 |

```bash
./scripts/aml/download_dataset.sh HI-Small_Trans.csv
```

Cần khoá Kaggle ở `~/.kaggle/kaggle.json`, hoặc tải tay rồi đặt vào
`data/raw/ibm-aml/`. Thư mục này nằm trong `.gitignore` nên không bị commit.

### Lệnh huấn luyện

```bash
python main.py --data Small_HI --model pna \
  --emlps --reverse_mp --ego --flatten_edges \
  --edge_agg_type pna --n_epochs 80 --save_model --task edge_class
```

Ba cờ đầu là đóng góp của bài AAAI 2024 (truyền thông điệp ngược, ego ID),
`--flatten_edges` và `--edge_agg_type pna` là đóng góp riêng của MEGA — gộp các
cạnh song song trước, rồi mới gộp theo đỉnh.

### Tiêu chí qua cổng

```
Khớp cả HI-Small VÀ LI-Small trong khoảng ± độ lệch chuẩn
    → thiết lập đúng, đi tiếp

Khớp một bộ, lệch bộ kia
    → có vấn đề phụ thuộc tỷ lệ ca bẩn, phải tìm ra trước khi đi tiếp

Lệch cả hai
    → DỪNG. Không chạy HI-Medium.
```

Chạy 5 seed để so được với độ lệch chuẩn họ công bố.

---

## Giai đoạn 2 — Mở rộng sang HI-Medium

Chỉ làm sau khi qua cổng ở Giai đoạn 1.

```bash
python format_kaggle_files.py data/raw/ibm-aml/HI-Medium_Trans.csv

python main.py --data Medium_HI --model pna \
  --emlps --reverse_mp --ego --flatten_edges \
  --edge_agg_type pna --n_epochs 80 --save_model --task edge_class
```

Mục tiêu: **78,26 ± 0,11**.

### Quy mô

| | HI-Small | HI-Medium |
|---|---|---|
| Giao dịch | ~5 triệu | **31,9 triệu** |
| Tài khoản | ~500 nghìn | **2,09 triệu** |

### Bộ nhớ

Rủi ro tràn GPU **đã được giải quyết**: MEGA-GNN dùng neighbor sampling — lấy
hàng xóm 2 bước, mỗi bước 100 hàng xóm. Không nạp toàn đồ thị.

Bài báo đo thông lượng trên **RTX 4090, 24 GB**.

---

## Giai đoạn 3 — Phần FIN-07 đóng góp thêm

Cả năm bài báo đều dừng ở F1 mức giao dịch. Không bài nào báo cáo ba thứ sau,
và đây là chỗ dự án vượt lên trên việc chạy lại code người khác.

### 3.1. Recall ở mức đường dây

`scripts/evaluate_ring_level.py` đã có sẵn, chỉ cần trỏ vào điểm số của
MEGA-PNA thay vì của mô hình cây.

Đo trên LI-Small với mô hình cây hiện tại cho thấy khoảng cách rất lớn:

| Cảnh báo | Recall giao dịch | **Recall đường dây** |
|---|---|---|
| 1.000 | 26,0% | **76,8%** |
| 5.000 | 39,6% | **89,3%** |

Một đường dây có nhiều giao dịch; bắt trúng một là mở được hồ sơ. Đo theo giao
dịch đang tự làm xấu kết quả so với giá trị nghiệp vụ thật.

### 3.2. Khối lượng công việc mỗi ngày

Quy đổi ngân sách cảnh báo ra số hồ sơ điều tra viên phải duyệt mỗi ngày, và số
người cần thiết. Đây là con số để ra quyết định vận hành, không phải F1.

### 3.3. Tỷ lệ gắn được bằng chứng

Trong các cảnh báo MEGA-PNA đưa lên, bao nhiêu phần trăm gắn được một typology
có tên và một đồ thị con để điều tra viên đọc. Đây là chỉ số của lớp bằng chứng.

---

## Giai đoạn 4 — Hợp nhất

Sau khi có MEGA-PNA và mô hình cây trên **cùng dữ liệu đã format**:

1. So sánh hai model trên cùng tập test
2. Thử hợp nhất điểm số, chọn trọng số **trên validation**
3. Ablation: mỗi thành phần đóng góp bao nhiêu
4. Lắp lớp bằng chứng và lớp novelty

---

## Môi trường

### Cục bộ (đã kiểm chứng)

Cả bốn gói đều có wheel cho Python 3.14 trên arm64:

```
torch           2.13.0   cp314 native
torch-geometric 2.8.0    pure python
xgboost         3.4.0    macos arm64
lightgbm        4.7.0    macos arm64
```

Máy M3 Pro có MPS backend. Dùng để phát triển và chạy thử bộ nhỏ.

Lưu ý: repo MEGA-GNN pin PyTorch 2.2.2 + CUDA 11.8. Bản mới hơn có thể cần
chỉnh nhẹ, và MPS không phải CUDA nên một số phép có thể rơi về CPU.

### GCP

| Phương án | VRAM | Dùng khi |
|---|---|---|
| **L4** | 24 GB | Mặc định — bằng RTX 4090 họ dùng |
| A100 40GB | 40 GB | Chỉ khi L4 tràn ở Giai đoạn 2 |

Bắt đầu bằng L4. Đừng thuê A100 trước khi biết có cần không.

Chưa kiểm tra giá hiện tại, cần xem lại trên trang GCP.

---

## Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Không tái lập được số công bố | Cổng chặn ở Giai đoạn 1, dừng trước khi tốn tiền |
| Phiên bản PyTorch lệch với repo | Thử bản họ pin trước, nâng cấp sau |
| HI-Medium tràn VRAM trên L4 | Giảm số hàng xóm mỗi bước, hoặc nâng A100 |
| Model chủ yếu học "ACH" | Bắt buộc chạy lượt bỏ Payment Format |
| Hai đường tiền xử lý bị lẫn | Ghi rõ trong mọi báo cáo con số thuộc đường nào |

---

## Thứ tự thực hiện

```
0. Tải HI-Small                              (~450 MB)
1. Dựng môi trường, clone MEGA-GNN
2. format_kaggle_files.py trên HI-Small + LI-Small
3. Tái lập MEGA-PNA, 5 seed, cả hai bộ       ← CỔNG CHẶN
4. format_kaggle_files.py trên HI-Medium
5. Huấn luyện MEGA-PNA trên HI-Medium
6. Chạy lại mô hình cây trên cùng dữ liệu
7. Đo mức đường dây và khối lượng vận hành
8. Hợp nhất, ablation, lắp lớp bằng chứng
```

Bước 3 là điểm quyết định. Mọi thứ sau đó chỉ có nghĩa nếu bước 3 qua.
