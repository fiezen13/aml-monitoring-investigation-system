# Mô hình dữ liệu — FIN-07

Nguồn dữ liệu, lược đồ cơ sở dữ liệu, đặc trưng mô hình và hợp đồng dữ liệu giữa
các thành phần.

Tài liệu liên quan: [đặc tả hệ thống](system-specification.md) ·
[thiết kế kỹ thuật](technical-design.md) · [kiến trúc](../architecture/architecture.md) ·
[hồ sơ mô hình](../ml/README.md).

---

## 1. Nguồn dữ liệu

Toàn bộ dự án dùng **dữ liệu công khai, tổng hợp**. Không có khách hàng thật,
không có dữ liệu định danh thật.

| Bộ dữ liệu | Vai trò | Đặc điểm |
|---|---|---|
| **IBM AML** (LI-Small, HI-Medium) | Nhánh phục vụ hàng đợi chính | LI-Small ≈ 6,12 triệu giao dịch / 576.781 tài khoản. HI-Medium là bộ **đang phục vụ bản triển khai**: 6.754.950 giao dịch đã chấm. Giấy phép CDLA-Sharing-1.0 |
| **SAML-D** | Nhánh ngân hàng xuyên biên giới | ≈ 9,5 triệu giao dịch, dùng chung bảng `transaction` với IBM |
| **Elliptic++** | Nhánh truy vết tài sản mã hoá | 67.504 giao dịch Bitcoin có nhãn |

Bộ dữ liệu ngân hàng Việt Nam mô phỏng (`ABM-BANK`) **đã gỡ tháng 08/2026**: dữ
liệu tự sinh không kiểm chứng được thì mọi chỉ số đo trên nó cũng không kiểm
chứng được. Lược đồ canonical trong `contracts/canonical/` giữ lại làm hợp đồng
dữ liệu cho tương lai.

### 1.1 Bộ dữ liệu gán nhãn những gì — và không gán nhãn những gì

Đây là câu quyết định phạm vi cả hệ thống. `LI-Small_Trans.csv` có **tám cột dữ
liệu và một cột nhãn**:

```text
Timestamp · From Bank · Account · To Bank · Account
Amount Received · Receiving Currency · Amount Paid · Payment Currency
Payment Format · Is Laundering
```

**Không có quốc gia. Không có cờ VASP. Không có hồ sơ khách hàng. Không có tên.**

Hệ quả trực tiếp lên phạm vi sản phẩm:

- Không xây được so khớp danh sách trừng phạt / PEP — không có tên để so khớp.
- Nhãn typology `T08` (dòng tiền gắn tài sản ảo) đã gỡ: luật sinh ra nó đọc một
  cờ `is_vasp` mà dự án **tự bịa**.
- Mọi nhãn khả dụng đều là **hình dạng dòng tiền trên đồ thị**, không phải động cơ.

File `*_Patterns.txt` gán nhãn các vụ rửa tiền theo mẫu hình; định dạng và cách
ánh xạ sang danh mục typology FIN-07 nằm ở mục 5.

### 1.2 Chia tập

Chia theo **thời gian**, không ngẫu nhiên. Chia ngẫu nhiên sẽ để mô hình nhìn
thấy tương lai của chính tài khoản nó đang chấm.

| Tập | Số dòng (LI-Small) |
|---|---|
| train | 3.671.838 |
| validation | 1.223.994 |
| test | 1.223.740 |

Nhãn dương trong tập test: **838 / 1.223.740 = 0,068%**.

Trên **HI-Medium** — bộ đang phục vụ bản triển khai — vùng đo của release
`REL-MP-6707e0cfbc33679f` có **11.016 nhãn dương trên 6.754.950 dòng = 0,163%**.
Cả hai đều dưới 0,2%. Xem
[thiết kế kỹ thuật §2.6](technical-design.md#26-vì-sao-không-dùng-accuracy) về
hệ quả lên bộ chỉ số đánh giá.

---

## 2. Lược đồ cơ sở dữ liệu

PostgreSQL 16. **51 file migration** trong [`db/init/`](../../db/init/), áp theo
thứ tự số và **idempotent** — chạy lại nhiều lần cho cùng kết quả.

### 2.1 Nhóm bảng

| Nhóm | Bảng chính |
|---|---|
| **Dữ liệu nghiệp vụ** | `transaction`, `account`, `customer`, `bank`, `country_geo` |
| **Phát hiện** | `detection_result`, `transaction_model_score`, `edge_model_release`, `graph_detector_evidence`, `behavior_feature_snapshot`, `behavior_batch` |
| **Cảnh báo & vụ việc** | `alert`, `alert_reason`, `alert_typology_match`, `aml_case`, `case_note`, `case_explanation`, `case_assignment` |
| **Điều tra bằng tác tử** | `investigation`, `investigation_agent_run`, `investigation_evidence`, `investigation_tool_call`, `investigation_trace`, `investigation_validation` |
| **SAR & phê duyệt** | `sar_draft`, `sar_statement`, `sar_statement_evidence`, `approval`, `review_feedback` |
| **Người dùng & kiểm toán** | `app_user`, `app_session`, `audit_log`, `system_setting` |
| **Tài sản mã hoá** | `bitcoin_scored_tx`, `crypto_review` |
| **Địa lý vận hành** | `edge_country_hub`, `edge_country_flow`, `operational_country_hub`, `operational_country_flow` |
| **Luồng (streaming)** | `stream_transaction`, `stream_edge`, `stream_edge_score`, `stream_alert`, `stream_case`, `stream_ibm_edge`, `stream_bitcoin_tx`, … |
| **Chất lượng & giám sát** | `data_quality_check`, `model_monitor_metric` |
| **Giữ chỗ, chưa có đường nạp** | `watchlist_entry`, `watchlist_version`, `screening_result` |

Lược đồ phụ `fc.*` phục vụ các màn hình console (thực thể, quan hệ, hành lang
dòng tiền, lượt chạy tác tử); `label.*` và `fc_gt.*` giữ nhãn ground truth, **chỉ
dùng để đánh giá**, không bao giờ là đầu vào detector.

### 2.2 Ràng buộc cưỡng chế ở tầng cơ sở dữ liệu

Ba ràng buộc quan trọng nhất **không** nằm trong mã ứng dụng — chúng nằm trong
chính cơ sở dữ liệu, nên không lách được bằng cách gọi thẳng SQL:

| Ràng buộc | Cơ chế | File |
|---|---|---|
| Nhật ký kiểm toán **chỉ ghi thêm** | Trigger chặn `UPDATE` / `DELETE` trên `audit_log` | [`002_audit_immutability.sql`](../../db/init/002_audit_immutability.sql) |
| Tác tử **chỉ đọc** | Vai trò PostgreSQL riêng, chỉ cấp `SELECT` | [`003_agent_readonly_role.sh`](../../db/init/003_agent_readonly_role.sh) |
| Trạng thái vụ việc hợp lệ | `CHECK` trên cột trạng thái của `aml_case` | [`001_schema.sql`](../../db/init/001_schema.sql) |

> **Lưu ý khi thao tác dữ liệu.** Trigger bất biến trên `audit_log` cũng chặn cả
> thao tác dọn dữ liệu hợp lệ — xoá một vụ việc thử nghiệm sẽ vấp trigger. Đây là
> hành vi đúng, không phải lỗi.

### 2.3 Truy nguyên mô hình

`edge_model_release` giữ mã băm **SHA-256** của file mô hình đã sinh ra điểm đang
phục vụ. PostgreSQL **không** giữ file mô hình; [`models/`](../../models/) là bản
gốc duy nhất. Mất file thì mã băm ấy không còn đối chiếu được với gì.

Đúng **một** release ở trạng thái `active` tại một thời điểm. Các nhánh Bitcoin và
SAML-D phục vụ ở trạng thái `reference` qua bảng riêng, không chiếm slot `active`.

---

## 3. Khoá và định danh

| Khoá | Dạng | Ghi chú |
|---|---|---|
| `account_key` | `bank:account` | Định danh tài khoản dùng xuyên suốt mọi nhánh |
| `transaction_id` | chuỗi | Khoá khử trùng lặp ở tầng SILVER (tầng này **chưa hiện thực**) |
| `as_of_ts` | `TIMESTAMPTZ` | Mốc chốt sổ, cuối ngày lịch UTC (`23:59:59Z`) |
| `window` | `'1d'` / `'7d'` | Cửa sổ nhìn lùi, **nửa mở** `[as_of_ts − window, as_of_ts)` |
| `sample_split` | `train`/`val`/`test` | Gán theo **thời gian của snapshot**, không theo nhãn giao dịch |
| `alert_id` | `ALT-<nhánh>-<hash>` | Tiền tố cho biết nhánh nào sinh ra |
| `release_id` | `REL-EDGE-<hash>` | Định danh một lần phát hành mô hình |

---

## 4. Đặc trưng hành vi (Isolation Forest)

**20 đặc trưng** cấp `account_key`, mỗi mẫu là bộ ba
`(account_key, as_of_ts, window)`. Sáu nhóm:

| Nhóm | Đặc trưng | Kiểu |
|---|---|---|
| **A · Cường độ hoạt động** | `txn_count`, `incoming_count`, `outgoing_count`, `active_days`, `txn_per_active_day` | `BIGINT` / `DOUBLE` |
| **B · Khối lượng dòng tiền** | `total_inflow`, `total_outflow`, `net_flow`, `outflow_inflow_ratio` | `DOUBLE`, biến đổi `log1p` |
| **C · Tốc độ luân chuyển** | `rapid_outflow_ratio`, `median_dwell_time` (giờ) | `DOUBLE` |
| **D · Mạng lưới đối tác** | `unique_in_counterparties`, `unique_out_counterparties`, `new_counterparty_ratio` | `BIGINT` / `DOUBLE` |
| **E · Hình dạng số tiền** | `median_amount`, `p90_amount`, `amount_std`, `repeated_amount_ratio` | `DOUBLE`, `log1p` |
| **F · Nhịp thời gian** | `median_inter_txn_gap`, `p10_inter_txn_gap` (phút) | `DOUBLE` |

Nhóm A bắt cường độ, B bắt khối lượng, C bắt kiểu "tiền vào rồi rút ngay", D bắt
mạng lưới bất thường, E bắt số tiền lặp lại kiểu chia nhỏ, F bắt giao dịch dồn
sát nhau.

---

## 5. Đặc trưng đồ thị

**8 phép đo + 2 trường siêu dữ liệu khởi động nguội**, mỗi dòng ứng với
`(account_key, as_of_ts)` trên cửa sổ 7 ngày:

| Cột | Ý nghĩa |
|---|---|
| `in_degree_7d` | Số đối tác khác nhau chuyển tiền **vào** tài khoản |
| `out_degree_7d` | Số đối tác khác nhau **nhận** tiền từ tài khoản |
| `unique_neighbors_7d` | Tổng số đối tác khác nhau theo cả hai chiều |
| `in_out_degree_ratio_7d` | Tỷ lệ bậc vào / bậc ra, có xử lý mẫu số bằng 0 |
| `new_in_counterparty_ratio_7d` | Tỷ lệ đối tác nhận vào **chưa từng** xuất hiện trước cửa sổ |
| `new_out_counterparty_ratio_7d` | Tỷ lệ đối tác gửi ra **chưa từng** xuất hiện trước cửa sổ |
| `inflow_concentration_7d` | Mức **tập trung** của dòng tiền vào giữa các đối tác |
| `outflow_dispersion_7d` | Mức **phân tán** của dòng tiền ra giữa các đối tác |
| `history_available` | Có lịch sử trước cửa sổ để tính đặc trưng "mới lạ" hay không |
| `history_days_observed` | Số ngày có giao dịch lịch sử trước cửa sổ |

Hai trường cuối tồn tại vì một lý do cụ thể: đặc trưng "đối tác mới" **vô nghĩa**
với tài khoản chưa có lịch sử. Đánh dấu rõ ràng còn hơn để mô hình hiểu nhầm giá
trị 0 là "không có đối tác mới".

Đầu ra của detector ghép thêm: `fan_in_hit`, `fan_out_hit`, `gather_scatter_hit`,
`cycle_hit`, `cycle_motif_count`, `cycle_length_min`, `cycle_length_max`,
`detector_motif_count`.

---

## 6. Danh mục typology

Mã T01–T10, định nghĩa tại [`src/domain.py`](../../src/domain.py), danh mục ánh xạ
có phiên bản tại [`docs/reference/typology_mapping_catalog_v1.json`](../reference/typology_mapping_catalog_v1.json)
và lược đồ tại [`contracts/registry/typology.v1.schema.json`](../../contracts/registry/typology.v1.schema.json).

| Mã | Nhãn | Trạng thái |
|---|---|---|
| `T00` | Rủi ro theo mô hình — chưa khớp nhóm hành vi có tên | đang phục vụ |
| `T01` | Chia nhỏ giao dịch dưới ngưỡng báo cáo | đang phục vụ |
| `T02` | Tài khoản trung chuyển trong mạng lưới | đang phục vụ |
| `T03` | Giao dịch vòng quay lại chủ thể ban đầu | đang phục vụ |
| `T04` | Gom vào và toả ra bất thường | đang phục vụ |
| `T05` | Luân chuyển tốc độ cao | đang phục vụ |
| `T06` | Giao dịch với vùng tài phán rủi ro cao | đang phục vụ |
| `T07` | Sử dụng tài khoản người khác đứng tên | đang phục vụ |
| `T08` | *(dòng tiền gắn tài sản ảo)* | **đã gỡ** — luật nguồn đọc cờ tự bịa |
| `T09` | Thương mại quốc tế khai khống giá trị | đang phục vụ |
| `T10` | Dòng tiền không tương xứng hồ sơ khách hàng | đang phục vụ |

Mã `T08` để trống, **không tái dùng** cho nghĩa khác — một mã đã xuất hiện trong
nhật ký kiểm toán thì không được đổi nghĩa.

`T00` tồn tại vì thà nói "chưa khớp nhóm nào" còn hơn gán bừa một mẫu hình cho một
cảnh báo có căn cứ nhưng không khớp mô tả nào.

---

## 7. Hợp đồng dữ liệu

[`contracts/`](../../contracts/) là **nguồn sự thật duy nhất** về hình dạng dữ liệu
đi giữa các thành phần. Mọi producer và consumer phải tuân theo; không thành phần
nào được tự định nghĩa lại một cấu trúc đã có ở đây.

| Thư mục | Nội dung |
|---|---|
| `contracts/common/` | Kiểu dùng chung |
| `contracts/events/` | Phong bì sự kiện (`envelope.v1`) và các sự kiện nghiệp vụ: `aml.alert.created`, `aml.detection.result`, `aml.case.changed`, `aml.agent.claim`, `aml.agent.toolcall`, `aml.analyst.decision`, `aml.feature.updated`, `bank.*` |
| `contracts/canonical/` | Thực thể canonical có phiên bản: `transaction`, `account` (v1/v2), `customer` (v1/v2), `relationship` (v1/v2), `business`, `device`, `merchant`, `case`, `evidence-item`, `agent-run` |
| `contracts/agent/` | Hợp đồng tác tử: `tool-call-request`, `tool-call-response`, `structured-case-output`, `agent-case-state` |
| `contracts/ingestion/` | Lược đồ nạp dữ liệu: `aml-transaction-v1`, `behavior-batch-v1` |
| `contracts/registry/` | `typology.v1` |

Mỗi hợp đồng đi kèm **ví dụ hợp lệ và ví dụ không hợp lệ** trong `examples/`; bộ
kiểm thử xác thực cả hai chiều — hợp đồng phải chấp nhận ví dụ hợp lệ **và** từ
chối ví dụ không hợp lệ. Chạy bằng `make contracts-check`.

Phiên bản v2 của `account`, `customer`, `relationship` là hợp đồng **bank-observable
và không chứa nhãn**: chúng cố ý không mang ý đồ của trình mô phỏng, vai trò tội
phạm, hay tư cách thành viên kịch bản — để không tạo đường rò rỉ nhãn vào tầng
phát hiện.

---

## 8. Quy tắc dữ liệu bắt buộc

- Không commit `.env`, thông tin xác thực, dữ liệu IBM AML thô, DuckDB, parquet
  điểm số, hay dump PostgreSQL.
- `Amount Paid` / `Amount Received` và `Payment Currency` / `Receiving Currency`
  **giữ nguyên**.
- Chuẩn hoá theo loại tiền **chỉ fit trên tập train**; không dùng tỷ giá tĩnh
  trong mô hình.
- Chỉ quy đổi USD cho luật nghiệp vụ / pháp lý, và phải có nguồn tỷ giá kèm
  `as_of_ts`.
- Điểm mô hình dùng để **xếp hàng ưu tiên**, không phải xác suất rửa tiền và
  không phải kết luận pháp lý.
- Tác tử **không được đọc nhãn ground truth**; mọi kết luận cần bằng chứng và cần
  người rà soát.

---

## 9. Lineage mô hình và gói bàn giao

File mô hình nằm rải ở vài nơi (`models/`, `data/models/`, `if_handoff/`,
`graph_handoff/`, `models/mega-pna/`). Đây **không phải lộn xộn** — mỗi vị trí
tương ứng một mốc trong lineage, có manifest và checksum kèm theo.

### 9.1 Điều quan trọng nhất

**API, web và worker KHÔNG nạp file mô hình lúc chạy.** Chúng đọc **điểm đã tính
sẵn** trong PostgreSQL (`transaction_model_score`, `bitcoin_scored_tx`,
`edge_model_release`). File mô hình chỉ cần cho **script chấm điểm và huấn luyện
ngoại tuyến**.

Hệ quả: xoá nhầm file mô hình **không** làm sập bản đang chạy — nhưng **phá
runbook tạo lại dữ liệu**.

### 9.2 Ba mô hình đang phục vụ

| | Bitcoin | IBM AML *(hàng đợi chính)* | SAML-D |
|---|---|---|---|
| **File** | `data/models/bitcoin_elliptic/elliptic_rf.joblib` | `models/fin07_currency_native_policy_edge_li_small_v1.joblib` | `data/models/samld/runs/seed{42,1337,2026}/model_seed*.pt` |
| **Loại** | Random Forest, chấm độc lập từng giao dịch | Edge model chấm từng giao dịch, đặc trưng theo tiền tệ gốc | MEGA-PNA (Multi-PNA + Edge Updates), chấm cạnh trên đồ thị |
| **Mã nạp** | `src/bitcoin_aml/scoring.py`, `scripts/build_elliptic_scored.py` | `src/models/currency_native_edge.py`, `scripts/{train,score,load}_currency_native_edge*.py` | `src/samld/inference.py`, `scripts/samld_benchmark.py` |
| **Ghi vào** | `bitcoin_scored_tx` | `transaction_model_score` | bảng riêng của nhánh |
| **Release** | `REL-BTC-ELLIPTIC-ORIG-V1` (`reference`) | `REL-EDGE-…` (**`active`**) | `REL-GRAPH-SAMLD-V1` (`reference`) |
| **Màn hình** | Truy vết tài sản mã hoá | Tổng quan · Tra cứu giao dịch · Cảnh báo | — |

> **Lỗi đã biết ở nhánh SAML-D.** `SamlDetector` hard-code `node_features=1`
> trong khi checkpoint được huấn luyện với `ego_ids=True` (cần 2) → **nạp
> checkpoint sẽ lỗi**. Bản đúng nằm ở `src/mega_pna/inference.py`. Phải sửa
> trước khi chấm lại nhánh này.

`data/models/*` và `data/processed/*` bị `.gitignore` chặn — chỉ có trên máy cá
nhân và Drive. `models/*` (gồm mô hình IBM đang `active`) **có** trong Git.

### 9.3 Phần legacy — giữ lại có lý do

Không còn phục vụ, nhưng **không phải rác**: chúng nằm trong chuỗi nạp dữ liệu
hoặc được manifest bàn giao tham chiếu.

| Thư mục / file | Là gì | Vì sao giữ |
|---|---|---|
| `src/fusion/`, `models/fin07_if_graph_fusion_v*.joblib`, `models/fin07_{if,graph}_7d_v2.joblib`, `configs/fusion/`, `reports/fusion*` | Nhánh IF + Graph fusion cũ, tiền thân của IBM edge model | `scripts/load_edge_scores.py`, `scripts/load_graph_evidence.py` và `src/services/typology_assignment.py` đều tham chiếu `load_fusion_release.py` → **nằm trong chuỗi nạp dữ liệu**. Xoá là phá runbook nạp lại CSDL |
| `graph_handoff/graph_histgb_v1.joblib` | Mô hình đồ thị đã bàn giao | `src/detection/graph_loader.py` dùng trực tiếp |
| `if_handoff/` | Gói bàn giao Isolation Forest đã đóng băng | `if_handoff/manifest.json` giữ SHA-256 của từng file trong gói; sửa hay xoá một file là làm hỏng chuỗi kiểm chứng |
| `models/mega-pna/…/seed_42.pt` | Checkpoint bàn giao MEGA-PNA | `scripts/build_mega_pna_release.py` dùng đúng đường dẫn này |

Muốn dọn thật sự phần legacy thì phải xác nhận trước bản đang chạy đã nạp dữ
liệu qua đường nào, rồi xoá theo từng cụm — **không xoá loạt**.

### 9.4 Gói bàn giao đồ thị

`graph_handoff/` là bản v1 đã **đóng băng**, để tích hợp mà không phải chạy lại
detector hay huấn luyện lại.

| Tệp | Nội dung |
|---|---|
| `graph_features_v1.parquet` | Đặc trưng đồ thị canonical cấp tài khoản–snapshot |
| `graph_detection_v1.parquet` | Detection của FAN / GATHER_SCATTER / CYCLE |
| `graph_evidence_v1.jsonl` | Giao dịch chứng minh cho từng detection |
| `graph_account_modeling_v1.parquet` | Bảng nối đặc trưng, hit/count detector và target |
| `graph_histgb_v1.joblib` | HistGradientBoosting v1 đã fit **chỉ trên train** |
| `graph_scores_v1.parquet` | Điểm mô hình kèm khoá nối, split và hit detector |
| `graph_pipeline_manifest_v2.json` | Phiên bản, checksum, số dòng, trạng thái kiểm tra |

Năm payload `.parquet` / `.jsonl` **không đưa vào Git** — lấy từ Drive rồi đối
chiếu SHA-256 trong manifest trước khi tích hợp.

Cấu hình mô hình: 18 cột (10 đặc trưng đồ thị + 8 cột detector),
`learning_rate=0.1`, `max_iter=100`, `max_leaf_nodes=31`,
`min_samples_leaf=100`, `l2_regularization=1.0`, class weight cân bằng.

Cách tích hợp: nối `graph_scores_v1.parquet` vào bảng nghiệp vụ bằng
`(account_key, as_of_ts)`, giữ `sample_split`, chọn ngưỡng theo chính sách đã ghi
trong báo cáo baseline. `graph_score` là **xác suất lớp dương**, chưa phải quyết
định phát cảnh báo.

> **Không dùng `target_laundering`** trong tệp score khi đưa vào hệ thống chấm
> điểm thật. Cột đó chỉ tồn tại trong bảng modeling để đánh giá current-window —
> dùng nhầm là rò rỉ nhãn.
