# Làm lại phần model — kế hoạch cho cả nhóm

Tài liệu này trả lời một câu: **nên dựng lại tầng phát hiện như thế nào cho đúng
với cách những nhóm giỏi nhất làm trên chính bộ dữ liệu này.**

Đọc hết mất khoảng 15 phút. Mọi con số đều dẫn nguồn: hoặc từ hai bài báo bên
dưới, hoặc từ chính hệ thống đang chạy.

---

## 1. Kết luận trong hai phút

Kiến trúc hiện tại là **ba nhánh phát hiện rồi cộng điểm có trọng số**. Không
nhóm nghiên cứu nào làm vậy trên bộ dữ liệu này. Cả lĩnh vực dùng **một mô hình
phân loại cạnh duy nhất**, và biến mẫu hình rửa tiền thành **đặc trưng đầu vào**
chứ không phải bộ phát hiện riêng.

Tin tốt: **thứ tốt nhất chúng ta đang có lại đúng hướng đó.** Mô hình
currency-native edge đạt F1 30,2%, ngang tầm SOTA — và nó **đã sẵn** sáu đặc
trưng đồ thị. Việc cần làm không phải viết lại từ đầu, mà là **bỏ hai nhánh vô
giá trị và đổ toàn bộ công sức vào mô hình đang thắng**.

| | Bây giờ | Sau khi làm lại |
|---|---|---|
| Số mô hình chấm điểm | 3 nhánh + 1 bước hợp nhất | **1** |
| Mẫu hình rửa tiền | một nhánh phát hiện riêng | **đặc trưng của mô hình** |
| Luật nghiệp vụ | góp vào điểm rủi ro | **chỉ để giải thích, không chấm điểm** |
| Isolation Forest | có, trọng số 0,00 | **bỏ** |

---

## 2. Nguồn tham khảo

| Bài | Vai trò |
|---|---|
| Altman, Blanuša, von Niederhäusern, Egressy, Anghel, Atasu — *Realistic Synthetic Financial Transactions for AML Models*, **NeurIPS 2023** ([arXiv:2306.16424](https://arxiv.org/abs/2306.16424)) | Bài **tạo ra chính bộ dữ liệu ta đang dùng**. Định nghĩa baseline chuẩn. |
| Egressy, von Niederhäusern, Blanuša, Altman, Wattenhofer, Atasu — *Provably Powerful GNNs for Directed Multigraphs*, **AAAI 2024** ([arXiv:2306.11586](https://arxiv.org/abs/2306.11586), mã nguồn [IBM/Multi-GNN](https://github.com/IBM/Multi-GNN)) | Kết quả tốt nhất hiện nay trên bộ này. |

---

## 3. Bảng chuẩn trên LI-Small

F1 của **lớp thiểu số** — không dùng accuracy, vì tỷ lệ dương chỉ 0,068%.

| Mô hình | F1 (%) | Loại kiến trúc |
|---|---|---|
| GIN | 7,90 | GNN chuẩn |
| PNA | 14,85 | GNN chuẩn |
| GIN+EU | 20,62 | GNN + cập nhật cạnh |
| GFP + LightGBM | 20,83 | **đặc trưng đồ thị + cây** |
| Multi-GIN | 22,12 | GNN đa đồ thị |
| Multi-GIN+EU | 26,88 | GNN đa đồ thị |
| **GFP + XGBoost** | **27,30** | **đặc trưng đồ thị + cây** |
| **Multi-PNA** | **30,65** | GNN đa đồ thị |
| **Multi-PNA+EU** | **33,07** | GNN đa đồ thị — tốt nhất |

**Mô hình edge của chúng ta: 30,2%** (seed chính; trung bình 5 seed 29,7% ± 1,3).

> ⚠️ Không so trực tiếp được: chúng ta tự chia train/val/test theo thời gian, bài
> báo dùng split của họ. Nhưng con số nằm **đúng trong dải SOTA**, không phải
> ngoài lề. Muốn so nghiêm túc thì phải chạy trên đúng split của họ — xem mục 8.

---

## 4. Ba sự thật quyết định thiết kế

### 4.1 Không ai dùng luật tay, mô hình bất thường, hay hợp nhất trọng số

Đọc hết bảng baseline: **không một dòng nào** là luật nghiệp vụ viết tay,
Isolation Forest, hay bất kỳ kiểu cộng điểm nhiều nhánh nào. Toàn bộ là *một*
mô hình học từ dữ liệu.

### 4.2 Mẫu hình là ĐẶC TRƯNG, không phải bộ phát hiện

IBM Graph Feature Preprocessor tính sẵn scatter-gather, chu trình thời gian, chu
trình đơn **dài tới 10**, và thống kê đỉnh — rồi **gắn thêm vào chính bảng đặc
trưng của giao dịch** để XGBoost học.

Cấu hình họ dùng, chép lại để làm theo:

| Tham số | Giá trị |
|---|---|
| Cửa sổ scatter-gather | **6 giờ** |
| Cửa sổ cho phần còn lại | **1 ngày** |
| Độ dài chu trình đơn | tới **10** |
| Kích thước lô | 128 |
| Thứ tự xử lý | **tăng dần theo thời gian** — để đặc trưng chỉ dùng dữ liệu quá khứ |

Dòng cuối là chống rò rỉ dữ liệu, không phải chi tiết kỹ thuật vặt.

### 4.3 71% giao dịch rửa tiền trong LI-Small KHÔNG thuộc mẫu hình nào

Trích nguyên văn phụ lục bài AAAI:

> *"...low aggregate minority class F1 scores for Small LI where **71% of the
> laundering transactions are not part of laundering patterns**. The equivalent
> value for Small HI is only 38%."*

Đây là con số quan trọng nhất trong cả tài liệu này. Nó nói rằng:

- Một hệ thống **chỉ** đi tìm 8 mẫu hình có trần cứng khoảng **29%** số giao
  dịch rửa tiền. Không cách nào vượt qua.
- Vì vậy nhánh đồ thị **không thể** là trụ cột. Nó là *một nguồn đặc trưng tốt*.
- Và nó giải thích vì sao mọi mô hình đều chật vật trên LI-Small (tốt nhất 33%)
  trong khi HI-Small lên tới 68%.

---

## 5. Kiến trúc hiện tại — và chỗ sai

```mermaid
flowchart TD
    TX["Giao dịch<br/>6,1 triệu"]

    RULE["<b>Nhánh luật</b><br/>R01 + R02<br/>F1 0,0127"]
    ML["<b>Isolation Forest</b><br/>F1 0,0159"]
    GRAPH["<b>Nhánh đồ thị</b><br/>3 trong 8 mẫu hình<br/>F1 0,1338"]
    EDGE["<b>Mô hình edge</b><br/>37 đặc trưng · HistGB<br/><b>F1 0,302</b>"]

    FUSE["<b>Hợp nhất trọng số</b><br/>luật 0,55 · IF 0,00 · đồ thị 0,45<br/>F1 0,1365"]
    ALERT["Cảnh báo"]
    UI["Điểm hiển thị<br/>trên giao diện"]

    TX --> RULE --> FUSE
    TX --> ML --> FUSE
    TX --> GRAPH --> FUSE
    FUSE --> ALERT
    TX --> EDGE --> UI

    style ML stroke-dasharray: 5 5
    style FUSE stroke-dasharray: 5 5
```

Bốn vấn đề, đọc thẳng từ sơ đồ:

1. **Mô hình tốt nhất nằm ngoài luồng hợp nhất.** Edge F1 0,302 chỉ dùng để hiển
   thị; nó không tham gia sinh cảnh báo.
2. **Bước hợp nhất gần như vô ích.** 0,1365 so với 0,1338 của riêng nhánh đồ thị
   — hơn 0,0027, mà PR-AUC lại *tệ hơn* (0,0790 so với 0,0841).
3. **Isolation Forest nhận trọng số 0,00.** Cả 8 tổ hợp trọng số tốt nhất đều
   cho nó bằng 0. Tổ hợp tốt nhất *có* dùng nó kém 0,0095 F1.
4. **Ba nhánh cùng nhìn một dữ liệu bằng ba cách rời rạc,** rồi cộng lại — thay
   vì để một mô hình học cách kết hợp.

---

## 6. Kiến trúc đích

```mermaid
flowchart TD
    TX["<b>Giao dịch</b><br/>thời điểm · ngân hàng · tài khoản<br/>số tiền · loại tiền · hình thức"]

    F1G["<b>Đặc trưng cơ bản</b><br/>giữ nguyên loại tiền gốc<br/>chuẩn hoá log1p z-score theo từng tiền tệ"]
    F2G["<b>Đặc trưng đồ thị</b><br/>fan-in · fan-out · scatter-gather<br/>chu trình tới độ dài 10 · thống kê đỉnh"]

    MODEL["<b>Một mô hình phân loại cạnh</b><br/>HistGradientBoosting"]
    SCORE["<b>Điểm rủi ro từng giao dịch</b>"]
    ALERT["<b>Cảnh báo</b><br/>xếp hạng theo điểm"]
    RULES["<b>Luật R01 · R02</b><br/>gắn nhãn giải thích<br/><i>không chấm điểm</i>"]

    TX --> F1G --> MODEL
    TX --> F2G --> MODEL
    MODEL --> SCORE --> ALERT
    TX --> RULES -.->|"chú giải cho chuyên viên"| ALERT

    style RULES stroke-dasharray: 5 5
```

Ba thay đổi so với hiện tại:

- **Một mô hình, một điểm.** Không còn bước hợp nhất, không còn trọng số phải
  giải thích.
- **Mẫu hình đi vào làm đặc trưng.** Nhánh đồ thị đổi vai từ *bộ phát hiện* sang
  *bộ sinh đặc trưng*.
- **Luật tách khỏi điểm số.** Chúng vẫn chạy, vẫn gắn nhãn "vi phạm quy tắc nào"
  — thứ mà cây tăng cường không cho được. Nhưng không góp vào điểm.

---

## 7. Chúng ta đã có sẵn những gì

Đây là phần đáng mừng: **phần lớn đã có rồi.**

| Cần gì | Đã có chưa | Ở đâu |
|---|---|---|
| Mô hình phân loại cạnh | ✅ HistGB, 37 đặc trưng, F1 0,302 | `scripts/train_currency_native_edge.py` |
| Chuẩn hoá theo từng loại tiền, chỉ fit trên train | ✅ | cùng file |
| Chia tập theo thời gian, không ngẫu nhiên | ✅ train 3,67M / val 1,22M / test 1,22M | `reports/edge-benchmark/li_small_currency_native_policy_v1.json` |
| fan-in, fan-out | ✅ `fan_in_b`, `fan_out_a` | `scripts/benchmark_edge_level.py` |
| scatter-gather | ✅ `gather_scatter_a`, `gather_scatter_b` | cùng file |
| Chu trình | ⚠️ mới `n_2cycle`, `n_3cycle` | cùng file |
| Chu trình tới độ dài 10 | ❌ **thiếu** | — |
| Chu trình theo thời gian | ❌ **thiếu** | — |
| Cửa sổ 6 giờ cho scatter-gather | ❌ **thiếu** — hiện dùng 24 giờ | — |
| Thống kê đỉnh phong phú | ⚠️ một phần | `src/data/graph_features.py` |
| Chấm điểm toàn bộ 6,1 triệu giao dịch | ✅ | `scripts/score_currency_native_edge.py` |
| Sổ phát hành có mã băm, chống sửa lén | ✅ | bảng `edge_model_release` |

**Nói cách khác: kiến trúc đích đã làm được khoảng 70%.** Việc còn lại chủ yếu là
bổ sung đặc trưng đồ thị còn thiếu và bỏ hai nhánh thừa.

---

## 8. Kế hoạch bốn giai đoạn

### Giai đoạn 1 — Chốt mốc so sánh (nửa ngày)

Không sửa gì cả. Chỉ đo lại để có mốc trung thực.

**Làm gì**
- Chạy lại `scripts/train_currency_native_edge.py` với đúng 5 seed, ghi lại F1
  từng seed và độ lệch chuẩn.
- Ghi rõ số giao dịch, số nhãn dương, và mốc cắt của từng tập vào báo cáo.

**Xong khi** có một con số duy nhất, tái lập được, để mọi thay đổi sau so vào.
Hiện là **F1 0,2969 ± 0,0131**.

### Giai đoạn 2 — Bổ sung đặc trưng đồ thị (2–3 ngày)

Đây là phần mang lại nhiều nhất.

**Làm gì** — thêm vào `scripts/benchmark_edge_level.py`, theo đúng cấu hình mục 4.2:

| Đặc trưng mới | Ghi chú |
|---|---|
| Chu trình đơn độ dài 4–10 | hiện mới có 2 và 3 |
| Chu trình theo thời gian | chu trình mà thứ tự thời gian đi đúng chiều |
| scatter-gather cửa sổ **6 giờ** | hiện dùng 24 giờ |
| Thống kê đỉnh: bậc, tổng, lớn nhất, trung bình theo cửa sổ 1 ngày | mở rộng phần đã có |

**Hai lựa chọn thực hiện**

*Cách A — tự viết SQL trong DuckDB.* Giữ nguyên đường ống hiện tại, không thêm
phụ thuộc. Chu trình dài tới 10 viết bằng SQL đệ quy sẽ nặng, cần giới hạn cửa sổ
thời gian trước khi tìm.

*Cách B — dùng thẳng IBM Graph Feature Preprocessor.* Nó nằm trong thư viện
Snap ML (`pip install snapml`), là đúng công cụ hai bài báo dùng. Đổi lại là thêm
một phụ thuộc và phải khớp định dạng đầu vào.

Khuyến nghị: **thử cách B trước.** Nếu chạy được thì ta so sánh được trực tiếp
với con số 27,30% của GFP+XGBoost.

**Đo bằng gì** — F1 lớp thiểu số trên tập test, so với mốc 0,2969. Mỗi đặc trưng
thêm vào phải trả lời được: nó có nâng F1 không? Không nâng thì bỏ.

### Giai đoạn 3 — Gỡ hai nhánh thừa (1 ngày)

**Làm gì**
- Bỏ Isolation Forest khỏi hợp nhất — trọng số đã là 0,00, nên bỏ không đổi kết quả.
- Bỏ hẳn bước hợp nhất; điểm rủi ro lấy thẳng từ mô hình edge.
- Nhánh đồ thị đổi vai: thôi sinh cảnh báo, chỉ sinh đặc trưng cho mô hình.
- Luật R01/R02 giữ nguyên nhưng `weight = 0` — chú giải, không chấm điểm.

**Đo bằng gì** — số cảnh báo và F1 trước/sau. Kỳ vọng: **ít cảnh báo hơn, chất
lượng cao hơn**, vì mọi cảnh báo giờ đến từ mô hình mạnh nhất.

### Giai đoạn 4 — Thử GNN đa đồ thị (1–2 tuần, tuỳ chọn)

Chỉ làm khi giai đoạn 2 đã cạn.

Kho mã [IBM/Multi-GNN](https://github.com/IBM/Multi-GNN) công khai, giấy phép
Apache. Ba sửa đổi cần có: **reverse message passing**, **port numbering**,
**ego IDs**. Multi-PNA+EU đạt 33,07% trên LI-Small.

Repo đã có `src/mega_pna/` dùng PyTorch Geometric — cùng hệ sinh thái, nên không
phải dựng lại hạ tầng.

**Cảnh báo trung thực:** bài báo cho biết tổng thời gian GPU của họ khoảng **1000
giờ** trên Tesla V100. Đừng bắt đầu giai đoạn này nếu chưa có GPU.

---

## 9. Giao thức đánh giá — để không tự lừa mình

Bốn quy tắc này lấy từ chính hai bài báo. Phá quy tắc nào là kết quả mất giá trị.

```mermaid
flowchart LR
    A["<b>Chia theo THỜI GIAN</b><br/>không chia ngẫu nhiên"]
    B["<b>Chuẩn hoá chỉ fit trên train</b><br/>val/test dùng tham số của train"]
    C["<b>Đặc trưng đồ thị<br/>chỉ dùng quá khứ</b><br/>xử lý tăng dần theo thời gian"]
    D["<b>Chạm tập test<br/>ĐÚNG MỘT LẦN</b><br/>ở ngưỡng đã đóng băng"]
    A --> B --> C --> D
```

1. **Chia theo thời gian.** Chia ngẫu nhiên cho mô hình nhìn thấy tương lai của
   chính tài khoản nó đang chấm. Ta đã làm đúng — giữ nguyên.
2. **Chuẩn hoá chỉ fit trên train.** Ta đã làm đúng.
3. **Đặc trưng đồ thị chỉ dùng dữ liệu quá khứ.** Đây là chỗ dễ sai nhất khi thêm
   chu trình: một chu trình "phát hiện được" bằng cạnh tương lai là rò rỉ.
4. **Chạm tập test đúng một lần.** Chọn trọng số và ngưỡng trên tập validation,
   rồi đóng băng. Đường ống hiện tại đã theo đúng giao thức này.

**Chỉ số báo cáo:** F1 lớp thiểu số và PR-AUC. **Không bao giờ dùng accuracy** —
mô hình trả lời "không có gì bất thường" cho mọi giao dịch vẫn đúng 99,93%.

Kèm theo, luôn báo cáo **bảng điểm vận hành** — chuyên viên rà N cảnh báo đầu thì
bắt được bao nhiêu. Đây mới là con số người dùng cảm nhận được:

| Rà bao nhiêu | Bắt được | Báo nhầm | Độ chính xác |
|---|---|---|---|
| 100 | 98 | 2 | 98% |
| 250 | 160 | 90 | 64% |
| 500 | 201 | 299 | 40% |

---

## 10. Bẫy đã biết

| Bẫy | Vì sao nguy hiểm |
|---|---|
| **Viết luật dựa trên thuộc tính không có trong dữ liệu** | Đã mắc một lần: hai luật dựa trên cờ VASP và quốc gia ngân hàng do dự án tự gán, sinh 10.620 cảnh báo không kiểm chứng được. Kiểm tra: cột đó có trong `LI-Small_Trans.csv` không? |
| **Lệch giữa huấn luyện và phục vụ** | Đã mắc một lần: lưới huấn luyện chạy 2 luật, production chạy 4. Kiểm tra: hai đường có chạy cùng một hàm không? |
| **Rò rỉ thời gian qua đặc trưng đồ thị** | Chu trình và scatter-gather rất dễ vô tình dùng cạnh tương lai. |
| **Nhắm 8 mẫu hình rồi kỳ vọng phủ hết** | Trần cứng ~29% trên LI-Small — mục 4.3. |
| **Dùng accuracy** | 99,93% mà vô dụng. |
| **So F1 với bài báo mà khác split** | Muốn so nghiêm túc phải chạy trên đúng split của họ. |

---

## 11. Ta đang đứng ở đâu

```mermaid
flowchart LR
    subgraph now["Hiện tại"]
        N1["Mô hình edge<br/><b>F1 30,2%</b>"]
    end
    subgraph target["Sau giai đoạn 2"]
        T1["+ đặc trưng đồ thị đầy đủ<br/><b>mục tiêu > 33%</b>"]
    end
    subgraph sota["SOTA công bố"]
        S1["GFP+XGBoost 27,3%"]
        S2["Multi-PNA 30,7%"]
        S3["Multi-PNA+EU <b>33,1%</b>"]
    end
    now --> target
    target -.->|"so sánh"| sota
```

Mô hình edge hiện tại **đã ngang Multi-PNA và vượt GFP+XGBoost** (với lưu ý khác
split). Mục tiêu của giai đoạn 2 là vượt 33,1% — khả thi, vì ta mới dùng 6 đặc
trưng đồ thị trong khi GFP dùng chu trình tới độ dài 10 cộng thống kê đỉnh đầy đủ.

**Điều quan trọng nhất cần nhớ:** thứ đang kéo con số tổng thể xuống không phải
mô hình yếu, mà là **kiến trúc chôn mô hình mạnh dưới ba nhánh yếu**. Gỡ chúng ra
là bước rẻ nhất và hiệu quả nhất.

---

## 12. Bắt đầu từ đâu

Người nhận việc đọc theo thứ tự này:

| Bước | File |
|---|---|
| 1. Hiểu mô hình đang có | `scripts/train_currency_native_edge.py` |
| 2. Xem đặc trưng được tính ở đâu | `scripts/benchmark_edge_level.py` |
| 3. Xem kết quả hiện tại | `reports/edge-benchmark/li_small_currency_native_policy_v1.json` |
| 4. Hiểu bối cảnh cả hệ thống | [`docs/TONG_KET_VA_HUONG_PHAT_TRIEN.md`](TONG_KET_VA_HUONG_PHAT_TRIEN.md) |
| 5. Đọc bài báo gốc | [arXiv:2306.16424](https://arxiv.org/abs/2306.16424) mục 4 và phụ lục D |

Việc đầu tiên nên làm: **giai đoạn 1**, chốt mốc so sánh. Không có mốc thì mọi
cải tiến sau đều là cảm tính.
