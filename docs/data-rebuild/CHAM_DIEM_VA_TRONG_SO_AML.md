# Chấm điểm AML và xác định trọng số

Tài liệu hướng dẫn cho hai vấn đề:

1. Agent phải **giải thích được** vì sao nó cho rằng một giao dịch là rửa tiền —
   tức là phải có điểm số và bằng chứng, không phải một câu khẳng định.
2. Huấn luyện cần **trọng số**, nhưng chưa biết ngân hàng đánh giá mức độ quan
   trọng của từng yếu tố như thế nào.

---

## Phần 0. Đảo lại câu hỏi

> "Trọng số đúng của ngành ngân hàng là bao nhiêu?"

Câu hỏi này không có đáp án, và đó **không phải** vì bạn chưa tìm ra. Không ngân
hàng nào có một bảng trọng số chuẩn. Hai ngân hàng cùng quy mô ở cùng thị trường
sẽ có bộ trọng số khác nhau, vì trọng số phụ thuộc vào **danh mục khách hàng của
chính ngân hàng đó**, khẩu vị rủi ro, và năng lực xử lý cảnh báo.

Câu hỏi trả lời được là:

> "Làm sao để **suy ra** trọng số một cách có thể bảo vệ được trước kiểm toán, và
> làm sao để **chứng minh** chúng hợp lý?"

Phần còn lại của tài liệu trả lời câu đó.

---

## Phần 1. Kiến trúc hai tầng

Sai lầm phổ biến nhất là bắt một mô hình duy nhất vừa cho điểm chính xác vừa giải
thích được. Hai mục tiêu đó kéo ngược chiều nhau. Ngành giải quyết bằng cách tách
làm hai tầng.

```text
                    ┌─────────────────────────────────────┐
Giao dịch  ────────►│  TẦNG 1: CHỈ BÁO (indicator)        │
+ hồ sơ KYC         │  Rời rạc, có/không, mỗi cái gắn với  │
+ đồ thị            │  một nguồn quy định hoặc typology    │
                    └──────────────┬──────────────────────┘
                                   │ vector chỉ báo + bằng chứng
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  TẦNG 2: ĐIỂM THỐNG KÊ              │
                    │  Mô hình học từ nhãn, cho xác suất   │
                    │  đã hiệu chuẩn + SHAP từng quyết định│
                    └──────────────┬──────────────────────┘
                                   │ điểm + đóng góp từng yếu tố
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  TẦNG 3: NGƯỠNG & DIỄN GIẢI          │
                    │  Ngưỡng theo năng lực xử lý          │
                    │  Agent viết narrative từ 2 tầng trên │
                    └─────────────────────────────────────┘
```

**Tầng 1 là thứ agent trích dẫn. Tầng 2 là thứ xếp hạng cảnh báo. Đừng để agent
giải thích bằng cách kể lại trọng số của tầng 2.**

Lý do: một analyst hoặc thanh tra không chấp nhận "mô hình cho 0,87". Họ chấp
nhận "tài khoản này nhận tiền từ 23 đối tác khác nhau trong 4 ngày, mỗi khoản
dưới ngưỡng báo cáo, rồi chuyển đi 96% trong vòng 6 giờ" — đó là chỉ báo, và nó
đúng hay sai thì kiểm chứng được trên dữ liệu.

---

## Phần 2. Tầng 1 — xây bộ chỉ báo

### 2.1 Mỗi chỉ báo phải có một nguồn

Không tự nghĩ ra chỉ báo. Mỗi cái phải trỏ về một trong bốn loại nguồn:

| Loại nguồn | Ví dụ | Cho ta điều gì |
|---|---|---|
| Luật/quy định VN | Luật Phòng, chống rửa tiền 2022; Nghị định 19/2023/NĐ-CP; Thông tư của NHNN về tiêu chí rủi ro | Nghĩa vụ bắt buộc, ngưỡng báo cáo, nhóm rủi ro cao |
| Typology quốc tế | FATF *Professional Money Laundering* (2018); FinCEN Advisory FIN-2014-A005 (funnel accounts) | Cấu trúc mạng lưới, vai trò, trình tự các bước |
| Dữ liệu nội bộ ngân hàng | Hồ sơ cảnh báo và SAR đã xử lý | Chỉ báo nào thực sự chuyển thành case |
| Bộ dữ liệu này | 8 typology của IBM, 6 họ hard negative | Kiểm định phương pháp trước khi có dữ liệu thật |

> **Cần xác minh:** số hiệu và điều khoản cụ thể của văn bản pháp luật Việt Nam
> phải được đối chiếu với bản gốc trước khi đưa vào tài liệu mô hình. Tôi liệt kê
> tên văn bản để bạn biết chỗ tra, không phải để trích dẫn nguyên văn.

### 2.2 Cấu trúc một chỉ báo

Mỗi chỉ báo là một bản ghi, không phải một dòng code:

```yaml
indicator_id: IND_FUNNEL_RAPID_PASSTHROUGH
name: Nhận nhiều nguồn rồi chuyển đi nhanh
source:
  - FinCEN FIN-2014-A005 (funnel account)
  - FATF PML 2018, mục về tài khoản trung chuyển
logic: >-
  Trong cửa sổ 7 ngày: số đối tác gửi tiền >= N1
  VÀ tỷ lệ tiền chuyển đi / tiền nhận vào >= N2
  VÀ thời gian lưu trung vị <= N3 giờ
parameters: {N1: 10, N2: 0.90, N3: 24}
parameter_basis: >-
  N1, N2, N3 CHƯA có cơ sở thực nghiệm. Đặt theo phân vị 99 của
  chính danh mục, hiệu chỉnh lại sau 3 tháng vận hành.
evidence_fields: [counterparty_count_7d, outflow_ratio_7d, median_dwell_hours]
legitimate_explanations:
  - Người bán online gom tiền khách rồi thanh toán nhà cung cấp
  - Đầu mối chuyển tiền gia đình
  - Doanh nghiệp quét vốn (treasury sweep)
false_positive_family: MARKETPLACE_SELLER, FAMILY_REMITTANCE_HUB, TREASURY_SWEEP
```

Trường **`legitimate_explanations`** là bắt buộc và là phần quan trọng nhất. Một
chỉ báo mà bạn không kể được lý do hợp pháp cho nó là một chỉ báo bạn chưa hiểu,
và nó sẽ tạo ra cảnh báo mà analyst không đóng được.

Bộ dữ liệu này có sẵn **225 episode hard negative thuộc 6 họ** chính là để làm
việc đó: mỗi họ ghi rõ `legitimate_explanation` và `observable_collision`.

### 2.3 Nhóm chỉ báo nên có

Với các cột có trong `bank_view/`:

| Nhóm | Chỉ báo | Tính từ |
|---|---|---|
| Cấu trúc | fan-in, fan-out, pass-through, chu trình, số chặng | `transactions`, `relationships` |
| Tốc độ | thời gian lưu, tỷ lệ chuyển đi trong 24h | `timestamp`, `amount` |
| Lệch chuẩn | độ lệch so với chính mình, so với nhóm đồng đẳng | `accounts.expected_monthly_turnover_vnd` |
| Kênh | đổi kênh đột ngột, tiền mặt bất thường theo ngành | `channel`, `payment_format` |
| Thiết bị | chia sẻ thiết bị, thiết bị mới | `devices`, `relationships` |
| Mạng lưới | khoảng cách tới thực thể đã bị gắn cờ, cụm liên thông | `relationships` + đồ thị giao dịch |

**Cảnh báo về hai cột:** `payment_format` và giờ trong ngày ở bộ dữ liệu này là
**vẽ lại theo giả định**, không phải phân phối đo được của Việt Nam. Chỉ báo dựa
trên chúng kiểm định được *cơ chế* nhưng không chuyển sang production được.

---

## Phần 3. Tầng 2 — trọng số đến từ đâu

Bốn nguồn, xếp theo thứ tự ưu tiên. Thực tế nên **kết hợp**.

### 3.1 Học từ nhãn (tốt nhất, khi có nhãn)

Bộ dữ liệu này cho bạn nhãn. Hai lựa chọn:

**Hồi quy logistic có ràng buộc** — hệ số *chính là* trọng số, đọc được trực
tiếp, và odds ratio giải thích được cho người không làm kỹ thuật:

```text
log-odds = β₀ + β₁·fan_in + β₂·dwell_ratio + β₃·peer_deviation + …
```

**Gradient boosting + SHAP** — chính xác hơn, và SHAP cho đóng góp *từng quyết
định* chứ không chỉ trọng số toàn cục. Đây là thứ agent cần để giải thích.

> Trọng số toàn cục trả lời "yếu tố nào quan trọng nói chung".
> SHAP trả lời "vì sao **giao dịch này**". Agent cần cái thứ hai.

### 3.2 Hỏi chuyên gia ngân hàng có cấu trúc — AHP

Đây là câu trả lời trực tiếp cho "ngân hàng đánh giá mức độ quan trọng thế nào".
Đừng hỏi "yếu tố này quan trọng bao nhiêu điểm trên 10" — người ta trả lời không
nhất quán. Dùng **AHP (Analytic Hierarchy Process)**: so sánh **từng cặp**.

Quy trình:

1. Liệt kê 7–9 yếu tố (nhiều hơn thì con người so sánh không đáng tin).
2. Hỏi từng cặp: "So với *lệch chuẩn so với nhóm đồng đẳng*, thì *pass-through
   nhanh* quan trọng hơn bao nhiêu?" Thang 1–9.
3. Lập ma trận so sánh, lấy **vector riêng ứng với trị riêng lớn nhất** → trọng số.
4. Tính **Consistency Ratio (CR)**. **CR > 0,1 thì bộ trả lời không nhất quán,
   phải hỏi lại** — đây là điểm mạnh của AHP: nó tự phát hiện câu trả lời tuỳ tiện.
5. Lặp với 3–5 chuyên gia, lấy trung bình nhân.

Sản phẩm: một bộ trọng số **có biên bản**, ghi rõ ai trả lời, khi nào, CR bao
nhiêu. Đó là thứ đưa được vào hồ sơ mô hình.

### 3.3 Tiên nghiệm từ quy định (cho dấu và thứ tự, không cho độ lớn)

Quy định nói "khách hàng nước ngoài rủi ro cao hơn" — tức là hệ số **dương**.
Nó không nói dương bao nhiêu. Dùng để **ràng buộc**, không dùng để gán số.

### 3.4 Đồng đều (giả thuyết null trung thực)

Trọng số bằng nhau. Luôn chạy cái này làm baseline. **Nếu mô hình có trọng số
không thắng được baseline đồng đều một cách rõ rệt, thì trọng số của bạn chưa
chứng minh được điều gì.**

### 3.5 Cách nên dùng: học có ràng buộc

Kết hợp 3.1 và 3.3:

- **Ràng buộc đơn điệu (monotonic constraints).** LightGBM và XGBoost đều hỗ trợ.
  Buộc "fan-in cao hơn → điểm không giảm". Quy định cho *hướng*, dữ liệu cho *độ lớn*.
- **Ràng buộc dấu** trong hồi quy logistic.
- **Chuẩn hoá về tiên nghiệm chuyên gia**: phạt độ lệch giữa trọng số học được và
  trọng số AHP; hệ số phạt là một tham số điều chỉnh được.

Cách này là thứ bộ phận quản trị rủi ro mô hình chấp nhận được: mô hình không thể
học ra một quan hệ ngược chiều với quy định chỉ vì dữ liệu tình cờ như vậy.

---

## Phần 4. Hiệu chuẩn và ngưỡng

### 4.1 Điểm thô không phải xác suất

Đầu ra gradient boosting **không** phải xác suất, kể cả khi nó nằm trong [0,1].
Phải hiệu chuẩn: **Platt scaling** hoặc **isotonic regression** trên tập
validation. Sau đó "điểm 0,8" mới thực sự nghĩa là "khoảng 80% khả năng".

Chưa hiệu chuẩn thì agent không được phép nói "xác suất 87%". Nó phải nói "xếp
hạng ở nhóm 1% cao nhất".

### 4.2 Ngưỡng đặt theo năng lực, không theo F1

Đây là chỗ giáo trình sai và thực tế đúng.

Ngân hàng có **N analyst**, mỗi người xử lý được **M cảnh báo/ngày**. Tổng năng
lực là N×M. Ngưỡng phải đặt sao cho số cảnh báo ≈ năng lực đó. Tối ưu F1 cho ra
một ngưỡng mà không ai xử lý nổi.

Nên chỉ số cần báo cáo là **precision@k**, với k = năng lực ngày. AUC gần như vô
dụng để ra quyết định vận hành — nó tính trung bình trên mọi ngưỡng, kể cả những
ngưỡng không bao giờ dùng.

### 4.3 Chỉ số nên báo cáo

| Chỉ số | Vì sao |
|---|---|
| Precision@k (k = năng lực ngày) | Ràng buộc vận hành thật |
| Recall trên các typology **đã biết** | Có bắt được cấu trúc không |
| **Tỷ lệ cảnh báo trên hard negative** | Chỉ số chẩn đoán quan trọng nhất |
| Recall theo từng typology | Mô hình mù với loại nào |
| Độ ổn định điểm theo thời gian | Chuẩn bị cho drift |

**Tỷ lệ cảnh báo trên hard negative là phép thử thật.** Bộ dữ liệu có 225 episode
hợp pháp được thiết kế để va vào đúng những quy tắc đơn giản. Mô hình bắt hết
typology mà cũng bắt luôn 60% hard negative là mô hình đã học "hoạt động bất
thường", không phải "rửa tiền".

---

## Phần 5. Agent giải thích như thế nào

### 5.1 Bốn thành phần của một lời giải thích

Agent **không** được nói "mô hình cho 0,87 nên tôi nghi ngờ". Cần:

1. **Chỉ báo nào kích hoạt** + giá trị quan sát được
2. **Đóng góp SHAP** của từng yếu tố cho quyết định này
3. **So sánh phản thực**: điều gì phải khác đi thì đã không cảnh báo
4. **Giải thích hợp pháp đã loại trừ**: đã cân nhắc khả năng nào và vì sao loại

### 5.2 Mẫu narrative

```text
Cảnh báo: ACC-00001234 · điểm 0,91 (nhóm 0,4% cao nhất) · 2022-09-14

CHỈ BÁO KÍCH HOẠT
  IND_FUNNEL_RAPID_PASSTHROUGH
    23 đối tác gửi tiền / 7 ngày   (ngưỡng 10; phân vị 99 của nhóm đồng đẳng: 6)
    tỷ lệ chuyển đi 0,94           (ngưỡng 0,90)
    thời gian lưu trung vị 3,2 giờ (ngưỡng 24)
  IND_PEER_DEVIATION_TURNOVER
    turnover tháng 412 tr VND so với kỳ vọng 18 tr  (22,9×)

ĐÓNG GÓP TỪNG YẾU TỐ (SHAP, đơn vị log-odds)
  +1,84  số đối tác gửi trong 7 ngày
  +1,12  tỷ lệ chuyển đi trong 24h
  +0,77  độ lệch turnover so với nhóm đồng đẳng
  −0,31  quan hệ ngân hàng 5 năm+       ← giảm nghi ngờ
  −0,18  không chia sẻ thiết bị

PHẢN THỰC
  Nếu số đối tác gửi ≤ 9 thì điểm còn 0,42 — dưới ngưỡng cảnh báo.
  Đây là yếu tố quyết định duy nhất.

ĐÃ CÂN NHẮC VÀ LOẠI TRỪ
  Người bán online (MARKETPLACE_SELLER): mẫu này thường có tiền vào rải đều
    trong ngày và tiền ra tới một số ít nhà cung cấp cố định. Ở đây tiền ra đi
    tới 19 đích khác nhau chưa từng xuất hiện trước đó.
  Đầu mối chuyển tiền gia đình: quy mô vượt 22,9 lần thu nhập kỳ vọng.

KHÔNG DÙNG LÀM CĂN CỨ
  Nghề nghiệp, giới tính, khu vực cư trú, nhóm thu nhập.
```

### 5.3 Ba quy tắc bắt buộc

**Không lấy thuộc tính KYC làm bằng chứng buộc tội.** Nghề nghiệp, giới tính, khu
vực, nhóm thu nhập **không được** xuất hiện trong phần lý do. Chúng dùng để xây
*baseline kỳ vọng* ("turnover này bất thường **so với khách hàng như thế nào**"),
không dùng làm chứng cứ. Đây vừa là yêu cầu chống phân biệt đối xử, vừa là lý do
Phase 14 tồn tại trong bộ dữ liệu này.

**Cờ đỏ không phải bằng chứng phạm tội.** FinCEN nói rõ điều này trong chính
advisory về funnel account. Agent phải viết "mẫu hình phù hợp với X, cần xác
minh", không viết "đây là rửa tiền".

**Ghi lại điều gì sẽ làm thay đổi kết luận.** Phần phản thực không phải trang
trí — nó là thứ analyst dùng để bác bỏ nhanh.

---

## Phần 6. Làm gì với bộ dữ liệu này

### 6.1 Quy trình

1. **Đặc trưng chỉ từ `bank_view/`.** Không đụng `ground_truth/` khi tính đặc trưng.
2. **Join point-in-time.** Chỉ dùng dữ liệu có trước thời điểm dự đoán.
3. **Train trên TRAIN, tinh chỉnh trên VALIDATION, báo cáo trên TEST.**
   **Không mở HIDDEN_TEST** cho tới khi chốt mô hình.
4. **Mọi mạng lưới nằm trọn trong một split** — đã kiểm chứng, 0 mạng bị cắt.
5. **Chạy 3 cấu hình**: trọng số đồng đều / AHP / học có ràng buộc. So sánh.
6. **Báo cáo tỷ lệ cảnh báo trên hard negative** cùng với mọi chỉ số khác.

### 6.2 Điều tuyệt đối phải nói rõ khi trình bày

> **Ngưỡng và trọng số hiệu chuẩn trên bộ dữ liệu này KHÔNG chuyển sang production
> được.**

Ba lý do, đều đã ghi trong `manifest.json`:

- Tỷ lệ dương tính là **hệ quả của cách chọn tập con** (chọn hạt giống từ các mẫu
  rửa tiền), không phải tỷ lệ thực. `prevalence_claim: false`.
- Payment format và giờ trong ngày là **giả định**, không phải phân phối đo được
  của Việt Nam.
- IBM **99,7% là doanh nghiệp**, nên hành vi khách bán lẻ ở đây là hành vi doanh
  nghiệp mang nhãn bán lẻ.

Cái bộ dữ liệu này chứng minh được là **phương pháp**: pipeline chạy được, đặc
trưng tính được, mô hình học được cấu trúc, agent giải thích được, hard negative
phân biệt được mô hình tốt với mô hình chỉ bắt "bất thường".

Cái nó **không** chứng minh được là một cấu hình cụ thể sẽ hoạt động ở ngân hàng
thật.

### 6.3 Lộ trình sang dữ liệu thật

| Bước | Việc | Thay thế cho |
|---|---|---|
| 1 | Chạy toàn bộ pipeline trên bộ này | — |
| 2 | Workshop AHP với 3–5 chuyên gia AML của ngân hàng | Trọng số đồng đều |
| 3 | Xin **thống kê tổng hợp** danh mục thật (phân phối turnover theo phân khúc) | `ASSUME_INCOME_TO_TURNOVER` |
| 4 | Xin thống kê tổng hợp kênh thanh toán thật | `ASSUME_CHANNEL_MIX`, `ASSUME_DIURNAL_PROFILE` |
| 5 | Hiệu chuẩn lại ngưỡng theo năng lực analyst thật | Ngưỡng của bộ này |
| 6 | Kiểm định ngược trên hồ sơ cảnh báo/SAR đã xử lý | Nhãn của IBM |

Bước 3 và 4 chỉ cần **số liệu tổng hợp**, không cần dữ liệu khách hàng — thường
là thứ xin được mà không vướng bảo mật.

---

## Phần 7. Hồ sơ mô hình cần có

Để qua được kiểm toán/thanh tra, cần lưu:

- **Danh mục chỉ báo**: mỗi cái kèm nguồn, tham số, cơ sở đặt tham số, các giải
  thích hợp pháp
- **Biên bản trọng số**: AHP thì ghi ai trả lời, khi nào, CR bao nhiêu; học từ dữ
  liệu thì ghi tập huấn luyện, phiên bản, seed
- **Báo cáo hiệu chuẩn**: đường hiệu chuẩn, Brier score, phân tích ngưỡng
- **Phân tích công bằng**: tỷ lệ cảnh báo theo giới tính, khu vực, nhóm thu nhập
  — phải chứng minh **không** có chênh lệch không giải thích được
- **Kết quả hard negative**: bao nhiêu trong 225 episode bị cảnh báo, họ nào
- **Đăng ký hạn chế**: 12 hạn chế trong `manifest.json`, cộng thêm của mô hình

Mục *phân tích công bằng* không phải hình thức. Bộ dữ liệu này có sẵn thuộc tính
nhân khẩu học, nên tính được — và Phase 14 đã chứng minh rằng ở tầng dữ liệu,
không thuộc tính KYC nào dự đoán nhãn quá 2,08×. Nếu mô hình của bạn tạo ra chênh
lệch lớn hơn thế theo giới tính hay khu vực, thì chênh lệch đó **do mô hình sinh
ra**, không phải do dữ liệu.

---

## Tóm tắt

| Câu hỏi | Trả lời ngắn |
|---|---|
| Trọng số ngành ngân hàng là bao nhiêu? | Không tồn tại. Phải suy ra và ghi lại cách suy ra |
| Lấy trọng số ở đâu? | Học từ nhãn + AHP với chuyên gia + ràng buộc từ quy định |
| Agent giải thích bằng gì? | Chỉ báo có nguồn (tầng 1), không phải trọng số mô hình (tầng 2) |
| SHAP dùng làm gì? | Đóng góp *từng quyết định*, khác với trọng số toàn cục |
| Đặt ngưỡng thế nào? | Theo năng lực analyst, không theo F1 |
| Chỉ số quan trọng nhất? | Precision@k và **tỷ lệ cảnh báo trên hard negative** |
| Có dùng được trọng số này cho production? | **Không.** Chỉ chứng minh phương pháp |
