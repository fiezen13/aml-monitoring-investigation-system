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
| Detection Engine (rules, behavioral, graph, ML) | **CHƯA CÓ** | `services/detection/` |
| Feature platform, entity resolution | **CHƯA CÓ** | `services/feature-platform/` |
| AI Investigation Agent | **KHUNG MẪU** — `src/agents/` không gọi LLM, không gọi tool, không chạm DB | `services/agent-runtime/` |

**Điểm rủi ro hiện tại đến từ luật và heuristic trong `scripts/seed_data.py`, chưa phải mô hình đã
huấn luyện.** Toàn bộ dữ liệu là tổng hợp: không khách hàng thật, không danh sách trừng phạt thật.

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
  agents/           Khung mẫu LangGraph (chưa hiện thực)
  domain.py         Máy trạng thái và từ vựng nghiệp vụ dùng chung

services/           Nhà chờ sẵn cho các thành phần chưa viết (detection, feature, agent runtime)
flink/              Job Flink nạp dữ liệu vào HDFS
web/                Console React + Vite + TypeScript
db/init/            Lược đồ SQL đánh số, chạy tuần tự khi PostgreSQL khởi tạo
scripts/            Vận hành: seed, migrate, thao tác AML
ci/ deploy/ jenkins/  CI/CD và triển khai
docs/
  architecture/     Tài liệu kiến trúc (PDF)
  operations/       Runbook, CI/CD, triển khai VM
  repository/       Audit và báo cáo chuẩn hoá repo
  adr/              Quyết định kiến trúc
tests/              pytest, chia theo module
```

---

## 4. Chạy

### Toàn bộ hệ thống

```bash
docker compose up -d --wait     # postgres, redis, seed, api, worker, web
make help                       # danh sách lệnh
```

### Đường ống nạp dữ liệu AML

Nằm sau profile `aml`, **không** chạy cùng `docker compose up` (nặng ~4 GB RAM):

```bash
make aml-up                 # Kafka + HDFS + Flink, tạo topic
make aml-submit             # nộp job Flink
make aml-producer-sample    # phát 1.000 giao dịch đầu
make aml-smoke              # kiểm tra khói đầu–cuối, không cần tải gì từ Kaggle
```

Chi tiết: [`contracts/ingestion/README.md`](contracts/ingestion/README.md).
Flink UI <http://localhost:8081> · HDFS UI <http://localhost:9870>

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

## 9. Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/architecture/`](docs/architecture/) | Kiến trúc chuẩn (PDF) |
| [`contracts/README.md`](contracts/README.md) | Hợp đồng dữ liệu và quy tắc thay đổi |
| [`docs/operations/RUNBOOK.md`](docs/operations/RUNBOOK.md) | Dựng, vận hành, xử lý sự cố |
| [`docs/operations/CICD.md`](docs/operations/CICD.md) | Cổng chặn merge và pipeline giao hàng |
| [`docs/operations/DEPLOY_VM.md`](docs/operations/DEPLOY_VM.md) | Triển khai lên VM sau Caddy + TLS |
| [`.env.example`](.env.example) | Toàn bộ biến môi trường, kèm giải thích |
| [`docs/repository/`](docs/repository/) | Audit repo, báo cáo phụ thuộc |
| [`docs/adr/`](docs/adr/) | Quyết định kiến trúc |
