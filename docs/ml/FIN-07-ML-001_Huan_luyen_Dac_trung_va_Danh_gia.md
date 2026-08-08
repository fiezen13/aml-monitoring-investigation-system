# FIN-07 — Huấn luyện, đặc trưng và đánh giá

| | |
|---|---|
| **Mã tài liệu** | FIN-07-ML-001 |
| **Phiên bản** | 1.1 |
| **Ngày** | 08/08/2026 |
| **Người lập** | Bảo — PM/DevOps |
| **Người thực hiện** | Hiển (AI Engineer), Hường (ML/Feature) |
| **Tài liệu gốc** | FIN-07-BUS-001 (nghiệp vụ), FIN-07-ARC-001 (kiến trúc), FIN-07-DAT-001 (dữ liệu) |
| **Mức độ mật** | Nội bộ — Hạn chế |

Tài liệu này trả lời bốn câu hỏi cho hai người làm mô hình: **huấn luyện trên cái gì và như thế nào, dùng model và đặc trưng gì, kết quả trả về kèm bằng chứng ra sao, và đo bằng chỉ số nào so với đường cơ sở nào.**

Nó không thay thế FIN-07-DAT-001 mà cụ thể hoá phần mô hình. Chỗ nào khác tài liệu gốc đều đánh dấu **[LỆCH]** kèm lý do — không có thay đổi thầm lặng nào.

> ## ⚠ Cảnh báo phiên bản — đọc trước
>
> **Ngày 08/08/2026 dự án quay lại dùng bản LI-Small** (theo DAT-001 §3.1), và EDA đã chạy xong trên bản đó — kết quả ở **FIN-07-ML-002 Chương 4 và 5**.
>
> Tài liệu này viết ở v1.1 cho bản **HI-Medium**. **Mọi con số trong Chương 1, và các ngưỡng dẫn xuất ở §3, §5, §8, §9, đều là số đo trên HI-Medium** — vẫn đúng, nhưng đúng về HI-Medium. Không trích dẫn như số liệu của bộ đang dùng.
>
> **Số liệu thay thế cho LI-Small, lấy từ ML-002 §5:**
>
> | | HI-Medium (tài liệu này) | **LI-Small (đang dùng)** |
> |---|---:|---:|
> | Giao dịch | 31.898.238 | **6.924.049** |
> | Tài khoản | 2.077.023 | **705.907** |
> | Cửa sổ dùng được | 27,67 ngày | **10 ngày** |
> | Tỉ lệ nền giao dịch | 0,1104% | **0,0515%** |
> | Tỉ lệ nền tài khoản | 2,0152% | **0,7514%** |
> | Tài khoản dương | 41.857 | **5.304** |
> | Lift ACH | 7,2× | **6,37×** |
> | Bộ cửa sổ đặc trưng | 1/3/7/14 ngày | **1/2/3 ngày** |
> | Tài khoản bậc ≥ 20 | 39,3% | **33,7%** |
> | Cạnh tự trỏ | 8,03% | **11,62%** |
>
> **Phần vẫn đúng nguyên vẹn, không phụ thuộc bản nào:** quy tắc chống rò rỉ (§2), phương pháp chia tập theo mạng lưới (§3.2), chiến lược huấn luyện và phễu hai tầng (§5), lớp bằng chứng (§6), cách so với đường cơ sở (§7), bộ chỉ số (§8), toàn bộ cạm bẫy (§9).

---

## 0. Phân công

Rủi ro RK5 (ARC-001) và RD7 (DAT-001) đều ghi Hiển là nút thắt năng lực. Bản này tách đôi theo đường ranh tự nhiên nhất: **đặc trưng bảng và mô hình hành vi** tách khỏi **đồ thị và agent**.

| Hạng mục | Chủ trì | Ghi chú |
|---|---|---|
| Chuyển CSV sang Parquet, khoá tài khoản, kiểm tra chất lượng | Hường | Chặn mọi việc phía sau |
| Chia tập và bộ kiểm thử chống rò rỉ | Hường | §3 |
| Bảng đặc trưng hành vi cửa sổ trượt | Hường | Đầu ra dùng chung, không phải sản phẩm phụ |
| Sinh hồ sơ khách hàng + nhãn T10 | Hường | Mục 5 DAT-001 |
| Isolation Forest + hiệu chỉnh ngưỡng | Hường | Nhánh B |
| Bộ luật ngưỡng (đường cơ sở) | Hường | **Phải xong và đóng băng trước mọi việc ML** |
| Dựng đồ thị, chu trình, cụm, trung chuyển | Hiển | Nhánh C |
| Đối soát 493 pattern IBM sang T01–T10 | Hiển | Quyết định phạm vi cam kết |
| Lớp hợp nhất điểm và phân rã đóng góp | Hiển | QD8, NT7 |
| Lớp bằng chứng và evidence ledger | Hiển | §6 |
| Agent LangGraph, bộ kiểm chứng | Hiển | ARC-001 Hình 4 |
| Đối chiếu danh sách trừng phạt | Hường (nếu Hiển quá tải) | Hạng mục chuyển giao được, DAT-001 mục 1 |

**Giao diện giữa hai người là một file duy nhất:** bảng đặc trưng mức tài khoản, khoá `(account_key, as_of_ts)`. Hường sinh ra, Hiển tiêu thụ. Chốt schema trong ngày đầu tiên, trước khi ai viết code.

---

## 1. Nguồn dữ liệu

### 1.1. [LỆCH] Chốt dùng HI-Medium

DAT-001 §3.1 chọn LI-Small với lý do bản HI cho chỉ số "đẹp giả tạo". Quyết định ngày 08/08/2026 đổi sang **HI-Medium**, vì ba lý do đo được:

| | LI-Small | HI-Medium |
|---|---:|---:|
| Giao dịch | ~7 triệu | **31.898.238** |
| Tài khoản | ~705 nghìn | **2.077.023** |
| Dòng nhãn dương | ~3.500 | **35.230** |
| Tỉ lệ nền | ~0,05% | **0,1105%** |

1. **Gấp mười lần số mẫu dương.** Với cách chia ở ML-002 §2.1, tập test giữ được khoảng 3.500 mẫu dương mức giao dịch và ~4.200 tài khoản dương, thay vì vài trăm. Ở cỡ vài trăm, PR-AUC dao động đủ mạnh để hai model khác nhau thật sự vẫn không phân biệt được. Đây là lý do chính.
2. **Chênh lệch tỉ lệ nền chỉ 2,2 lần.** Cả 0,05% lẫn 0,11% đều nằm sâu trong vùng cực kỳ mất cân bằng; không có bản nào biến bài toán thành dễ. Lo ngại của §3.1 là có thật nhưng nhỏ hơn lợi ích thống kê ở điểm 1.
3. **Đã profiling đầy đủ.** Mọi con số ở §1.3 là đo trực tiếp trên file, không phải giả định.

**Cái giá phải trả, ghi rõ để không quên:** mật độ kịch bản rửa tiền trong bản HI cao hơn thực tế, nên mẫu hình dễ tìm hơn. Bù lại bằng hai việc bắt buộc — luôn báo cáo tỉ lệ nền 0,1105% ngay cạnh mọi chỉ số, và thực thi nghiêm §4.2 về `Payment Format`. Khi hội đồng hỏi tỉ lệ nền, câu trả lời là "0,11%, cao hơn khoảng hai lần so với tỉ lệ thường thấy ở một ngân hàng thật, và chúng tôi công bố con số này chứ không giấu".

### 1.2. Nguồn và checksum

| File | Kích thước | Nội dung |
|---|---:|---|
| `HI-Medium_Trans.csv` | 3.031.783.420 B | 31.898.238 giao dịch, 11 cột |
| `HI-Medium_accounts.csv` | 145.008.642 B | 2.087.786 dòng — tên ngân hàng, mã ngân hàng, số tài khoản, mã pháp nhân, tên pháp nhân |
| `HI-Medium_Patterns.txt` | 407.882 B | 493 instance kịch bản rửa tiền có nhãn |

SHA-256 của file giao dịch: `3126afb8155e7c8815d62bc5370549a7b5ae6bf7dfe872b3cd7813e66a3d7ff5`.

Mọi báo cáo kết quả phải trích checksum này. Ba file nằm ở `data/raw/ibm-aml/`, **không sửa, mở read-only**. Giấy phép CDLA-Sharing-1.0, ghi nguồn trong README (DAT-001 §3.2).

`HI-Medium_accounts.csv` cho mã pháp nhân và tên pháp nhân — đủ để một vụ việc có chủ thể trên console, không chỉ là dãy số tài khoản.

### 1.3. Số liệu đã đo — dùng trực tiếp, không đo lại

**Lược đồ.** 11 cột, **hai cột đều tên `Account`**. Đọc **theo vị trí**, không theo tên: `pandas` đổi tên thành `Account.1`, `csv.DictReader` âm thầm vứt một cột. `src/aml/csvsource.py` đã đọc theo vị trí và kiểm tra header — dùng lại, đừng viết lại.

**Thời gian.** 2022/09/01 00:00 → 2022/09/28 15:58. **Span 27,67 ngày.** Đây là ràng buộc nặng nhất của cả dự án; xem §3.1 và §4.1.

**Định danh.** 2.076.999 số tài khoản riêng biệt, 2.077.023 khoá `bank:account`, 24 trùng chéo ngân hàng. Mã ngân hàng **lệch zero-padding**: `020` và `0020` là cùng một ngân hàng — trên 3 triệu dòng đầu, 71.822 chuỗi thô rút còn 71.773 sau khi strip. **Mọi phép ghép phải strip leading zeros trước.**

**Hub.** Ngân hàng `070` xuất hiện trên 2.979.311 chân giao dịch, hơn một bậc so với ngân hàng kế tiếp (`012`, 240.541). Tài khoản bận nhất có 1.083.821 giao dịch. Đây là hạ tầng thanh toán, không phải khách hàng.

**Số tiền.** Trải 18 bậc độ lớn: min 0,000001 — trung vị ≈ 1.496 — p99 ≈ 10.592.537 — max 8,16 × 10¹². Phần lớn độ trải là do **trộn 15 đơn vị tiền tệ** (Bitcoin 6 chữ số thập phân, Yen hàng nghìn tỷ), **không có VND**. 485.144 dòng (1,52%) có số tiền trả khác số tiền nhận, gần trùng khớp với số dòng chéo tiền tệ.

> Mọi thống kê số tiền không điều kiện theo `currency` là vô nghĩa. Chuẩn hoá trong từng đơn vị, hoặc dùng tỉ lệ nội bộ tài khoản.

**Phân bố hoạt động mỗi tài khoản.**

| | p25 | trung vị | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|
| Số giao dịch | 3 | **7** | 42 | 114 | 1.083.821 |
| Số ngày hoạt động | 2 | **4** | 16 | 16 | 26 |

**Giờ giao dịch phân bố đều** — mỗi giờ từ 01:00 đến 23:00 chiếm 3,88–3,90%. `night_transaction_share` có trung vị 0,40 với p25 0,286 và p95 1,0; kỳ vọng lý thuyết dưới phân bố đều là 8/24 = 0,333. **Toàn bộ độ tán quanh con số đó là nhiễu nhị thức trên vài giao dịch, không phải hành vi.**

**Cạnh tự trỏ.** 2.561.860 dòng (8,03%) có nguồn = đích.

**Kênh thanh toán và nhãn.**

| Kênh | Toàn file | Dòng laundering |
|---|---:|---:|
| Cheque | 12.280.058 (38,5%) | |
| Credit Card | 8.777.816 (27,5%) | |
| **ACH** | **3.868.410 (12,1%)** | **30.746 — 87,3%** |
| Cash | 3.217.531 (10,1%) | |
| Reinvestment | 1.945.611 (6,1%) | 0 |
| Wire | 1.119.774 (3,5%) | 0 |
| Bitcoin | 689.038 (2,2%) | |

P(laundering \| ACH) = 0,795% so với tỉ lệ nền 0,1105% → **lift 7,2 lần từ một cột hạng mục duy nhất**. Wire và Reinvestment không chứa dòng laundering nào. Đây là chữ ký của bộ sinh dữ liệu, không phải đặc điểm của rửa tiền. Xem §4.2.

**Mạng lưới tội phạm.** 493 pattern instance. **219 tài khoản thuộc nhiều hơn một instance** — nên việc gom instance phải là một lượt duyệt thành phần liên thông, không phải vòng lặp theo từng network.

---

## 2. Bốn nhãn và quy tắc chống rò rỉ

Theo DAT-001 mục 8.

| Nhãn | Nguồn | Đánh giá cái gì |
|---|---|---|
| `label_laundering` | Cột `Is Laundering` | Năng lực phát hiện tổng thể |
| `label_typology` | 493 instance trong file pattern, ánh xạ T01–T10 | Độ phủ theo từng typology |
| `label_profile_mismatch` | Tiêm ở bước 4 mục 5 DAT-001 | Riêng T10 — đọc cảnh báo §9.1 |
| `label_watchlist_match` | Lớp liên kết danh tính | Epic E06, tỉ lệ khớp sai |

### Ba bài kiểm thử chống rò rỉ, chạy trong CI

1. **Không cột `label_*` nào trong ma trận đặc trưng.** So tập tên cột đặc trưng với tập cột tiền tố `label_`; giao phải rỗng.
2. **Không đặc trưng nào dẫn xuất từ file pattern.** File pattern sinh ra `label_typology`; dùng nó để tính thành viên cụm, độ dài chu trình hay bất cứ gì đưa vào model là rò rỉ gián tiếp mà bài số 1 không bắt được. Mỗi cột đặc trưng phải khai báo nguồn, và không cột nào được ghi nguồn là file pattern.
3. **Không thống kê nào fit trên toàn bộ dữ liệu.** Trung bình, độ lệch chuẩn, phân vị, ngưỡng, tham số scaler — fit trên tập huấn luyện rồi áp cho validation và test. Bao gồm cả bước sinh hồ sơ khách hàng ở mục 5 DAT-001.

Bài số 3 là bài dễ quên nhất và tốn nhất khi phát hiện muộn.

---

## 3. Chia tập

### 3.1. Cửa sổ 27,67 ngày quyết định mọi thứ

Chia 60/20/20 theo thời gian như DAT-001 §4.2 cho ra:

```
TRAIN        16,6 ngày      2022/09/01 → 2022/09/17
VALIDATION    5,5 ngày      2022/09/17 → 2022/09/23
TEST          5,5 ngày      2022/09/23 → 2022/09/28
```

Hệ quả bắt buộc phải chấp nhận:

- **Không có mùa vụ, không có chu kỳ tháng, không có baseline 90 ngày.**
- Cửa sổ đặc trưng dài nhất dùng được là **14 ngày**; cửa sổ 30 ngày bằng gần trọn bộ dữ liệu nên là hằng số, không phải đặc trưng.
- Trong 5,5 ngày test, đặc trưng vẫn được nhìn lịch sử trước mốc cắt — ngân hàng thật cũng biết quá khứ — nhưng nghĩa là train và test **không độc lập ở mức tài khoản**. Phải đo và báo cáo, không phải giấu.

> **[CẬP NHẬT 08/08/2026 — cách chia này đã bị bác bỏ bằng số liệu.]**
>
> EDA ở FIN-07-ML-002 §2.1 đo phân bố nhãn dương theo ngày và phát hiện nó **sụp đổ ở cuối cửa sổ**: từ đỉnh 2.416 dòng ngày 09/16 xuống còn 3 dòng ngày 09/28. Nguyên nhân là pattern instance trải trung vị 3–7 ngày nên bộ mô phỏng không tiêm được kịch bản mới ở cuối cửa sổ.
>
> Chia 60/20/20 theo thời gian để lại **khoảng 262 mẫu dương** trong tập test, không phải ~7.000 như ước lượng ban đầu ở bản này. Cỡ đó không đánh giá được.
>
> **Cách chia thay thế — chia theo thành phần liên thông của mạng lưới rồi tới thực thể, 70/10/10/10, giữ cột `time_partition` để đánh giá theo thời gian vẫn làm được.** Chi tiết và lý do ở ML-002 §2.1. Mục §3.2 dưới đây vẫn đúng và trở thành cơ chế chia chính thay vì cơ chế bổ sung.

### 3.2. [LỆCH] Chia theo thời gian một mình không chặn được rò rỉ mạng lưới

Nguyên tắc ND2 giải thích: chia ngẫu nhiên làm rò rỉ tương lai vào quá khứ, **"vì các giao dịch trong cùng một kịch bản rửa tiền nằm rải theo thời gian."**

Chính câu đó chỉ ra vấn đề của cách chia thuần thời gian. Kịch bản nào trải qua mốc cắt sẽ có chân ở cả hai bên: model nhìn thấy nửa đầu mạng lưới khi huấn luyện rồi bị chấm điểm trên nửa sau. Nó học thuộc mạng lưới chứ không học mẫu hình.

Thời gian chặn rò rỉ *thời gian*. Nó không chặn rò rỉ *mạng lưới*. Cần cả hai.

```
Bước 1 — Cắt theo thời gian 60/20/20. Giữ nguyên ND2 và §4.2.

Bước 2 — Với mỗi trong 493 pattern instance, tính khoảng thời gian nó trải qua.
         Instance vắt qua mốc cắt được gán TRỌN VẸN về tập chứa giao dịch
         ĐẦU TIÊN của nó; các giao dịch còn lại bị LOẠI KHỎI TẬP ĐÁNH GIÁ
         ở tập sau. Chúng vẫn dùng làm lịch sử để tính đặc trưng, nhưng
         không xuất hiện như mẫu chấm điểm.

         Vì 219 tài khoản thuộc nhiều instance, bước gom phải là một lượt
         duyệt THÀNH PHẦN LIÊN THÔNG trên đồ thị thành viên, không phải
         vòng lặp theo từng network.

Bước 3 — Báo cáo bắt buộc trong report chia tập:
         · số instance vắt mốc và đã xử lý
         · số tài khoản xuất hiện ở cả train và test
         · số dòng nhãn dương còn lại ở mỗi tập
```

Con số thứ hai không cần bằng không — một tài khoản hoạt động liên tục qua 27 ngày là bình thường. Nhưng phải **biết** nó là bao nhiêu.

### 3.3. Quy tắc nhân quả

> Đặc trưng tại thời điểm `t` chỉ được dùng giao dịch có thời điểm **≤ t**. (DAT-001 §9)

Cách kiểm thực dụng: với mỗi cột, lấy một tài khoản, tính đặc trưng tại `t`, thêm một giao dịch giả tại `t + 1 ngày`, tính lại. Giá trị phải không đổi. Test này bắt gần hết lỗi cửa sổ trượt.

### 3.4. Tập test bị niêm phong

Không dùng trong bất kỳ vòng tinh chỉnh nào cho tới đánh giá cuối ở Sprint 5. Chọn ngưỡng, chọn tham số, chọn trọng số hợp nhất — tất cả trên validation.

Thực thi bằng quy ước thư mục: tập test ở đường dẫn riêng, script huấn luyện không nhận đường dẫn đó làm tham số hợp lệ.

---

## 4. Đặc trưng

**Không đặc trưng nào ngoài danh sách này được đưa vào bất kỳ nhánh nào mà không cập nhật tài liệu và được PM duyệt.**

### 4.1. [LỆCH] Cửa sổ theo tháng phải đổi sang theo tuần

DAT-001 §5.1 định nghĩa "doanh số trung vị **theo tháng**", "phân vị 90 của doanh số **tháng**", "tỉ lệ đối tác mới **theo tháng**". Dữ liệu chỉ có 27,67 ngày — chưa đủ một tháng, và chỉ có đúng một. Ba đại lượng đó không tính được.

Thay bằng cửa sổ tuần, giữ nguyên ý nghĩa nghiệp vụ:

| DAT-001 §5.1 | Thay bằng |
|---|---|
| Doanh số trung vị theo tháng | Doanh số trung vị theo **cửa sổ 7 ngày trượt** |
| Phân vị 90 của doanh số tháng | Phân vị 90 của doanh số **7 ngày** |
| Tỉ lệ đối tác mới theo tháng | Tỉ lệ đối tác mới trong **7 ngày** |
| Cửa sổ 1 / 7 / **30** ngày (§9) | Cửa sổ **1 / 3 / 7 / 14** ngày |

Tương tự, `expected_monthly_volume` ở mục 5.3 DAT-001 đổi thành `expected_weekly_volume`, hoặc giữ tên tháng nhưng ngoại suy từ tuần và ghi rõ là ngoại suy.

### 4.2. Được phép

| Nhóm | Đặc trưng | Typology | Điều kiện |
|---|---|---|---|
| **Cường độ** | Doanh số cửa sổ 1/3/7/14 ngày; số giao dịch; trung vị; phân vị 90 | T01, T10 | Chuẩn hoá trong từng `currency` |
| **Cận ngưỡng** | Tỉ lệ giao dịch trong dải sát dưới ngưỡng; độ lệch chuẩn số tiền; số lần lặp trong cửa sổ | T01 | Ngưỡng định nghĩa ở §4.4 |
| **Luân chuyển** | Tỉ lệ tiền ra / tiền vào; thời gian lưu tiền trung vị; số dư cuối ngày | T02, T05 | Thời gian lưu tiền là **hiệu hai mốc** — hợp lệ kể cả khi giờ trong ngày là nhiễu |
| **Mạng lưới** | Bậc vào, bậc ra, tỉ lệ đối tác mới, PageRank, chỉ số cụm | T02, T03, T04 | Trên đồ thị đã loại cạnh tự trỏ và loại hub; xem §5.2 về chi phí |
| **Chu trình** | Thuộc chu trình hay không, độ dài, giá trị, độ trễ giữa các bước | T03 | Phát hiện bằng thuật toán, **tuyệt đối không đọc file pattern** |
| **Lệch hồ sơ** | Doanh số thực tế / doanh số kỳ vọng khai báo; lệch so với nguyên mẫu | T10 | Đọc §9.1 trước khi báo cáo bất kỳ con số nào |
| **Vòng đời** | Số ngày hoạt động, tuổi tài khoản tại thời điểm xét, khoảng cách giao dịch đầu–cuối | T02, T05 | Tối đa 27 ngày, đừng kỳ vọng hơn |
| **Liên ngân hàng** | Tỉ lệ giao dịch có ngân hàng gửi khác ngân hàng nhận | T04, T08 | Sau khi strip zero-padding |
| **Tiền tệ** | Số đơn vị tiền tệ riêng biệt; có giao dịch chéo tiền tệ hay không | T03, T06 | Xem cảnh báo §9.3 |

### 4.3. Bị loại

| Bị loại | Lý do | Gỡ khi nào |
|---|---|---|
| Mọi cột `label_*` | ND1 | Không bao giờ |
| Bất cứ gì dẫn xuất từ file pattern | Rò rỉ gián tiếp qua `label_typology` | Không bao giờ |
| **`Payment Format` / `channel` làm đặc trưng model** | **Đo được: lift 7,2 lần theo nhãn. 87,3% dòng laundering là ACH trong khi ACH chỉ chiếm 12,1% toàn file; Wire và Reinvestment không có dòng nào** | **Không bao giờ — đã đo, không còn gì để chờ** |
| Đặc trưng theo **giờ trong ngày** (tỉ lệ giao dịch đêm, ngoài giờ) | Đo được: giờ phân bố đều 3,88–3,90%. Độ tán quanh 8/24 là nhiễu nhị thức | Không bao giờ trên bộ này |
| Cửa sổ 30 ngày và mọi đại lượng theo tháng | Bằng gần trọn bộ dữ liệu 27,67 ngày → hằng số | Không |
| Tài khoản và ngân hàng kiểu hub | Bank `070` chiếm 2,98 triệu chân; tài khoản bận nhất 1,08 triệu giao dịch | Không — loại vĩnh viễn, ghi lại số lượng đã loại |
| Số tiền chưa điều kiện theo `currency` | Trải 18 bậc độ lớn do trộn đơn vị | Không |
| Cạnh tự trỏ | 8,03% dòng, làm lệch bậc vào/ra | Không — loại trước khi dựng đồ thị |

**[LỆCH] về `Payment Format`.** DAT-001 §4.1 ánh xạ `Payment Format → transaction.channel` và giữ lại. Việc **lưu** cột này là đúng: cần cho gán nguyên mẫu khách hàng (§5.1 DAT-001) và cần để hiển thị trong hồ sơ vụ việc. Điều tài liệu này cấm hẹp hơn — **không đưa vào ma trận đặc trưng của model phát hiện**. Lưu và hiển thị vẫn giữ nguyên.

Nếu để cột này trong đặc trưng, kết quả sẽ rất đẹp và đo bộ sinh dữ liệu chứ không đo rửa tiền. Tệ hơn con số sai: nó đặt ra một mốc mà các model trung thực về sau không vượt được.

### 4.4. Ngưỡng báo cáo cho T01

BUS-001 và DAT-001 lấy ngưỡng giao dịch giá trị lớn là **400 triệu VND** (Thông tư 09/2023/TT-NHNN). Dữ liệu IBM có 15 đơn vị tiền tệ và **không có VND**.

**Quy ước:** ngưỡng cận-báo-cáo cho T01 lấy **10.000 USD**, quy đổi tương đương sang từng đơn vị khác, vì bộ mô phỏng IBM mang đặc trưng thị trường Mỹ. Dải "sát dưới ngưỡng" = **[0,80 · ngưỡng, 1,00 · ngưỡng)**.

Ghi thành giả định có tên `ASSUME_CTR_THRESHOLD_USD`, đặt trong file cấu hình **không phải trong mã nguồn**. Khi triển khai tại ngân hàng Việt Nam, đổi sang 400 triệu VND chỉ bằng sửa cấu hình.

---

## 5. Chiến lược huấn luyện

Phần này trả lời câu "huấn luyện như thế nào là tốt nhất cho dự án", với ràng buộc thật: 31,9 triệu dòng, 2,08 triệu tài khoản, 27,67 ngày, 5 tuần làm.

### 5.1. Đơn vị dự đoán là tài khoản, không phải giao dịch

Nhãn `Is Laundering` gắn với **giao dịch**. Nhưng hàng đợi mà phân tích viên xử lý gắn với **chủ thể** — đó là toàn bộ ý nghĩa của bước gom cảnh báo ở ARC-001 §3.3 và nỗi đau P01.

**Chốt: đơn vị chính là `(account_key, as_of_ts)`.** Nhãn tài khoản = tài khoản có tham gia ít nhất một giao dịch laundering trong cửa sổ đang xét.

- Báo cáo chỉ số ở **cả hai mức**, nhưng mức tài khoản là mức đưa vào cam kết BUS-001 §7.
- **Tỉ lệ nền mức tài khoản đã đo: 2,0152%** — 41.857 tài khoản chạm ít nhất một giao dịch laundering, trên 2.077.023 tài khoản. Gấp 18 lần tỉ lệ mức giao dịch. Đây là con số dùng cho mọi tính toán precision@k. (ML-002 §1.1)

Lợi ích phụ đáng kể: 31,9 triệu dòng rút xuống 2,08 triệu dòng đặc trưng, biến bài toán từ "cần cụm máy" thành "chạy được trên laptop".

### 5.2. Phễu hai tầng — quyết định kỹ thuật quan trọng nhất

Ở quy mô 2,08 triệu nút và ~31,9 triệu cạnh, một số đặc trưng đồ thị **không tính nổi trên toàn đồ thị**:

| Đặc trưng | Trên toàn đồ thị | Cách xử lý |
|---|---|---|
| Bậc vào, bậc ra, tỉ lệ đối tác mới | Rẻ — `groupby`, không cần dựng đồ thị | Tầng 1 |
| PageRank | Chạy được bằng ma trận thưa scipy, vài phút | Tầng 1 |
| Betweenness centrality | **Bất khả thi** ở 2 triệu nút | Tầng 2, hoặc xấp xỉ có lấy mẫu `k` |
| Liệt kê chu trình 2–6 bước | **Bất khả thi** trên 31,9 triệu cạnh | Tầng 2 |
| Phát hiện cộng đồng | Rất chậm | Tầng 2 |

**Thiết kế phễu:**

```
TẦNG 1 — chạy trên toàn bộ 2,08 triệu tài khoản
  · Đặc trưng bảng: cường độ, cận ngưỡng, luân chuyển, vòng đời, tiền tệ
  · Đặc trưng đồ thị rẻ: bậc vào/ra, tỉ lệ đối tác mới, PageRank
  · Luật ngưỡng (nhánh A)
  · Isolation Forest (nhánh B)
  → Lấy ra tập ứng viên: hợp của (luật bật) ∪ (top N% điểm bất thường)
     N chọn sao cho tập ứng viên khoảng 1–2% tài khoản, tức 20–40 nghìn

TẦNG 2 — chỉ chạy trên tập ứng viên và lân cận 1–2 bước của chúng
  · Dựng subgraph bằng NetworkX (đúng tinh thần QD4)
  · Chu trình, cộng đồng, betweenness, tài khoản trung chuyển
  · Đặc trưng đồ thị đắt tiền
  → Hợp nhất ba nhánh, sinh cảnh báo
```

Phễu này không phải thủ thuật kỹ thuật — nó **là cách một ngân hàng thật vận hành**: luật rẻ quét toàn bộ, điều tra sâu chỉ chạy trên cái đã nổi lên. Nó cũng khớp đúng luồng cảnh báo → điều tra ở ARC-001 Hình 3 và QD4 ("phạm vi điều tra luôn là subgraph quanh một chủ thể").

**Cái giá phải đo và báo cáo:** tài khoản nào tầng 1 bỏ sót thì tầng 2 không có cơ hội cứu. Phải báo cáo **recall của tầng 1** — trong số tài khoản có nhãn dương, bao nhiêu phần trăm lọt vào tập ứng viên. Đây là trần recall của cả hệ thống. Nếu tầng 1 chỉ đạt 70% thì dù tầng 2 hoàn hảo, hệ thống cũng chỉ đạt 70%.

Chỉnh N cho tới khi recall tầng 1 ≥ 95% trên validation, rồi mới tối ưu tầng 2.

### 5.3. Chuẩn bị dữ liệu

**Chuyển sang Parquet trước tiên.** CSV 3 GB đọc đi đọc lại hàng chục lần trong quá trình phát triển là lãng phí lớn nhất của cả dự án. Một lượt chuyển sang Parquet có phân vùng theo ngày cho file nhỏ hơn 3–4 lần và đọc nhanh gấp nhiều lần, đọc được từng cột.

```
data/processed/transactions/date=2022-09-01/part-*.parquet
```

Dùng `pyarrow`, đọc CSV theo lô, đọc cột theo vị trí. Một lượt, khoảng 40 giây trên máy cá nhân — đợt profiling trước đọc hết file trong 39,6 giây bằng một lượt streaming.

**Thứ tự dọn dữ liệu, không đảo:**

1. Strip zero-padding mã ngân hàng → ghép khoá `bank:account`.
2. Loại 2,56 triệu cạnh tự trỏ, **ghi lại số lượng**.
3. Loại hub theo ngưỡng số giao dịch, ghi lại số lượng và danh sách.
4. Kiểm tra chất lượng theo mục 10 DAT-001 — số dòng khớp tuyệt đối, tổng giá trị khớp, tỉ lệ nhãn ≈ 0,11%.

### 5.4. Ba nhánh phát hiện

**Nhánh A — Luật ngưỡng.** Chủ trì Hường. Phủ T01 (cận ngưỡng, cộng dồn cửa sổ 24h/7 ngày), T05 (thời gian lưu tiền ngắn, doanh số ngày lớn nhưng số dư nhỏ), lọc CTR. Mỗi luật có mã riêng, ngưỡng trong cấu hình, khi bật ghi lý do kèm giá trị đã vượt.

Nhánh này **đồng thời là đường cơ sở benchmark** (§7). Phải xong và **đóng băng bằng tag git** trước khi bắt đầu bất kỳ việc ML nào — tinh chỉnh nó song song với model thì con số "giảm 50% báo động giả" không còn nghĩa.

**Nhánh B — Isolation Forest.** Chủ trì Hường. `sklearn.ensemble.IsolationForest` trên bảng đặc trưng mức tài khoản.

Chọn không giám sát là có chủ ý: tỉ lệ nhãn dương quá thấp để huấn luyện có giám sát ổn định, và khi triển khai thật thì ngân hàng không có nhãn.

- `n_estimators=200`, `max_samples=256` (mặc định 'auto' — ở 2 triệu dòng nên đặt tường minh), `n_jobs=-1`, `random_state` cố định (ND5).
- **`contamination` không được đặt bằng tỉ lệ nhãn — đó là rò rỉ.** Đặt theo năng lực xử lý của đội, ví dụ 0,5%, và ghi là tham số vận hành chứ không phải tham số học.
- Fit trên train, transform cho validation và test.
- Đóng góp từng đặc trưng: độ dài đường đi trung bình theo từng chiều, hoặc SHAP nếu kịp. Cần cho NT7.

**Nhánh C — Đồ thị.** Chủ trì Hiển. NetworkX trên subgraph tầng 2 (QD4). Phủ T02, T03, T04: chu trình có hướng độ dài 2–6 kèm tổng giá trị và độ trễ; tài khoản trung chuyển (tỉ lệ ra/vào ≈ 1, lưu tiền ngắn, bậc vào và ra đều lớn); gom vào/toả ra (đột biến bậc, tỉ lệ đối tác mới cao); cộng đồng và chỉ số trung tâm.

### 5.5. Hợp nhất điểm

Theo QD8: tổng có trọng số, trọng số trong cấu hình, kèm phân rã đóng góp.

```
risk_score = w_rule · s_rule + w_anomaly · s_anomaly + w_graph · s_graph
```

Ba điểm thành phần đưa về cùng thang [0, 1] bằng **phân vị trên tập huấn luyện**, không dùng min-max — với đuôi phân bố dài 18 bậc độ lớn, một ngoại lai làm hỏng min-max hoàn toàn.

Trọng số ban đầu bằng nhau (1/3 mỗi nhánh), tinh chỉnh **trên validation**. Mọi lần đổi trọng số kèm báo cáo ảnh hưởng: bao nhiêu ca thật bị mất trên tập có nhãn (BUS-001 §5.3).

### 5.6. Gom cảnh báo theo chủ thể

Đòn bẩy lớn nhất cho P01 (ARC-001 §3.3). Một tài khoản bật bốn mươi luật phải tạo **một** dòng trong hàng đợi, không phải bốn mươi.

Khoá gom: `account_key` trong một cửa sổ thời gian. Cảnh báo gộp **giữ nguyên toàn bộ danh sách lý do thành phần** — gom để hiển thị, không gom để mất bằng chứng.

Báo cáo riêng **tỉ lệ nén hàng đợi** = số cảnh báo thô / số cảnh báo sau gom.

### 5.7. Hai năng lực phát hiện, và phạm vi áp dụng của từng cái

Hệ thống phải trả lời hai câu hỏi khác nhau, và chúng có phạm vi khác nhau trên bộ dữ liệu này:

**"Tài khoản này bất thường so với các tài khoản cùng hành vi?"** — áp dụng cho **toàn bộ 2,08 triệu tài khoản**. Đây là việc của Isolation Forest cộng với phân nhóm nguyên mẫu ở mục 5.2 DAT-001. Đây là năng lực chính, dùng được rộng nhất.

**"Tài khoản này bất thường so với chính lịch sử của nó?"** — chỉ áp dụng cho tài khoản **đủ lịch sử**. Trung vị là 7 giao dịch trong 4 ngày hoạt động; không dựng nổi nền hành vi từ đó. Đo được: **815.817 tài khoản (39,3%) có bậc tổng ≥ 20** — đó là phạm vi áp dụng của nhánh này. (ML-002 §1.2)

**Không phải lý do để bỏ, mà là lý do để khai báo phạm vi:** nhánh tự-so-sánh chỉ chạy cho tài khoản đủ lịch sử, phần còn lại đi nhánh so-với-nhóm. Ngân hàng thật cũng làm đúng vậy với khách hàng mới. Báo cáo tỉ lệ bao phủ của từng nhánh.

### 5.8. Xử lý mất cân bằng

- **Không SMOTE, không oversampling tổng hợp.** Nội suy giữa hai tài khoản trên các đặc trưng đồ thị tạo ra thực thể bất khả thi — một tài khoản có 3,5 chu trình.
- Với model tham chiếu có giám sát: dùng `scale_pos_weight` hoặc `class_weight='balanced'`.
- **Tuyệt đối không resample validation và test.** Chỉ số phải đo trên tỉ lệ nền tự nhiên; resample tập đánh giá là cách nhanh nhất để có một con số đẹp vô nghĩa.
- Undersampling lớp âm ở tập train thì được, nhưng phải hiệu chỉnh lại xác suất đầu ra trước khi so ngưỡng.

### 5.9. Cross-validation

Với 27,67 ngày, k-fold theo thời gian là mỏng — 5 fold cho ra fold 5,5 ngày mỗi cái, và fold đầu không đủ lịch sử để tính đặc trưng 14 ngày.

**Chốt:** một lần chia theo thời gian như §3.1, cộng với **bootstrap khoảng tin cậy** trên tập đánh giá, cộng với **lặp lại 5 lần bằng 5 seed khác nhau** để đo phương sai do khởi tạo model. Đừng giả vờ làm 5-fold temporal CV trên 27 ngày.

### 5.10. Tái lập (ND5)

Một lệnh dựng lại toàn bộ từ đầu; chạy hai lần cùng seed cho kết quả **giống hệt**. Nghĩa là: seed cố định ở mọi nguồn ngẫu nhiên (numpy, sklearn, bước sinh hồ sơ, bước lấy mẫu), thứ tự đọc file tất định, không dùng `set` hay `dict` iteration order làm cơ sở cho bất kỳ phép chọn nào.

Kiểm bằng cách so checksum của bảng đặc trưng và của file điểm số giữa hai lần chạy.

### 5.11. [BỔ SUNG] Model tham chiếu — chỉ để đo, không triển khai

QD8 đã loại phương án "một mô hình đầu-cuối duy nhất" vì không giải thích được. Tài liệu này không mở lại quyết định đó.

Đề nghị huấn luyện thêm **một mô hình có giám sát (LightGBM) làm dụng cụ đo** — không nằm trong đường sinh cảnh báo, không lên giao diện, không vào hồ sơ nghi vấn. Hai công dụng:

1. **Trần tín hiệu.** Cho biết dữ liệu này tối đa học được đến đâu. Nếu điểm hợp nhất ba nhánh đạt PR-AUC 0,30 mà tham chiếu đạt 0,32, kiến trúc ba nhánh không bỏ sót gì đáng kể. Nếu tham chiếu đạt 0,70, có tín hiệu chưa bắt được và đáng đi tìm.
2. **Máy dò rò rỉ.** PR-AUC gần 1,0 nghĩa là gần như chắc chắn có rò rỉ nhãn ở đâu đó. Đây là cách rẻ nhất phát hiện RM1, và nó bắt được cả loại rò rỉ mà bài kiểm thử tên cột không thấy.

Chi phí: khoảng nửa ngày. Giá trị: một con số để trả lời "sao không dùng deep learning cho mạnh hơn" bằng dữ liệu thay vì bằng quan điểm.

---

## 6. Bằng chứng trả về cùng kết quả

Nối mô hình vào NT1, NT7 và nỗi đau P09, P10.

### 6.1. Mỗi cảnh báo mang tối thiểu ba yếu tố đóng góp có giá trị số

NT7 quy định mọi cảnh báo trả về **≥ 3 yếu tố đóng góp kèm trọng số**. Cụ thể hoá thành bản ghi `alert_reason`:

| Trường | Nội dung |
|---|---|
| `alert_id` | Cảnh báo nào |
| `factor_code` | `NEAR_THRESHOLD_RATIO`, `CYCLE_LENGTH_4`, `IF_ANOMALY_SCORE`, … |
| `factor_value` | Giá trị số thực tế đã quan sát |
| `factor_weight` | Đóng góp vào điểm hợp nhất |
| `branch` | `RULE` \| `ANOMALY` \| `GRAPH` |
| `evidence_refs` | Danh sách mã bản ghi gốc, **tối thiểu một** |

Cảnh báo có ít hơn ba `alert_reason` không được đẩy lên hàng đợi. Ràng buộc ở tầng dịch vụ, kiểm được bằng test.

### 6.2. Mã bằng chứng gắn từ tầng công cụ

Theo QD1: agent không truy vấn thẳng cơ sở dữ liệu mà đi qua bộ công cụ chỉ đọc. Đó là nơi **duy nhất** gắn mã bằng chứng, và mã đó là khoá bất biến vào evidence ledger.

Hợp đồng đã có trong repo: `contracts/agent/structured-case-output.v1.schema.json` bắt buộc mỗi `claim` có `evidence_refs` tối thiểu một phần tử và cờ `fact_or_inference`. Model không cần biết schema này, nhưng **mọi con số model sinh ra phải truy được về bản ghi đã tính ra nó**, nếu không bộ kiểm chứng sẽ chặn ở lớp ba.

Thực hiện: mỗi giá trị đặc trưng lưu kèm danh sách `transaction_id` đã tham gia tính. Với cửa sổ trượt thì đó là danh sách giao dịch trong cửa sổ. Đây là chi phí lưu trữ có thật, và là cái giá của NT1.

### 6.3. Ba lớp bảo vệ, chỉ lớp ba cưỡng chế được

Theo ARC-001 §5.2. Với hai người làm mô hình, phần liên quan là: mọi con số trong hồ sơ phải khớp **tuyệt đối** với truy vấn độc lập — không phải "sai số nhỏ", mà bằng không. Nếu lớp ba báo lệch, lỗi nằm ở phía tính đặc trưng chứ không phải phía agent.

---

## 7. Benchmark — so với cái gì

### 7.1. Đường cơ sở là bộ luật cứng, bị đóng băng

BUS-001 §7 cam kết "tỉ lệ báo động giả giảm ≥ 50% so với đường cơ sở luật cứng". Muốn có nghĩa thì đường cơ sở phải: xong **trước** khi bắt đầu ML; **đóng băng** bằng tag git; chạy trên **đúng cùng dữ liệu và cùng cách chia**; kết quả lưu artifact có checksum.

Nó mô phỏng đúng thứ một ngân hàng đang chạy hôm nay, nên là mốc so sánh hợp lệ về nghiệp vụ, không chỉ về kỹ thuật.

### 7.2. So sánh phải cố định một chiều

Điểm phương pháp quan trọng nhất của cả tài liệu.

Câu "giảm 50% báo động giả" **tự nó vô nghĩa**: chỉ cần nâng ngưỡng là giảm bao nhiêu cũng được, đồng thời ca thật cũng biến mất.

| Cách so | Cố định | Báo cáo |
|---|---|---|
| **A — cùng recall** | Chỉnh ngưỡng model cho recall bằng đúng recall đường cơ sở | Báo động giả giảm bao nhiêu phần trăm |
| **B — cùng khối lượng** | Chỉnh ngưỡng cho số cảnh báo/ngày bằng đường cơ sở | Precision và recall tăng bao nhiêu |

Cách A trả lời cam kết BUS-001 §7. Cách B trả lời câu hỏi thực tế của trưởng bộ phận tuân thủ: "cùng chừng đó người, tôi bắt được nhiều hơn bao nhiêu?"

Con số nào báo cáo mà không nói rõ đang cố định chiều nào đều phải bị trả lại.

---

## 8. Bộ chỉ số đánh giá

### 8.1. Chất lượng phát hiện

| Chỉ số | Mức | Mục tiêu | Ghi chú |
|---|---|---|---|
| **PR-AUC** (average precision) | Tài khoản **và** giao dịch | Báo cáo cả hai | Chỉ số chính. Ở tỉ lệ 0,11% đây là chỉ số duy nhất phản ánh đúng độ khó |
| **Precision@k** | Tài khoản | k = năng lực xử lý thật của đội | Con số ngân hàng thực sự mua |
| **Recall theo typology** | Instance | **≥ 85% cho T01–T05** | Dùng `label_typology`. Cam kết BUS-001 §7 |
| **Recall tầng 1 của phễu** | Tài khoản | **≥ 95%** | Trần recall của cả hệ thống, §5.2 |
| **ROC-AUC** | — | Chỉ báo cáo phụ | Ở mức mất cân bằng này ROC-AUC đẹp một cách vô nghĩa. Không dùng làm chỉ số chính, không đưa lên slide |
| **Accuracy** | — | **Cấm báo cáo** | Đoán toàn âm đã đạt 99,89% |

**Khoảng tin cậy bắt buộc.** Mọi PR-AUC phải kèm **khoảng tin cậy 95% bằng bootstrap 1.000 lần**. Hai model lệch nhau trong khoảng tin cậy thì không được tuyên bố cái nào tốt hơn.

Với cách chia theo mạng lưới (ML-002 §2.1), tập TEST 10% giữ được khoảng 3.500 mẫu dương mức giao dịch và ~4.200 tài khoản dương — đủ cho PR-AUC ổn định. Đây là lợi ích cụ thể của việc chọn HI-Medium: ở LI-Small con số tương ứng chỉ vài trăm.

### 8.2. So với đường cơ sở

| Chỉ số | Mục tiêu | Điều kiện |
|---|---|---|
| Giảm báo động giả | ≥ 50% | **Ở cùng recall** (§7.2 cách A) |
| Tăng precision | Báo cáo | Ở cùng khối lượng cảnh báo (§7.2 cách B) |
| Tỉ lệ nén hàng đợi | Báo cáo | Cảnh báo thô / cảnh báo sau gom |

### 8.3. Đối chiếu danh sách (epic E06)

| Chỉ số | Mục tiêu | Nguồn |
|---|---|---|
| Nhận diện đúng trên bộ biến thể tên | ≥ 95% | DAT-001 §7.2 |
| Tỉ lệ khớp sai trên nhóm `near_miss` | Báo cáo, càng thấp càng tốt | DAT-001 mục 6 |
| Nhóm `near_miss` chiếm bao nhiêu | ~2% | Nghiệm thu DAT-001 mục 11 |

Nhóm `near_miss` là nhóm quan trọng nhất — không có nó thì không đo được việc giảm khớp sai, vì không tồn tại khớp sai nào để giảm. Đó chính là P07.

### 8.4. Trung thực, hiệu năng, tuân thủ

Lấy nguyên từ BUS-001 §7:

| Nhóm | Chỉ số | Mục tiêu |
|---|---|---|
| Trung thực | Câu khẳng định có trích dẫn hợp lệ | 100% |
| Trung thực | Sai lệch số liệu giữa hồ sơ và nguồn | 0 trường hợp |
| Hiệu năng | Agent hoàn tất một vụ điều tra | ≤ 3 phút |
| Hiệu năng | Dựng và hiển thị đồ thị 5.000 nút | ≤ 5 giây |
| Tuân thủ | Hành động nhạy cảm có bản ghi phê duyệt | 100% |
| Tuân thủ | Tái dựng đầy đủ diễn tiến một vụ việc | Đạt |
| Trải nghiệm | Thời gian xử lý một cảnh báo | Giảm ≥ 40% |

---

## 9. Cạm bẫy đo lường

Sáu chỗ đều tạo ra con số đẹp và sai.

### 9.1. T10 gần như là vòng tròn tự chứng minh

DAT-001 mục 5 sinh `expected_monthly_volume` **quanh doanh số quan sát được**, rồi tiêm lệch 2–3% tài khoản và lấy chính danh sách bị tiêm làm `label_profile_mismatch`.

Hệ quả: đặc trưng "thực tế / kỳ vọng khai báo" ≈ 1 với mọi tài khoản **theo đúng cách nó được sinh ra**, trừ nhóm bị tiêm. Nên nó dự đoán nhãn T10 gần như hoàn hảo — không vì model giỏi, mà vì đặc trưng và nhãn là hai mặt của cùng một phép tiêm.

**Cách báo cáo trung thực:**
- Chỉ số T10 là **kiểm thử đường ống** — xác nhận đặc trưng lệch hồ sơ tính đúng — không phải bằng chứng năng lực phát hiện. Ghi rõ như vậy.
- Phần có giá trị thật: một phần tư số tài khoản bị tiêm được cho trùng với nhãn rửa tiền (DAT-001 §5.4). Đo xem **thêm đặc trưng lệch hồ sơ có cải thiện PR-AUC trên `label_laundering` hay không**. Đó mới là câu hỏi có nghĩa, và câu trả lời có thể là không.
- Không đưa "phát hiện T10 đạt 98%" lên slide mà thiếu đoạn giải thích trên.

### 9.2. Đường tắt kênh thanh toán

Xem §4.3. Đã đo, không còn gì để bàn: lift 7,2 lần. Cột này ở trong đặc trưng thì mọi con số về sau đều hỏng.

### 9.3. Số đơn vị tiền tệ mang một phần chữ ký nhãn

Kịch bản CYCLE của IBM nhảy qua lại giữa các đơn vị tiền tệ, nên "số currency riêng biệt" vừa là hành vi thật vừa là dấu vết bộ sinh. Khác `Payment Format` ở chỗ nó **cũng** thực sự là hành vi — rửa tiền qua biên giới có đổi tiền thật.

Giữ lại làm đặc trưng, nhưng đo lift của nó giống cách đo ACH ở §1.3 và **ghi con số đó vào báo cáo**. Nếu lift ≥ 3 lần thì đưa PM quyết. Đây là lựa chọn có ý thức, không phải chuyện hiển nhiên.

### 9.4. ROC-AUC ở tỉ lệ 0,11%

Model dự đoán gần như toàn âm vẫn cho ROC-AUC trông được. Nếu ai báo ROC-AUC 0,95, câu hỏi tiếp theo là PR-AUC bao nhiêu — và câu trả lời thường khiêm tốn hơn nhiều.

### 9.5. Khoá tài khoản và zero-padding

Mã tài khoản chỉ duy nhất trong phạm vi một ngân hàng (RD2). Không ghép với mã ngân hàng thì hai tài khoản khác nhau bị coi là một, sinh **cạnh giả và chu trình không có thật** — đúng loại chu trình mà T03 đi tìm. Lỗi im lặng: không có thông báo lỗi, chỉ có kết quả sai và trông rất thuyết phục.

Thêm một tầng: `020` và `0020` là cùng ngân hàng. Strip leading zeros **trước** khi ghép khoá.

### 9.6. Chạm tập test sớm

Xem §3.4. Chạm một lần là hỏng vĩnh viễn — không có cách nào "quên" nó đi. Nếu lỡ chạm, cách xử lý duy nhất trung thực là ghi vào báo cáo và coi tập đó là validation thứ hai.

---

## 10. Tiêu chí nghiệm thu phần mô hình

Bổ sung cho DAT-001 mục 11.

- [ ] Ba file HI-Medium có checksum ghi trong manifest; nguồn CDLA-Sharing-1.0 ghi trong README.
- [ ] Chuyển Parquet xong, phân vùng theo ngày; kiểm tra chất lượng mục 10 DAT-001 đều đạt.
- [ ] Tỉ lệ nền **mức tài khoản** đã đo và ghi lại (§5.1).
- [ ] Danh sách đặc trưng (§4) được PM duyệt bằng văn bản trước khi huấn luyện.
- [ ] Ba bài kiểm thử chống rò rỉ (§2) chạy trong CI và đều đạt.
- [ ] Báo cáo chia tập có đủ ba con số ở §3.2 bước 3.
- [ ] Test nhân quả cửa sổ trượt (§3.3) phủ toàn bộ cột đặc trưng.
- [ ] Đường cơ sở luật cứng xong, đóng băng bằng tag git, artifact có checksum.
- [ ] Recall tầng 1 của phễu ≥ 95% trên validation.
- [ ] Bảng ánh xạ 493 pattern sang T01–T10 và báo cáo độ phủ hoàn tất.
- [ ] Điểm hợp nhất có phân rã đóng góp; mọi cảnh báo mang ≥ 3 `alert_reason` có giá trị số.
- [ ] Gom cảnh báo theo chủ thể hoạt động; báo cáo tỉ lệ nén hàng đợi.
- [ ] Model tham chiếu chạy xong; PR-AUC ghi trong báo cáo kèm kết luận về rò rỉ.
- [ ] Mọi PR-AUC kèm khoảng tin cậy bootstrap.
- [ ] So sánh đường cơ sở báo cáo đủ cả cách A và cách B (§7.2).
- [ ] Một lệnh dựng lại toàn bộ; hai lần cùng seed cho checksum giống hệt (ND5).

---

## 11. Thứ tự làm việc

Việc sau phụ thuộc việc trước. Không đảo.

```
1. Chuyển Parquet + dọn khoá, cạnh tự trỏ, hub      Hường   ← chặn tất cả
2. Kiểm tra chất lượng + đo tỉ lệ nền mức tài khoản Hường
3. Chốt danh sách đặc trưng (PM duyệt)              Hường + Bảo   ← điểm chặn
4. Chia tập + bộ kiểm thử chống rò rỉ               Hường
5. Đường cơ sở luật cứng → ĐÓNG BĂNG                Hường   ← điểm chặn
6. Đặc trưng tầng 1 + Isolation Forest              Hường
7. Chốt ngưỡng phễu, đo recall tầng 1 ≥ 95%         Hường   ← điểm chặn
   ────────── từ đây hai nhánh chạy song song ──────────
8a. Model tham chiếu (đo trần + dò rò rỉ)           Hường
8b. Đồ thị tầng 2 + ánh xạ typology                 Hiển
9. Hợp nhất điểm + phân rã đóng góp                 Hiển
10. Gom cảnh báo theo chủ thể                       Hiển
11. Đánh giá cuối trên tập test niêm phong          Cả hai
```

Bước 3, 5 và 7 là ba điểm chặn. Bỏ qua bước 3 thì bước 11 phải làm lại. Bỏ qua bước 5 thì cam kết "giảm 50% báo động giả" không có cách nào chứng minh. Bỏ qua bước 7 thì tầng 2 có thể hoàn hảo mà hệ thống vẫn bỏ sót, và không ai biết vì sao.

---

## 12. Rủi ro riêng của phần mô hình

| Mã | Rủi ro | Mức | Biện pháp |
|---|---|---|---|
| RM1 | Rò rỉ nhãn qua đường gián tiếp mà test tên cột không bắt được | Rất cao | Model tham chiếu §5.11 làm máy dò; PR-AUC gần 1,0 là còi báo động |
| RM2 | Báo cáo T10 như năng lực phát hiện | Cao | §9.1; PM rà soát mọi slide có số T10 |
| RM3 | `Payment Format` lọt vào đặc trưng | Cao | Đã đo lift 7,2 lần; cấm vĩnh viễn, kiểm bằng test danh sách cột |
| RM4 | So sánh đường cơ sở không cố định recall | Cao | §7.2 bắt buộc cả hai cách |
| RM5 | Tầng 1 của phễu bỏ sót, tầng 2 không cứu được | Cao | Đo recall tầng 1 trước khi tối ưu tầng 2; là điểm chặn ở bước 7 |
| RM6 | Cửa sổ 27,67 ngày không đủ cho đặc trưng dài | Trung bình | Đổi sang cửa sổ tuần (§4.1); ghi giới hạn vào manifest, không giấu |
| RM7 | Đồ thị 2,08 triệu nút không tính nổi đặc trưng đắt | Trung bình | Phễu hai tầng §5.2; betweenness chỉ chạy trên subgraph |
| RM8 | Mật độ kịch bản của bản HI cao hơn thực tế | Trung bình | Luôn báo cáo tỉ lệ nền 0,1105% cạnh mọi chỉ số; nêu rõ khi trình bày |
| RM9 | Hiển vẫn quá tải dù đã tách việc | Cao | Đối chiếu danh sách trừng phạt chuyển sang Hường trước tiên |
| RM10 | Chạm tập test sớm | Trung bình | Tách đường dẫn; script huấn luyện không nhận đường dẫn test |

---

## Phụ lục — Những chỗ khác tài liệu gốc

| # | Chỗ lệch | Tài liệu gốc | Tài liệu này | Lý do |
|---|---|---|---|---|
| 1 | Bản dataset | DAT-001 §3.1 chốt LI-Small | **HI-Medium** | Gấp 10 lần mẫu dương; tỉ lệ nền chỉ chênh 2,2 lần; đã profiling đầy đủ. §1.1 |
| 2 | Chia tập | §4.2 chia theo thời gian 60/20/20 | **Chia theo thành phần liên thông mạng lưới + thực thể, 70/10/10/10**, giữ `time_partition` để đánh giá theo thời gian | Đo được: chia theo thời gian để lại 262 mẫu dương ở test vì nhãn dương sụp đổ cuối cửa sổ. ML-002 §2.1 |
| 3 | Cửa sổ đặc trưng | §5.1 và §9 dùng cửa sổ tháng và 30 ngày | Cửa sổ **1/3/7/14 ngày** | Dữ liệu chỉ có 27,67 ngày; cửa sổ tháng không tính được |
| 4 | `Payment Format` | §4.1 ánh xạ và giữ | Giữ để lưu và hiển thị, **cấm** làm đặc trưng model | Đo được lift 7,2 lần theo nhãn |
| 5 | Đặc trưng theo giờ | §9 liệt kê phân bố giờ và tỉ lệ ngoài giờ cho T05, T07 | **Loại**; T05 vẫn phủ được bằng thời gian lưu tiền | Giờ phân bố đều 3,88–3,90%, là nhiễu |
| 6 | Ngưỡng T01 | BUS-001 dùng 400 triệu VND | 10.000 USD quy đổi, giả định có tên, đặt trong cấu hình | Dữ liệu IBM không có VND |
| 7 | Model | ARC-001 QD8 loại mô hình đầu-cuối | Giữ nguyên; thêm model tham chiếu **chỉ để đo** | Không vào đường sinh cảnh báo nên không vi phạm QD8 |
| 8 | Kiến trúc chạy | ARC-001 Hình 3 vẽ ba nhánh song song trên toàn bộ | Ba nhánh, nhưng **phễu hai tầng** | 2,08 triệu nút: betweenness và liệt kê chu trình bất khả thi trên toàn đồ thị. Đúng tinh thần QD4 |
| 9 | Cam kết typology | BUS-001 §7 cam kết độ phủ ≥ 85% cho **T01–T05** | Thu hẹp còn **T02–T04**; T01 và T05 xử lý riêng | Đo được: IBM có 8 typology và **không có cái nào là structuring**. T01 là mẫu hình theo ngưỡng, không phải mẫu hình đồ thị. ML-002 §2.2 |
| 10 | Mẫu số độ phủ | — | Độ phủ typology tính trên **492 instance**, không phải 35.230 dòng nhãn | File pattern chỉ phủ 11,6% số dòng nhãn dương. ML-002 §2.3 |

Mười chỗ này cần PM xác nhận trước khi Hiển và Hường bắt đầu. Chỗ **2, 3, 4, 8 và 9** là năm chỗ nếu bỏ qua thì phải làm lại từ đầu.
