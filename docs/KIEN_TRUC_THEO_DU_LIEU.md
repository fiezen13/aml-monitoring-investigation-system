# Kiến trúc FIN-07 vẽ lại theo đúng những gì dữ liệu có

Sơ đồ cũ đúng về **hình dạng** — 3 agent, 8 công cụ, chứng cứ trước giải thích —
nhưng vài hộp phát hiện dựa trên thứ dữ liệu không có, hoặc đã đo được là không
đóng góp gì.

Tài liệu này giữ nguyên hình dạng ấy và thay các hộp bằng thứ **truy được về cột
dữ liệu thật hoặc số đo đã có**. Yêu cầu không đổi: **mọi thứ xuất ra phải được
tác tử giải thích đầy đủ.**

---

## 1. Dữ liệu thật sự có gì

Toàn bộ `HI-Medium_Trans.csv` có **11 cột**, không hơn:

```
Timestamp, From Bank, Account, To Bank, Account,
Amount Received, Receiving Currency, Amount Paid, Payment Currency,
Payment Format, Is Laundering
```

Tệp nhãn `HI-Medium_Patterns.txt` gán **493 vụ** theo **8 mẫu hình đồ thị**:
FAN-IN, FAN-OUT, CYCLE, SCATTER-GATHER, GATHER-SCATTER, STACK, BIPARTITE, RANDOM.

**Không có trong dữ liệu:** quốc gia · cờ VASP · KYC · nghề nghiệp · PEP · ngày mở
tài khoản · hạn mức. Mọi thành phần cần chúng đều là thứ dự án tự bịa ra rồi tự
phát hiện lại.

Đó là lý do `R03_VASP_EXPOSURE` và `R04_CROSS_BORDER_FLOW` đã bị gỡ: chúng đọc
`bank_country.csv` do dự án viết, trong đó `is_vasp` chỉ đánh dấu **một** họ ngân
hàng hư cấu.

---

## 2. Cái gì bị bỏ, và bằng chứng nào

| Thành phần | Số đo | Quyết định |
|---|---|---|
| Isolation Forest | trọng số hợp nhất **0,00**; cả 8 tổ hợp tốt nhất đều loại nó | **Bỏ** |
| Bộ dò mẫu hình đồ thị | precision **0,14%**, recall 58,3% | **Giữ, nhưng chỉ sinh chứng cứ** |
| Luật R01/R02 | precision **0,64%**, phủ 6,6%, lift 2,6× | **Giữ, trọng số nhỏ + lý do có tên** |
| Mô hình đặc trưng đồ thị | trùng nguồn tín hiệu với MEGA-PNA | **Chờ đo tương quan** |
| Hợp nhất 3 nhánh | 0,1365 so với riêng graph 0,1338 | **Giữ, nhưng đổi nhánh** |

Điểm chung: thứ có precision dưới 1% **không được tự mở cảnh báo**, nhưng vẫn có
giá trị làm chứng cứ và lý do.

---

## 3. Sơ đồ mới

```mermaid
flowchart TD
    subgraph S1["1 · DỮ LIỆU — chỉ 11 cột"]
        D[("<b>IBM AML HI-Medium</b><br/>29.336.378 giao dịch<br/>35.158 nhãn rửa tiền<br/><i>493 vụ · 8 mẫu hình</i>")]
    end

    subgraph S2["2 · TIỀN XỬ LÝ"]
        P["account_key = bank:account<br/>chia 60/20/20 tại ranh giới ngày<br/><b>giữ self-loop khi ĐO</b><br/><b>bỏ self-loop khi PHỤC VỤ</b>"]
    end

    subgraph S3["3 · ĐẶC TRƯNG — chỉ thứ suy được"]
        F1["<b>Cạnh</b><br/>thời điểm · số tiền<br/>loại tiền · hình thức"]
        F2["<b>Đồ thị</b><br/>fan-in/out · chu trình<br/>gom-toả · bậc đỉnh"]
    end

    subgraph S4["4 · PHÁT HIỆN"]
        R["<b>Rule R01 · R02</b><br/><i>lift 2,6× · precision 0,64%</i><br/>trọng số nhỏ + LÝ DO CÓ TÊN"]
        M["<b>MEGA-PNA</b><br/><i>bộ xếp hạng chính</i><br/>chấm từng cạnh"]
        G["<b>Bộ dò mẫu hình</b><br/><i>precision 0,14% → KHÔNG chấm điểm</i><br/>CHỈ sinh chứng cứ cấu trúc"]
    end

    AGG["<b>4b · GOM VỀ TÀI KHOẢN</b><br/>cửa sổ 7 ngày<br/>điểm cao nhất · trung bình top-5<br/>số cạnh vượt ngưỡng · tổng tiền"]

    FUS["<b>5 · HỢP NHẤT</b><br/>risk = w₁·rule + w₂·mega_pna<br/><i>phân vị chốt trên TRAIN</i><br/>→ phân rã được cho Agent 2"]

    AL["<b>6 · CẢNH BÁO TÀI KHOẢN</b><br/>account_key · risk_score<br/>alert_reason · typology · top signal"]

    D --> P --> F1 & F2
    F1 --> M
    F2 --> M & G
    P --> R
    M --> AGG
    AGG --> FUS
    R --> FUS
    FUS --> AL
    G -.->|"chứng cứ, không phải điểm"| AL

    style M fill:#d4edda,stroke:#28a745,stroke-width:3px
    style G fill:#fff3cd,stroke:#ffc107
    style AGG fill:#d4edda,stroke:#28a745
    style FUS fill:#cce5ff,stroke:#0066cc
```

Đường **nét đứt** từ bộ dò mẫu hình là thay đổi quan trọng nhất: nó vào cảnh báo
làm **chứng cứ**, không đi qua hợp nhất. Precision 0,14% quá thấp để chấm điểm,
nhưng nó là thứ duy nhất gọi được tên `CYCLE`.

---

## 4. Mỗi công cụ của tác tử lấy dữ liệu từ đâu

Đây là bảng trả lời câu "agent có giải thích được đầy đủ không".

```mermaid
flowchart LR
    subgraph SRC["Nguồn"]
        S1["<b>Hợp nhất</b><br/>phân vị + đóng góp<br/>từng nhánh"]
        S2["<b>Luật R01/R02</b><br/>mã · nhãn · tín hiệu"]
        S3["<b>Bộ dò mẫu hình</b><br/>cụm giao dịch<br/>+ tên hình dạng"]
        S4["<b>Bảng transaction</b><br/>giao dịch thô"]
        S5["<b>Danh mục typology</b><br/>tín hiệu bắt buộc<br/>/ hỗ trợ"]
    end

    subgraph TOOL["8 công cụ"]
        T1["GetRiskBreakdown"]
        T2["GetAccountBehavior"]
        T3["GetTransactions"]
        T4["GetGraphEvidence"]
        T5["GetGraphNeighborhood"]
        T6["GetTypology"]
        T7["GetAnomalyExplanation"]
        T8["Report Formatter"]
    end

    S1 --> T1
    S2 --> T1 & T6
    S3 --> T4 & T6
    S4 --> T2 & T3 & T5
    S5 --> T6
    S1 --> T7
    T1 & T2 & T3 & T4 & T5 & T6 & T7 --> T8

    style T7 fill:#fff3cd,stroke:#ffc107
```

| Công cụ | Nguồn | Còn sống sau khi đổi? |
|---|---|---|
| `GetRiskBreakdown` | hợp nhất | ✅ hai nhánh thay vì ba |
| `GetAccountBehavior` | bảng `transaction` | ✅ không đổi |
| `GetTransactions` | bảng `transaction` | ✅ không đổi |
| `GetGraphEvidence` | `graph_detector_evidence` | ✅ **chính vì giữ bộ dò** |
| `GetGraphNeighborhood` | bảng `transaction` | ✅ không đổi |
| `GetTypology` | danh mục + tín hiệu luật | ✅ không đổi |
| `GetAnomalyExplanation` | ⚠️ Isolation Forest | **đổi nguồn sang MEGA-PNA** |
| `Report Formatter` | tất cả | ✅ không đổi |

Chỉ **một** công cụ phải đổi nguồn. `GetAnomalyExplanation` hiện đọc cảnh báo
`detector='ml'` của Isolation Forest; nó sẽ đọc mức đóng góp của nhánh MEGA-PNA
cùng bốn số đo gom theo tài khoản — tức *"12 giao dịch vượt ngưỡng, tổng 240.000
USD, cạnh cao nhất 0,97"*.

---

## 5. Một cảnh báo trông như thế nào

Ví dụ dựng từ đúng những trường có thật:

```mermaid
flowchart TD
    A["<b>Cảnh báo · tài khoản 0111632:8062C56E0</b><br/>risk_score = 0,91"]

    B1["<b>Phân rã</b> — Agent 2<br/>0,83 mega_pna + 0,08 rule"]
    B2["<b>Lý do có tên</b> — R02<br/>78% tiền ra trong 2 giờ<br/><i>short_dwell_time</i>"]
    B3["<b>Cụm chứng cứ</b><br/>7 giao dịch · 6 giờ · 240.000 USD<br/><i>đủ transaction_id</i>"]
    B4["<b>Hình dạng</b><br/>A→B→C→A<br/>khớp CYCLE"]

    A --> B1 & B2 & B3 & B4
    B1 & B2 & B3 & B4 --> C{"<b>Agent 3</b><br/>mỗi khẳng định<br/>có transaction_id?"}
    C -->|PASS| D["<b>Gói điều tra</b>"]
    C -->|FAIL| E["quay lại Agent 1<br/>thu thêm chứng cứ"]

    style B2 fill:#fff3cd,stroke:#ffc107
    style B3 fill:#d4edda,stroke:#28a745
```

Câu hệ thống nói được với chuyên viên:

> *Tài khoản 0111632:8062C56E0, rủi ro 0,91. Bảy giao dịch tạo thành chu trình
> A→B→C→A trong 6 giờ, tổng 240.000 USD; mô hình chấm cả bảy trên 0,9. Tài khoản
> đẩy 78% tiền nhận được đi trong vòng 2 giờ (R02). Hình dạng khớp CYCLE.*

Mọi con số trong câu đó truy ngược được về `transaction_id` — đó là điều Agent 3
kiểm, và là lý do bộ dò mẫu hình được giữ dù precision chỉ 0,14%.

### Vì sao R02 xuất hiện trong ví dụ CYCLE

Không phải ngẫu nhiên. Đo trên 1.758.597 tài khoản HI-Medium:

| | Nền chung | Trong CYCLE | Lift |
|---|---:|---:|---:|
| R02 chuyển tiền nhanh | 0,55% | **4,4%** | **8×** |
| R01 chia nhỏ | 2,02% | 5,9% | 2,9× |

R02 là dấu hiệu mạnh nhất của CYCLE — hợp lý, vì chu trình là phân lớp nên tiền
phải đi qua nhanh. Ngược lại **R02 bằng đúng 0,0% với FAN-IN**, nên Agent 2
**không được** viện dẫn R02 cho cảnh báo FAN-IN.

---

## 6. Điều kiện nghiệm thu

Sơ đồ chỉ đúng khi bốn điều sau đo được:

| # | Điều kiện | Cách đo |
|---|---|---|
| 1 | MEGA-PNA đủ mạnh | báo cáo `fin07.benchmark.v1`, đơn vị `account_window` |
| 2 | Nhánh rule còn đóng góp | trọng số hợp nhất **≠ 0** trên validation |
| 3 | Bỏ mô hình đặc trưng đồ thị không mất gì | thêm nó vào tăng **< 0,005 F1** |
| 4 | Mọi khẳng định có chứng cứ | tỷ lệ PASS của Agent 3 trên mẫu cảnh báo |

Điều kiện 2 quan trọng: nếu trọng số rule về 0 như Isolation Forest, thì nó chỉ
còn là nguồn lý do chứ không còn là nhánh chấm điểm — và sơ đồ phải sửa lại lần
nữa, trung thực với số đo.

Mọi con số phải qua `src/benchmark/standard.py`, đơn vị `account_window`, dãy
ngân sách cố định. Không con số nào ngoài chuẩn được đưa vào tài liệu.
