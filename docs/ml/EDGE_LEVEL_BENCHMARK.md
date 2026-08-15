# Benchmark mức giao dịch (edge-level) cho LI-Small

Tài liệu này giải thích `scripts/benchmark_edge_level.py` và cách đọc
`reports/edge-benchmark/benchmark.json`.

## Vì sao cần benchmark này

Benchmark cũ (`reports/fusion-v2/benchmark.json`) chấm điểm **ảnh chụp tài
khoản**: mỗi dòng là một cặp (tài khoản, ngày) với cửa sổ 7 ngày. Toàn bộ kết
quả đã công bố trên bộ dữ liệu IBM AML lại chấm điểm **giao dịch**. Hai thứ
không so sánh được với nhau, nên trước đây không có cách nào biết model của
mình tốt hay dở so với mặt bằng chung.

Ngoài ra benchmark cũ đặt tập val/test lên phần đuôi rỗng của dữ liệu — xem
mục "Bẫy dữ liệu" bên dưới.

## Giao thức

Theo đúng hai bài báo gốc để số của mình nằm cùng một trục với họ:

| Hạng mục | Giá trị |
|---|---|
| Đơn vị | một dòng = một giao dịch |
| Chia tập | 60/20/20 theo thời gian, sắp xếp giao dịch theo timestamp |
| Chỉ số chính | F1 của lớp thiểu số |
| Ngưỡng | chọn trên tập validation để F1 cao nhất, rồi áp một lần duy nhất lên test |
| Siêu tham số | chọn trên validation; test chỉ chạy sau khi đã khoá |
| Sai số | trung bình ± độ lệch chuẩn trên 5 seed |

Nguồn: Altman và cộng sự, NeurIPS 2023 Datasets & Benchmarks
([arXiv:2306.16424](https://arxiv.org/abs/2306.16424)); Blanuša và cộng sự,
ICAIF 2024 ([arXiv:2402.08593](https://arxiv.org/abs/2402.08593)).

## Tính nhân quả

Mọi đặc trưng đồ thị của một giao dịch tại thời điểm `t` chỉ được tính từ các
giao dịch **trước** `t`:

- Cửa sổ trượt 7 ngày và 24 giờ kết thúc **trước `t` một phút**, nên một giao
  dịch không bao giờ nhìn thấy chính nó hay các giao dịch cùng phút.
- Đặc trưng chu trình chỉ đếm cấu trúc mà **mọi cạnh đều đã xuất hiện trước
  `t`** (cột `ready_ts` trong bảng `triangles`).

Script có một chốt chặn: nếu số dòng sau khi dựng đặc trưng khác số giao dịch
gốc thì báo lỗi ngay, vì đó là dấu hiệu một phép join đang nhân hàng.

## Vì sao phải đọc trung bình 5 seed, không đọc một lần chạy

Script đặt `preserve_insertion_order=false` để DuckDB không phải giữ nguyên thứ
tự dòng — nếu không, trên HI-Medium nó đổ hơn 30 GB ra đĩa rồi chết. Đánh đổi là
**thứ tự dòng không cố định giữa các lần chạy**.

Thứ tự dòng thay đổi thì `HistGradientBoostingClassifier` lấy mẫu con khác nhau
khi chia bin cho đặc trưng, dẫn tới cây khác nhau. Đo thực tế trên LI-Small: cùng
một bộ đặc trưng y hệt, hai lần chạy cho F1 trung bình 0,2879 và 0,3022 — lệch
khoảng 1,4 điểm.

Nên khi báo cáo, luôn trích **trung bình ± độ lệch chuẩn trên 5 seed**, đừng trích
con số của một lần chạy đơn lẻ. Chênh lệch dưới khoảng 2 điểm giữa hai lần chạy
không có ý nghĩa.

## Nhóm đặc trưng

**Cơ bản** (8 đặc trưng): số tiền, tỷ lệ quy đổi, khác ngân hàng, khác loại
tiền, kênh thanh toán, giờ, thứ trong tuần.

**Đồ thị** (26 đặc trưng) — dựng lại ý tưởng Graph Feature Preprocessor của IBM
bằng DuckDB, vì `snapml` không có bản cho Python 3.14:

- Thống kê theo đỉnh: số lượng, tổng và giá trị lớn nhất của tiền vào/ra cho cả
  bên gửi và bên nhận, trong 7 ngày và 24 giờ.
- Mẫu hình một bước: fan-in của bên nhận, fan-out của bên gửi, và cờ
  `is_new_pair` (cặp đối tác này giao dịch lần đầu).
- Mẫu hình nhiều bước: số chu trình độ dài 2 và độ dài 3, chỉ số gather-scatter.
- Tỷ lệ bảo toàn số tiền: tiền ra trên tiền vào 24 giờ, tiền chuyển trên khoản
  vào lớn nhất 24 giờ, tỷ lệ vào/ra 7 ngày.

Từng có thêm hai đặc trưng đếm luỹ kế số đối tác riêng biệt, ghép bằng `ASOF
JOIN`. Chúng đã bị bỏ: trên HI-Medium hai phép ghép đó bắt sắp xếp lại toàn bộ
29 triệu dòng và làm hết đĩa tạm, còn trên LI-Small thì bản đếm luỹ kế đo yếu
hơn chính cờ `is_new_pair` thay thế nó.

Đếm chu trình độ dài 3 bỏ qua các đỉnh trung gian có bậc trên 200
(`--degree-cap`). 15 tài khoản trung tâm chiếm phần lớn chi phí duyệt đường đi
2 bước; cắt ở 200 vẫn giữ 99,96% tài khoản và chỉ loại 29 trên 5.303 tài khoản
có dính giao dịch rửa tiền.

## Chạy

```bash
python scripts/benchmark_edge_level.py
```

Khoảng 10 phút. Kết quả ghi vào `reports/edge-benchmark/benchmark.json`.

## Bẫy dữ liệu cần biết

Bảng `transaction` có 6.119.572 giao dịch nhưng **99,998% nằm trong
01/09–10/09/2022**; từ 11/09 đến 17/09 chỉ còn 148 giao dịch. Với cửa sổ 7
ngày, chỉ 3 ảnh chụp (08, 09, 10/09) có cửa sổ đầy đủ.

Benchmark này không dính bẫy đó vì nó chia theo **giao dịch** chứ không theo
ảnh chụp ngày, nên cả ba tập đều nằm gọn trong vùng có dữ liệu thật.

Một điểm nữa cần nhớ khi đọc kết quả: **73% giao dịch rửa tiền đi qua kênh
ACH**, trong khi ACH chỉ chiếm 11% tổng giao dịch. Kênh WIRE không có ca nào.
Đây là đặc tính của bộ sinh dữ liệu, không phải rò rỉ nhãn, nhưng nghĩa là một
phần độ chính xác đến từ kênh thanh toán chứ không phải từ cấu trúc đồ thị.
