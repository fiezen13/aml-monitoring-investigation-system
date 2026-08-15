# FIN-07 — Nền tảng phòng, chống rửa tiền Level 1 cho ngân hàng

Console giám sát và điều tra rửa tiền, xây theo *Kiến trúc chi tiết nền tảng AML Level 1 cho ngân
hàng* (v1.0, 05/08/2026). Level 1 nghĩa là: vận hành **trong ranh giới dữ liệu và quyền truy cập
của một ngân hàng**, không phụ thuộc dữ liệu Nhà nước hay dữ liệu xuyên biên giới.

```bash
docker compose up
```

- Console — <http://localhost:5173>
- API docs — <http://localhost:8000/docs>
- Bản chạy thật — <https://amlmonitoring.site/>

Không cần tạo `.env`, không cần cài Python hay Node. Chỉ cần Docker.

---

## 1. Trạng thái thật của từng phần

Bảng này là thứ cần đọc trước tiên. Một tài liệu mô tả năng lực chưa tồn tại như thể đã chạy còn tệ
hơn không có tài liệu.

| Thành phần | Trạng thái | Ở đâu |
|---|---|---|
| Console 22 màn hình (React + Vite) | **ĐANG CHẠY** — mọi trang gọi API thật | `web/` |
| API FastAPI, 40 endpoint | **ĐANG CHẠY** | `src/api/` |
| Máy trạng thái vụ việc + worker nền | **ĐANG CHẠY** — chuyển trạng thái tất định, dừng ở chỗ cần người duyệt | `src/domain.py`, `src/worker/` |
| Nhật ký kiểm toán bất biến, phê duyệt ghi một lần | **ĐANG CHẠY** — cưỡng chế bằng trigger PostgreSQL | `db/init/002` |
| Cách ly nhãn khỏi vai trò agent | **ĐANG CHẠY** — cưỡng chế bằng quyền PostgreSQL | `db/init/003` |
| Đường ống CSV → Kafka → Flink → HDFS | **ĐANG CHẠY** — profile `aml`, không chạy mặc định | `src/aml/`, `flink/` |
| Bộ dữ liệu huấn luyện và đánh giá | **IBM AML công khai** — nguồn duy nhất của mọi con số hiệu năng | `data/raw/ibm-aml/` |
| Hợp đồng dữ liệu, sự kiện, tool | **ĐÃ ĐỊNH NGHĨA**, phần lớn chưa có bên hiện thực | `contracts/` |
| Detection Engine | **BEHAVIOUR + GRAPH + FUSION OFFLINE ĐÃ CHẠY**; bundle và điểm hợp nhất có checksum | `src/fusion/`, `scripts/build_fusion_release.py` |
| Feature platform, entity resolution | **CHƯA CÓ** | `services/feature-platform/` |
| Explainable AI Investigation | **ĐANG CHẠY** — 3 agent có giới hạn, 7 tool tất định, evidence/trace bền vững, human review | `src/investigation/` |

Ba agent AML dùng Google Gemini qua official `google-genai` SDK. Không dùng OpenAI, Anthropic hoặc
local LLM. CI/dev dùng `LLM_MODE=mock`; runtime thật cần cấu hình server-side:

```env
LLM_MODE=gemini
GOOGLE_API_KEY=<server-side secret>
GEMINI_MODEL=gemini-3.1-flash-lite
```

Cả Supervisor, Explanation và Critic bị khóa vào `gemini-3.1-flash-lite`; cấu hình model khác bị
từ chối ngay khi nạp settings. API key không được gửi tới React.

Stack không tự sinh dữ liệu mẫu. Console chỉ đọc batch IBM AML LI-Small đã hoàn tất gần nhất;
đường Behaviour nhận CSV canonical không nhãn, chạy Isolation Forest và lưu detection/alert vào
PostgreSQL. Xem [`contracts/ingestion/README.md`](contracts/ingestion/README.md).
Release fusion 7 ngày kết hợp model IF của Hường và Graph của Hiển bằng percentile train-only,
không đưa model tham chiếu có giám sát khác vào đường quyết định. Xem
[`docs/ml/FIN-07-FUSION-001.md`](docs/ml/FIN-07-FUSION-001.md).
Không có dữ liệu khách hàng thật nào được commit trong repo.

---

## 2. Kiến trúc

Tài liệu kiến trúc chuẩn là PDF trong [`docs/architecture/`](docs/architecture/) — sáu mặt phẳng,
mô hình thực thể, contract, ma trận phê duyệt agent, lộ trình Level 1.

> **Cần bổ sung:** `Kien_truc_chi_tiet_AML_Level1_Ngan_hang.pdf` hiện **chưa được commit** vào repo.
> Nó là nguồn sự thật của mọi quyết định thiết kế nên phải nằm trong repo, không chỉ trong chat.

Sáu mặt phẳng và chỗ đặt code: xem [`services/README.md`](services/README.md).

Bốn ranh giới quan trọng nhất, và chúng được cưỡng chế ở tầng nào:

| Ranh giới | Cưỡng chế ở đâu |
|---|---|
| LLM không nằm trên đường quyết định đồng bộ | Agent chạy bất đồng bộ qua hàng đợi Redis |
| Agent không đọc được nhãn / ground truth | Quyền PostgreSQL (`db/init/003`) |
| Nhật ký và bằng chứng chỉ ghi thêm | Trigger PostgreSQL (`db/init/002`) |
| Mọi khẳng định của agent phải có bằng chứng | JSON Schema (`contracts/agent/`, `minItems: 1`) |

---

## 3. Cấu trúc repo

```
contracts/          Hợp đồng dữ liệu, sự kiện, tool — NGUỒN SỰ THẬT DUY NHẤT về hình dạng dữ liệu
  common/           $defs dùng chung
  events/           Envelope CloudEvents + payload từng topic Kafka
  canonical/        Thực thể vùng GOLD
  agent/            Tool call, agent state, structured output
  registry/         Typology registry
  ingestion/        Hợp đồng đường ống IBM AML — phần ĐANG CHẠY

src/                Backend Python
  api/              FastAPI: routes.py (quy trình AML) + fc_routes.py (màn hình Financial City)
  worker/           Worker nền, máy trạng thái vụ việc
  aml/              Producer phát lại CSV → Kafka
  fusion/           Bundle IF + Graph, percentile calibration và score fusion giải thích được
  agents/           Khung mẫu LangGraph (chưa hiện thực)
  domain.py         Máy trạng thái và từ vựng nghiệp vụ dùng chung

services/           Nhà chờ sẵn cho các thành phần chưa viết (detection, feature, agent runtime)
flink/              Job Flink nạp dữ liệu vào HDFS
web/                Console React + Vite + TypeScript
db/init/            Lược đồ SQL đánh số, chạy tuần tự khi PostgreSQL khởi tạo
scripts/            Vận hành: migrate, chuẩn bị/nạp LI-Small, thao tác AML
models/             Model release nhỏ, có phiên bản; payload dữ liệu lớn nằm ngoài Git
ci/ deploy/ jenkins/  CI/CD và triển khai
docs/
  architecture/     Kiến trúc chuẩn (PDF) và kiến trúc production
  operations/       Runbook, CI/CD, triển khai VM
  ml/               Đặc tả huấn luyện, đặc trưng, EDA, kiến trúc ML/Agent
  adr/              Quyết định kiến trúc
tests/              pytest, chia theo module
```

---

## 4. Chạy

### Toàn bộ hệ thống

```bash
docker compose up -d --wait     # postgres, redis, migrate, api, worker, web
make help                       # danh sách lệnh
```

### Đường ống nạp dữ liệu AML

Nằm sau profile `aml`, **không** chạy cùng `docker compose up` (nặng ~4 GB RAM):

```bash
make aml-up                 # Kafka + Kafka UI + HDFS + Flink, tạo topic
make aml-submit             # nộp job Flink
make aml-producer-sample    # phát 1.000 giao dịch đầu
make aml-smoke              # kiểm tra khói đầu–cuối, không cần tải gì từ Kaggle
```

Chi tiết, kèm ba cái bẫy hay gặp khi chạy lần đầu:
[`contracts/ingestion/README.md`](contracts/ingestion/README.md).

Kafka UI <http://localhost:8082> · Flink UI <http://localhost:8081> · HDFS UI <http://localhost:9870>

### Dựng release hợp nhất IF + Graph

Đặt payload lớn đúng trong `if_handoff/` và `graph_handoff/`; checksum nguồn đã khóa ở
`configs/fusion/if_graph_v1.json`. Sau đó chạy:

```bash
python scripts/build_fusion_release.py
```

Kết quả gồm một runtime bundle `models/fin07_if_graph_fusion_v1.joblib`, bảng điểm canonical
`data/processed/fusion_scores_v1.parquet`, và báo cáo kiểm định
`reports/fusion_release_v1.json`.

### Phát triển ngoài Docker

```bash
docker compose up -d postgres redis
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # đổi host trong DATABASE_URL thành localhost
make run                        # API
make worker                     # worker, cửa sổ khác
cd web && npm install && npm run dev
```

---

## 5. Kiểm thử

```bash
make check                      # lint + toàn bộ test — chạy trước khi mở PR
make contracts-check            # chỉ kiểm chứng hợp đồng dữ liệu
cd web && npm run typecheck && npm run build
cd flink/aml-ingestion && mvn -B test
```

Kiểm thử tích hợp dùng PostgreSQL và Redis **thật**, không mock: các ràng buộc quan trọng nhất nằm
ở tầng cơ sở dữ liệu, và mock một cơ sở dữ liệu rồi kiểm tra mock không chứng minh được gì.

---

## 6. Hợp đồng dữ liệu — đọc trước khi viết code mới

Mọi thành phần đọc/ghi dữ liệu phải bám vào một schema trong [`contracts/`](contracts/README.md).
Không thành phần nào được tự định nghĩa lại một cấu trúc đã có ở đó.

Bảy quy ước bắt buộc (chi tiết trong `contracts/README.md`): `schema_version` bắt buộc; thời gian
tách bạch `event_time`/`ingestion_time`/`posting_time`/`available_from`; số tiền là chuỗi thập phân;
mọi khẳng định có `evidence_refs`; mọi liên kết suy luận có `confidence` và `provenance`;
`additionalProperties: false`; không có trường nhãn ẩn.

Thay đổi phá vỡ tương thích phải tạo version mới, giữ nguyên bản cũ, và có kế hoạch chuyển đổi.

---

## 7. Sở hữu

| Người | Phạm vi |
|---|---|
| Bảo | Kiến trúc, hạ tầng, CI/CD, `contracts/`, `db/init/`, `flink/` |
| Hưng | `web/` |
| Tin Tin | `src/api/`, `src/models/`, `src/worker/` |
| Hiển | `src/agents/`, `services/agent-runtime/` |

Chi tiết ở [`.github/CODEOWNERS`](.github/CODEOWNERS) và [`WORKLOG.md`](WORKLOG.md).
Quy trình làm việc: [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 8. An toàn dữ liệu

- Toàn bộ dữ liệu trong repo là **tổng hợp từ mô phỏng**. Không dữ liệu khách hàng thật.
- Bí mật đọc từ biến môi trường; `.env` không bao giờ commit. Xem [`SECURITY.md`](SECURITY.md).
- Bộ dữ liệu IBM AML không commit (250 MB – 10 GB) — xem `data/raw/ibm-aml/README.md`.
- Phạm vi khẳng định: bộ dữ liệu này đủ để dựng PoC và benchmark có căn cứ, **chưa đủ** để khẳng
  định mô hình sẵn sàng triển khai sản xuất. Việc đó cần hiệu chỉnh và kiểm định trên dữ liệu thật
  đã được bảo vệ tại một tổ chức có thẩm quyền.

---

## 9. Dữ liệu và Graph pipeline

Transaction và pattern data sử dụng **IBM Transactions for AML — LI-Small** từ Kaggle:
[`ealtman2019/ibm-transactions-for-anti-money-laundering-aml`](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml),
theo giấy phép CDLA-Sharing-1.0. Đặt các file tại `data/raw/ibm-aml/`:

- `LI-Small_Trans.csv`
- `LI-Small_Patterns.txt`

```bash
pip install -r requirements.txt

# Task 1 — ETL transactions + accounts → DuckDB
python3 scripts/run_task1_etl.py \
  --raw data/raw/ibm-aml/LI-Small_Trans.csv \
  --db data/processed/aml.duckdb \
  --seed 42

# Task 2 — pattern inventory + typology coverage (T01–T10)
python3 scripts/run_task2_typology.py \
  --patterns data/raw/ibm-aml/LI-Small_Patterns.txt \
  --catalog docs/reference/typology_mapping_catalog_v1.json \
  --out-dir data/processed
```

Task 1 tạo DuckDB với bảng `transaction`, `account`, cùng `dq_report.json` và
`split_cutoffs.json`. Task 2 tạo `ibm_pattern_instances.json`,
`typology_mapping_catalog.json`, `typology_coverage.json` và
`typology_coverage.md`. Chi tiết schema: [`docs/task2_schema.md`](docs/task2_schema.md).

Huấn luyện Behaviour Isolation Forest cửa sổ 7 ngày:

```bash
make behavior-train
```

Quy trình, artifact và giới hạn của LI-Small được mô tả tại
[`docs/ml/FIN-07-BEHAVIOR-7D.md`](docs/ml/FIN-07-BEHAVIOR-7D.md).

---

## 10. Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/architecture/`](docs/architecture/) | Kiến trúc chuẩn (PDF) |
| [`docs/architecture/PRODUCTION_ARCHITECTURE.md`](docs/architecture/PRODUCTION_ARCHITECTURE.md) | Từ máy cá nhân tới production: hiện trạng, kiến trúc đích, khoảng cách |
| [`contracts/README.md`](contracts/README.md) | Hợp đồng dữ liệu và quy tắc thay đổi |
| [`docs/operations/RUNBOOK.md`](docs/operations/RUNBOOK.md) | Dựng, vận hành, xử lý sự cố |
| [`docs/operations/CICD.md`](docs/operations/CICD.md) | Cổng chặn merge và pipeline giao hàng |
| [`docs/operations/DEPLOY_VM.md`](docs/operations/DEPLOY_VM.md) | Triển khai lên VM sau Caddy + TLS |
| [`docs/operations/GCP_SETUP.md`](docs/operations/GCP_SETUP.md) | Dựng hạ tầng GCP từng bước: gcloud, VM, Terraform, DNS, Cloud SQL |
| [`infra/terraform/README.md`](infra/terraform/README.md) | Hạ tầng GCP dưới dạng mã: IP tĩnh, tường lửa, Cloud SQL |
| [`.env.example`](.env.example) | Toàn bộ biến môi trường, kèm giải thích |
| [`docs/ml/`](docs/ml/) | Đặc tả huấn luyện, đặc trưng và kiến trúc ML/Agent |
| [`docs/adr/`](docs/adr/) | Quyết định kiến trúc |

---

## 11. Giấy phép

Mã nguồn sử dụng giấy phép MIT. Bộ dữ liệu IBM AML tiếp tục tuân theo
CDLA-Sharing-1.0.
