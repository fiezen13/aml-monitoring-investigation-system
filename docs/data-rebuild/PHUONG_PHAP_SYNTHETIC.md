# Phương pháp sinh dữ liệu: IBM làm xương sống, nguồn Việt Nam làm KYC

Tài liệu này giải thích **cách** bộ dữ liệu được sinh ra, chứ không phải nó chứa
gì. Cấu trúc cột nằm ở [CSV_DATA_DICTIONARY.md](CSV_DATA_DICTIONARY.md).

Viết bằng tiếng Việt vì đây là tài liệu để cả nhóm (Bảo, Hường, Hiển) và phía
ngân hàng cùng đọc và phản biện.

---

## 1. Quyết định gốc: tại sao không sinh từ con số ngẫu nhiên

Cách làm cũ (v0.2.0, đã bị xoá ở Phase 0) sinh toàn bộ thế giới ngân hàng từ
bảng tham số. Vấn đề của cách đó không phải là dữ liệu "trông giả" — mà là
**cấu trúc mạng lưới giao dịch là thứ không thể bịa ra một cách đáng tin**.

Một mạng lưới rửa tiền thật có chu trình, có tầng, có fan-in/fan-out, có độ dài
đường đi, có thời gian trễ giữa các chặng. Nếu ta tự sinh những thứ đó theo giả
định của chính mình, thì mô hình học được chính giả định đó — và điểm số cao trên
tập test chỉ chứng minh rằng mô hình đọc được ý đồ của người viết generator.

Nên kiến trúc là:

```text
IBM AML CSV  ──►  hồ sơ hành vi tài khoản  ──►  archetype hành vi
                                                      │
Nguồn công khai VN  ──►  phân phối có điều kiện  ──►  dân số KYC tổng hợp
                                                      │
                                          ghép thống kê (statistical matching)
                                                      │
                                          hiệu chỉnh tiền tệ (VND)
                                                      │
                                          release CSV chuẩn tắc
```

**IBM cung cấp cấu trúc quan hệ và thời gian. Nguồn Việt Nam cung cấp bối cảnh
con người. Không nguồn nào bị dùng cho việc mà nó không chứng minh được.**

---

## 2. Phần IBM: giữ cái gì, bỏ cái gì

### 2.1 Đo trước, dùng sau

Trước khi dùng một dòng nào của IBM, toàn bộ file được đo (Phase 1–2). Việc đo
này tìm ra bốn điều mà nếu không biết thì cả bộ dữ liệu sẽ sai:

| Phát hiện | Hệ quả |
|---|---|
| IBM có **99,7% là doanh nghiệp** — chỉ 3.017 tài khoản cá nhân trên 2.077.023 | Khách hàng bán lẻ VN buộc phải ghép vào hành vi của doanh nghiệp. Đây là **hạn chế lớn nhất** của bộ dữ liệu |
| Cửa sổ quan sát chỉ **27,67 ngày** | Không có mùa vụ tháng, không có baseline 30/60/90 ngày |
| `payment_format` **dự đoán được nhãn rửa tiền** ở mức 7,2× (87% giao dịch rửa tiền là ACH; Wire và Reinvestment không có ca nào) | Không được bê cột này sang. Phải vẽ lại |
| Giờ trong ngày **phân bố đều tuyệt đối** (01:00–23:00 mỗi giờ đúng 3,88–3,90%) | Đặc trưng "giao dịch ban đêm" tính trên IBM là nhiễu, không phải tín hiệu |

Ngoài ra: mã ngân hàng có số 0 đầu **không nhất quán** (`020` và `0020` là cùng
một ngân hàng). Không chuẩn hoá thì mọi phép join đều hỏng âm thầm.

### 2.2 Giữ nguyên

- **Ai trả cho ai** — toàn bộ cạnh của đồ thị
- **Thứ tự thời gian** — tuyệt đối, kể cả trong cùng một ngày
- **Ngày giao dịch** — không đổi
- **Tỷ lệ tương đối giữa các khoản trong cùng một tài khoản**
- **Cấu trúc fan-in / fan-out, chu trình, đường đi nhiều chặng**
- **Nhãn rửa tiền** — nhưng để riêng ở `ground_truth/`, không bao giờ ở Bank View

### 2.3 Thay đổi có chủ đích

| Thứ | Cách thay | Lý do |
|---|---|---|
| Số tiền | Nhân với một hệ số **cố định cho từng tài khoản** | Đưa về VND mà vẫn giữ nguyên mọi tỷ lệ trong tài khoản |
| Payment format | Vẽ lại theo taxonomy VN, điều kiện trên `digital_usage_segment` của khách | Cột gốc rò rỉ nhãn ở 7,2× |
| Giờ trong ngày | Vẽ lại theo đường cong sinh hoạt VN, **giữ nguyên ngày và thứ tự** | Cột gốc không mang tín hiệu nào |
| Định danh | `ACC-*`, `TXN-*`, `CPY-*` | Không để lộ khoá IBM |

### 2.4 Chọn tập con: tại sao phải chọn đồ thị trước, ghép KYC sau

Đây là chỗ dễ sai nhất và tôi đã sai một lần.

Phase 9 ban đầu ghép mỗi khách hàng KYC với một tài khoản IBM chọn **độc lập**
theo độ khớp hành vi. Cách đó chọn *hành vi* thì đúng, nhưng chọn *đồ thị* thì
sai hoàn toàn: 6.000 tài khoản rút ra từ 2,08 triệu gần như không chia sẻ cạnh
nào với nhau. Kết quả đo được: **chỉ 3,8% giao dịch là nội bộ–nội bộ**. Toàn bộ
cấu trúc mạng lưới — thứ duy nhất mà IBM thực sự cho ta — biến mất.

Sửa lại: **chọn đồ thị con trước, rồi ghép KYC lên các tài khoản đã chọn.**

- Hạt giống = các **instance rửa tiền trọn vẹn** (nguyên vẹn, không cắt nửa chu trình)
- Mở rộng 1 bước sang các đối tác giao dịch của chúng
- Kết quả: **22,4% cạnh nội bộ** thay vì 3,8%

Với bản `full` thì câu hỏi này không còn: giữ toàn bộ 2.077.023 tài khoản. Kết
quả đo được: **92,0% sự kiện là nội bộ–nội bộ**, và cấu trúc từng tài khoản khớp
IBM với sai lệch tối đa **0,6%** trên cả sáu chỉ số hình dạng.

---

## 3. Phần Việt Nam: KYC được sinh có điều kiện

### 3.1 Nguyên tắc: không gõ tay một con số phần trăm nào

Mọi con số định hình dân số tổng hợp đều đi qua code, từ một chỉ số có tên, và
phản hồi thô được lưu lại kèm checksum. Lý do rất thực tế: một phần trăm chép
tay từ báo cáo không ai kiểm chứng lại được, và sáu tháng sau không ai nhớ nó
đến từ đâu.

**152 chỉ số** được lấy qua World Bank open data API và cache tại
`data/raw/worldbank/` (164 file JSON, có checksum):

| Nhóm | Nguồn | Dùng cho |
|---|---|---|
| Global Findex 2024 (source 28) | Khảo sát đại diện quốc gia của World Bank | Sở hữu tài khoản, thanh toán số, tiết kiệm, vay, mobile money, lương vào tài khoản |
| WDI — dân số | UN World Population Prospects | Nhóm tuổi 5 năm một, giới tính, thành thị/nông thôn |
| WDI — lao động, thu nhập | ILO modelled estimates, tài khoản quốc gia | Tình trạng việc làm, ngành nghề 3 khu vực, ngũ phân vị thu nhập, GDP/người **bằng VND** |
| Enterprise Surveys VN 2023 | World Bank | Tỷ lệ doanh nghiệp có tín dụng ngân hàng, dùng ngân hàng cho vốn lưu động |

Dùng `NY.GDP.PCAP.CN` (GDP/người tính bằng VND) thay vì quy đổi USD — tránh luôn
một giả định tỷ giá.

### 3.2 Sinh có điều kiện, không sinh độc lập

Đây là điểm khác biệt cốt lõi so với `age = random()`, `income = random()`:

```text
học vấn + việc làm + nơi ở + thu nhập   (đồng thời, bằng IPF)
        └──► nhóm tuổi, giới tính        (độc lập — không nguồn nào liên kết được)
                └──► ngành nghề          (chỉ khi có việc làm)
                        └──► có tài khoản ngân hàng
                                └──► thanh toán số, tiết kiệm, vay
```

**Khối đồng thời dùng IPF (Iterative Proportional Fitting).** Nguồn công bố
*biên* (33,4% là người làm công ăn lương; mỗi ngũ phân vị chiếm 20%) nhưng không
bao giờ công bố *phân phối đồng thời*. Hai lựa chọn tồi: coi các chiều là độc lập
(thì chủ doanh nghiệp nghèo cũng thường như lao động gia đình giàu), hoặc tự viết
bảng đồng thời (thì biên không còn khớp thống kê nào cả).

IPF cho lựa chọn thứ ba: một ma trận mầm mã hoá *hình dạng* của mối liên hệ, rồi
scale hàng/cột luân phiên đến khi biên khớp chính xác. **Bằng chứng ràng buộc
biên, giả định cung cấp mối liên hệ, và hai thứ tách rời nhau** — nên có thể đổi
giả định để kiểm định độ nhạy mà không đụng vào bằng chứng. Ở `strength = 0` nó
tái tạo đúng trạng thái độc lập.

### 3.3 Ghép các chiều Findex: giả định duy nhất phải chấp nhận

Findex công bố mỗi hành vi theo **từng chiều một**. Có tỷ lệ cho phụ nữ, cho
nông thôn, cho 40% nghèo nhất — nhưng **không có** tỷ lệ cho *phụ nữ nông thôn
thuộc 40% nghèo nhất*.

Nên phải giả định, và giả định đó được ghi rõ là `ASSUME_LOGIT_ADDITIVITY`: mỗi
chiều đóng góp một dịch chuyển cộng tính độc lập trong log-odds.

**Cái mất đi là hiệu ứng tương tác.** Bất lợi thật ngoài đời cộng dồn nhau — một
phụ nữ nông thôn học vấn thấp thuộc nhóm nghèo nhất thường thiệt thòi hơn tổng
bốn hiệu ứng riêng lẻ. Mô hình cộng tính trong log-odds đánh giá thấp điều đó
theo đúng cấu trúc của nó.

### 3.4 Hai lỗi âm thầm đã phải sửa

Cả hai đều được phát hiện bằng cách **so đầu ra với nguồn**, không phải bằng suy
luận. Cả hai đều lệch vài điểm phần trăm — đủ nhỏ để lọt qua mắt thường.

**Lỗi 1 — chưa căn giữa (centering).** Logit là hàm phi tuyến, nên log-odds của
tỷ lệ tổng thể **không** bằng trung bình có trọng số của log-odds từng nhóm.
Riêng học vấn: 34% dân số ở mức −1,56 và 66% ở mức +0,24 cho trung bình có trọng
số là −0,37, không phải 0. Cộng sáu chiều như vậy thì trừ mất gần trọn một đơn vị
log-odds của khách hàng trung bình → tỷ lệ có tài khoản ra **62%** trong khi
nguồn công bố **70,6%**.

**Lỗi 2 — bất đẳng thức Jensen.** Căn giữa là cần nhưng chưa đủ. Trung bình của
*xác suất* không bằng xác suất tại *trung bình dịch chuyển*, vì đường logistic
lõm ở trên 0,5 — và chính các tương quan mà IPF cố ý tạo ra làm giãn độ phân tán
và đẩy hai đại lượng đó xa nhau thêm. Sai số còn lại vẫn khoảng 6 điểm.

Cách sửa: **giải hệ số chặn (intercept) bằng chia đôi** sao cho trung bình xác
suất của **dân số thực tế sinh ra** khớp đúng tỷ lệ công bố, giữ nguyên mọi
gradient tương đối — phần mà Findex thực sự đo được.

Kết quả sau khi sửa: cả sáu biên hành vi lệch dưới 0,35 điểm phần trăm.

---

## 4. Chỗ hai thế giới gặp nhau: ghép thống kê

### 4.1 Không có tuyên bố đồng nhất

Một tài khoản IBM **không** được khẳng định *là* một người Việt Nam. Agent KYC
được sinh trước, hành vi kỳ vọng của nó được suy ra từ chính thuộc tính của nó,
rồi mới được ghép với một tài khoản IBM có hành vi tương thích. **Cái chuyển giao
là hình dạng hoạt động; không có gì về danh tính được chuyển giao.**

### 4.2 Hai bước, cố tình minh bạch

Không dùng embedding học được, không dùng matcher nơ-ron — không dùng thứ gì mà
khi hỏng thì không nhìn thấy được.

**Bước 1 — xu hướng archetype.** Thuộc tính của agent ngụ ý kỳ vọng trên 5 chiều
không thứ nguyên: chiều dòng tiền, độ rộng đối tác, nhịp hoạt động, mức độ quốc
tế, độ tập trung công cụ. Chấm điểm với centroid của từng archetype, softmax, rồi
**lấy mẫu** (không lấy argmax).

Lấy mẫu chứ không lấy max là điều bắt buộc: argmax sẽ dồn mọi agent có cùng thuộc
tính vào một archetype và huỷ hoại phương sai trong nhóm — thứ làm cho bộ dữ liệu
đáng để mô hình hoá.

**Bước 2 — ghép theo thứ hạng (rank matching) trong archetype.** Thực thể và tài
khoản đều được sắp theo turnover kỳ vọng rồi ghép theo thứ hạng: khách nghèo nhất
trong nhóm nhận tài khoản turnover thấp nhất, khách giàu nhất nhận cao nhất. Mỗi
tài khoản dùng đúng một lần.

Cách này thay cho tìm-láng-giềng-gần-nhất tham lam. Tham lam chạy được khi pool
còn rỗng và thành bậc hai khi pool đầy — phải bước qua mọi tài khoản đã dùng — và
ở 2 triệu thực thể thì không chạy xong. Rank matching là O(n log n), và với hàm
khoảng cách đơn điệu thì nó còn là **lời giải tối ưu** chứ không phải xấp xỉ.
Tính ngẫu nhiên được giữ bằng cách nhiễu nhẹ giá trị mục tiêu trước khi sắp xếp.

### 4.3 Rò rỉ mà bước ghép phải tránh

Archetype `MULTI_CURRENCY_SELF_CYCLING` mang tỷ lệ tài khoản dính rửa tiền
**gấp 6,67 lần** dân số, vì typology CYCLE của IBM nhảy qua lại giữa các loại
tiền tệ.

Nếu việc gán archetype bị điều khiển bởi bất cứ thứ gì giống một phán đoán rủi ro
— ví dụ đẩy khách thu nhập cao hoặc có hoạt động quốc tế vào archetype đó — thì
thu nhập và mức độ quốc tế sẽ dự đoán được nhãn AML **trước khi** sinh bất kỳ
kịch bản nào, và Phase 14 trở nên không thể phủ định.

Hai lớp phòng vệ: (1) xu hướng chỉ dùng kỳ vọng hành vi, không dùng điểm rủi ro,
không dùng bất kỳ trường nào dẫn xuất từ nhãn; (2) `ASSUME_ARCHETYPE_TEMPERATURE`
giữ việc lấy mẫu đủ "mềm" để mỗi archetype nhận một hỗn hợp thuộc tính KYC rộng.

**Đo lại sau khi ghép:** lift tối đa 2,08×, không có yếu tố nào dự đoán hoàn hảo,
mutual information ≤ 0,0024 bit.

---

## 5. Hiệu chỉnh tiền tệ

### 5.1 Cách sai: nhân tỷ giá

Số tiền của IBM trải 15 loại tiền tệ và 18 bậc độ lớn, trong một thế giới tổng
hợp không có nội dung Việt Nam nào. Nhân với tỷ giá VND cho ra những con số
*trông* như tiền Việt và **không mang ý nghĩa gì**.

### 5.2 Cách làm: một hệ số nhân cho mỗi tài khoản

```text
hệ số = dòng tiền vào mục tiêu (VND/tháng) / dòng tiền vào quan sát được của IBM
```

Vì hệ số **không đổi trong phạm vi một tài khoản**, mọi tỷ lệ nội bộ tài khoản
được giữ nguyên chính xác: cấu trúc fan, cân bằng vào/ra, bội số turnover, thứ tự
và độ lớn tương đối giữa các khoản. Chỉ có đơn vị thay đổi.

Cửa sổ 27,67 ngày được quy về tháng 30 ngày trước khi so sánh — bỏ qua bước này
thì mọi số tiền lệch khoảng 8%, đủ nhỏ để không ai để ý và đủ lớn để sai.

### 5.3 Giả định nằm ở tâm

```text
mục tiêu = thu nhập tháng kỳ vọng
         × ASSUME_HOUSEHOLD_INCOME_RATIO   (GDP/người ≠ thu nhập hộ gia đình)
         × ASSUME_INCOME_TO_TURNOVER       (tiền qua tài khoản so với thu nhập)
```

**`ASSUME_INCOME_TO_TURNOVER` là bản lề của toàn bộ thang tiền tệ, và không nguồn
nào đã lấy được công bố nó.** Không có thống kê nào nối thu nhập khai báo với
lượng tiền chạy qua tài khoản. Nó được đăng ký với `confidence: low` và khoảng
độ nhạy rộng (1,0–3,0), và release nên được sinh ở nhiều mức để **đo** độ nhạy
thay vì khẳng định.

Doanh nghiệp dùng **doanh thu**, không bao giờ dùng phân phối thu nhập cá nhân.
Một hộ kinh doanh quay vòng 30 triệu/tháng và một người làm công lương 30 triệu
là hai con vật khác nhau; cho chúng chung một phân phối thì mọi đặc trưng AML
dựa trên turnover mất hết ý nghĩa.

---

## 6. Chuỗi xuất xứ đầy đủ

Mỗi dòng trong release truy ngược được về byte gốc:

```text
IBM AML CSV (sha256 3126afb8…)
  └─► hồ sơ nguồn      artifacts/source_profiles/ibm_aml_profile.json
      └─► hồ sơ hành vi 2.077.023 tài khoản (không đọc nhãn)
          └─► 5 archetype (ARI subsample 0,998)
              └─► tài khoản đã ghép ─► hệ số hiệu chỉnh ─► giao dịch

World Bank API (152 chỉ số, cache có checksum)
  └─► data/source_registry/distributions/vn_population.yaml   (theo dõi trong Git)
      └─► generator KYC ─► thuộc tính khách hàng
```

`manifest.json` ghi checksum của mọi file, seed, git commit, 29 giả định kèm
khoảng độ nhạy, và 12 hạn chế đã biết.

**Tái tạo được từng byte**: cùng seed → cùng checksum trên toàn bộ file.

---

## 7. Những gì tài liệu này không khẳng định

- **Không khẳng định tỷ lệ rửa tiền thực tế.** `prevalence_claim: false`. Số
  lượng kịch bản là quyết định phủ sóng benchmark. Tỷ lệ thực thể bị gắn cờ là
  hệ quả của cách chọn tập con.
- **Không khẳng định đây là hành vi ngân hàng Việt Nam đã được đo.** Payment
  format, đường cong giờ, cường độ tiền mặt theo ngành — tất cả là giả định,
  không phải phân phối đo được.
- **Không khẳng định khách hàng bán lẻ có hành vi bán lẻ.** IBM 99,7% là doanh
  nghiệp. Đây là hạn chế lớn nhất và không sửa được bằng code.

Ba điều trên là lý do `known_limitations` trong manifest bắt buộc không được rỗng.
