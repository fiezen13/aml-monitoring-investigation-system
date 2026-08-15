# FIN-07 — Runbook MEGA-PNA

Runbook này vận hành phần hiện thực tại `src/mega_pna/` theo
`FIN-07-ML-004_Ke_hoach_MEGA_PNA.md` và giao thức edge-classification của Bilgi
et al., *Multigraph Message Passing with Bi-Directional Multi-Edge Aggregations*.

## Phạm vi và hợp đồng

Đây là **đường học thuật**, tách khỏi preprocessing sản xuất. Nó cố ý:

- giữ self-transfer và số 0 đầu bank code;
- giữ nguyên amount/currency/payment format thay vì đổi USD;
- dùng đúng 4 edge feature: timestamp, amount received, received currency,
  payment format;
- chia 60/20/20 theo thời gian tại ranh giới ngày như source chính thức;
- sample 2 hop × 100 neighbor quanh seed edge;
- dùng ego-ID, reverse message passing, edge-update MLP;
- PNA ở cả tầng aggregate parallel edge và tầng aggregate distinct neighbor;
- batch 8.192, hidden 20, 2 layer, learning rate 0,0008, dropout 0,28, class
  weights 1:7, 80 epoch;
- báo mean ± sample standard deviation trên đúng 5 seed.

`no_payment_format` là ablation bắt buộc của FIN-07, không phải kết quả tái lập
paper và không được dùng để mở cổng HI-Medium.

## Cài môi trường

Các package ML nằm riêng trong `requirements-mega-pna.txt`, không vào image API.
Trên macOS arm64/Python 3.14, PyG chưa phát hành wheel cho sampler extension;
build hai extension sau khi cài torch:

```bash
.venv/bin/pip install -r requirements-mega-pna.txt
MAX_JOBS=4 .venv/bin/pip install --no-build-isolation \
  -r requirements-mega-pna-sampler.txt
```

Preflight sẽ dừng rõ ràng nếu sampler extension thiếu. PNA forward/backward đã
được kiểm chứng trên MPS; benchmark paper nên chạy CUDA L4 24 GB như kế hoạch
FIN-07 để có thông lượng phù hợp.

Trên L4, ưu tiên image gần runtime chính thức (PyTorch 2.2.2 + CUDA 11.8):

```bash
docker build -f docker/mega-pna/Dockerfile -t fin07-mega-pna:cuda118 .
docker run --rm --gpus all \
  -v "$PWD/data:/workspace/data" \
  -v "$PWD/models:/workspace/models" \
  -v "$PWD/reports:/workspace/reports" \
  fin07-mega-pna:cuda118 --suite gate --device cuda --include-ablation
```

## Format dữ liệu

```bash
.venv/bin/python scripts/format_mega_pna.py --dataset all
```

Output nằm dưới `data/processed/mega-pna/<dataset>/formatted_transactions.csv`.
Mỗi dataset có manifest SHA-256 cạnh file output. Formatter dùng DuckDB vì
`datatable` của source chính thức không build được trên Python 3.14, nhưng giữ
nguyên hợp đồng quan sát của formatter gốc: kiểu chuỗi đầu vào, first-seen IDs,
EdgeID nguồn, mốc thời gian và sort theo timestamp. Unit test khóa các quy tắc
này.

## Cổng tái lập Small

```bash
.venv/bin/python scripts/benchmark_mega_pna.py \
  --suite gate --device cuda --include-ablation
```

Cổng chỉ qua khi mean F1 paper arm của **cả hai** bộ nằm trong một độ lệch chuẩn
đã công bố:

| Dataset | Mục tiêu |
|---|---:|
| Small_HI | 0,7401 ± 0,0155 |
| Small_LI | 0,4507 ± 0,0226 |

Script luôn yêu cầu đúng 5 seed. Nếu thiếu seed hoặc một bộ lệch chuẩn, nó trả
exit code 2 và không cho chạy Medium.

## HI-Medium

Chỉ sau khi cổng Small đã qua:

```bash
.venv/bin/python scripts/benchmark_mega_pna.py \
  --suite medium --device cuda --include-ablation
```

Mục tiêu paper arm là F1 `0,7826 ± 0,0011`. Chạy toàn bộ từ đầu bằng:

```bash
.venv/bin/python scripts/benchmark_mega_pna.py \
  --suite all --device cuda --include-ablation
```

## Artifact

- checkpoint: `models/mega-pna/<dataset>/<arm>/seed_<n>.pt`;
- score test: `models/mega-pna/<dataset>/<arm>/seed_<n>_test.parquet`;
- kết quả từng seed: `reports/mega-pna/<dataset>/<arm>/seed_<n>.json`;
- tổng hợp và trạng thái gate: `reports/mega-pna/benchmark.json`.

Checkpoint chứa model state, optimizer state, epoch, seed, full config, feature
list và split boundaries. Báo cáo có F1/precision/recall/PR-AUC theo ngưỡng
paper 0,5, ngưỡng chọn trên validation, confusion matrix và operating points
theo alert budget.

Tái tạo score từ checkpoint đã khóa:

```bash
.venv/bin/python scripts/infer_mega_pna.py \
  --dataset Small_HI \
  --checkpoint models/mega-pna/Small_HI/paper/seed_42.pt \
  --output models/mega-pna/Small_HI/paper/seed_42_test_reproduced.parquet \
  --device cuda
```

Đo recall giao dịch/đường dây, workload và tỷ lệ alert có evidence:

```bash
.venv/bin/python scripts/evaluate_mega_pna_operations.py \
  --predictions models/mega-pna/Small_LI/paper/seed_42_test.parquet \
  --raw-transactions data/raw/ibm-aml/LI-Small_Trans.csv \
  --patterns data/raw/ibm-aml/LI-Small-Patterns.txt \
  --evidence-jsonl data/processed/graph_evidence_v1.jsonl \
  --report-out reports/mega-pna/Small_LI/paper/operations_seed_42.json
```

Evidence attachment chỉ được tính khi chính transaction được alert xuất hiện
trong hop của evidence có cả `detected_pattern` và `evidence_id`; script không
suy diễn coverage từ việc hai record chỉ cùng account.

## Kiểm thử

```bash
.venv/bin/pytest tests/test_mega_pna -q
.venv/bin/ruff check src/mega_pna tests/test_mega_pna scripts/*mega_pna.py
```

Không công bố một run 1 seed, run giảm neighbor, run giảm epoch, hoặc MPS smoke
test như benchmark paper. Các run đó chỉ xác nhận code path và tài nguyên.
