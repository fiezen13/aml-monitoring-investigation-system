# Isolation Forest handoff — FIN-07

## Mục đích tài liệu

Hướng dẫn nhánh **Isolation Forest** (phát hiện bất thường theo hành vi tài khoản) dùng đúng output Task 1 để làm feature engineering, train model, và xuất điểm + evidence.

**Phạm vi Task 1 đã xong:**

1. Nạp raw IBM AML LI-Small
2. Chuẩn hóa bảng giao dịch + tài khoản
3. Chia train / val / test theo thời gian
4. Lưu DuckDB + báo cáo JSON

**Phạm vi nhánh Isolation Forest:**

- Dùng **dữ liệu đã xử lý sẵn**
- Thiết kế behavior feature, train Isolation Forest
- Xuất `anomaly_score` + evidence

**Ngoài phạm vi nhánh Isolation Forest:**

- Tự ETL lại từ CSV IBM
- Đổi cách ghép tài khoản / chia tập / bảng tỷ giá

---

## Nguyên tắc

> **Task 1 là lớp dữ liệu chuẩn (canonical).**
> Nhánh Isolation Forest được tự do thiết kế feature và model, nhưng **không được thay đổi** định nghĩa giao dịch, tài khoản, tiền tệ / FX, hay cách chia train–val–test của Task 1.

Nếu Isolation Forest và Graph mỗi nhánh clean data một kiểu, điểm sau này **không ghép được** và khó giải trình.

---

## 1. Input nhận từ Task 1

### 1.1. Code Task 1 (Git)

Đây là quy tắc đã dùng để tạo dữ liệu. Checkout để xem schema / cột. **Không bắt buộc chạy lại ETL** nếu đã có file DuckDB processed.

| Mục | Giá trị |
|-----|---------|
| Commit | `5b15a51` — *feat: implement ETL pipeline for FIN-07 Task 1…* |
| Script ETL | `scripts/run_task1_etl.py` |
| Định nghĩa cột | `src/data/schemas.py` |
| Bảng tỷ giá | `src/data/currency.py` (`FX_VERSION = "2026-07-31-static-v2"`) |

```bash
git fetch origin
git checkout 5b15a51
```

### 1.2. Dữ liệu processed (Drive / shared storage — không nằm trong Git)

Git cố ý không chứa dataset lớn. Đặt các file sau vào repo (hoặc trỏ đúng path):

| File | Path gợi ý | Mục đích |
|------|------------|----------|
| `aml.duckdb` | `data/processed/aml.duckdb` | Database: giao dịch + tài khoản |
| `dq_report.json` | `data/processed/dq_report.json` | Báo cáo chất lượng dữ liệu |
| `split_cutoffs.json` | `data/processed/split_cutoffs.json` | Mốc cắt train / val / test |

### 1.3. Bảng trong DuckDB

| Bảng | Ý nghĩa |
|------|---------|
| `transaction` | Mỗi dòng = một giao dịch đã chuẩn hóa + cột `split` |
| `account` | Mỗi dòng = một tài khoản xuất hiện trong giao dịch (node), kèm thống kê sơ bộ |

Không dùng file account CSV riêng từ IBM. Bảng `account` được **suy ra từ giao dịch** (gom mọi `from` / `to`).

```python
import duckdb

con = duckdb.connect("data/processed/aml.duckdb", read_only=True)

# Dùng cột split có sẵn — không tự chia lại
train = con.execute(
    "SELECT * FROM transaction WHERE split = 'train'"
).df()

print(con.execute("SHOW TABLES").fetchall())
print(con.execute(
    "SELECT split, COUNT(*) FROM transaction GROUP BY 1 ORDER BY 1"
).fetchall())
```

### 1.4. Cột `transaction` (theo `schemas.py`)

| Cột | Giải thích |
|-----|------------|
| `transaction_id` | Mã giao dịch ổn định (hash) |
| `occurred_at` | Thời điểm giao dịch (UTC) |
| `from_account_key` | Tài khoản gửi, dạng `ngân_hàng:số_TK` |
| `to_account_key` | Tài khoản nhận, cùng dạng |
| `amount_paid_orig` / `payment_currency` | Số tiền & loại tiền **gốc** phía gửi |
| `amount_received_orig` / `receiving_currency` | Số tiền & loại tiền **gốc** phía nhận |
| `amount` / `amount_received` | Đã quy đổi **USD** (dùng cho feature tiền) |
| `currency` | Luôn `"USD"` — đơn vị chung sau quy đổi |
| `channel` | `ACH`, `WIRE`, `CHEQUE`, `CREDIT_CARD`, `CASH`, `BITCOIN`, `REINVESTMENT`, `OTHER` |
| `split` | `train` / `val` / `test` |
| `label_laundering` | 0 hoặc 1: giao dịch thuộc kịch bản rửa tiền IBM hay không |

`label_laundering` chỉ dùng **đánh giá sau khi đã scoring**.
**Không** đưa vào feature khi train Isolation Forest (rò rỉ nhãn).

Helper trong Task 1: `feature_columns()` / `assert_no_label_leakage()` — `src/data/schemas.py`.

### 1.5. Tiền tệ — gốc và USD

- **Gốc:** khớp raw → DQ, audit.
- **USD:** cùng một thước → so hành vi / ngưỡng giữa các loại tiền.

Feature Isolation Forest ưu tiên `amount` và `amount_received` (USD).
Không tự viết lại bảng tỷ giá. Version: `2026-07-31-static-v2`.

### 1.6. Self-loop

Giao dịch gửi và nhận **cùng một** `account_key`. Pipeline Task 1 **đã loại** các dòng đó.

Invariant DQ: `n_loaded + n_self_loops == n_raw`.

Snapshot `dq_report.json`:

- raw ≈ 6.92M
- self-loop ≈ 0.80M
- còn trong DB ≈ 6.12M giao dịch

### 1.7. Train / val / test

Chia theo **thời gian** (sớm → train, sau → val, sau nữa → test), mục tiêu 60/20/20 — không chia ngẫu nhiên.

Snapshot `split_cutoffs.json`:

| Tập | Số giao dịch (xấp xỉ) | Mục đích |
|-----|----------------------|----------|
| train | ~3.67M | Fit model + scaler / thống kê |
| val | ~1.22M | Tune hyperparameter / ngưỡng |
| test | ~1.22M | Đánh giá cuối |
| `train_end_ts` | `2022-09-06 23:43:00+00:00` | Mốc hết train |
| `val_end_ts` | `2022-09-08 21:12:00+00:00` | Mốc hết val |

Lọc bằng `WHERE split = '…'` chỉ đúng khi làm việc **trực tiếp với từng dòng transaction** (audit).

Khi build mẫu Isolation Forest / Graph theo `(account_key, as_of_ts, window)`, dùng **`sample_split = assign_snapshot_split(as_of_ts, …)`** — xem §3.3.1. Không gán split mẫu theo majority `transaction.split` trong window.

### 1.8. Soft warning DQ

`dq_report.json`: `"ok": true`, kèm warning số account ≈ 577K (paper ~705K ±15%).

Nguyên nhân hợp lý: unique sau khi bỏ self-loop + ghép `bank:account`.
Không “sửa” bằng account CSV riêng hay đổi format `account_key`.
Báo cáo: trích `dq_report.json` + commit `5b15a51`.

Seed ETL: `42`.

---

## 2. Ràng buộc — không làm lại

| Không làm | Lý do |
|-----------|--------|
| Đọc raw `LI-Small_Trans.csv` rồi tự clean cho IF | Hai nguồn “sự thật” lệch nhau |
| Tự chia lại train/val/test | Phá time-split → leakage / khó so với Graph |
| Đổi `account_key` | Không join được với Graph |
| Tự đổi FX / tự quy USD | Điểm tiền lệch giữa nhánh |
| Dùng `label_laundering` làm feature | Model học đáp án |
| Dùng Patterns / typology làm feature | Ground truth kịch bản, không phải tín hiệu IF baseline |
| Ghi đè `aml.duckdb` shared | Phá bản canonical |

`LI-Small_Patterns.txt` thuộc Task 2 / đánh giá typology — không phải input Isolation Forest baseline.

---

## 3. Feature engineering Isolation Forest

### 3.1. Vai trò trong hệ thống

Isolation Forest tìm tài khoản có **hành vi thống kê khác phần lớn** trong một cửa sổ thời gian.

Nhánh Graph nhìn **cấu trúc mạng** (chu trình, fan-in/out…).
Hai nhánh bổ sung; điểm hợp nhất sau này — contract điểm phải thống nhất (mục 5).

Baseline IF: **chỉ behavior features**, chưa đưa graph features vào IF.

### 3.2. Đơn vị scoring

Không chấm từng giao dịch tùy ý.

Mỗi mẫu = bộ ba:

| Thành phần | Nghĩa |
|------------|--------|
| `account_key` | Tài khoản |
| `as_of_ts` | Thời điểm chốt sổ |
| `window` | Độ dài nhìn lùi (vd 1d / 7d / 14d) |

Ví dụ: tài khoản `1:ACC001`, snapshot ngày `2022-09-09` (`as_of_ts = 2022-09-10T00:00:00Z`), window 7 ngày → vector feature → `anomaly_score`.

### 3.3. Chiến lược `as_of_ts` (baseline đã chốt — đồng bộ Graph)

**Snapshot theo ngày lịch UTC, cửa sổ half-open** (không dùng `23:59:59`):

Với mỗi ngày snapshot `D` (UTC):

```text
end_ts   = (D + 1 day) at 00:00:00 UTC
start_ts = end_ts - W   # W = 1d / 7d / 14d tùy window
```

| Field | Giá trị |
|-------|---------|
| `snapshot_date` | `D` (khuyến nghị lưu) |
| `as_of_ts` | `end_ts` — exclusive upper bound; join key với Graph |

Transaction trong window:

```text
start_ts <= occurred_at < end_ts
```

Ví dụ `D = 2022-09-09`, window `7d`:

```text
2022-09-03 00:00:00 UTC  <= occurred_at  <  2022-09-10 00:00:00 UTC
as_of_ts = 2022-09-10T00:00:00+00:00
```

Baseline: chỉ tạo mẫu cho account có ≥ 1 giao dịch (gửi hoặc nhận) trong window.

Window gợi ý: `1d`, `7d`, `14d` — **fusion với Graph khóa `7d`** cùng convention half-open.

Chiến lược khác (theo giờ, thưa ngày…): phải **một định nghĩa duy nhất**, ghi trong `feature_spec.md`, và không tạo sample “mỗi transaction một dòng” tùy hứng. **Không** lệch convention với Graph nếu vẫn join theo `as_of_ts`.

### 3.3.1. Gán `sample_split` cho snapshot (đã khóa — contract chung với Graph)

Cột `transaction.split` của Task 1 **không** đủ để gán split cho mẫu `(account_key, as_of_ts, window)`. Window có thể chứa tx thuộc nhiều split; điều đó **không phải leakage** nếu chỉ dùng quá khứ (`occurred_at < end_ts`).

**Đã khóa:** `sample_split` theo **`as_of_ts`**, không theo mix tx trong window.

Helper chung với Graph (`assign_snapshot_split`):

```text
assign_snapshot_split(as_of_ts, split_cutoffs) -> {"train","val","test"}

train_end_ts = cutoffs["train_end_ts"]
val_end_ts   = cutoffs["val_end_ts"]

if as_of_ts <= train_end_ts: return "train"
elif as_of_ts <= val_end_ts: return "val"
else: return "test"
```

- Fit IF / fit scaler: chỉ sample `sample_split = train`
- Tune: `val`
- Evaluate cuối: `test`
- Val/test snapshot **được** dùng historical tx xảy ra trước `end_ts` (kể cả tx có `transaction.split = train`)
- **Cấm** tx `occurred_at >= end_ts`
- **Cấm** gán split theo majority `transaction.split` trong window

Chi tiết cutoffs: `data/processed/split_cutoffs.json` (cùng file Graph). Xem thêm `docs/graph_branch_plan.md` §2.2.1.

### 3.4. Nhóm feature gợi ý (~20–30)

Trong window:

- **Outgoing** = `from_account_key = account`
- **Incoming** = `to_account_key = account`
- Tiền: `amount` / `amount_received` (USD)

| Nhóm | Feature gợi ý | Ý nghĩa |
|------|---------------|---------|
| A. Cường độ | `txn_count`, `incoming_count`, `outgoing_count`, `active_days`, `txn_per_active_day` | Tần suất hoạt động |
| B. Dòng tiền | `total_inflow`, `total_outflow`, `net_flow`, `outflow_inflow_ratio` | Vào / ra / cân bằng |
| C. Luân chuyển nhanh | `rapid_outflow_ratio`, `median_dwell_time` | Tiền vào rồi ra nhanh |
| D. Đối tác | `unique_in_counterparties`, `unique_out_counterparties`, `new_counterparty_ratio` | Độ rộng / mới của mạng đối tác |

Với `new_counterparty_ratio` (nếu dùng lookback `all_past` trước window): đầu dataset / account mới thường cho ratio ≈ 1 vì **cold-start**, không phải tín hiệu AML mạnh. Ghi cold-start policy trong `feature_spec.md` (vd `history_available`); không diễn giải ratio=1 khi chưa có history — cùng tinh thần Graph plan §3.5.
| E. Phân bố số tiền | `median_amount`, `p90_amount`, `amount_std`, `repeated_amount_ratio` | Phân bố & độ lặp số tiền |
| F. Nhịp thời gian | `median_inter_txn_gap`, `p10_inter_txn_gap` | Khoảng cách giữa các giao dịch |

### 3.5. Bắt buộc: `feature_spec.md` trước khi code

Chỉ liệt kê tên feature dễ hiểu lệch (`rapid_*`, `dwell`, `new_counterparty_*`).

Trước khi implement, tạo `docs/feature_spec.md` (hoặc path tương đương). Mỗi feature ghi:

1. **Definition** — công thức / pseudo-code
2. **Window** — 1d / 7d / 14d; lookback phụ nếu có
3. **Inputs** — cột Task 1
4. **Edge cases** — chia 0, chỉ in/out, window rỗng, timestamp trùng
5. **Transform** — `log1p` / clip hay không

Cần chốt rõ trong spec, ví dụ:

- `new_counterparty_ratio_7d` — lookback lịch sử dài bao nhiêu ngày?
- `rapid_outflow_ratio` — ngưỡng “nhanh” bao nhiêu giờ?
- `median_dwell_time` — cách ghép cặp in→out?

### 3.6. Transform sau aggregation

Count/amount AML thường heavy-tail. Isolation Forest nhạy với phân phối lệch.

Cho phép: `log1p`, clipping / winsorization, quy ước ratio khi mẫu số = 0.

Ràng buộc:

- Scaler / ngưỡng clip / tham số transform **chỉ fit từ TRAIN**, rồi đóng băng
- Lưu cùng `model_version`
- Không fit normalize riêng trên val/test

---

## 4. Train / val / test và chống leakage

| Tập (`split` / `sample_split`) | Mục đích |
|---------------|----------|
| `train` | Fit Isolation Forest; fit scaler, phân phối tham chiếu, transform — **chỉ sample** có `sample_split=train` |
| `val` | Tune hyperparameter, ngưỡng |
| `test` | Metric cuối — không tune lặp trên test |

**Không** train bằng cách `SELECT * FROM transaction WHERE split='train'` rồi aggregate tùy ý mà bỏ qua `assign_snapshot_split`. Feature rows phải mang `sample_split` từ helper chung.

Chống leakage:

1. Feature tại snapshot `end_ts` chỉ dùng giao dịch `occurred_at < end_ts` (trong window: `start_ts <= occurred_at < end_ts`).
2. Không dùng `label_*` khi `fit`.
3. Không dùng Patterns / typology làm feature.
4. Thống kê toàn cục chỉ từ train.

### Metric

Ưu tiên: **Precision, Recall, PR-AUC, Precision@K**.

Không ưu tiên Accuracy (tỷ lệ laundering ~0.05% — đoán toàn “không” cũng accuracy cao nhưng vô dụng).

### Nhãn evaluate (baseline đã chốt)

Chỉ dùng sau khi có `anomaly_score` — để đo, không để train.

```text
Với mỗi mẫu (account_key, as_of_ts, window):

y = 1  nếu trong đúng scoring window,
       account là from_account_key HOẶC to_account_key
       của ≥ 1 giao dịch có label_laundering = 1

y = 0  nếu không
```

Đổi định nghĩa (vd horizon sau `as_of_ts`): trình team và ghi lại trước khi evaluate — không đổi thầm giữa các lần chạy metric.

---

## 5. Output contract

Mỗi dòng = một lần chấm một account tại một `as_of_ts` + `window`.

| Trường | Bắt buộc | Ý nghĩa |
|--------|----------|---------|
| `account_key` | Có | Tài khoản |
| `as_of_ts` | Có | Thời điểm chốt (UTC) |
| `window` | Có | vd `1d`, `7d`, `14d` |
| các cột feature | Có | Vector hành vi (+ transform nếu có) |
| `anomaly_score` | Có | Điểm bất thường — quy ước dưới |
| `model_version` | Có | Version model + config + transform |
| `top_anomalous_features` | Có | Evidence — mục 6 |

Xuất file riêng (vd `data/processed/if_scores_v1.parquet`).
Không ghi đè `aml.duckdb` dùng chung.

### Quy ước `anomaly_score`

| Quy ước FIN-07 | Chi tiết |
|----------------|----------|
| Chiều | **Cao hơn = rủi ro / bất thường hơn** |
| Thang | **`[0, 1]`** |

scikit-learn `decision_function` / `score_samples` không tự khớp quy ước trên. Cần **map rõ** sang “cao = rủi ro, [0,1]” và ghi công thức cạnh `model_version`.

Mục đích: fusion với rule_score / graph_score không bị lệch chiều.

---

## 6. Candidate evidence

Ngoài `anomaly_score`, cần biết feature nào **nổi bật** kèm theo.
Không khẳng định đó là nguyên nhân tuyệt đối trừ khi có attribution method riêng.

Baseline:

1. Trên TRAIN, lưu phân phối từng feature (sau transform đóng băng).
2. Với mẫu đang chấm, tính percentile so với train.
3. Giữ feature rất cao/thấp (vd > p95 hoặc < p5).
4. Rank → `top_anomalous_features`.

```json
{
  "account_key": "1:ACC001",
  "as_of_ts": "2022-09-10T00:00:00+00:00",
  "window": "7d",
  "anomaly_score": 0.92,
  "model_version": "if_baseline_v1",
  "top_anomalous_features": [
    {
      "feature": "txn_count_7d",
      "value": 48,
      "percentile": 99
    },
    {
      "feature": "new_counterparty_ratio_7d",
      "value": 0.81,
      "percentile": 98
    }
  ]
}
```

Diễn giải khi demo / báo cáo:

> Các behavior feature nổi bật đi kèm anomaly score cao.

Tránh khẳng định: “Vì feature X nên Isolation Forest quyết định bất thường” — trừ khi có attribution riêng.

---

## 7. Checklist

### Nhận dữ liệu & code

- [ ] Checkout commit Task 1: `5b15a51`
- [ ] Có `aml.duckdb` (hoặc Parquet tương đương từ cùng ETL)
- [ ] Đọc được `split_cutoffs.json`
- [ ] Đọc được `dq_report.json` (`"ok": true`)
- [ ] `SHOW TABLES` có `transaction`, `account`; sample khớp mục 1.4

### Pipeline Isolation Forest

- [ ] Có `feature_spec.md` (công thức + window + edge case + transform) trước khi code feature
- [ ] Chốt `as_of_ts` half-open (đồng bộ Graph: `start_ts <= occurred_at < end_ts`)
- [ ] Gán `sample_split` bằng `assign_snapshot_split(as_of_ts, split_cutoffs)` — không theo mix `transaction.split`
- [ ] Feature từ processed `transaction`, không từ raw
- [ ] Transform / scaler fit trên `split='train'`, lưu cùng `model_version`
- [ ] Không dùng `label_*` / Patterns làm feature
- [ ] Train trên train; tune trên val; evaluate trên test
- [ ] Nhãn evaluate đúng baseline mục 4 (hoặc đã thống nhất với team và ghi lại)
- [ ] Metric: Precision / Recall / PR-AUC / Precision@K
- [ ] `anomaly_score` ∈ `[0, 1]`, cao = rủi ro
- [ ] Xuất `anomaly_score` + `top_anomalous_features` + `account_key`, `as_of_ts`, `window`, `model_version`

### Smoke test

```python
import json
import duckdb

con = duckdb.connect("data/processed/aml.duckdb", read_only=True)
tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
assert {"transaction", "account"} <= tables

print(con.execute(
    "SELECT split, COUNT(*) FROM transaction GROUP BY 1 ORDER BY 1"
).fetchall())

cutoffs = json.load(open("data/processed/split_cutoffs.json"))
dq = json.load(open("data/processed/dq_report.json"))
assert dq["ok"] is True
print("counts:", cutoffs["counts"])
print("n_loaded:", dq["metrics"]["n_loaded"])
```

---

## Khi nào cần thống nhất lại với team Data

- Thiếu DuckDB / JSON, hoặc `dq_report.ok != true`
- Schema trên DB không khớp mục 1.4
- Muốn đổi nhãn evaluate hoặc chiến lược `as_of_ts` so với baseline tài liệu này

Thuật toán IF chi tiết, danh sách feature cụ thể, hyperparameter: trách nhiệm nhánh Isolation Forest, miễn tuân thủ contract input / anti-leakage / output ở trên.

---

*Handoff v1.5 — half-open window + `assign_snapshot_split` đồng bộ Graph plan v0.5. Khớp Task 1 commit `5b15a51`.*
