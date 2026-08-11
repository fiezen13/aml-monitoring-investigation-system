# Graph Detection Branch Plan — FIN-07

**Status:** implemented baseline — features + FAN v3-min + GATHER_SCATTER; CYCLE full-data remains performance-blocked  
**Scope:** Graph Detection baseline for FIN-07 AML  
**Supersedes (for Graph direction):** cheap/deep graph + PageRank/betweenness/pass-through/GNN ideas in mentor review / older Data-ML notes, to the extent they conflict with this document  
**Related contracts:** Task 1 (`src/data/schemas.py`, `data/processed/aml.duckdb`), Task 2 (`docs/task2_schema.md`), Isolation Forest (`docs/isolation_forest_handoff.md`)

---

## 1. Mục tiêu và vị trí Graph trong FIN-07

FIN-07 detection baseline có **ba nhánh song song**, rồi mới fusion theo account:

1. **Rule**
2. **Isolation Forest** — behavior anomaly
3. **Graph Detection** — network structure

Luồng tổng quát:

```text
Canonical Transactions (Task 1)
        ↓
   ┌────┴────┬────────────────┐
   Rule      Isolation Forest   Graph Detection
   └────┬────┴────────────────┘
        ↓
   Risk Score / Ranking  (per account @ as_of_ts)
        ↓
   High-risk Alert
        ↓
   Investigation Agent  (tools: Behavior / Transaction / Graph / Typology evidence)
        ↓
   Case Report → Human Analyst
```

**Graph branch là gì**

- Graph feature engineering
- Deterministic / configurable graph detectors
- Graph evidence generation (truy ngược được tới transaction)

**Graph branch không phải**

- Investigation Agent / LangGraph workflow
- GNN baseline
- Nơi tự invent fusion `risk_score` cuối cùng
- Nơi đọc `LI-Small_Patterns.txt` để “biết trước” account có cycle

Investigation Agent ở bước sau chỉ **consume** output Graph (pattern, nodes, edges, `transaction_id`s) qua tool — **không** tự phát hiện cycle/fan từ raw transactions.

---

## 2. Input canonical + scoring contract

### 2.1. Input từ Task 1 (đã verify trên repo)

| Artifact | Path | Ghi chú |
|----------|------|---------|
| DuckDB | `data/processed/aml.duckdb` | Có trên máy (~2.1G); **không** commit Git |
| Split contract | `data/processed/split_cutoffs.json` | Time split 60/20/20 |
| DQ | `data/processed/dq_report.json` | `ok: true`; `n_loaded = 6_119_572` |
| Schema code | `src/data/schemas.py` | Source of truth cột |
| Load / index | `src/data/load_duckdb.py` | Index trên `occurred_at`, `from_account_key`, `to_account_key`, … |
| IF handoff (song song) | `docs/isolation_forest_handoff.md` | Cùng consume Task 1 |

**Bảng chính**

| Bảng | Ý nghĩa |
|------|---------|
| `transaction` | Một dòng = một giao dịch đã chuẩn hóa + `split` + `label_laundering` |
| `account` | Node suy ra từ mọi `from`/`to` (không phải KYC CSV riêng) |

**Cột `transaction` dùng cho Graph** (từ `TRANSACTION_ALL_COLUMNS` / `TRANSACTION_FEATURE_COLUMNS`):

| Cột | Vai trò Graph |
|-----|----------------|
| `transaction_id` | Evidence / join |
| `occurred_at` | Cửa sổ thời gian (UTC) |
| `from_account_key` / `to_account_key` | Node + cạnh có hướng (`bank:account`) |
| `amount` / `amount_received` | USD đã chuẩn hóa — đo tiền trên cạnh / concentration |
| `amount_paid_orig` / `payment_currency` / `amount_received_orig` / `receiving_currency` | Giữ gốc nếu cần audit; feature tiền ưu tiên USD |
| `channel` | Optional trên evidence |
| `split` | Train / val / test — **không** tự chia lại |
| `label_laundering` | **Chỉ evaluate** — **cấm** làm graph feature |

**Nguyên tắc đã khóa (Graph phải tuân thủ giống IF)**

- `account_key = bank:account` (`make_account_key`)
- Currency chuẩn hóa USD; vẫn giữ amount/currency gốc
- Self-loop đã loại ở Task 1 (`n_raw = n_loaded + n_self_loops`)
- Train/val/test time split 60/20/20; dùng cột `split` + `split_cutoffs.json`
- Không ETL lại raw IBM; không đổi FX; không ghi đè `aml.duckdb` chỉ để phục vụ Graph
- `LI-Small_Patterns.txt` **không** là detection input

Snapshot cutoffs (repo):

| Field | Value |
|-------|--------|
| `n` | 6_119_572 |
| `train` / `val` / `test` | 3_671_838 / 1_223_994 / 1_223_740 |
| `train_end_ts` | `2022-09-06 23:43:00+00:00` |
| `val_end_ts` | `2022-09-08 21:12:00+00:00` |

### 2.2. Scoring unit (đã chốt — khớp Isolation Forest)

```text
window = 7d
sample identity = (account_key, as_of_ts, window=7d)
```

**Baseline thời gian (đã khóa — half-open, đồng bộ IF handoff):**

Với mỗi **ngày lịch snapshot** `D` (UTC):

```text
end_ts   = (D + 1 day) at 00:00:00 UTC
start_ts = end_ts - 7 days
```

Transaction thuộc scoring window:

```text
start_ts <= occurred_at < end_ts
```

| Field artifact | Giá trị |
|----------------|---------|
| `snapshot_date` | `D` (optional nhưng khuyến nghị lưu) |
| `as_of_ts` | `end_ts` — exclusive upper bound; **join key** với IF |

Ví dụ snapshot `D = 2022-09-09`:

```text
2022-09-03 00:00:00 UTC  <= occurred_at  <  2022-09-10 00:00:00 UTC
as_of_ts = 2022-09-10T00:00:00+00:00
```

Không dùng `23:59:59` (tránh lệch sub-second / precision). IF và Graph **bắt buộc cùng convention này**.

**Lý do đồng bộ 7d với IF:** fusion sau này cần cùng `account_key`, cùng `as_of_ts`, cùng khoảng quan sát.

### 2.2.1. Gán `sample_split` cho snapshot (đã khóa — contract chung với IF)

Task 1 gắn cột `split` trên **từng transaction**. Graph/IF tạo sample `(account_key, as_of_ts, window)`.

Một window 7d **có thể** chứa transaction thuộc nhiều split Task 1 (vd snapshot đầu val nhìn lại ngày train). Điều đó **không phải leakage** nếu chỉ dùng `occurred_at < end_ts` — đó là quá khứ tại thời điểm scoring.

**Đã khóa:**

> `sample_split` được xác định theo **`as_of_ts`**, **không** theo mix `transaction.split` bên trong window.

Helper **chung** (IF + Graph phải gọi cùng một định nghĩa — đặt sau ở `src/data/snapshot_split.py` hoặc tương đương; ghi lại trong `graph_feature_spec.md` / IF `feature_spec.md`):

```text
assign_snapshot_split(as_of_ts, split_cutoffs) -> {"train","val","test"}

Với cutoffs từ data/processed/split_cutoffs.json:
  train_end_ts = cutoffs["train_end_ts"]
  val_end_ts   = cutoffs["val_end_ts"]

if as_of_ts <= train_end_ts:
    return "train"
elif as_of_ts <= val_end_ts:
    return "val"
else:
    return "test"
```

Snapshot hiện tại (ví dụ):

| `as_of_ts` (UTC) | So với cutoffs | `sample_split` |
|------------------|----------------|----------------|
| `≤ 2022-09-06 23:43:00` | ≤ train_end | `train` |
| `≤ 2022-09-08 21:12:00` (và > train_end) | ≤ val_end | `val` |
| `> 2022-09-08 21:12:00` | sau val_end | `test` |

Ví dụ midnight: `as_of_ts = 2022-09-07T00:00:00+00:00` > `train_end_ts` → **`val`**, dù window vẫn chứa nhiều tx `split=train`.

**Quyền nhìn history trong window / lookback:**

| `sample_split` | Được dùng tx với `occurred_at < end_ts` từ |
|----------------|-----------------------------------------------|
| train | Chỉ thời điểm trong train regime; với rule trên, `as_of_ts ≤ train_end` ⇒ mọi tx trong window cũng `≤ train_end` |
| val | Train + val history trước `end_ts` (quá khứ hợp lệ) |
| test | Train + val + test history trước `end_ts` |

**Cấm:** dùng bất kỳ transaction `occurred_at >= end_ts` (= `as_of_ts`).

**Cấm:** tự suy “window lẫn train+val → bỏ sample” hoặc “gán split theo majority tx trong window”.

Mọi artifact feature/detection nên có cột `sample_split` (hoặc `split`) lấy từ helper trên.

Fit IF / calibrate FAN threshold: **chỉ** trên sample có `sample_split = train`. Tune trên `val`. Báo cáo cuối trên `test`.

Một feature có thể cần **historical lookback dài hơn 7d** (ví dụ “counterparty mới”) nhưng phải:

1. Ghi rõ trong feature spec  
2. Chỉ dùng quá khứ: `occurred_at < start_ts` (với `all_past`: `occurred_at < start_ts`)  
3. **Không** thay đổi scoring window 7d half-open  
4. Không dùng tx `>= end_ts`  

### 2.3. Graph representation

**Directed transaction graph**

| Thành phần | Định nghĩa |
|------------|------------|
| Node | `account_key` |
| Edge | `from_account_key → to_account_key` |

Edge / evidence phải **truy ngược** được tới transaction gốc, tối thiểu:

- `transaction_id`
- `occurred_at`
- source / destination (`from_account_key`, `to_account_key`)
- `amount` / `amount_received` (USD) khi cần
- `channel` khi cần

Không aggregate đến mức mất khả năng chỉ ra transaction chứng minh.

**Ba lớp khái niệm — phải tách trong code/docs**

| Lớp | Nghĩa |
|-----|--------|
| **A. Graph feature** | Measurement của account/network trong window (có thể weighted trên cạnh) |
| **B. Graph detector** | Logic phát hiện cấu trúc/pattern cụ thể |
| **C. Graph evidence** | Nodes / edges / transactions hỗ trợ kết quả detector |

### 2.4. Quan hệ với Isolation Forest khi trùng tên phép đo

Một số phép đo thô (vd `new_*_counterparty_ratio`, concentration tiền) **có thể xuất hiện ở cả IF và Graph**. Điều đó **được phép**, nhưng vai trò khác:

| Nhánh | Vai trò phép đo |
|-------|-----------------|
| **Isolation Forest** | Behavior anomaly input — tín hiệu “hành vi account bất thường so với đám đông” |
| **Graph** | Node-level **network / structural measurement** (degree, neighbor set, weighted edge money flow trên đồ thị) hoặc hỗ trợ detector |

- **Không** đưa graph feature table vào IF baseline.  
- **Không** đưa IF score / behavior model vào Graph.  
- Khi bảo vệ trước mentor: nhấn mạnh cùng raw measurement ≠ cùng feature semantics / pipeline.  
- Naming trong artifact Graph nên có tiền tố hoặc schema version rõ (vd cột trong `graph_features_v1.parquet`) để không nhầm file IF.

## 3. Graph features (baseline ~8)

Baseline **không** thêm PageRank, betweenness, embeddings, GNN, hay feature phức tạp khác trừ khi review sau.

Sau khi plan này được duyệt phần còn mở → khóa exact formula còn lại trong `docs/graph_feature_spec.md` trước khi code. Các công thức **đã khóa** dưới đây ghi thẳng vào feature spec (không mở lại trừ khi team đổi).

Quy ước chung (đã khóa một phần):

- Chỉ account có ≥ 1 tx (in hoặc out) trong window 7d mới có sample (khớp IF handoff).
- Tiền dùng USD: **inbound** ưu tiên `amount_received` (khi `to_account_key = account`); **outbound** ưu tiên `amount` (khi `from_account_key = account`).
- Degree / neighbor: đếm **unique** counterparty (không đếm mỗi tx một lần), trừ khi feature khác nói rõ.
- Ratio / index: nếu không có giao dịch hướng đó → giá trị `0` theo từng định nghĩa bên dưới (không ra `inf`).

### 3.1. `in_degree_7d`

| | |
|--|--|
| **Đo gì** | Số **unique** tài khoản gửi vào account trong 7d |
| **AML** | Hub nhận nhiều nguồn — tín hiệu fan-in / gom tiền |
| **Vai trò Graph** | Structural degree (in) trên đồ thị có hướng |
| **Inputs** | `to_account_key`, `from_account_key`, `occurred_at` |
| **Công thức (đã khóa)** | `\|{ from_account_key : tx.to = account, trong window }\|\` |
| **Window** | 7d scoring |
| **Edge cases** | Không inbound → `0` |

### 3.2. `out_degree_7d`

| | |
|--|--|
| **Đo gì** | Số unique destination account gửi tới trong 7d |
| **AML** | Hub tỏa / fan-out |
| **Vai trò Graph** | Structural degree (out) |
| **Công thức (đã khóa)** | `\|{ to_account_key : tx.from = account, trong window }\|\` |
| **Edge cases** | Không outbound → `0` |

### 3.3. `unique_neighbors_7d`

| | |
|--|--|
| **Đo gì** | Số unique neighbor undirected trong 7d: union(in, out) |
| **AML** | Độ rộng mạng cục bộ (một số) |
| **Công thức (đã khóa)** | `\| in_set ∪ out_set \|` |
| **Edge cases** | Cùng account vừa in vừa out: đếm 1 lần |
| **Quyết định** | **Giữ** feature này dù gần degree — hữu ích cho “độ rộng mạng” một chỉ số |

### 3.4. `in_out_degree_ratio_7d`

| | |
|--|--|
| **Đo gì** | Cân lệch hướng hub nhận vs gửi |
| **Công thức (đã khóa)** | `(in_degree_7d - out_degree_7d) / (in_degree_7d + out_degree_7d)` |
| **Edge cases** | `in = 0` và `out = 0` → `0` (không chia 0) |
| **Phạm vi** | Kết quả ∈ `[-1, 1]` |

### 3.5. `new_in_counterparty_ratio_7d`

| | |
|--|--|
| **Đo gì** | Tỷ lệ đối tác **inbound mới** trong window so với lịch sử trước window |
| **AML** | Mạng nhận mở rộng đột ngột |
| **Vai trò Graph** | Structural: sự mới của neighbor set trên đồ thị (không phải IF behavior vector) |
| **Historical lookback (đã khóa)** | `all_past`: mọi tx thỏa `occurred_at < start_ts` (toàn bộ trước scoring window half-open) |
| **Công thức (đã khóa)** | Với mỗi inbound CP trong 7d: “mới” nếu **chưa** từng có tx từ CP → account trong lookback; `ratio = n_new_in / max(n_in_unique_7d, 1)` |
| **Edge cases** | `in_degree_7d = 0` → `0`; account không có history → mọi CP trong 7d đều “mới” **về mặt định nghĩa** |
| **Không overlap** | history: `occurred_at < start_ts`; current window: `start_ts <= occurred_at < end_ts` |

**Cold-start policy (đã khóa — bắt buộc ghi trong `graph_feature_spec.md`):**

Đầu dataset / account mới quan sát: `new_*_counterparty_ratio` thường ≈ `1` vì **chưa có history**, không phải bằng chứng AML mạnh (“đột ngột mở rộng mạng”).

- Feature **giữ** công thức trên (không đổi toán học).  
- Thêm metadata / quality flag (không nhất thiết đưa vào 8 feature chính), ví dụ:  
  - `history_available` = `1` nếu tồn tại ≥ 1 tx của account với `occurred_at < start_ts`, else `0`  
  - và/hoặc `history_days_observed` = số ngày lịch có activity trước `start_ts`  
- **Diễn giải / Agent / eval:** chỉ coi `new_*` là tín hiệu structural đáng tin khi `history_available = 1` (hoặc `history_days_observed` ≥ ngưỡng đã document).  
- **Không** coi `ratio = 1` trong cold-start là bằng chứng rửa tiền mạnh.

### 3.6. `new_out_counterparty_ratio_7d`

Đối xứng 3.5 phía outbound. Cùng lookback `all_past`, công thức `n_new_out / max(n_out_unique_7d, 1)`, và **cùng cold-start policy**.

### 3.7. `inflow_concentration_7d`

| | |
|--|--|
| **Đo gì** | Tiền vào có tập trung vào ít nguồn không (weighted network) |
| **Vai trò Graph** | Money-flow **trên cạnh inbound** của node — không phải behavior feature IF |
| **Công thức (đã khóa)** | HHI: với mỗi nguồn `i`, `share_i = sum(amount_received từ i) / total_inflow`; `HHI = Σ share_i²` |
| **Cột tiền** | `amount_received` khi `to_account_key = account` |
| **Edge cases** | `total_inflow = 0` → `0`; một source duy nhất → HHI = `1` |
| **Phạm vi** | HHI ∈ `[0, 1]` (với unique sources; max = 1 khi một nguồn) |

### 3.8. `outflow_dispersion_7d`

| | |
|--|--|
| **Đo gì** | Tiền ra phân tán nhiều đích (đối trọng concentration) |
| **Công thức (đã khóa)** | `1 - HHI_out`, với HHI_out tính trên outbound shares theo `amount` khi `from_account_key = account` |
| **Edge cases** | `total_outflow = 0` → `0`; một đích duy nhất → dispersion = `0` |
| **Đối xứng** | Concentration cao ↔ dispersion thấp trên hướng tương ứng |

### Ngoài scope feature (không tự thêm)

PageRank, betweenness, embeddings, GNN features, community id, reciprocity phức tạp — trừ khi review sau.

---

## 4. Graph detectors (baseline = 4)

Detector codes trong plan này dùng tên **underscore** theo quyết định mới. Khi join Task 2 / IBM, map sang canonical hyphen:

| Detector (Graph) | IBM / Task 2 canonical |
|------------------|-------------------------|
| `CYCLE` | `CYCLE` |
| `FAN_IN` | `FAN-IN` |
| `FAN_OUT` | `FAN-OUT` |
| `GATHER_SCATTER` | `GATHER-SCATTER` |

Baseline **không** cover `SCATTER-GATHER`, `STACK`, `BIPARTITE`, `RANDOM`.

### 4.1. `CYCLE`

**Ý tưởng:** dòng tiền khép kín `A → B → C → … → A` trong window 7d.

**Baseline dự kiến**

- Directed, **simple** cycles (không lặp đỉnh trừ điểm đầu/cuối)
- Length **2–6**
- Trong graph dựng từ window 7d (half-open) của snapshot
- Mỗi motif cycle → một **`pattern_instance_id`** + một **`evidence_id`** (witness TX)
- Mỗi participant account → một **`detection_id`** (account-level signal) trỏ cùng `pattern_instance_id` (xem §5.1 / §6.2)

**Canonical hóa motif (đã khóa hướng — chi tiết trong detector spec)**

Cùng một chu trình có thể bị enumerator trả dưới nhiều rotation / điểm bắt đầu:

```text
A→B→C→A   ≡   B→C→A→B   ≡   C→A→B→C
```

Phải coi là **một** `pattern_instance_id`. Baseline: canonicalize bằng cách chọn rotation lexicographically nhỏ nhất trên chuỗi node (hoặc trên chuỗi `(from,to,transaction_id)` của witness đã chọn) — ghi exact rule trong detector spec; **không** emit ba motif trùng.

**Temporal consistency (đã khóa — witness transactions, không collapse multi-edge)**

Topology cycle **không đủ**. Baseline yêu cầu **temporal-consistent CYCLE** dựa trên **giao dịch thật**, không gán một timestamp đại diện (`min`/`max`) cho mỗi cặp cạnh trước khi kiểm tra.

Với một topological cycle `N1 → N2 → … → Nk → N1`, detector phải xác định có tồn tại một tập transaction thực tế `(tx1, tx2, …, txk)` — **mỗi hop đúng một transaction** tương ứng cạnh đó trong window — sao cho sau một **rotation hợp lệ**:

```text
t(tx1) <= t(tx2) <= … <= t(txk)
```

- **Không** collapse multi-edge (nhiều TX cùng cặp A→B) thành một timestamp duy nhất rồi mới check temporal.
- Nếu tồn tại tập TX thỏa điều kiện → đó là **witness evidence** của motif (một `evidence_id`).
- Nếu có nhiều witness hợp lệ: baseline chọn **một** witness theo **deterministic ordering** (đề xuất: sớm nhất theo `(t(tx1),…,t(txk), transaction_id…)` lexicographic) để reproducibility — ghi rõ trong detector spec.
- Cho phép timestamp bằng nhau giữa các hop kề; không chấp nhận chuỗi “đi ngược thời gian” trên vòng.

Ví dụ multi-edge: A→B có TX1@01:00 và TX2@18:00; B→C có TX3@12:00; C→A có TX4@15:00.  
Witness hợp lệ: `(TX1, TX3, TX4)` vì `01:00 ≤ 12:00 ≤ 15:00`.  
Không chỉ lấy `min` trên mỗi cạnh rồi kết luận.

Ví dụ **không** đạt nếu không có tổ hợp TX nào tạo được rotation không giảm thời gian (dù topology vẫn có cycle).

**Thuật toán:** tìm candidate topological cycles → canonicalize motif → tìm witness TX trên multi-graph. **Phải** đo performance / giới hạn độ phức tạp trên sample trước full data. Có thể prefilter bằng SCC.

**Threshold nghiệp vụ “có cycle?”:** presence của ≥1 temporal-consistent witness (length 2–6) là tín hiệu boolean/count ở **motif level**. Ranking score theo account (nếu có) thuộc `graph_score` — **chưa làm**.

### 4.2. `FAN_IN`

**Ý tưởng:** nhiều source → một center.

**Measurements (variables — chưa hard-code ngưỡng)**

- `in_degree` / unique incoming counterparties
- Inflow transaction count
- New incoming counterparties (cùng định nghĩa “new” với feature §3.5)
- Temporal concentration (burst inbound)

**Cấm:** `in_degree >= 5 ⇒ FAN_IN` hard-code như business truth.

**Threshold policy (bắt buộc)**

1. Ước lượng từ **train** distribution  
2. Tune trên **validation**  
3. Freeze config + `detector_version`  
4. Evaluate **test** một lần  

Code sau này: threshold **configurable** (file config / CLI), không magic number trong source.

**Còn mở:** percentile / metric cụ thể trên train–val (xem Decisions còn mở). Subject account cho detection row thường là **center** (1 motif ↔ 1 detection tại center).

### 4.3. `FAN_OUT`

Đối xứng `FAN_IN` (out_degree, unique out CP, outflow count, new out CP, temporal concentration). Cùng threshold policy. Ngưỡng cụ thể **còn mở**.

### 4.4. `GATHER_SCATTER`

**Hai pha:** many sources → center, sau đó center → many destinations.

Cần xét:

- Topology (fan-in rồi fan-out cùng center)
- **Timestamp order** (gather phase trước scatter phase)
- Số sources / destinations
- Inflow vs outflow amount (USD)
- Time gap giữa gather và scatter

**Temporal baseline v1 (đã đóng OPEN — train/val EDA)**

Không dùng literal `p75(in) ≤ p25(out)` (gần như 0 hit trên LI-Small) và không dùng `last_in ≤ first_out` làm rule chính.

**Median-based (frozen):**

```text
median(occurred_at | inbound) <= median(occurred_at | outbound) + tolerance_hours
```

Skeleton:

```text
1. Trong window 7d quanh account C:
2. Xác định inbound set S và outbound set D
3. Kiểm tra |S| >= s_min và |D| >= d_min
4. Kiểm tra temporal median-based (+ tolerance_hours)
5. Kiểm tra amount: sum(out)/sum(amount_received in) trong [r_lo, r_hi]
6. Emit evidence: S, D, tx ids gather/scatter, medians, amounts, ratio
```

Frozen numbers: `configs/graph/graph_gather_config_v1.json` (tuned on val; no test/GT).

---

## 5. Evidence + Task 2 / ground truth

### 5.1. Evidence contract + tách motif vs account signal (đã khóa)

**Ba ID — không gộp thành một:**

| ID | Nghĩa |
|----|--------|
| `pattern_instance_id` | Một **motif graph thực tế** trong `(as_of_ts, window, detector_version)` — unique sau canonicalize |
| `evidence_id` | Evidence (nodes + ordered witness TX + metrics) của **đúng một** motif |
| `detection_id` | **Account-level signal**: một subject account “exposed” tới motif đó (để join IF / alert) |

Quan hệ:

```text
pattern_instance_id  (1 motif, detect/evaluate một lần)
        ↓
evidence_id          (1 evidence blob / JSONL line)
        ↓
ordered witness TX + participants

detection_id         (nhiều dòng có thể trỏ cùng pattern_instance_id)
        ↓
account_key = subject nhận graph signal
```

**Ví dụ CYCLE** `A → B → C → A`:

| pattern_instance_id | evidence_id | participants |
|---------------------|-------------|--------------|
| `PI_CYCLE_001` | `EV_CYCLE_001` | A, B, C |

| detection_id | account_key | pattern_instance_id |
|--------------|-------------|---------------------|
| `DET_001_A` | A | `PI_CYCLE_001` |
| `DET_001_B` | B | `PI_CYCLE_001` |
| `DET_001_C` | C | `PI_CYCLE_001` |

Cùng evidence:

```text
A --TX17--> B
B --TX35--> C
C --TX48--> A
```

**Không** sinh ba motif / ba evidence giống nhau chỉ vì detector chạy theo ego-account.

**FAN_IN / FAN_OUT / GATHER_SCATTER:** subject thường là **center** → thường 1 `pattern_instance_id` ↔ 1 `detection_id` (center). Vẫn giữ đủ ba field cho schema thống nhất.

Evidence JSONL (theo `evidence_id` / motif), ví dụ:

```json
{
  "evidence_id": "EV_CYCLE_001",
  "pattern_instance_id": "PI_CYCLE_001",
  "as_of_ts": "2022-09-10T00:00:00+00:00",
  "snapshot_date": "2022-09-09",
  "window": "7d",
  "detected_pattern": "CYCLE",
  "accounts": ["A", "B", "C"],
  "transaction_ids": ["TX17", "TX35", "TX48"],
  "cycle_length": 3,
  "duration_hours": 8.0,
  "detector_version": "graph_detectors_v1"
}
```

Graph branch phải trả lời được:

1. Pattern / motif nào được phát hiện? (`pattern_instance_id`)  
2. Account nào tham gia / account nào nhận signal? (participants vs `detection_id.account_key`)  
3. Transaction witness nào chứng minh?  
4. Pattern xảy ra trong khoảng thời gian nào?  

Agent: Alert → Graph Tool → `detection_id` → `pattern_instance_id` / `evidence_id` → TX — không chỉ “account A có CYCLE”, và không nhận ba bản evidence trùng cho cùng cycle.

### 5.2. Task 2 ≠ Graph detector

```text
transaction graph
      ↓
Graph detectors (CYCLE / FAN_IN / …)
      ↓
detected IBM-style pattern code
      ↓
Task 2 mapping catalog  (docs/reference/typology_mapping_catalog_v1.json)
      ↓
FIN-07 typology T01–T10  (nếu mapping tồn tại)
```

| Pattern (IBM) | Mapping status (catalog v1) | Primary typology |
|---------------|-----------------------------|------------------|
| CYCLE | MAPPED | T03 |
| FAN-IN | MAPPED | T04 |
| FAN-OUT | MAPPED | T04 |
| GATHER-SCATTER | PARTIAL | null (secondary T02, T04) |

`LI-Small_Patterns.txt` / `data/processed/ibm_pattern_instances.json` (117 instances):

- **Ground truth** để evaluate / đối chiếu instance / tune threshold trên train+val khi thích hợp  
- **Không** feed vào detector để nói “account này có cycle”

Anti-leakage: không dùng pattern labels / typology làm graph feature; không peek test khi tune.

---

## 6. Graph score, artifacts, evaluation

### 6.1. `graph_score` — chưa làm trong baseline detector

Trước hết Graph phải tạo:

1. Graph feature table  
2. Detector results  
3. Detector evidence  

**Đã khóa phạm vi MVP detector:**

> Baseline **detector evaluation có thể hoàn thành mà chưa cần `graph_score`**.  
> Không ép mọi detector thành một scalar sớm. Fusion với IF/rule xảy ra sau khi team chốt aggregation.

Contract tương lai (khi team chốt aggregation):

```text
0 <= graph_score <= 1
cao hơn = rủi ro hơn
```

**Không implement** `graph_score` trong giai đoạn feature + 4 detectors + eval.

### 6.2. Output artifacts (riêng nhánh — không ghi đè `aml.duckdb`)

**A. Documentation**

| File | Vai trò |
|------|---------|
| `docs/graph_branch_plan.md` | Plan này (SoT hướng Graph) |
| `docs/graph_feature_spec.md` | Exact formulas — **v1.0 created** from locked §3 / §2.2 (features only; no detectors) |

**B. Features**

`data/processed/graph_features_v1.parquet`

Tối thiểu: `account_key`, `as_of_ts`, `window`, `sample_split` (từ `assign_snapshot_split`), + 8 feature values (+ optional `feature_schema_version`; optional cold-start flags `history_available` / `history_days_observed`).

**C. Detection / evidence (đã khóa format)**

Hai file riêng — không nhét nested nodes/edges/tx list vào một cột Parquet phức tạp:

| File | Nội dung |
|------|----------|
| `data/processed/graph_detection_v1.parquet` | Account-level detection signals — join IF / filter |
| `data/processed/graph_evidence_v1.jsonl` | Motif-level evidence (một dòng / `evidence_id`) |

**`graph_detection_v1.parquet`** — **một dòng = một account-level signal** tới một motif:

| Field | Ghi chú |
|-------|---------|
| `detection_id` | PK — signal của **một** `account_key` tới **một** motif |
| `pattern_instance_id` | FK — motif graph unique (canonicalize) |
| `evidence_id` | FK — evidence của motif (cùng mọi detection trỏ cùng motif) |
| `account_key` | Subject account (join IF scoring unit) |
| `as_of_ts`, `window` | Cùng convention half-open với IF |
| `sample_split` | Từ `assign_snapshot_split(as_of_ts, …)` — **không** suy từ mix tx |
| `detected_pattern` | `CYCLE` / `FAN_IN` / `FAN_OUT` / `GATHER_SCATTER` |
| `detector_version` | Version + config hash |
| Scalar metrics | Optional copy/summary; chi tiết nằm ở evidence |

Quy tắc:

```text
pattern_instance_id  → unique graph motif trong một as_of/window (+ version)
evidence_id          → evidence của motif (1–1 với pattern_instance_id ở baseline)
detection_id         → account-level exposure/signal tới motif đó
```

- Eval / đếm motif: group by `pattern_instance_id` (không đếm 3 lần vì 3 participant).  
- Join IF / alert theo account: dùng `detection_id` + `account_key`.  

**`graph_evidence_v1.jsonl`** — một dòng / `evidence_id` (= một motif), chứa participants / ordered hops / witness `transaction_ids`.

**Naming export (đã khóa):** underscore trong artifact Graph (`FAN_IN`); khi join Task 2 map sang hyphen (`FAN-IN`) theo bảng §4.

**D. Evaluation**

Evaluation reports:

- `detector_version`, config/threshold freeze  
- `split`  
- Metrics theo detector / IBM pattern type  
- Ground truth count vs detected count  
- Precision / Recall **khi** matching rule đã chốt  
- Coverage  

Eval này **không** phụ thuộc có `graph_score`.

**Matching GT (đã đóng — FAN / GATHER eval v1):**  
cùng loại pattern + cùng **center** + IBM time span overlap window 7d detection.  
Enrich Patterns.txt → `ibm_graph_eval_gt_v1.json`; GATHER audit → `reports/graph_eval_v2.json`; frozen FAN comparison → `reports/fan_final_test_comparison_v1.json`. CYCLE excluded.

---

## 7. Performance + test strategy

### 7.1. Performance (≈6.1M tx sau ETL)

Không thiết kế naive rõ ràng \(O(N^2)\) trên full graph lịch sử.

Kế hoạch baseline:

1. **DuckDB filter/aggregate trước** (window predicates + group by account) cho degree / concentration — tận dụng index Task 1  
2. Chỉ dựng NetworkX graph **theo window cần thiết** (per day snapshot hoặc per candidate account ego), không full-history một shot  
3. **Candidate pruning** trước CYCLE enumeration (degree filter, SCC, chỉ account active trong ngày)  
4. SCC trước `simple_cycles`; **cycle length ≤ 6**  
5. Pipeline: fixture nhỏ → sample ngày/account → full LI-Small  
6. Đo wall time / peak memory trước khi scale  

Bottleneck dự kiến: `simple_cycles` trên hub dày; fan thresholds quét mọi account-ngày nếu không prune.

### 7.2. Test plan tối thiểu

| Case | Kỳ vọng |
|------|---------|
| Directed cycle + tồn tại witness TX temporal hợp lệ | Một `pattern_instance_id` + evidence witness; N `detection_id` cho N participants |
| Cùng cycle qua rotation A-B-C / B-C-A / C-A-B | **Một** `pattern_instance_id` (canonicalized) |
| Topology cycle nhưng không có tổ hợp TX temporal hợp lệ | **Không** emit motif |
| Cùng account-ngày hai cycle khác nhau (A-B-C vs A-D-E) | Hai `pattern_instance_id` / hai evidence |
| Acyclic graph | Không emit false CYCLE |
| Fan-in fixture | Đúng in_degree / unique in CP; thường 1 detection tại center |
| Fan-out fixture | Đúng out_degree / unique out CP |
| Gather-scatter | Tôn trọng temporal hai pha (gather trước scatter theo rule đã chốt) |
| Future leak | Tx `occurred_at >= end_ts` không được dùng trong window |
| Label leak | `label_laundering` không có trong feature columns (`assert_no_label_leakage`) |
| Determinism | Cùng input + config → cùng pattern_instance_id + cùng witness khi tie-break |
| Evidence | Motif có `evidence_id` + witness TX; mỗi participant có `detection_id` trỏ đúng motif |

---

## 8. Quan hệ với Isolation Forest và Investigation Agent

### 8.1. Isolation Forest

| | IF | Graph |
|--|----|-------|
| Window | **7d** (baseline fusion) | **7d** (khóa) |
| Join key | `(account_key, as_of_ts, window)` | cùng |
| Output chính | behavior features, `anomaly_score`, top anomalous features | graph features, patterns, evidence (`graph_score` **sau**, không bắt buộc cho eval detector) |

- **Không** đưa graph feature vào IF baseline  
- **Không** đưa IF / behavior model vào Graph  
- Phép đo trùng tên (vd new counterparty): xem §2.4 — vai trò khác nhau  

### 8.2. Investigation Agent

Detection Layer → High-risk Alert → Agent chọn tool theo signal → Behavior / Transaction / **Graph** / Typology evidence → Case report → Analyst.

Graph = **evidence provider / tool** dưới Agent. LLM không tự tính graph pattern.

Luồng evidence tối thiểu:

```text
Alert → Graph Tool → detection_id → pattern_instance_id / evidence_id → ordered witness transaction_ids
```

---

## 9. Implementation roadmap (sau khi duyệt phần còn mở)

1. Chốt nốt mục **Decisions còn mở** (FAN / GATHER_SCATTER / GT; EDA trước khi hard-code FAN percentile)  
2. Viết `docs/graph_feature_spec.md` từ công thức đã khóa §3 (+ cold-start flags)  
3. Implement `assign_snapshot_split` chung (IF + Graph)  
4. Feature pipeline → `graph_features_v1.parquet` (có `sample_split`)  
5. Detector `CYCLE` (witness TX + canonicalize motif + fan-out `detection_id` theo participant) + evidence JSONL + perf smoke  
6. EDA trên **train samples** → `FAN_IN` / `FAN_OUT` configurable thresholds (train→val freeze→test)  
7. ~~`GATHER_SCATTER` median-based temporal~~ — baseline v1 frozen (`graph_gather_config_v1.json`); artifacts merged into `graph_detection_v1` / `graph_evidence_v1`  
8. ~~Eval vs Task 2~~ — FAN_IN / FAN_OUT / GATHER_SCATTER P/R/F1 on test (`scripts/run_graph_detector_eval.py`); CYCLE deferred  
9. (Sau / optional) `graph_score` aggregation theo account + fusion hook  

**Không làm trong bước document này:** implement code Graph, sửa Task 1/2, invent FAN/GATHER thresholds, invent `graph_score`.

---

## Decisions đã khóa (v0.5)

1. `in_out_degree_ratio_7d = (in - out) / (in + out)`; cả hai = 0 → `0`  
2. `new_*_counterparty_ratio`: lookback = **all past** trước window (`occurred_at < start_ts`) + **cold-start policy** (`history_available` / không diễn giải ratio=1 khi không có history)  
3. `inflow_concentration_7d` = **HHI** trên `amount_received` inbound  
4. `outflow_dispersion_7d` = **1 − HHI** trên `amount` outbound  
5. Giữ `unique_neighbors_7d`  
6. Export naming: **underscore** trong Graph artifact; map **hyphen** khi join Task 2  
7. Evidence storage: **`graph_detection_v1.parquet` + `graph_evidence_v1.jsonl`**  
8. Tách **`pattern_instance_id` (motif)** / **`evidence_id`** / **`detection_id` (account-level signal)**  
9. CYCLE: canonicalize rotations; witness TX temporal-consistent; không collapse multi-edge bằng `min`/`max`  
10. **`graph_score` chưa làm**; detector eval theo motif id  
11. Time window **half-open**; `as_of_ts = end_ts`; đồng bộ IF  
12. **`sample_split = assign_snapshot_split(as_of_ts, split_cutoffs)`** — theo `as_of_ts`, không theo mix `transaction.split`; helper chung IF+Graph  
13. Vai trò trùng measurement với IF: §2.4  

---

## Decisions còn mở (trước khi code detector / eval)

Chỉ các mục sau vẫn cần team/chốt thêm — **không** tự invent khi implement:

1. ~~**FAN_IN / FAN_OUT threshold strategy**~~ — **ĐÃ ĐÓNG:** v1 audit (`graph_fan_config_v1.json`); MVP freeze **v2B** → `graph_fan_config_v2.json` (deg/HHI/dispersion siết trên train/val volume; không tune theo test)  
2. ~~**GATHER_SCATTER parameters**~~ — **ĐÃ ĐÓNG (baseline v1, train/val EDA):**  
   - Temporal: **median-based** (không dùng literal `p75_in ≤ p25_out` vì gần như 0 hit trên LI-Small; cũng không dùng `last_in ≤ first_out`)  
     `median(occurred_at | inbound) <= median(occurred_at | outbound) + tolerance_hours`  
   - `s_min = d_min = 5` (unique counterparties)  
   - Amount ratio `sum(amount out) / sum(amount_received in) ∈ [r_lo, r_hi]` với grid tune val  
   - Frozen values: xem `configs/graph/graph_gather_config_v1.json`  
3. ~~**GT matching rule**~~ — **ĐÃ ĐÓNG (eval v1, FAN/GATHER only):**  
   - Same `detected_pattern` (map hyphen↔underscore) + **center** account (normalize `account_key` như Task 1) + IBM `[t_min, t_max]` **overlap** detection 7d window  
   - Enrich từ `LI-Small_Patterns.txt` (JSON Task 2 thiếu time; bank leading-zero lệch) → `data/processed/ibm_graph_eval_gt_v1.json`  
   - Credit: recall theo GT, precision theo `pattern_instance_id`; **primary = test**. FAN final comparison v1/v2B/v3-min nằm ở `reports/fan_final_test_comparison_v1.json`.  
   - **CYCLE excluded** while blocked; no complex matching  
4. **CYCLE performance bounds** — giới hạn số motif / snapshot; heuristic prune multi-edge enumeration nếu cần  
5. **Sample generation volume** — mọi account-ngày active vs subsample để kiểm soát kích thước artifact  

---

## Legacy / decisions superseded

Repo hiện có pipeline Graph Detection cho features, FAN và GATHER_SCATTER. CYCLE đã có code/unit test nhưng full-data còn bị chặn bởi hiệu năng. Các mâu thuẫn chủ yếu nằm ở **tài liệu hướng cũ**:

| Nguồn cũ | Nội dung cũ | Quyết định mới (plan này) |
|----------|-------------|---------------------------|
| `FIN-07_Mentor_Review_Data_ML_Graph_Agent.md` §7 | Kiến trúc **Cheap Graph + Deep Graph** 2 tầng; candidate union rồi deep | Graph baseline = **feature phẳng (~8) + 4 detectors**; không bắt buộc 2-tier execution trong scope này |
| Mentor review §7.3 / nhóm F | PageRank, cross_bank, ghép cheap graph **vào Isolation Forest** | **Không** PageRank; **không** đưa graph feature vào IF baseline |
| Mentor review §7.4 | Thêm pass-through, betweenness, community, scatter-gather | Baseline detectors **chỉ** CYCLE, FAN_IN, FAN_OUT, GATHER_SCATTER |
| Mentor review §7.1 | Graph tại `t` chứa mọi tx `occurred_at <= t` (full history tới t) | Scoring graph **window 7d half-open**: `start_ts <= occurred_at < end_ts` với `as_of_ts = end_ts`; lookback dài hơn chỉ khi feature spec cho phép |
| Mentor review §7.5 | Ví dụ JSON `graph_score` + nhiều signal codes đã “có vẻ chốt” | `graph_score` **chưa** được invent/implement như quyết định cuối |
| `docs/isolation_forest_handoff.md` | Window ví dụ `1d / 7d / 14d` | Graph (và fusion với IF) **khóa `window=7d`** cho scoring unit baseline |
| `FIN-07_Kien_truc_He_thong.md` Hình 4 | Agent state “Phân tích đồ thị” như bước agent | Agent **gọi Graph Evidence Tool**; không tự chạy detector trong LLM loop |
| `ARCHITECTURE.md` (boilerplate) | LangGraph agent generic | Không mô tả Graph AML branch — không dùng làm SoT Graph |
| Task 2 docs | Pattern names `FAN-IN` (hyphen); nhấn mạnh Task 2 **không** xây detector | Vẫn đúng: Task 2 = mapping/eval; detector thuộc Graph branch; cần map tên `FAN_IN` ↔ `FAN-IN` |

**Bước document này:** chưa xóa/sửa code hay rewrite toàn bộ mentor review — chỉ ghi nhận supersede. Sau khi plan được duyệt, nên cập nhật handoff/mentor notes hoặc link về file này để tránh hai SoT.

---

*Graph branch baseline — implementation status summarized above; frozen FAN details are in `docs/fan_detector_v3_design.md`.*
