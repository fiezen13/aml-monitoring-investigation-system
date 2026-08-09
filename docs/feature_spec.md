# FIN-07 — Đặc tả 20 đặc trưng hành vi tài khoản (Isolation Forest)

Tài liệu này định nghĩa **20 đặc trưng hành vi cấp `account_key`** dùng cho mô hình Isolation Forest (nhánh Behavioral ML, dự án FIN-07).

Mỗi mẫu là bộ ba:

\[
({account_key}; {as_of_ts}; {window})
\]

- `as_of_ts`: mốc chốt sổ UTC (mặc định end-of-day `23:59:59Z` của ngày \(D\)).
- `window`: cửa sổ nhìn lùi — hỗ trợ `'1d'`, `'7d'` (mặc định), `'14d'`.
- Chỉ dùng giao dịch có `occurred_at ≤ as_of_ts` và nằm trong `[as_of_ts − window, as_of_ts]`.

**Nguồn dữ liệu:** bảng `transaction` trong DuckDB (`data/processed/aml.duckdb`):

| Cột | Ý nghĩa |
|---|---|
| `occurred_at` | Thời điểm giao dịch (UTC) |
| `from_account_key` | Tài khoản gửi |
| `to_account_key` | Tài khoản nhận |
| `amount` | Số tiền đã quy đổi USD |

---

## 0. Tóm tắt ngắn 20 đặc trưng

### Nhóm A — Cường độ (Frequency / Intensity) — 5 đặc trưng

1. `txn_count_{w}` — Tổng số giao dịch (gửi + nhận) trong window.
2. `incoming_count_{w}` — Số giao dịch nhận (`to_account_key = account`).
3. `outgoing_count_{w}` — Số giao dịch gửi (`from_account_key = account`).
4. `active_days_{w}` — Số ngày riêng biệt có phát sinh giao dịch.
5. `txn_per_active_day_{w}` — `txn_count / active_days` (mật độ giao dịch/ngày hoạt động).

### Nhóm B — Dòng tiền (Money Flow) — 4 đặc trưng

6. `total_inflow_{w}` — Tổng tiền nhận (USD).
7. `total_outflow_{w}` — Tổng tiền gửi (USD).
8. `net_flow_{w}` — `total_inflow − total_outflow`.
9. `outflow_inflow_ratio_{w}` — `total_outflow / (total_inflow + 1e-6)` (dấu hiệu mule / ống dẫn).

### Nhóm C — Luân chuyển nhanh (Pass-through) — 2 đặc trưng

10. `rapid_outflow_ratio_{w}` — Tỷ lệ tiền ra trong vòng **2 giờ** sau khi nhận tiền.
11. `median_dwell_time_{w}` — Thời gian lưu tiền trung vị (giờ) giữa nhận và rút.

### Nhóm D — Mạng lưới đối tác (Counterparty) — 3 đặc trưng

12. `unique_in_counterparties_{w}` — Số tài khoản gửi riêng biệt (fan-in).
13. `unique_out_counterparties_{w}` — Số tài khoản nhận riêng biệt (fan-out).
14. `new_counterparty_ratio_{w}` — Tỷ lệ đối tác mới so với lịch sử trước window.

### Nhóm E — Phân bố số tiền (Amount Distribution) — 4 đặc trưng

15. `median_amount_{w}` — Trung vị số tiền giao dịch.
16. `p90_amount_{w}` — Phân vị 90% (bắt đột biến lớn).
17. `amount_std_{w}` — Độ lệch chuẩn (smurfing thường có std thấp).
18. `near_threshold_ratio_{w}` — Tỷ lệ TX trong dải **$9,000–$10,000** (T01 né CTR).

### Nhóm F — Nhịp thời gian (Temporal Timing) — 2 đặc trưng

19. `off_hour_ratio_{w}` — Tỷ lệ TX giờ **0h–5h**.
20. `median_inter_txn_gap_{w}` — Khoảng cách thời gian trung vị giữa 2 TX liên tiếp (phút).

> Ký hiệu `{w}` ∈ `{1d, 7d, 14d}`. Trong schema output có thể ghi tên không suffix khi `window` là cột riêng.

---

## 1. Bốn quy tắc phòng thủ (Fallbacks)

### 1.1. Fallback Account im lặng

**Sự cố:** Tạo mẫu dư cho account không có hoạt động trong window.

**Quy tắc:** Chỉ tạo sample cho `(account_key, as_of_ts, window)` nếu account có **≥ 1** giao dịch (gửi hoặc nhận) trong window.

### 1.2. Fallback Chia 0

**Sự cố:** Ratio/density sinh `NaN` / `Inf` khi mẫu số = 0.

**Quy tắc:** Cộng \(\varepsilon = 10^{-6}\) vào mọi mẫu số tỉ lệ; sau đó `.fillna(0.0)` cho các cột tỉ lệ bị thiếu/ô nhiễm.

### 1.3. Fallback Heavy-tailed

**Sự cố:** `amount` lệch nặng (vài USD → hàng triệu USD) làm nhiễu Isolation Forest.

**Quy tắc:** Thuộc tính số tiền tuyệt đối áp dụng `log1p(amount)` và/hoặc clipping/winsorization. **Scaler / thông số clipping chỉ fit trên TRAIN**, đóng băng khi transform Val/Test.

### 1.4. Fallback Anti-leakage

**Quy tắc:**

- Không dùng `label_laundering` / `Is Laundering` / Patterns làm feature.
- Tại `as_of_ts = t`, chỉ dùng giao dịch có `occurred_at ≤ t`.
- Mọi transform thống kê (scaler, clip bounds) fit **duy nhất trên TRAIN**.

---

## 2. Mô tả chi tiết từng đặc trưng

Ký hiệu: account đang xét = \(a\); tập giao dịch trong window = \(\mathcal{T}_a(w)\).

---

### Nhóm A — Cường độ (Intensity)

#### 1. `txn_count`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tổng số TX (gửi + nhận) của \(a\) trong window |
| **Công thức** | $\sum_{tx} \mathbf{1}\{\text{from}=a \lor \text{to}=a\}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | Không có TX → không tạo sample (1.1); nếu cần điền = 0 |

#### 2. `incoming_count`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Số TX nhận tiền (`to_account_key = a`) |
| **Công thức** | $\sum \mathbf{1}\{\text{to} = a\}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `to_account_key` |
| **Fallback** | 0 nếu không có TX nhận |

#### 3. `outgoing_count`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Số TX gửi tiền (`from_account_key = a`) |
| **Công thức** | $\sum \mathbf{1}\{\text{from} = a\}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key` |
| **Fallback** | 0 nếu không có TX gửi |

#### 4. `active_days`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Số ngày lịch UTC riêng biệt có ≥ 1 TX |
| **Công thức** | $\|\text{distinct}(\text{DATE}(\text{occurred\_at}))\|$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at` |
| **Fallback** | ∈ \([1, \text{window\_days}]\) khi đã qua rule 1.1 |

#### 5. `txn_per_active_day`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Mật độ giao dịch trên mỗi ngày hoạt động |
| **Công thức** | $\frac{\text{txn\_count}}{\text{active\_days} + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | suy từ `txn_count`, `active_days` |
| **Fallback** | \(\varepsilon\) ở mẫu số; `.fillna(0.0)` |

---

### Nhóm B — Dòng tiền (Money Flow)

#### 6. `total_inflow`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tổng USD nhận trong window (sau đó `log1p`) |
| **Công thức** | $\log(1 + \sum_{\text{to}=a} \text{amount})$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `to_account_key`, `amount` |
| **Fallback** | Heavy-tail `log1p`; `.fillna(0.0)` |

#### 7. `total_outflow`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tổng USD gửi trong window (sau đó `log1p`) |
| **Công thức** | $\log(1 + \sum_{\text{from}=a} \text{amount})$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `amount` |
| **Fallback** | Heavy-tail `log1p`; `.fillna(0.0)` |

#### 8. `net_flow`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Dòng tiền ròng (giữ dấu, thu hẹp biên độ bằng `log1p`) |
| **Công thức** | $\text{sign}(In - Out) \cdot \log(1 + |In - Out|)$ với $In = \sum_{\text{to}} \text{amount}$, $Out = \sum_{\text{from}} \text{amount}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | Heavy-tail trên \(\lvert net\rvert\) |

#### 9. `outflow_inflow_ratio`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tỷ lệ tiền ra/vào — mule thường ≈ 1 |
| **Công thức** | $\frac{\sum_{\text{from}=a} \text{amount}}{\sum_{\text{to}=a} \text{amount} + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | \(\varepsilon\) mẫu số; `.fillna(0.0)` |

---

### Nhóm C — Luân chuyển nhanh (Pass-through)

#### 10. `rapid_outflow_ratio`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tỷ lệ tiền ra xảy ra ≤ 2 giờ sau một khoản tiền vào |
| **Công thức** | $\frac{\sum \text{amount}_{\text{out}}(\exists t_{\text{in}}: 0 \le t_{\text{out}} - t_{\text{in}} \le 2h)}{\sum \text{amount}_{\text{out}} + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | \(\varepsilon\) mẫu số; `.fillna(0.0)` nếu không có outflow |

#### 11. `median_dwell_time`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Trung vị thời gian lưu tiền (giờ) giữa nhận và rút (cặp In→Out liền kề / FIFO) |
| **Công thức** | $\text{Median}(t_{\text{out}} - t_{\text{in}})$ (đơn vị giờ) |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | Không ghép được cặp → gán `999.0` giờ (không có dấu hiệu xả nhanh) |

---

### Nhóm D — Đối tác (Counterparty)

#### 12. `unique_in_counterparties`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Số tài khoản gửi riêng biệt dồn tiền vào (fan-in) |
| **Công thức** | $\|\text{distinct}(\text{from} \mid \text{to}=a)\|$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | 0 nếu không có inflow |

#### 13. `unique_out_counterparties`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Số tài khoản nhận riêng biệt được tỏa tiền tới (fan-out) |
| **Công thức** | $\|\text{distinct}(\text{to} \mid \text{from}=a)\|$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | 0 nếu không có outflow |

#### 14. `new_counterparty_ratio`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tỷ lệ đối tác trong window chưa từng xuất hiện trước window |
| **Công thức** | $\frac{|CP_{\text{window}} \setminus CP_{\text{history}}|}{|CP_{\text{window}}| + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` (history = trước cạnh trái window, vẫn `occurred_at ≤ as_of_ts`) |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | \(\varepsilon\) mẫu số; history rỗng → gán `1.0` |

---

### Nhóm E — Phân bố số tiền (Amount Distribution)

Mọi TX của \(a\) trong window (cả gửi và nhận) tạo tập \(\{amount_i\}\).

#### 15. `median_amount`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Trung vị số tiền; sau đó `log1p` |
| **Công thức** | $\log(1 + \text{Median}(\text{amount}))$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | Heavy-tail; `.fillna(0.0)` |

#### 16. `p90_amount`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Phân vị 90% — bắt TX đột biến lớn |
| **Công thức** | $\log(1 + Q_{0.90}(\text{amount}))$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | Heavy-tail; `.fillna(0.0)` |

#### 17. `amount_std`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Độ lệch chuẩn amount; smurfing thường std thấp |
| **Công thức** | $\log(1 + \text{StdDev}(\text{amount}))$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | 1 TX → không tính std → `.fillna(0.0)` |

#### 18. `near_threshold_ratio`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tỷ lệ TX trong dải né CTR **$9,000 ≤ amount < $10,000** (T01) |
| **Công thức** | $\frac{\sum \mathbf{1}\{9000 \le \text{amount} < 10000\}}{\text{txn\_count} + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key`, `amount` |
| **Fallback** | \(\varepsilon\) mẫu số; `.fillna(0.0)` |

---

### Nhóm F — Nhịp thời gian (Temporal Timing)

#### 19. `off_hour_ratio`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Tỷ lệ TX phát sinh giờ **0h–5h** UTC |
| **Công thức** | $\frac{\sum \mathbf{1}\{\text{hour}(\text{occurred\_at}) \in \{0,1,2,3,4,5\}\}}{\text{txn\_count} + 10^{-6}}$ |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | \(\varepsilon\) mẫu số; `.fillna(0.0)` |

#### 20. `median_inter_txn_gap`

| Mục | Nội dung |
|---|---|
| **Định nghĩa** | Trung vị khoảng cách giữa 2 TX liên tiếp (phút) |
| **Công thức** | $\text{Median}(t_{i+1} - t_i)$ sau khi sort `occurred_at` tăng dần |
| **Window** | `1d` / `7d` / `14d` |
| **Cột DuckDB** | `occurred_at`, `from_account_key`, `to_account_key` |
| **Fallback** | Chỉ 1 TX → `.fillna(99999.0)` |

---

## 3. Schema output pipeline

File kết quả: `data/processed/features_{train,val,test}.parquet`

| Tên cột | Kiểu | Nhóm / ghi chú |
|---|---|---|
| `account_key` | VARCHAR | Khóa `bank:account` |
| `as_of_ts` | TIMESTAMPTZ | Mốc chốt sổ UTC |
| `window` | VARCHAR | `'1d'` / `'7d'` / `'14d'` |
| `txn_count` | BIGINT | A |
| `incoming_count` | BIGINT | A |
| `outgoing_count` | BIGINT | A |
| `active_days` | BIGINT | A |
| `txn_per_active_day` | DOUBLE | A |
| `total_inflow` | DOUBLE | B (`log1p`) |
| `total_outflow` | DOUBLE | B (`log1p`) |
| `net_flow` | DOUBLE | B (`log1p` trên \|net\|) |
| `outflow_inflow_ratio` | DOUBLE | B |
| `rapid_outflow_ratio` | DOUBLE | C |
| `median_dwell_time` | DOUBLE | C (giờ) |
| `unique_in_counterparties` | BIGINT | D |
| `unique_out_counterparties` | BIGINT | D |
| `new_counterparty_ratio` | DOUBLE | D |
| `median_amount` | DOUBLE | E (`log1p`) |
| `p90_amount` | DOUBLE | E (`log1p`) |
| `amount_std` | DOUBLE | E (`log1p`) |
| `near_threshold_ratio` | DOUBLE | E |
| `off_hour_ratio` | DOUBLE | F |
| `median_inter_txn_gap` | DOUBLE | F (phút) |

**Vector đưa vào Isolation Forest:** 20 cột số ở trên (không gồm `account_key`, `as_of_ts`, `window`; không gồm nhãn).

---

## 4. Ánh xạ nhanh nghiệp vụ AML

| Feature | Tín hiệu nghiệp vụ gợi ý |
|---|---|
| `near_threshold_ratio` | T01 Structuring / né CTR |
| `outflow_inflow_ratio` ≈ 1 + `rapid_outflow_ratio` cao / `median_dwell_time` thấp | Mule / pass-through (T02/T05) |
| `unique_in_*` / `unique_out_*` cao | Fan-in / fan-out (T04) |
| `off_hour_ratio` cao | Hoạt động tự động / ngoài giờ |
| `amount_std` rất thấp + `txn_count` cao | Smurfing nhiều khoản gần bằng nhau |
| `new_counterparty_ratio` cao | Mạng đối tác mới bất thường |

---

## 5. Liên hệ triển khai

- Đặc tả này là **hợp đồng feature** cho pipeline Behavioral ML (DuckDB → Parquet → Isolation Forest).
- Pipeline CSV hiện tại (`scripts/extract_features.py` trên LI-Small) dùng bộ 11 feature rút gọn; khi nâng cấp lên 20 feature bắt buộc tuân thủ đúng schema và 4 fallback trong tài liệu này.
