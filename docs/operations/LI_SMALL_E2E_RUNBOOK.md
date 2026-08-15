# FIN-07 — Runbook LI-Small end-to-end

Tài liệu này là thứ tự chạy chuẩn để dựng lại hệ thống FIN-07 từ bộ dữ liệu
IBM AML **LI-Small**, huấn luyện hai nhánh Behaviour và Graph, hợp nhất score,
nạp dữ liệu vận hành vào PostgreSQL, rồi kiểm tra Console, Grafana, Loki và
Jaeger.

> Chạy từ thư mục gốc của repo. Không chạy `make db-reset` trừ khi thật sự muốn
> xoá toàn bộ dữ liệu PostgreSQL. Task 1 bên dưới **ghi lại**
> `data/processed/aml.duckdb`, vì vậy hãy sao lưu file đó nếu cần giữ bản cũ.

## 0. Trạng thái hiện tại cần biết

| Khối | Trạng thái |
|---|---|
| LI-Small CSV → DuckDB + train/val/test | Chạy được |
| Typology từ `LI-Small-Patterns.txt` | Chạy được |
| Huấn luyện Isolation Forest rolling 7 ngày | Chạy được |
| Tạo Graph features + chạy FAN/GATHER/CYCLE + benchmark | Chạy được |
| Retrain và lưu estimator Graph mới | Chạy được qua `make train-fusion` |
| Retrain chung IF + Graph + calibration/fusion v2 | Chạy được |
| Bulk load account/transaction/detection/alert vào PostgreSQL | Chạy được, idempotent |

Không dùng `scripts/build_fusion_release.py` để thay cho retrain: script đó chỉ
đóng gói hai handoff cũ. Luồng chuẩn bên dưới luôn huấn luyện lại IF và Graph
trên cùng một contract snapshot trưởng thành.

## 1. Kiểm tra môi trường và giữ nguyên mã nguồn

```bash
cd /Users/nguyenbao/P-022
git branch --show-current
git status --short
docker --version
docker compose version
python3 --version
```

Nhánh mong đợi là `develop`. Trước khi chạy job dài, commit những thay đổi mã
nguồn cần giữ. Không dùng `git clean -fdx`, vì lệnh đó có thể xoá dữ liệu và
artifact local không thể lấy lại.

Tạo môi trường Python nếu chưa có:

```bash
cd /Users/nguyenbao/P-022
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade --upgrade-strategy eager -r requirements-dev.txt
python -m pip check
```

Phải dùng đúng Python trong repo:

```bash
which python
python -c 'import sys; print(sys.executable)'
```

Cả hai kết quả phải trỏ vào `/Users/nguyenbao/P-022/.venv/`. Gói meta
`opentelemetry-exporter-otlp` giữ exporter gRPC và HTTP ở cùng một phiên bản;
`pip check` phải in `No broken requirements found.`.

Tạo `.env` nhưng không ghi đè file đang dùng:

```bash
cd /Users/nguyenbao/P-022
test -f .env || cp .env.example .env
```

## 2. Kiểm tra đúng ba file LI-Small

```bash
cd /Users/nguyenbao/P-022
test -s data/raw/ibm-aml/LI-Small_Trans.csv
test -s data/raw/ibm-aml/LI-Small_accounts.csv
test -s data/raw/ibm-aml/LI-Small-Patterns.txt
ls -lh \
  data/raw/ibm-aml/LI-Small_Trans.csv \
  data/raw/ibm-aml/LI-Small_accounts.csv \
  data/raw/ibm-aml/LI-Small-Patterns.txt
```

Tên file pattern có dấu gạch ngang: `LI-Small-Patterns.txt`. Phải truyền đường
dẫn này tường minh vì default của một số script cũ dùng dấu gạch dưới.

## 3. Chạy cổng chất lượng trước khi xử lý dữ liệu

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m pytest -m "not integration"
.venv/bin/python scripts/validate_observability.py
```

Chỉ đi tiếp khi tất cả lệnh thoát với mã `0`.

Không gọi trực tiếp `pytest`: máy có thể lấy executable từ Anaconda hoặc một
Python khác dù dependencies đã được cài đúng trong `.venv`. Nếu cần kiểm tra:

```bash
command -v python
command -v pytest
.venv/bin/python -m pip show pytest-asyncio
```

## 4. Build image và áp migration PostgreSQL

Migration `011_remove_behavior_14d.sql` loại bỏ contract model 14 ngày;
`012_operational_geography_rollup.sql` tạo serving rollup để World Monitor
không aggregate hàng triệu giao dịch trên request path. Cần build lại image
`migrate` trước, nếu không container cũ không nhìn thấy migration mới.

```bash
cd /Users/nguyenbao/P-022
docker compose build migrate api worker web
docker compose up -d --wait postgres redis
make migrate
make migrate-status
```

Cổng kiểm tra: `make migrate-status` phải báo migration 001–012 đã áp và không
còn file chờ.

Nếu migration 011 dừng vì còn dòng `window='14d'`, không xoá mù dữ liệu. Kiểm
tra trước:

```bash
docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-fin07}" \
  -d "${POSTGRES_DB:-fin07}" \
  -c "SELECT feature_window, count(*) FROM behavior_batch GROUP BY feature_window ORDER BY feature_window;" \
  -c "SELECT feature_window, count(*) FROM behavior_feature_snapshot GROUP BY feature_window ORDER BY feature_window;"
```

## 5. Dựng lại DuckDB đầy đủ và chia train/val/test

Lệnh này thay thế bản DuckDB rút gọn hiện tại bằng toàn bộ LI-Small:

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
python scripts/run_task1_etl.py \
  --raw data/raw/ibm-aml/LI-Small_Trans.csv \
  --db data/processed/aml.duckdb \
  --report-dir data/processed \
  --seed 42 \
  --strict-li-small-stats
```

DQ kiểm tra population đúng theo contract ETL. Raw LI-Small có 6.924.049
transactions và 705.907 account endpoint. Sau khi loại 804.477 self-loop trước
bước dựng Graph, model input còn 6.119.572 transactions và 576.781 active
account. Không so population sau filter với con số raw.

Kiểm tra bắt buộc:

```bash
python - <<'PY'
from pathlib import Path
import json
import duckdb

db = Path("data/processed/aml.duckdb")
assert db.is_file(), db
assert Path("data/processed/dq_report.json").is_file()
assert Path("data/processed/split_cutoffs.json").is_file()

con = duckdb.connect(str(db), read_only=True)
total, start, end = con.execute(
    "SELECT count(*), min(occurred_at), max(occurred_at) FROM transaction"
).fetchone()
splits = dict(con.execute(
    "SELECT split, count(*) FROM transaction GROUP BY split ORDER BY split"
).fetchall())
accounts = con.execute("SELECT count(*) FROM account").fetchone()[0]
con.close()

calendar_days = (end.date() - start.date()).days + 1
print({
    "transactions": total,
    "accounts": accounts,
    "start": str(start),
    "end": str(end),
    "calendar_days": calendar_days,
    "splits": splits,
})
assert total == 6_119_572, "DuckDB không khớp population sau self-loop filter"
assert calendar_days >= 17, "Không đủ 17 ngày lịch"
assert set(splits) == {"train", "val", "test"}, "Thiếu split"

report = json.loads(Path("data/processed/dq_report.json").read_text())
print("DQ warnings:", report.get("warnings", []))
PY
```

Lưu ý: LI-Small trải trên 17 ngày lịch nhưng phần lớn giao dịch tập trung trong
10 ngày đầu. Cửa sổ 7 ngày là contract feature rolling; nó không có nghĩa hệ
thống chỉ đọc bảy ngày của toàn bộ dataset.

## 6. Dựng ground truth typology

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
python scripts/run_task2_typology.py \
  --patterns data/raw/ibm-aml/LI-Small-Patterns.txt \
  --catalog docs/reference/typology_mapping_catalog_v1.json \
  --out-dir data/processed
```

Chỉ đi tiếp khi script in `OK` và các artifact Task 2 tồn tại trong
`data/processed/`.

## 7. Huấn luyện nhánh Behaviour — Isolation Forest 7 ngày

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
make behavior-train
```

Kiểm tra artifact:

```bash
test -s data/processed/behavior-7d/isolation_forest_model_7d.joblib
test -s data/processed/behavior-7d/if_scores_7d.parquet
test -s reports/behavior-7d/evaluation_7d.txt
test -s reports/behavior-7d/best_threshold_7d.txt
test -s reports/behavior-7d/manifest.json
python -m json.tool reports/behavior-7d/manifest.json >/dev/null
```

Nếu manifest cảnh báo train chưa có snapshot trưởng thành đủ 7 ngày, đó là
giới hạn thật của cách chia thời gian trên LI-Small; không được giấu cảnh báo
hoặc dùng test để chọn threshold.

## 8. Chạy nhánh Graph và benchmark độc lập

### 8.1. Tạo Graph features

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
python scripts/run_graph_features.py \
  --db data/processed/aml.duckdb \
  --cutoffs data/processed/split_cutoffs.json \
  --out data/processed/graph_features_v1.parquet
```

### 8.2. Chạy FAN, GATHER_SCATTER và CYCLE

```bash
GRAPH_FEATURE_SHA="$(shasum -a 256 data/processed/graph_features_v1.parquet | awk '{print $1}')"
python scripts/run_graph_pipeline.py \
  --features data/processed/graph_features_v1.parquet \
  --feature-checksum "$GRAPH_FEATURE_SHA" \
  --manifest reports/graph_pipeline_manifest_v2.json
```

### 8.3. Đánh giá detector theo IBM Patterns

```bash
python scripts/run_graph_detector_eval.py \
  --patterns data/raw/ibm-aml/LI-Small-Patterns.txt \
  --detections data/processed/graph_detection_v1.parquet \
  --evidence data/processed/graph_evidence_v1.jsonl \
  --split-cutoffs data/processed/split_cutoffs.json \
  --report-out reports/graph_eval_v2.json \
  --gt-out data/processed/ibm_graph_eval_gt_v1.json \
  --primary-split test
```

### 8.4. Chạy baseline Graph

```bash
python scripts/run_graph_baseline.py \
  --db data/processed/aml.duckdb \
  --features data/processed/graph_features_v1.parquet \
  --detections data/processed/graph_detection_v1.parquet \
  --modeling-out data/processed/graph_account_modeling_v1.parquet \
  --report-out reports/graph_account_baseline_v1.json \
  --precision-k 1000 \
  --alert-budget-rate 0.01
```

Kiểm tra:

```bash
test -s data/processed/graph_features_v1.parquet
test -s data/processed/graph_detection_v1.parquet
test -s data/processed/graph_evidence_v1.jsonl
test -s data/processed/graph_account_modeling_v1.parquet
python -m json.tool reports/graph_pipeline_manifest_v2.json >/dev/null
python -m json.tool reports/graph_eval_v2.json >/dev/null
python -m json.tool reports/graph_account_baseline_v1.json >/dev/null
```

## 9. Retrain chung, hiệu chỉnh và khóa champion fusion v2

Chạy pipeline chung sau khi cả hai nhánh độc lập ở Bước 7–8 đã hoàn tất:

```bash
make train-fusion
```

Pipeline thực thi contract sau:

1. Dùng cùng `data/processed/aml.duckdb` và cùng
   `data/processed/split_cutoffs.json` cho cả hai nhánh.
2. IF và Graph đều dùng khóa `(account_key, as_of_ts)` và cửa sổ half-open
   `[as_of_ts - 7 ngày, as_of_ts)`.
3. Fit estimator trên train; fit calibration và chọn trọng số/threshold trên
   validation; test chỉ chạy đúng một lượt sau khi mọi lựa chọn đã khóa.
4. Lưu estimator Graph, estimator IF, bundle fusion, score thành phần, score
   cuối, checksum và manifest. Không đọc model cũ từ `if_handoff/` hoặc
   `graph_handoff/`.
5. Nếu fusion không thắng Graph trên validation theo tiêu chí đã khóa, giữ
   Graph làm champion và ghi fusion là challenger; không ép deploy fusion.

Artifact đầu ra dự kiến:

```text
models/fin07_if_7d_v2.joblib
models/fin07_graph_7d_v2.joblib
models/fin07_if_graph_fusion_v2.joblib
data/processed/fusion-v2/fusion_scores.parquet
reports/fusion-v2/benchmark.json
reports/fusion-v2/manifest.json
```

Kiểm tra release:

```bash
test -s models/fin07_if_7d_v2.joblib
test -s models/fin07_graph_7d_v2.joblib
test -s models/fin07_if_graph_fusion_v2.joblib
test -s data/processed/fusion-v2/fusion_scores.parquet
python -m json.tool reports/fusion-v2/benchmark.json >/dev/null
python -m json.tool reports/fusion-v2/manifest.json >/dev/null
python scripts/load_fusion_release.py --dry-run
```

Release tham chiếu hiện tại chọn **Graph làm champion**, IF+Graph là
challenger: validation F1 lần lượt `0,1469` và `0,1288`; test F1 của Graph là
`0,1348`, PR-AUC `0,0837`. Đây là kết quả mong đợi, không phải lỗi fusion.

## 10. Nạp release vào PostgreSQL và gắn geography cho UI

```bash
make load-fusion
python scripts/load_bank_geography.py \
  --accounts data/raw/ibm-aml/LI-Small_accounts.csv
```

`make load-fusion` nạp theo batch gzip tạm, commit theo pha và idempotent:

1. Upsert `account` và `transaction` từ LI-Small canonical vào PostgreSQL.
2. Nạp ground truth vào schema `label` riêng, không đưa nhãn vào feature.
3. Nạp latest snapshot, component contribution, detection và alert champion.
4. Không sinh seed/demo data.
5. Chạy lại không tạo transaction hoặc alert trùng.
6. Ghi đúng `model_version`, checksum release và `as_of_ts`.

Country chỉ là metadata phục vụ UI và investigation. Không đưa `country`,
`country_code`, `country_source` hoặc tọa độ vào feature model v2.
Script geography đồng thời dựng lại 34 hub và các corridor serving rollup;
endpoint `/api/v1/world` đọc rollup này thay vì quét bảng transaction.

PostgreSQL dùng `NUMERIC(18,2)`, nên 6.735 giao dịch canonical nhỏ hơn nửa cent
được lượng tử hóa lên `0,01 USD` lúc nạp để không vi phạm ràng buộc `amount >
0`. Huấn luyện và benchmark vẫn dùng giá trị chính xác trong DuckDB.

Kiểm tra PostgreSQL:

```bash
docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-fin07}" \
  -d "${POSTGRES_DB:-fin07}" \
  -c "SELECT count(*) AS accounts FROM account;" \
  -c "SELECT count(*) AS transactions FROM transaction;" \
  -c "SELECT count(*) AS alerts FROM alert;" \
  -c "SELECT count(*) AS detection_results FROM detection_result;" \
  -c "SELECT count(*) FILTER (WHERE b.country_code IS NOT NULL) AS located, count(*) AS total FROM account a LEFT JOIN bank b ON b.bank_code = a.bank_code;"
```

Chạy `make load-fusion` lần thứ hai rồi kiểm tra lại các count. Chúng phải giữ
nguyên; nếu tăng thì loader chưa idempotent.

## 11. Khởi động ứng dụng và observability

```bash
cd /Users/nguyenbao/P-022
make obs-up
make health
make obs-status
```

Địa chỉ kiểm tra:

- Console: <http://localhost:5173/models>
- API: <http://localhost:8000/docs>
- Grafana trực tiếp: <http://localhost:3000>
- Prometheus: <http://localhost:9090>
- Jaeger: <http://localhost:16686>

Trên trang giám sát của Console:

1. Tab tổng quan chỉ có một dashboard Grafana sáu panel.
2. Log nằm ở view riêng và truy vấn từ Loki.
3. Trace nằm ở view riêng và mở được Jaeger.
4. Một failure phải lần được cùng `trace_id` từ metric → log → trace.

Smoke test live chỉ chạy sau khi PostgreSQL đã có ít nhất một alert:

```bash
bash scripts/observability_smoke.sh
```

## 12. Tiêu chí hoàn thành

- [ ] DuckDB có 6.119.572 giao dịch sau self-loop filter, đủ 17 ngày lịch và đủ
      ba split.
- [ ] Không còn model/window 14 ngày trong contract vận hành.
- [ ] IF và Graph được retrain trên cùng dữ liệu, cutoff và mốc thời gian.
- [ ] Threshold/trọng số không dùng test để tuning.
- [ ] Manifest chứa checksum của dữ liệu, feature, model và score.
- [ ] Champion được chọn theo validation; test chỉ dùng báo cáo cuối.
- [ ] PostgreSQL chứa account, transaction, detection result và alert thật từ
      LI-Small; không có seed/demo data.
- [ ] Country coverage phục vụ UI đầy đủ nhưng country không nằm trong feature
      model.
- [ ] Chạy loader lần hai không tạo dữ liệu trùng.
- [ ] API, worker, web, PostgreSQL và Redis đều healthy.
- [ ] Grafana, Loki, Jaeger và OTel hoạt động; log/trace nằm ở view riêng.
- [ ] Có thể mở một alert trên UI và lần ra nguyên nhân failure bằng log + trace.

Khi toàn bộ checklist xanh, hệ thống mới được coi là hoàn chỉnh end-to-end.
