# FIN-07 — Huấn luyện và kết quả trên IBM AML HI-Medium

Tài liệu này ghi lại toàn bộ cách model được huấn luyện và đánh giá trên bộ
HI-Medium, kèm kết quả đo được. Mọi con số trong đây đến từ một lần chạy thật,
có script và file JSON kèm theo, không có số nào gõ tay.

> **Cảnh báo phạm vi:** nhánh lịch sử tên `policy_compliant` trong tài liệu này
> chỉ bỏ `Payment Format` và giờ trong ngày; nó vẫn dùng các amount đã quy đổi
> bằng bảng FX tĩnh. Vì vậy không dùng artifact/kết quả đó làm currency-policy
> release cho MVP. Release giữ native currency nằm tại
> `docs/ml/CURRENCY_NATIVE_EDGE_MVP.md`.

| | |
|---|---|
| Bộ dữ liệu | IBM Transactions for Anti-Money Laundering — HI-Medium |
| Script huấn luyện + đánh giá | `scripts/benchmark_edge_level.py` |
| Script nạp dữ liệu | `scripts/load_ibm_dataset_duckdb.py` |
| Script đánh giá đường dây | `scripts/evaluate_ring_level.py` |
| Báo cáo máy đọc được | `reports/edge-benchmark/hi_medium.json` |

---

## 1. Vì sao không dùng benchmark cũ

Benchmark trước đó của repo (`reports/fusion-v2/benchmark.json`) chấm điểm ở mức
**ảnh chụp tài khoản** — mỗi dòng là một cặp (tài khoản, ngày) với cửa sổ 7 ngày.
Toàn bộ kết quả đã công bố trên bộ IBM AML lại chấm ở mức **giao dịch**. Hai
thang đo khác nhau nên không có cách nào biết model tốt hay dở so với mặt bằng.

Ngoài ra benchmark cũ có một lỗi nghiêm trọng: với LI-Small, dữ liệu giao dịch
thực tế kết thúc ngày 10/09 (từ 11/09 đến 17/09 chỉ còn 148 giao dịch trên tổng
6,1 triệu), nhưng tập validation và test lại được đặt vào khoảng 11–18/09. Cửa
sổ 7 ngày trượt dần ra khỏi dữ liệu; ảnh chụp ngày 18/09 có 164 dòng thì cả 164
đều là dương tính. Mọi con số test cũ đo độ trôi phân phối chứ không đo khả năng
phát hiện.

Benchmark trong tài liệu này chia theo **giao dịch**, nên không dính bẫy đó.

---

## 2. Nạp dữ liệu

ETL gốc của repo (`src/data/etl_transactions.py`) chạy bằng pandas, phù hợp với
LI-Small nhưng cần hàng chục GB RAM cho 31,9 triệu dòng của HI-Medium. Bộ nạp
mới chạy bằng DuckDB, dùng **chung** bảng tỷ giá (`src/data/currency.py`) và
bảng chuẩn hoá kênh (`src/data/schemas.py`) với ETL cũ nên không thể lệch.

Các bước biến đổi:

1. Ghép khoá tài khoản `bank:account`, mã ngân hàng dạng số bị bỏ số 0 đứng đầu
2. Loại giao dịch tự chuyển (người gửi trùng người nhận)
3. Quy đổi mọi loại tiền về USD bằng bảng tỷ giá tĩnh
4. Chuẩn hoá `Payment Format` về 6 giá trị kênh

**Kiểm chứng bộ nạp:** chạy trên LI-Small và đối chiếu với `aml.duckdb` sẵn có.

| | Bộ nạp mới | DuckDB cũ |
|---|---|---|
| Giao dịch | 6.119.572 | 6.119.572 |
| Ca rửa tiền | 3.562 | 3.562 |
| Tài khoản | 576.781 | 576.781 |
| Phân bố 6 kênh | khớp từng con số | — |

Mất 17 giây thay vì chạy ETL đầy đủ.

### Quy mô HI-Medium sau khi nạp

| | |
|---|---|
| Giao dịch (sau khi loại tự chuyển) | 29.336.378 |
| Giao dịch bị loại (tự chuyển) | 2.561.861 |
| Ca rửa tiền | 35.158 |
| Tỷ lệ | 1 trên 834 |
| Tài khoản | 1.758.597 |
| Cặp tài khoản riêng biệt | 2.998.917 |
| Khoảng thời gian | 01/09 → 28/09/2022 |

---

## 3. Giao thức

Theo đúng hai bài báo gốc để số của mình nằm cùng một trục với họ.

| Hạng mục | Giá trị |
|---|---|
| Đơn vị | một dòng = một giao dịch |
| Chia tập | 60/20/20 theo thời gian |
| Chỉ số so sánh | F1 của lớp thiểu số |
| Ngưỡng | chọn trên validation để F1 cao nhất, áp một lần lên test |
| Siêu tham số | chọn trên validation; test chỉ chạy sau khi đã khoá |
| Sai số | trung bình ± độ lệch chuẩn trên 5 seed |
| Thuật toán | `HistGradientBoostingClassifier` (tương đương LightGBM) |

Nguồn: Altman và cộng sự, NeurIPS 2023 ([arXiv:2306.16424](https://arxiv.org/abs/2306.16424));
Blanuša và cộng sự, ICAIF 2024 ([arXiv:2402.08593](https://arxiv.org/abs/2402.08593)).

### Mốc cắt

Điểm cắt lấy theo **phân vị của phân bố giao dịch**, không theo khoảng lịch.
Đây là điểm khác biệt quan trọng: chia theo khoảng lịch trên LI-Small làm tập
test còn 50 giao dịch, còn chia theo phân vị cho tập test dùng được.

Cách tính cũng tránh một phép sắp xếp toàn cục: `row_number() OVER (ORDER BY ...)`
trên 29,3 triệu dòng không chạy xong trong 10 phút và làm DuckDB đổ 30 GB ra đĩa.
Thay bằng hai mốc thời gian phân vị rồi so sánh trực tiếp — 3,5 giây, tỷ lệ vẫn
đúng 60/20/20.

| Tập | Giao dịch | Ca rửa tiền | Tỷ lệ |
|---|---|---|---|
| train | 17.602.032 | 16.632 | 1 trên 1.058 |
| val | 5.867.736 | 8.434 | 1 trên 695 |
| test | 5.866.610 | 10.092 | 1 trên 581 |

**Lưu ý khi đọc kết quả:** mật độ ca bẩn **tăng dần theo thời gian**. Vì chia
theo thời gian nên tập test rơi đúng vào đoạn dày ca bẩn nhất, dễ hơn tập train.
Bài báo cũng chia y hệt, nhưng đừng đọc kết quả test là độ chính xác ngoài đời.

---

## 4. Tính nhân quả — không rò rỉ tương lai

Mọi đặc trưng đồ thị của một giao dịch tại thời điểm `t` chỉ tính từ giao dịch
**trước** `t`:

- Cửa sổ trượt 7 ngày và 24 giờ kết thúc **trước `t` một phút**, nên một giao
  dịch không nhìn thấy chính nó hay các giao dịch cùng phút
- Đặc trưng chu trình chỉ đếm cấu trúc mà **mọi cạnh đều đã xuất hiện trước `t`**
  (cột `ready_ts` trong bảng `triangles`)
- Ngưỡng và siêu tham số chọn trên validation, test chạy đúng một lượt
- `label_laundering` không có mặt trong ma trận đặc trưng

Script có chốt chặn: nếu số dòng sau khi dựng đặc trưng khác số giao dịch gốc
thì báo lỗi ngay, vì đó là dấu hiệu một phép join đang nhân hàng. Chốt này đã
bắt được một lỗi thật trong quá trình phát triển.

---

## 5. Đặc trưng

### Nhóm cơ bản (8)

Số tiền, số tiền nhận, tỷ lệ quy đổi, khác ngân hàng, khác loại tiền, kênh
thanh toán, giờ, thứ trong tuần.

### Nhóm đồ thị (26)

Dựng lại ý tưởng Graph Feature Preprocessor của IBM bằng DuckDB, vì `snapml`
không có bản cho Python 3.14:

- **Thống kê theo đỉnh:** số lượng, tổng, giá trị lớn nhất của tiền vào/ra cho
  cả bên gửi và bên nhận, trong 7 ngày và 24 giờ
- **Mẫu hình một bước:** fan-in của bên nhận, fan-out của bên gửi, cờ
  `is_new_pair` (cặp đối tác giao dịch lần đầu)
- **Mẫu hình nhiều bước:** số chu trình độ dài 2 và 3, chỉ số gather-scatter
- **Tỷ lệ bảo toàn số tiền:** tiền ra trên tiền vào 24 giờ, tiền chuyển trên
  khoản vào lớn nhất 24 giờ, tỷ lệ vào/ra 7 ngày, kèm hai cờ "mẫu số bằng 0"

Đếm chu trình độ dài 3 bỏ qua đỉnh trung gian có bậc trên 200. 15 tài khoản
trung tâm chiếm phần lớn chi phí duyệt đường đi 2 bước; cắt ở 200 vẫn giữ 99,96%
tài khoản và chỉ loại 29 trên 5.303 tài khoản có dính rửa tiền.

### Đặc trưng bị EDA của nhóm cấm

`docs/ml/FIN-07-ML-002` cấm hai đặc trưng:

| Đặc trưng | Lý do cấm | Đo lại trên HI-Medium |
|---|---|---|
| `channel_code` (Payment Format) | Lift 6,37× trên LI-Small | **Lift 7,55×**, 87,25% ca rửa tiền qua ACH, kênh WIRE không có ca nào |
| `hour_of_day` | Giờ 00 là artifact bộ sinh, gấp 3,3× | **Không lặp lại** trên HI-Medium: giờ 00 chiếm 3,998%, các giờ khác 4,174% |

Hai đặc trưng này **vẫn nằm trong nhóm cơ bản** để số của mình so được với bài
báo (bài báo có dùng chúng), nhưng có một nhánh `policy_compliant` bỏ chúng để
**đo** chi phí của việc tuân thủ lệnh cấm thay vì giả định.

---

## 6. Cổng kiểm tra chất lượng dữ liệu

Chạy **trước** khi huấn luyện, ném lỗi và dừng nếu phát hiện bất thường, thay vì
âm thầm thay `inf`/`NaN` bằng 0 như bản đầu.

Kiểm tra trên bảng nguồn: giá trị thiếu ở cột thời gian / tài khoản / số tiền,
số tiền ≤ 0, giao dịch tự chuyển còn sót, nhãn ngoài {0,1}, trùng
`transaction_id`. Kiểm tra trên ma trận đặc trưng: đếm ô `NaN` và `inf`, và
liệt kê đặc trưng có giá trị vượt 1e12.

Kết quả trên HI-Medium: **không có giá trị thiếu, không có số tiền ≤ 0, không
trùng khoá, không kênh nào không map được.** Dữ liệu tổng hợp của IBM sạch theo
thiết kế.

### Ngoại lai là tín hiệu, không phải nhiễu

Phân bố số tiền rất lệch: trung vị 858 USD, phân vị 99,99 là 336 triệu USD, có
742 giao dịch trên 1 tỷ USD, cao nhất 476 tỷ USD. Theo bản năng thì đây là chỗ
phải cắt ngoại lai. Đo trước khi cắt:

| Nhóm | Tỷ lệ rửa tiền |
|---|---|
| Giao dịch > 1 tỷ USD | **3,91%** |
| Toàn bộ dữ liệu | 0,12% |
| Giao dịch < 1 xu USD | **0%** |

Nhóm khổng lồ có tỷ lệ rửa tiền **gấp 32 lần** mặt bằng. Cắt ngoại lai theo quy
trình thông thường sẽ vứt đi đúng nhóm giàu tín hiệu nhất. Những con số khổng lồ
này không do bảng tỷ giá tạo ra — giao dịch USD không qua quy đổi cũng đã lên
tới 97,4 tỷ USD.

---

## 7. Kết quả

*(Phần này điền sau khi lần chạy 3 nhánh hoàn tất.)*

---

## 8. Đo ở ba tầng: giao dịch, tài khoản, đường dây

Mọi kết quả đã công bố trên bộ IBM AML đều ở mức giao dịch, vì nhãn nằm ở mức
giao dịch. Nhưng đội điều tra AML không mở hồ sơ trên một dòng chuyển khoản — họ
mở trên một tài khoản, và điều họ cần biết là **vụ có bị bỏ lọt không**.

Một đường dây có nhiều giao dịch. Bắt được một là mở được hồ sơ, điều tra viên
lần ra phần còn lại. Nên recall mức giao dịch **đánh giá thấp** năng lực vận hành.

File `*_Patterns.txt` của IBM liệt kê chính xác các giao dịch thuộc từng vụ, nên
đo được ở mức đường dây.

### Kết quả trên LI-Small

Cùng một model, cùng một bộ điểm số, chỉ khác đơn vị đo:

| Cảnh báo | Giao dịch | Tài khoản | **Đường dây** |
|---|---|---|---|
| 100 | 10,1% | 7,2% | **53,6%** |
| 500 | 20,9% | 15,9% | **71,4%** |
| 1.000 | 26,0% | 21,2% | **76,8%** |
| 5.000 | 39,6% | 37,3% | **89,3%** |
| 12.239 | 52,6% | 55,1% | **92,9%** |

Ở mức 1.000 cảnh báo: đo theo giao dịch thì như bắt được một phần tư, đo theo
đường dây thì bắt được **ba phần tư số vụ**.

Giới hạn phải nói kèm: chỉ 56 trên 117 đường dây có mặt trong tập test (mẫu nhỏ),
và file pattern chỉ ghi 28,7% giao dịch rửa tiền của LI-Small. Phép khớp giữa
file pattern và bảng giao dịch đạt 99,7% (318 trên 319 dòng trong khoảng test;
dòng còn lại là giao dịch tự chuyển đã bị ETL loại).

File pattern của HI-Medium **bị cắt cụt** — 493 khối BEGIN nhưng chỉ 492 END,
dòng cuối đứt giữa chừng. Khối hỏng bị bỏ, còn 492 đường dây với 4.084 giao dịch
thành viên, phủ 11,6% hoạt động rửa tiền trong bộ.

---

## 9. Thí nghiệm cửa sổ nhìn tới (đã bác bỏ)

Giả thuyết: ca bị sót nằm trên tài khoản im lặng, và hành vi chuyển tiếp chỉ lộ
ra sau khi tiền đi tiếp, nên cho model nhìn tới 24 giờ sẽ bắt thêm được.

Phần nghiên cứu quy định cho thấy độ trễ là hợp lệ: giám sát theo lô qua đêm là
chuẩn mực ngành, và đồng hồ nộp báo cáo giao dịch đáng ngờ của FinCEN tính **30
ngày từ lúc phát hiện**, không phải từ lúc giao dịch.

Kết quả đo (HI-Medium, mỗi ngày):

| | Chỉ quá khứ | Thêm nhìn tới 24h |
|---|---|---|
| Bắt được | 390 | 398 |
| Bỏ sót | 321 | 312 |
| Báo nhầm | 58 | 63 |

Recall tăng 1,2 điểm, precision giảm 0,6 điểm. Mức tăng chỉ bằng khoảng một độ
lệch chuẩn — chưa đủ để gọi là chắc chắn.

**Kết luận: không đáng đổi.** Trễ 24 giờ mất khả năng chặn tiền để lấy 8 ca mỗi
ngày. Giả thuyết sai vì ca bị sót có `a_mins_since_last_in` trung vị 4.052 phút
(gần 3 ngày) — tiền không vừa vào rồi vội đi ra, nó nằm im rất lâu. Cửa sổ 24
giờ nhìn sai chỗ.

---

## 10. Giới hạn đã biết

1. **Kết quả dao động ±1,4 điểm giữa các lần chạy.** Script đặt
   `preserve_insertion_order=false` để DuckDB không tràn đĩa trên HI-Medium; đánh
   đổi là thứ tự dòng không cố định, làm `HistGradientBoostingClassifier` lấy mẫu
   con khác nhau khi chia bin. Luôn trích trung bình 5 seed, không trích một lần
   chạy đơn lẻ.

2. **So sánh với bài báo chưa hoàn toàn cùng điều kiện.** Đường ống loại giao
   dịch tự chuyển (29,3 trên 31,9 triệu) và cắt tập theo phân vị thời gian thay
   vì chỉ số dòng.

3. **Không có holdout tương lai đúng nghĩa.** EDA của nhóm đã kết luận điều này
   với LI-Small và nó vẫn đúng.

4. **Đây là dữ liệu tổng hợp.** Kết quả trên bộ IBM AML **không** suy ra được
   kết quả trên dữ liệu ngân hàng thật. Nó chỉ cho biết so với các nhóm nghiên
   cứu khác cùng chạy trên bộ này thì model đứng ở đâu.

5. **Đo mức đường dây chỉ phủ một phần.** File pattern ghi 11,6% giao dịch rửa
   tiền của HI-Medium, và file bị cắt cụt mất một khối.

---

## 11. Chạy lại

```bash
# Nạp dữ liệu (~1,5 phút)
python scripts/load_ibm_dataset_duckdb.py \
  --csv data/raw/ibm-aml/HI-Medium_Trans.csv \
  --out data/processed/hi_medium.duckdb

# Huấn luyện + đánh giá (~100 phút)
python scripts/benchmark_edge_level.py \
  --db data/processed/hi_medium.duckdb \
  --report-out reports/edge-benchmark/hi_medium.json \
  --threads 4 --memory-limit 10GB

# Đánh giá ba tầng
python scripts/evaluate_ring_level.py \
  --db data/processed/hi_medium.duckdb \
  --patterns data/raw/ibm-aml/HI-Medium_Patterns.txt \
  --report-out reports/edge-benchmark/hi_medium_ring_level.json
```
