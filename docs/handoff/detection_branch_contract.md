# Hợp đồng bàn giao — nhánh Rule và nhánh Graph

**Đối tượng:** người làm Detection Engine (`services/detection/`).
**Người viết:** phía tầng điều tra + hợp nhất điểm.
**Ngày:** 2026-08-15.

Tài liệu này không mô tả cách phát hiện. Nó mô tả **chỗ để ghi kết quả vào** để
tầng điều tra dùng được ngay, không cần sửa thêm dòng nào ở phía tôi.

---

## 1. Trạng thái hiện tại

Cả ba nhánh **đã chạy** trên bộ LI-Small và ghi vào PostgreSQL:

| Nhánh | Cảnh báo | Nguồn |
|---|---|---|
| rule | 19.704 | `src/detection/rule_engine.py` — quét trực tiếp bảng `transaction` |
| ml | 500 | Isolation Forest, `scripts/publish_if_alerts.py` |
| graph | 404 | bản phát hành fusion v2 (champion = graph) |

Bằng chứng đồ thị: **613 bản ghi** trong `graph_detector_evidence`, mọi cạnh đã
đối chiếu khớp với bảng `transaction` (0 cạnh lệch). `GetGraphEvidence` đọc được
và tác tử đã dựng được bằng chứng `GRAPH_PATTERN` thật.

Nhóm hành vi: 6 mã (T01, T02, T03, T04, T05, T08), 96,6% suy từ tín hiệu.

Tài liệu này giữ lại phần hợp đồng để ai mở rộng nhánh detection còn biết chỗ
ghi vào.

---

## 2. Nhánh Rule — đã có

`src/detection/rules.py` chứa bốn luật, mỗi luật khai tín hiệu riêng để nối vào
danh mục nhóm hành vi:

| Mã | Nội dung | Tín hiệu | Nhóm hành vi |
|---|---|---|---|
| R01_STRUCTURING | Nhiều giao dịch sát dưới ngưỡng báo cáo | `rule_trigger`, `repeated_amounts`, `short_window` | T01 |
| R02_RAPID_MOVEMENT | Tiền ra trong 2 giờ sau khi nhận | `rapid_outflow`, `short_dwell_time` | T05 |
| R03_VASP_EXPOSURE | Giá trị đi qua đối tác VASP | `vasp_link`, `rapid_cross_channel_flow` | T08 |
| R04_CROSS_BORDER_FLOW | Ngân hàng hai đầu khác quốc gia | `cross_border_flow` | *(phụ, không tự mở cảnh báo)* |

Ngưỡng nằm trong `RULE_THRESHOLDS`. **Chưa qua thẩm định nghiệp vụ** — đây là
việc cần làm trước khi chạy thật.

### Luật cố ý KHÔNG viết

* **T10 lệch hồ sơ khách hàng.** Bảng `customer` có 1.461.697 dòng nhưng chỉ một
  giá trị `expected_monthly_volume` và một `registered_country` — dữ liệu lấp chỗ
  do `ensure_subject` sinh. Viết luật trên đó là tạo cảnh báo không có căn cứ.
* **T06 quốc gia rủi ro cao.** Cần danh sách được chỉ định (FATF hoặc nội bộ).
  Repo chỉ có toạ độ quốc gia, không có xếp hạng rủi ro. R04 vì thế chỉ nêu dữ
  kiện "khác quốc gia", không khẳng định "rủi ro cao".

Muốn thêm hai luật này thì bổ sung dữ liệu trước, đừng bổ sung luật trước.

---

## 3. Nhánh Graph — đã có

`scripts/load_graph_evidence.py` nạp `graph_handoff/graph_evidence_v1.jsonl` vào
`graph_detector_evidence`, dịch `source_transaction_id` sang khoá canonical và
**loại cả bản ghi nếu bất kỳ cạnh nào không khớp**.

Đây là chốt chặn quan trọng nhất: bộ phản biện tất định đối chiếu từng cạnh với
bảng `transaction`, lệch một cạnh là cả phiên điều tra bị đánh trượt
(`MISSING_SOURCE_RECORD`). Nạp một nửa còn tệ hơn không nạp.

Muốn thêm mẫu hình mới, ghi vào `graph_detector_evidence` với payload khớp
`GraphEvidenceResult`:

```json
{
  "pattern": "CYCLE",
  "accounts": ["001:A", "070:B"],
  "edges": [{"from": "001:A", "to": "070:B", "transaction_id": "12217"}],
  "cycle_length": 3,
  "duration_hours": 18.5
}
```

`transaction_id` phải là khoá canonical (bigint dạng chuỗi), và `from`/`to` phải
khớp đúng bản ghi giao dịch đó. **Không** đặt `available` vào payload — đó là
trường suy ra lúc đọc.

---

## 4. Hợp nhất điểm

`get_risk_breakdown` đọc `behavior_feature_snapshot.features` và bật
`fusion_available` khi thấy đủ bộ khoá:

```
isolation_forest_percentile   graph_percentile
isolation_forest_contribution graph_contribution
champion                      -- "fusion" | "graph" | "isolation_forest"
```

Quan hệ phải giữ đúng (xem `src/fusion/model.py`):

```
contribution_i = weight_i × percentile_i
fusion_score   = Σ contribution_i
```

Bản phát hành hiện tại có `champion = "graph"`, nên `fusion_available` là false
và công cụ nêu đích danh nhánh thắng thay vì báo "chưa có runtime". Muốn thấy
`fusion_available = true` thì cần một bản phát hành mà fusion thắng ở bước kiểm
định — đó là việc huấn luyện.

---

## 5. Việc còn lại

### 5.1 Mô hình edge — đã huấn luyện lại trên LI-Small

`/transactions`, `/fc/crypto` và `/world` đều truy vấn qua
`transaction_model_score`. Bản phát hành edge cũ chấm trên HI-Medium nên ba trang
này rỗng sau khi chuyển sang LI-Small. Đã huấn luyện lại và nạp:

```
models/fin07_currency_native_policy_edge_li_small_v1.joblib
reports/edge-benchmark/li_small_currency_native_policy_v1.json
data/processed/edge-policy-v1/li_small_test_scores.parquet
```

**Không dùng `scripts/load_currency_native_edge_release.py` để nạp.** Nó là bộ
nạp từ đầu: chốt `_require_clean_schema` đòi `(customer, transaction, alert,
edge_model_release)` đều bằng 0, và nó tự nạp giao dịch từ `hi_medium.duckdb`.
Dùng `scripts/load_edge_scores.py` — chỉ ghi release + điểm, nối theo
`source_transaction_id`, không đụng bảng `transaction`.

Quy trình đầy đủ khi huấn luyện lại:

```bash
python scripts/train_currency_native_edge.py \
  --db data/processed/aml.duckdb \
  --model-out  models/fin07_currency_native_policy_edge_li_small_v1.joblib \
  --report-out reports/edge-benchmark/li_small_currency_native_policy_v1.json \
  --scores-out data/processed/edge-policy-v1/li_small_test_scores.parquet

python scripts/load_edge_scores.py \
  --scores  data/processed/edge-policy-v1/li_small_test_scores.parquet \
  --report  reports/edge-benchmark/li_small_currency_native_policy_v1.json \
  --model   models/fin07_currency_native_policy_edge_li_small_v1.joblib \
  --db      data/processed/aml.duckdb \
  --dataset "IBM AML LI-Small currency-native"

python scripts/load_bank_geography.py --accounts data/raw/ibm-aml/LI-Small_accounts.csv
```

#### Kết quả và giới hạn

| | HI-Medium | LI-Small |
|---|---|---|
| F1 (trung bình 5 seed) | 0,713 | **0,297** |
| PR-AUC (seed chính) | 0,713 | **0,237** |
| Precision / Recall | 0,914 / 0,592 | 0,435 / 0,232 |
| Tỷ lệ nhãn dương | 0,17% | 0,058% |

Chênh lệch này **nằm trong bản chất bộ dữ liệu**, không phải lỗi mô hình: tên
IBM AML mã hoá đúng điều đó — **HI** = *higher illicit ratio*, **LI** = *lower
illicit ratio*. LI-Small loãng gấp ba nên khó hơn hẳn. Mọi con số F1 quanh 0,7
trong tài liệu cũ là của HI-Medium; đừng trích dẫn chúng cho LI-Small.

**Độ phủ:** điểm chỉ có cho split `test` (1.223.740 / 6.119.572 dòng, tức 20%).
Ba trang trên vì thế chỉ hiển thị phần test. Muốn phủ toàn bộ thì chạy
`scripts/score_currency_native_edge.py` cho từng split rồi gộp parquet trước khi
nạp.

### 5.2 Tiêu thụ nhãn phản hồi

`review_feedback` đã có nhãn kèm điểm tại thời điểm ra quyết định, và
`GET /api/v1/feedback/labels` xuất được. Chưa có tiến trình nào đọc nhãn để hiệu
chỉnh ngưỡng hay huấn luyện lại.

### 5.3 Hiệu chỉnh ngưỡng

`RULE_THRESHOLDS` và `BEHAVIOR_SIGNAL_THRESHOLDS` là giá trị vận hành do kỹ
thuật đặt, chưa qua nghiệp vụ.

### 5.4 detection_result cho nhánh rule

Bảng có khoá ngoại NOT NULL trỏ `behavior_feature_snapshot`. Nhánh rule không
sinh ảnh chụp đặc trưng nên không ghi vào đó; đầu ra bền vững của nó là `alert`,
`alert_reason`, `alert_typology_match`. Muốn nhánh rule vào bảng chung thì phải
nới lược đồ trước.

---

## 6. Cách tự kiểm

```sql
SELECT detector, count(*) FROM alert GROUP BY 1;
SELECT typology_code, count(*) FROM alert GROUP BY 1 ORDER BY 2 DESC;
SELECT is_fallback, count(*) FROM alert_typology_match GROUP BY 1;
SELECT pattern, count(*) FROM graph_detector_evidence GROUP BY 1;

-- Không cạnh nào được lệch khỏi giao dịch nguồn.
SELECT count(*) FROM graph_detector_evidence g,
     LATERAL jsonb_array_elements(g.payload->'edges') AS e
LEFT JOIN transaction t ON t.transaction_id=(e->>'transaction_id')::bigint
     AND t.from_account_key=e->>'from' AND t.to_account_key=e->>'to'
WHERE t.transaction_id IS NULL;   -- phải bằng 0
```
