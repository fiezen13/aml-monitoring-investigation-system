# Repository Audit — FIN-07 / P-022 (AML Console)

**Ngày:** 2026-08-06
**Nhánh audit:** `chore/repository-standardization-v1` (tạo từ `develop`, working tree sạch trước khi bắt đầu)
**Người thực hiện:** Claude Code, theo yêu cầu chuẩn hoá repository của Bảo
**Phạm vi:** Audit-only. Không có file nào bị di chuyển hay xoá trong lần chạy này.

> Đọc trước khi đọc tiếp: repo này **không phải** một template AI20K còn sơ khai. Đây là hệ thống
> FIN-07 — console giám sát/điều tra AML cho một ngân hàng Việt Nam — đã có kiến trúc rõ ràng, tài
> liệu vận hành chi tiết (`docs/architecture_diagram.md`, `docs/RUNBOOK.md`, `docs/ENVIRONMENT.md`,
> `docs/CI.md`, `docs/CICD.md`, `docs/AML_INGESTION.md`), CI hai tầng (GitHub Actions chặn merge +
> Jenkins giao hàng), và một pipeline Kafka→Flink→HDFS đã hoạt động, có kiểm thử end-to-end. Phần
> lớn "Phase 1" của yêu cầu chuẩn hoá — tài liệu kiến trúc, tài liệu luồng dữ liệu — **đã tồn tại và
> ở chất lượng cao**. Việc còn thiếu chủ yếu là hygiene cấp repo (CODEOWNERS, PR template, license
> file) và một vài khoảng trống tài liệu/kiểm thử nhỏ, không phải một cuộc đại tu cấu trúc.

---

## 0. Hai điểm cần Bảo xác nhận trước khi làm Phase 2 trở đi

Yêu cầu gốc giả định một số điều không khớp với thực tế repo. Nêu ra ở đây thay vì âm thầm chọn
một hướng, theo đúng nguyên tắc "Ask for confirmation before... uncertain".

### 0.1. Thành phần team không khớp

Yêu cầu gốc mô tả team gồm **Bảo / Hưng / Hường / Hiển**, với Hường sở hữu `ml/behavioral` (ABM,
hành vi, tabular/temporal ML) và Hiển sở hữu `ml/graph` (entity resolution, graph ML) — hai
workstream ML độc lập.

`WORKLOG.md` (phần "Bàn giao", viết bởi Bảo) mô tả team thật là **Bảo / Hưng / Tin Tin / Hiển**:

| Người | Vai trò theo WORKLOG.md | Sở hữu |
|---|---|---|
| Bảo | PM / Solution Architect / DevOps | Hạ tầng, CI/CD, `db/init/`, `src/db/session.py`, `src/main.py` (health) |
| Hưng | Frontend | `web/src/**` |
| Tin Tin | Backend | `src/api/routes.py`, `src/models/schemas.py`, `src/worker/main.py` (cùng Hiển) |
| Hiển | AI Engineer | `src/agents/**`, nạp dataset IBM LI-Small (Sprint 1), phần điều phối LangGraph trong worker (Sprint 3) |

Không có ai tên "Hường" xuất hiện trong `WORKLOG.md`, git log, hay bất kỳ tài liệu nào trong repo.
Không có hai workstream ML độc lập nào tồn tại trong code — chỉ có **một** bộ sinh dữ liệu ABM
(`scripts/abm_generate.py`, do Bảo viết) và **một** agent LangGraph còn ở dạng khung mẫu
(`src/agents/`, do Hiển sở hữu, chưa hiện thực). Không có "graph ML" hay "entity resolution" nào
tách biệt khỏi bộ sinh ABM — `fc.entity`/`fc.relationship` (schema 005) là dữ liệu ABM sinh ra, có
cờ `is_inferred`/`confidence` cho quan hệ suy luận, nhưng không có pipeline graph ML nào xử lý nó.

**Câu hỏi:** Team đã đổi thành viên/vai trò so với đề bài gốc, hay đây là bốn người khác (Hường
thay Tin Tin, và Hường sẽ làm phần behavioral ML mới)? Nếu team thật vẫn là Bảo/Hưng/Tin Tin/Hiển
như `WORKLOG.md`, thì cấu trúc `ml/behavioral/` (Hường) + `ml/graph/` (Hiển) ở Phase 2–3 của yêu
cầu gốc **không có chủ sở hữu thật và không có code thật để đặt vào**, tạo ra "architectural
theater" — đúng thứ mà yêu cầu gốc tự cấm ("Do not create empty architectural theater").

### 0.2. Cấu trúc monorepo mục tiêu có phù hợp không

Yêu cầu gốc đề nghị một cấu trúc `apps/ + services/ + ml/ + contracts/ + packages/ + infrastructure/
+ deployment/` cho một hệ thống multi-service. Repo thật là **một backend monolith** (FastAPI +
worker, một image dùng chung), **một frontend SPA**, và **một pipeline ingestion** tách biệt qua
Docker Compose profile — không phải nhiều service độc lập cần `services/`. Ép vào cấu trúc đó sẽ vi
phạm chính nguyên tắc mà yêu cầu gốc đặt ra ở Phase 2: "Do not force a theoretical folder layout if
it conflicts with the actual stack" và "If the repository is currently small, retain a simpler
equivalent structure and explain why."

Mục 21 của audit này đề xuất một cấu trúc mục tiêu **rút gọn**, giữ nguyên hầu hết cây thư mục hiện
tại (đã hợp lý) và chỉ thêm những gì thật sự thiếu. Xem mục 21 để quyết định.

---

## 1. Cây thư mục hiện tại (đã loại trừ thư mục sinh ra/nhị phân)

```
.
├── .agents/                        # Quy tắc AI-log cho Antigravity IDE (bắt buộc chương trình)
├── .ai-log/                        # Nhật ký sử dụng AI — cấu trúc tracked, nội dung .jsonl ignored
├── .claude/ .codex/ .cursor/ .gemini/  # Cấu hình hook AI logging cho từng công cụ
├── .github/
│   ├── hooks/hooks.json            # Hook logging cho Copilot
│   ├── modernize/java-upgrade/     # Artifact công cụ modernize, rỗng thực chất (chỉ .gitignore + 2 script hook)
│   └── workflows/ci.yml            # CI duy nhất — cổng chặn merge
├── ci/                             # Script CI dùng chung giữa GitHub Actions, Jenkins, máy cá nhân
├── data/raw/ibm-aml/               # Chỉ .gitkeep + README — dataset không commit (đúng)
├── db/init/                        # 5 file lược đồ SQL, chạy tuần tự lúc PostgreSQL khởi tạo
├── deploy/                         # Compose override cho staging/prodlike/vm/test + Caddyfile
├── docker/flink/                   # Dockerfile tự build Flink kèm Hadoop client
├── docs/
│   ├── design/                     # PDF đặc tả ABM + prototype giao diện (vendor gốc của web/src/vendor/fc)
│   ├── guide/                      # 10 chương giáo trình AI20K (giữ nguyên, không phải tài liệu FIN-07)
│   └── *.md                        # 9 tài liệu vận hành/kiến trúc/CI đã viết, xem mục 2 “tài liệu”
├── eval/results/report.md          # Template chưa điền (placeholder từ AI20K)
├── flink/aml-ingestion/            # Job Flink (Java/Maven), có test suite riêng
├── jenkins/                        # Controller + agent Jenkins dựng bằng code (JCasC)
├── presentation/                   # Template Demo Day chưa điền
├── schemas/                        # Hợp đồng sự kiện AML (JSON Schema draft 2020-12) + ví dụ
├── scripts/                        # Script vận hành (aml/, seed, migrate, abm_generate, log hooks)
├── src/                            # Backend Python: agents/ api/ aml/ db/ models/ services/ worker/
├── tests/                          # pytest — theo module (test_api, test_db, test_aml, test_agents, test_worker)
├── web/                            # Frontend React 18 + Vite + TS + Tailwind, 22 màn hình
├── docker-compose.yml              # Stack chính (5 service) + profile `aml` (Kafka/Flink/HDFS, 8 service)
├── Dockerfile                      # Image dùng chung cho api/worker/seed/aml-producer
├── Jenkinsfile                     # Pipeline giao hàng (staging tự động, production-like cần duyệt)
├── Makefile                        # ~40 lệnh, gồm cả nhóm `aml-*` cho pipeline ingestion
├── requirements.txt / requirements-dev.txt
├── ruff.toml / pytest.ini
├── README.md / README_boilerplate.md / JOURNAL.md / WORKLOG.md
└── .env.example / .gitignore / .dockerignore
```

Không có `apps/`, `services/`, `ml/`, `contracts/`, `packages/`, `infrastructure/` — repo dùng cấu
trúc phẳng hơn (`src/`, `web/`, `flink/`, `db/`, `scripts/`) đã nhất quán và được tài liệu hoá tốt.

---

## 2. Ngôn ngữ và framework thực tế phát hiện được

| Layer | Công nghệ | Bằng chứng |
|---|---|---|
| Backend | Python 3.11, FastAPI ≥0.115, Uvicorn, Pydantic v2 + pydantic-settings | `requirements.txt`, `src/main.py` |
| ORM/DB driver | SQLAlchemy ≥2.0, psycopg 3 (không phải psycopg2) | `src/db/session.py` |
| Queue | Redis thuần (RPUSH/BLPOP tự viết) — **không phải Celery/RQ** | `src/services/queue.py`, `src/worker/main.py` |
| AI/Agent | LangGraph ≥0.2, LangChain, `langchain-google-genai` — **hiện là khung mẫu chưa nối** | xem mục 9 |
| Ingestion streaming | Java 11, Apache Flink 1.20.1, Maven; Python `confluent-kafka` cho producer | `flink/aml-ingestion/pom.xml`, `src/aml/` |
| Data lake | HDFS (Hadoop 3.3.6), định dạng Parquet (mặc định) hoặc JSON | `docker-compose.yml` (profile `aml`) |
| Frontend | React 18.3, Vite 6, TypeScript 5.7 (strict mode bật), Tailwind 3.4, `@xyflow/react`, `recharts` | `web/package.json`, `web/tsconfig.json` |
| Database | PostgreSQL 16, quản lý lược đồ bằng file SQL đánh số (không Alembic) | `db/init/`, `docs/architecture_diagram.md` |
| CI | GitHub Actions (cổng merge) + Jenkins (giao hàng), chạy trên self-hosted runner | `.github/workflows/ci.yml`, `Jenkinsfile` |
| Container | Docker + Docker Compose v2 (`profiles`, `!override`) | `docker-compose.yml`, `deploy/*.yml` |

Không phát hiện Next.js, Streamlit, SQLite, hay Celery dù README gốc (`README.md`, phần dưới banner
FIN-07) mô tả chúng — đó là mô tả của **template AI20K gốc**, không phải hệ thống thật đã build.
Đây là nguồn gây nhầm lẫn thật sự cho người mới đọc README từ trên xuống (xem mục 19).

---

## 3. Dịch vụ chạy được hiện tại

**Stack mặc định** (`docker compose up`, 6 dịch vụ, không cần `.env`):

| Dịch vụ | Vai trò | Cổng | Healthcheck |
|---|---|---|---|
| `postgres` | PostgreSQL 16, lược đồ nạp từ `db/init/` | 5432 | `pg_isready` qua TCP |
| `redis` | Hàng đợi + heartbeat worker | 6379 | `redis-cli ping` |
| `seed` | Nạp dữ liệu mẫu, chạy một lần rồi thoát | — | exit code 0 |
| `api` | FastAPI, 40 endpoint | 8000 | `/health/ready` |
| `worker` | Vòng lặp `BLPOP`, máy trạng thái 9 bước | — | heartbeat Redis |
| `web` | nginx phục vụ React build, proxy `/api` | 5173 | `/healthz` |

**Stack `aml` profile** (`docker compose --profile aml up`, không chạy mặc định, ~4GB RAM, 8 dịch
vụ thêm): `kafka`, `kafka-init`, `namenode`, `datanode`, `hdfs-init`, `flink-jobmanager`,
`flink-taskmanager`, `aml-producer` (chạy tay, không tự start).

**Ba môi trường triển khai** (qua Jenkins, không phải trong compose chính): development (local),
staging (`deploy/docker-compose.staging.yml`, tự động khi merge vào `develop`), production-like
(`deploy/docker-compose.prodlike.yml`, cần người duyệt khi merge vào `main`). VM production thật
(`amlmonitoring.site`) dùng thêm `deploy/docker-compose.vm.yml` + Caddy.

---

## 4. Kafka topics, producer, consumer

| Thuộc tính | Giá trị |
|---|---|
| Topic dữ liệu | `aml.transactions.raw.v1` (mặc định 3 partition, replication factor 1) |
| Topic DLQ | `aml.transactions.dlq.v1` (1 partition) |
| Producer | `python -m src.aml` (`src/aml/sink.py`, `confluent_kafka.Producer`, `acks=all`, idempotent) — đọc CSV IBM AML, phát lại thành sự kiện |
| Consumer | Flink job (`KafkaSource`, group `aml-hdfs-ingestion-v1`, offset reset `earliest`) |
| Key | `from_bank:from_account` (topic dữ liệu); `source_file:source_line_number` (DLQ) |
| Retention | 7 ngày (`AML_TOPIC_RETENTION_MS`, mặc định), broker giữ log 168h |
| Schema | `schemas/aml-transaction-v1.schema.json`, JSON Schema draft 2020-12, `additionalProperties:false`, field `schema_version` const `"1.0"` |
| PII | Không có tên khách hàng thật — `from_bank`/`from_account`/`to_bank`/`to_account` là mã định danh tổng hợp từ dataset IBM AML |
| Replay | At-least-once có chủ đích; `transaction_id` là SHA-256 tất định trên các trường thô để downstream dedup được |
| Dead-letter | Hai lớp: Kafka DLQ topic (từ producer, dòng CSV lỗi) + HDFS `rejected/transactions` (từ Flink, sự kiện qua được JSON parse nhưng fail validate) — **đây là hai cơ chế khác nhau, không phải một DLQ duy nhất** |
| Tạo topic | `scripts/aml/create_topics.sh`, idempotent (`--if-not-exists`) |

Tạo bằng `kafka-init` (chạy một lần) hoặc `make aml-topics`. Không có schema registry — version kiểm
bằng validator viết tay ở cả hai đầu (Java `TransactionValidator`, Python `schema.py`).

---

## 5. Flink job

| Thuộc tính | Giá trị |
|---|---|
| Entry point | `vn.fin07.aml.ingest.AmlIngestionJob` (`flink/aml-ingestion/src/main/java/.../AmlIngestionJob.java`) |
| Build | Maven, Java 11, Flink 1.20.1, shaded fat jar |
| Nguồn | `KafkaSource` trên `aml.transactions.raw.v1` |
| Đích | HDFS, Parquet (Avro-backed, mặc định) hoặc JSON Lines, chọn qua `AML_HDFS_FORMAT` |
| Checkpoint | `state.backend.type: hashmap`, storage filesystem, dir `hdfs://namenode:8020/data/aml/_checkpoints`, interval mặc định 30s, chịu được 3 lần fail liên tiếp |
| Watermark | `forBoundedOutOfOrderness` (mặc định 120s) + idleness detection (60s) — đã nối dây nhưng **chưa có window nào dùng tới** (tự tài liệu hoá, không phải thiếu sót bị bỏ quên) |
| Restart | `fixed-delay`, mặc định 10 lần / 10s giữa các lần |
| Rejected/DLQ | Side output riêng, luôn ghi JSON Lines vào `<hdfs>/rejected/transactions`, phân vùng theo `event_date` (ngày xử lý) + `error_type` |
| Giới hạn đã biết | Không exactly-once/dedup ở tầng Flink (tự tài liệu hoá, dedup đẩy xuống tầng "silver" chưa xây); amount lưu dạng Avro/Parquet `double` chứ không phải decimal (Flink Avro→Parquet writer không hỗ trợ decimal converter) |
| Test | 5 file, ~48 test method, không có integration test thật với Kafka/HDFS sống (việc đó do `scripts/aml/smoke_test.sh` đảm nhiệm, chạy trên docker compose thật) |

Vận hành qua `scripts/aml/submit_job.sh` / `cancel_job.sh` (không dùng REST API trực tiếp, gọi
`flink run`/`flink cancel` trong container).

---

## 6. HDFS layout

```
hdfs://namenode:8020/data/aml/
├── bronze/transactions/            # source_dataset=.../event_date=.../event_hour=... (Parquet hoặc JSON)
├── rejected/transactions/          # event_date=.../error_type=...  (luôn JSON Lines)
├── reference/patterns/             # *_Patterns.txt chép nguyên trạng, không phân tích
└── _checkpoints/                   # Checkpoint state của Flink
```

Không có tầng "silver"/"gold"/"feature"/"training dataset" — pipeline hiện tại dừng ở tầng bronze
theo đúng phạm vi đã công bố (`docs/AML_INGESTION.md`: "chỉ là đường ống dữ liệu, không mô hình,
không chấm điểm"). Cố ý không phân vùng theo account (tránh nổ NameNode memory với file nhỏ).

---

## 7. Backend: module và API

FastAPI, 2 router dưới `/api/v1`:

- **`src/api/routes.py`** (26 endpoint) — auth (bearer token + PBKDF2), cases, alerts, audit,
  dashboard, queue, chat (agent), SARs, approvals, users, settings. Có auth/role check theo từng
  endpoint (không có middleware/decorator chung).
- **`src/api/fc_routes.py`** (14 endpoint) — World Monitor, entity graph, crypto, token project,
  agent run, benchmark, model monitor, data quality, nguồn dữ liệu, transaction explorer.
  **Không có auth/role check nào** — toàn bộ 14 endpoint đọc công khai. Đây là chủ đích thiết kế
  hiện tại (đọc-only, không chạm `fc_gt`) nhưng nên chuẩn hoá cùng cơ chế auth với `routes.py`
  trước khi coi là production-ready.

`GET /health`, `GET /health/ready` (`src/main.py`) nằm ngoài `/api/v1` — pipeline triển khai và
healthcheck container phụ thuộc trực tiếp, không được đổi path.

**Database:** PostgreSQL, 4 schema (`public` 19 bảng nghiệp vụ AML, `label` 4 bảng nhãn — chỉ dùng
lúc đánh giá, `fc` 15 bảng bằng chứng ABM quan sát được, `fc_gt` 4 bảng ground truth ẩn). Ba ràng
buộc cưỡng chế ở tầng PostgreSQL bằng trigger, không phải quy ước code: `audit_log`/`evidence` chỉ
ghi thêm, `approval` quyết định một lần (`db/init/002_audit_immutability.sql`); vai trò
`fin07_agent` chỉ đọc qua view trong schema `agent`, không đọc được `label` hay bảng gốc
(`db/init/003_agent_readonly_role.sh`). Cả hai có test riêng, đều pass.

**Worker:** vòng lặp `BLPOP` (không phải Celery), 2 job type: `investigate_case` (chuyển trạng thái
tất định qua `src.domain.next_state`, **không phải bước AI/LLM** — chỉ là state machine) và `ping`.
Việc "điều phối agent LangGraph" trong worker là **Sprint 3, chưa hiện thực** (comment trong chính
`src/worker/main.py`).

---

## 8. Frontend: module và màn hình

React 18 + Vite 6 + TypeScript (strict) + Tailwind. SPA thuần, không SSR. **22 route/màn hình**, tất
cả đều gọi API thật qua `web/src/api/client.ts` (không có mock data nào trong `src/`, dù comment
trong `web/.env.example` nói ngược lại — xem mục 12). Danh sách đầy đủ và trạng thái từng trang nằm
trong báo cáo con của mục 8 (đã tổng hợp vào bản audit này) — không trang nào là placeholder/stub.

Bốn engine đồ hoạ canvas (`web/src/vendor/fc/*.js` — chart, chart-card, world map, force graph) là
**vendor nguyên trạng** từ `docs/design/prototype/`, tự đăng ký custom element, nhận dữ liệu qua
property (không phải JSX attribute) — có README riêng giải thích lý do không viết lại.

Không có ESLint/Prettier config, không có test framework (Vitest/Jest), không có file test nào dưới
`web/src`. Gate chất lượng duy nhất hiện tại là `tsc --noEmit` (chạy trong `npm run build`).

Hai đường triển khai frontend cùng tồn tại: Docker/nginx (chính, có Dockerfile 2-tầng kiểm tra CSS
Tailwind build đúng) và `web/vercel.json` (rewrite tĩnh, không rõ còn dùng hay là tàn dư từ giai
đoạn trước khi chuyển sang VM — xem mục 13).

---

## 9. Module ML/AI hiện tại

**Không có ML model nào đang chạy.** Toàn bộ điểm rủi ro trong hệ thống đến từ luật/heuristic trong
`scripts/seed_data.py` và bộ sinh ABM `scripts/abm_generate.py` — cả hai tự nhận là dữ liệu tổng hợp
tất định (cùng seed → cùng dữ liệu), không phải mô hình đã huấn luyện.

**Agent LangGraph** (`src/agents/`): graph 2 node thật (`analyze` → `respond`, có conditional edge),
nhưng cả hai node là **stub tường minh** (comment `# TODO: Thêm logic phân tích thực tế`), không gọi
LLM, không gọi DB, không gọi tool nào. `src/services/llm.py:get_llm()` được định nghĩa nhưng
**không có nơi nào gọi nó** — dead code. Hai tool mẫu (`search_knowledge` stub, `calculate` — cái
này thật sự hiện thực bằng `ast.parse` an toàn) tồn tại nhưng **không được gắn vào graph đã compile**.

Kết luận quan trọng cho yêu cầu "không đặt LLM vào synchronous transaction path": **hiện tại đúng
là không có LLM nào trong đường xử lý giao dịch nào cả** — không phải vì đã cố tình tránh, mà vì
agent chưa được hiện thực. Đây là điểm neo tốt để cắm agent thật vào sau này, không phải vi phạm
cần sửa ngay.

`fc.agent_run`/`fc.agent_step` (schema 005) là bảng audit trail cho một agent "thật" trong tương
lai, hiện được **sinh bởi `scripts/abm_generate.py`** để demo màn hình *Agent Run Console* — không
phải log của agent trong mục `src/agents/`.

---

## 10. Test coverage theo module

| Module | File test | Bao phủ |
|---|---|---|
| `src/api/routes.py` | `tests/test_api/*.py` (3 file) | health, chat rỗng, dashboard, alerts, case timeline, investigate-refused-khi-chờ-duyệt, audit feed |
| `src/api/fc_routes.py` | **không có** | Không test riêng cho 14 endpoint Financial City |
| `src/db/`, `db/init/*.sql` | `tests/test_db/*.py` (4 file) | Cách ly vai trò agent, bất biến audit log, máy trạng thái case, toàn bộ chuỗi điều tra |
| `src/aml/` (producer) | `tests/test_aml/*.py` (5 file) | checkpoint, CSV source, replay, schema, transform |
| `flink/aml-ingestion` (Java) | `src/test/java/...` (5 file, ~48 method) | config, partition/schema, sink factory, JSON parser, validator, routing |
| `src/agents/` | `tests/test_agents/test_graph.py` | Chỉ test luồng graph stub chạy được — không test hành vi AI thật (chưa có gì để test) |
| `src/worker/` | `tests/test_worker/test_dispatch.py` | Dispatch logic; **không có integration test chạy thật vòng lặp `BLPOP`** |
| `src/domain.py` | `tests/test_domain.py` | Máy trạng thái, nhãn typology |
| `scripts/seed_data.py` | `tests/test_seed_data.py` | Tính tái lập, không rò rỉ nhãn, ràng buộc nghiệp vụ |
| `src/services/llm.py`, `src/agents/tools/` | **không có** | Không có gì để test (dead code / chưa gắn) |
| `web/src/**` | **không có** | Không test framework nào được cấu hình |

Kết quả mong đợi khi chạy `pytest`: **301 passed** (theo `docs/HUONG_DAN_CHAY.md` mục 8.5).

---

## 11. Docker và topology triển khai

Một image dùng chung (`Dockerfile`, build 2 tầng, non-root uid 10001) cho bốn tiến trình khác nhau —
`api`, `worker`, `seed`, `aml-producer` — chỉ khác lệnh khởi động trong `docker-compose.yml`. Frontend
có Dockerfile riêng (2 tầng, `node:22-alpine` build → `nginx-unprivileged` serve). Flink có
Dockerfile thứ ba (3 tầng: Maven build job → lấy Hadoop client → runtime Flink), bắt buộc vì Flink
gốc không có Hadoop client và cần jar job build sẵn trong image.

Ba lớp phủ compose cho ba môi trường triển khai (`deploy/docker-compose.{staging,prodlike,vm,test}.yml`)
— không mở cổng Postgres/Redis ra ngoài, không build tại chỗ (chỉ pull image đã qua CI), `restart:
always`. VM production dùng thêm Caddy làm reverse proxy/TLS.

CI (`ci.yml`) và CD (`Jenkinsfile`) gọi **cùng một bộ script** trong `ci/` — không có logic viết
hai lần giữa hai hệ thống, đây là một quyết định thiết kế tốt đáng giữ nguyên.

---

## 12. File trùng lặp / mã trùng lặp

1. **`docs/RUNBOOK.md` và `docs/HUONG_DAN_CHAY.md`** — cả hai đều là "hướng dẫn chạy hệ thống trên
   máy cá nhân". `RUNBOOK.md` ngắn gọn hơn (tiếng Việt, dành cho người quen Docker); `HUONG_DAN_CHAY.md`
   dài hơn, có thêm bước ABM, đi một vòng UI, và bảng troubleshooting chi tiết hơn. Không mâu thuẫn
   nội dung, nhưng có trùng lặp đáng kể (cả hai liệt kê 6 dịch vụ, cùng bảng lệnh `make`). Nên gộp
   hoặc rõ ràng phân vai (một cái là "quick start", một cái là "hướng dẫn đầy đủ kèm demo tour").
2. **`docs/CI.md` và `docs/CICD.md`** — trùng tên nghe giống nhau nhưng phạm vi khác nhau thật sự
   (CI.md = riêng GitHub Actions/cổng merge; CICD.md = toàn bộ luồng gồm cả Jenkins) — **không phải
   trùng lặp thật**, chỉ là đặt tên dễ nhầm. Nên đổi tên rõ hơn, ví dụ `CI_GATE.md` / `CD_PIPELINE.md`.
3. **`README.md`** chứa cả banner FIN-07 thật (dòng 1–103) lẫn nguyên văn README của template AI20K
   gốc (dòng 105 trở đi, mô tả Next.js/Streamlit/SQLite/Celery — không có cái nào tồn tại trong repo
   thật). Đây không phải trùng lặp code nhưng là nguồn nhầm lẫn lớn nhất cho người đọc mới — xem mục
   19 (README_boilerplate.md giữ nguyên bản dùng cho các đội khác, không cần đổi).
4. Không phát hiện file mã nguồn Python/TS trùng lặp logic (không có hai bản implementation của
   cùng một tính năng).

---

## 13. File đặt sai chỗ

- **`web/vercel.json`** — cấu hình triển khai Vercel, nhưng `docs/DEPLOY_VM.md` nói rõ hệ thống đã
  chuyển từ Vercel sang VM GCP + Caddy ("Trước đây giao diện nằm trên Vercel... không có chỗ cho
  PostgreSQL, Redis"). File này có thể là tàn dư. **Cần hỏi Bảo** — giữ lại nếu vẫn dùng Vercel cho
  preview deploy nào đó, xoá nếu không.
- **`.github/modernize/java-upgrade/`** — chỉ chứa `.gitignore` (nội dung `**/*`, tức là ignore mọi
  thứ trong chính thư mục nó) và 2 script hook rỗng chức năng thực (`recordToolUse.sh/.ps1`). Trông
  như artifact tự sinh của một GitHub Copilot "modernize" flow chưa từng chạy thật trên repo Java.
  Không gây hại (không track gì thêm) nhưng không rõ mục đích — cần hỏi trước khi xoá.
- Ngoài hai điểm trên, cấu trúc hiện tại nhất quán: mã Python theo module trong `src/`, mã Java theo
  package Maven chuẩn, script vận hành gom trong `scripts/`, tài liệu gom trong `docs/`.

---

## 14. File chết / không dùng

- **`src/services/llm.py:get_llm()`** — định nghĩa nhưng **không có lời gọi nào** trong toàn bộ
  `src/` và `tests/` (grep xác nhận). Không phải file thừa để xoá — đây là điểm neo đã chuẩn bị sẵn
  cho khi hiện thực agent thật, nhưng nên có comment nói rõ "chưa dùng, dự kiến dùng ở Sprint 3" để
  người đọc không tưởng đây là bug.
- **`src/agents/tools/example_tool.py`** — hai tool định nghĩa nhưng không tool nào được gắn vào
  graph đã compile (`src/agents/graph.py` không import file này). Tương tự trên — khung mẫu chờ nối
  dây, không phải rác.
- **`presentation/README.md`, `eval/results/report.md`** — placeholder chưa điền của template
  AI20K (checklist rỗng, bảng metric toàn `[...]`). Không phải "chết" theo nghĩa mã không dùng, mà
  là deliverable chưa tới hạn nộp — giữ nguyên, không xoá.
- **`JOURNAL.md`** — vẫn là template "Week 1/Week 2..." hoàn toàn trống, chưa điền một dòng nhật ký
  thật nào, trong khi `WORKLOG.md` đã có nhật ký thật theo ngày. Khả năng cao `JOURNAL.md` bị bỏ
  quên sau khi chuyển sang dùng `WORKLOG.md`. Cần hỏi Bảo: gộp vào `WORKLOG.md` và xoá, hay vẫn cần
  giữ riêng cho hạng mục "Development Journal" của BTC?
- Không phát hiện file `.pyc`, thư mục `__pycache__`, hay artifact build nào bị tracked (đã xác
  minh bằng `git ls-files` — xem mục 17).

---

## 15. Cấu hình còn thiếu

- Không có `CODEOWNERS`.
- Không có `.github/pull_request_template.md`.
- Không có `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` (README claim "MIT" nhưng không có file
  `LICENSE` thật).
- Không có `.editorconfig`, `.gitattributes`.
- `docs/ENVIRONMENT.md` thiếu 6 biến môi trường phía Flink: `AML_ROLLOVER_INTERVAL_MS`,
  `AML_ROLLOVER_INACTIVITY_MS`, `AML_ROLLOVER_MAX_MB`, `AML_RESTART_ATTEMPTS`,
  `AML_RESTART_DELAY_SECONDS`, `AML_WATERMARK_IDLE_SECONDS`, `AML_SCHEMA_VERSION` — tồn tại thật
  trong `JobConfig.java` nhưng `tests/test_config_documented.py` **không có khả năng thấy chúng**
  vì test này chỉ soi các class `pydantic-settings` phía Python và biến `${...}` trong
  `docker-compose.yml`; các biến Flink được JVM đọc trực tiếp từ container env, không đi qua
  interpolation compose. Đây là một điểm mù cấu trúc của cơ chế kiểm tra tài liệu hiện tại, không
  chỉ là thiếu sót đơn lẻ.
- Không có ESLint/Prettier/test framework cho frontend (đã nêu ở mục 8).
- Không có kiểm thử tự động (Trivy/Grype) cho lỗ hổng image — chính `docs/CICD.md` mục 8 đã tự ghi
  nhận việc này còn thiếu.

---

## 16–17. Rủi ro bảo mật và lộ bí mật

**Không phát hiện secret nào bị commit trong `.env`, `coverage.xml`, `pytest-report.xml`,
`.pytest_cache/`, `.ruff_cache/`** — đã xác minh bằng `git ls-files`, tất cả các file này **không**
được track (đã bị `.gitignore` chặn đúng cách từ đầu).

**Phát hiện đã được xử lý ở working tree ngày 2026-08-06:** `.env.example` từng chứa giá trị trông
như secret thật, không phải placeholder. Giá trị không còn được lặp lại trong tài liệu này:

```
AI_LOG_API_KEY=<redacted; removed from current tree>
```

Khoá đã từng nằm trong lịch sử Git nên việc xoá khỏi cây hiện tại không thu hồi được khoá. Bảo vẫn
cần xác nhận với giảng viên/BTC, yêu cầu rotate/revoke, kiểm tra nhật ký sử dụng phía nhà cung cấp và
phối hợp dọn lịch sử nếu chính sách của tổ chức yêu cầu.

**Rủi ro khác đã ghi nhận:**
- `src/api/fc_routes.py` — 14 endpoint không có auth (mục 7). Không lộ dữ liệu thật (dữ liệu ABM
  tổng hợp), nhưng là điểm không nhất quán với phần còn lại của API.
- `web/src/pages/LoginPage.tsx` — form đăng nhập tự điền sẵn một email/password demo
  (`hung.nq@velrix.vn` / `demo-password`) và hiện danh sách "tài khoản demo" bấm để tự điền, không
  có gate `import.meta.env.DEV` bao quanh. Không phải secret bị lộ (không có mật khẩu thật nào),
  nhưng là một UX "tài khoản demo" cứng trong bundle production — đáng cân nhắc trước khi hệ thống
  này được xem như production thật (hiện tại nó là production-like/demo nên chấp nhận được).
- Endpoint `transactions()` trong `fc_routes.py` build câu `WHERE` bằng f-string nối các đoạn
  constant cố định (không phải input người dùng trực tiếp), có `# noqa: S608` — tham số vẫn được
  bind qua SQLAlchemy (`:q`, `:channel`...), nên không phải SQL injection thật, nhưng pattern này dễ
  gây nhầm lẫn khi review — nên refactor sang query builder rõ ràng hơn để không cần `# noqa`.

---

## 18. Vấn đề tái lập (reproducibility)

Nhìn chung rất tốt — đây là điểm mạnh của repo:

- `docker compose up` chạy được ngay trên máy vừa clone, không cần `.env`, không cần Python/Node
  cài sẵn (đã xác minh qua `docs/RUNBOOK.md` + `compose-smoke` job trong CI thật sự làm đúng việc
  này trên máy sạch mỗi PR).
- Seed data tất định theo `SEED_VALUE` (kiểm chứng bằng `make seed-verify`, chạy 2 lần phải ra cùng
  vân tay — có test `tests/test_seed_data.py`).
- ABM data tất định theo `--seed` (tự kiểm tra rò rỉ 6 điều kiện sau mỗi lần sinh).
- Lược đồ DB quản lý bằng file SQL đánh số + `scripts/migrate.py` áp tăng dần, không dùng Alembic —
  đơn giản hơn nhưng nghĩa là **không có cơ chế rollback lược đồ tự động**; migrate chỉ tiến, không
  lùi. Chấp nhận được ở quy mô hiện tại, nhưng nên ghi rõ trong tài liệu là một giới hạn có chủ đích.
- Điểm tái lập yếu duy nhất: **hạ tầng staging/production-like không phải infrastructure-as-code**
  (VPS thuê ngoài, dựng bằng tay, tự `docs/CICD.md` mục 8 đã ghi nhận). Dựng lại máy chủ từ đầu
  không tái lập được từ repo.

---

## 19. Naming không nhất quán

- `README.md` lẫn hai nội dung khác thời điểm (banner FIN-07 thật + boilerplate template AI20K gốc)
  — xem mục 12.
- `docs/CI.md` vs `docs/CICD.md` — tên dễ nhầm dù nội dung không trùng (mục 12).
- `docs/RUNBOOK.md` vs `docs/HUONG_DAN_CHAY.md` — trộn tiếng Anh/Việt cho cùng một loại tài liệu
  (mục 12). Phần lớn tài liệu FIN-07 khác đặt tên tiếng Anh viết hoa (`RUNBOOK.md`,
  `ENVIRONMENT.md`, `DEPLOY_VM.md`) nhưng nội dung 100% tiếng Việt — không phải vấn đề, chỉ ghi nhận
  quy ước đặt tên (tên file tiếng Anh, nội dung tiếng Việt) để giữ nhất quán khi thêm tài liệu mới.
- API: `routes.py` dùng response field kiểu `string` cho số thập phân (khớp serialize
  `NUMERIC` của Postgres), còn `fc_routes.py` dùng `number` — hai quy ước khác nhau cho cùng một
  loại dữ liệu (tiền tệ/risk score) giữa hai router, đã được README/comment nội bộ ghi nhận nhưng
  đáng cân nhắc thống nhất về lâu dài khi có phiên bản API mới.

---

## 20. Xung đột phụ thuộc và version

- `requirements.txt`: `chromadb` bị comment out ("mở khi cần") nhưng `CHROMA_PERSIST_DIR` vẫn tồn
  tại trong `src/config.py` và `.env.example` — cấu hình chờ sẵn cho tính năng chưa bật, không phải
  xung đột, nhưng nên ghi rõ trạng thái "planned" trong `docs/ENVIRONMENT.md`.
- `langchain-openai` có trong `requirements.txt` nhưng không có `ChatOpenAI` nào được dùng trong
  `src/` — LLM provider thật đang dùng là Gemini (`langchain-google-genai`, `src/services/llm.py`).
  OpenAI được giữ lại như phương án dự phòng (đúng như comment trong `.env.example`) — không phải
  bug, nhưng là một dependency không dùng tới ở runtime hiện tại.
- Không phát hiện version bị ghim xung đột giữa `requirements.txt`/`requirements-dev.txt` — tất cả
  dùng `>=`, không có pin cứng, không có hai bản của cùng một thư viện.
- `web/package.json`: một lock file duy nhất (`package-lock.json`, npm) — không có `yarn.lock` hay
  `pnpm-lock.yaml` lẫn vào, đúng chuẩn "một package manager, một lock file".
- Chưa chạy quét lỗ hổng (`pip-audit`/`npm audit`/Trivy) trong phạm vi audit này — đề xuất thêm vào
  Phase 7 (báo cáo phụ thuộc) nếu Bảo muốn số liệu cụ thể trước khi merge.

---

## 21. Cấu trúc mục tiêu đề xuất (rút gọn, bám theo stack thật)

Không áp cấu trúc `apps/services/ml/contracts/packages` đầy đủ của yêu cầu gốc — lý do đã nêu ở mục
0.2. Đề xuất **giữ nguyên bộ khung hiện tại** (đã hợp lý, đã có tài liệu tốt) và chỉ bổ sung phần
thật sự thiếu:

```
/  (giữ nguyên phần lớn cấu trúc hiện tại)
├── src/                      # KHÔNG đổi — đã tổ chức tốt theo module
├── web/                      # KHÔNG đổi
├── flink/aml-ingestion/      # KHÔNG đổi
├── scripts/                  # KHÔNG đổi
├── db/init/                  # KHÔNG đổi
├── deploy/, ci/, jenkins/    # KHÔNG đổi
├── schemas/                  # KHÔNG đổi — đã đóng vai trò contracts/events cho pipeline AML
├── docs/
│   ├── repository/           # MỚI — audit này + DEPENDENCY_REPORT.md + STANDARDIZATION_REPORT.md
│   └── adr/                  # MỚI — quyết định thiết kế lớn từ nay, hồi tố các quyết định đã có trong architecture_diagram.md §9 nếu cần
├── .github/
│   ├── CODEOWNERS            # MỚI
│   └── pull_request_template.md  # MỚI
├── CONTRIBUTING.md           # MỚI
├── SECURITY.md                # MỚI
├── LICENSE                    # MỚI (khớp "MIT" đã ghi trong README)
├── .editorconfig, .gitattributes  # MỚI
```

**Không tạo** `ml/behavioral/`, `ml/graph/`, `apps/`, `services/`, `contracts/`, `packages/`,
`infrastructure/` — không có code nào để đặt vào các thư mục đó hiện nay, và tạo chúng rỗng sẽ vi
phạm chính nguyên tắc "no empty architectural theater" của yêu cầu gốc. Nếu/khi có graph
ML/behavioral ML thật, sẽ tạo `ml/` lúc đó với chủ sở hữu thật — xem câu hỏi ở mục 0.1.

---

## 22. Bản đồ di chuyển file (migration map)

Vì cấu trúc mục tiêu chỉ **thêm**, không tổ chức lại, bản đồ di chuyển rất ngắn:

| Hiện tại | Đề xuất | Lý do |
|---|---|---|
| *(không có)* | `.github/CODEOWNERS` | Yêu cầu Phase 13 |
| *(không có)* | `.github/pull_request_template.md` | Yêu cầu Phase 13 |
| *(không có)* | `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` | Yêu cầu Phase 8 |
| *(không có)* | `.editorconfig`, `.gitattributes` | Hygiene cơ bản |
| `docs/CI.md` | *(đổi tên, không di chuyển)* `docs/CI_GATE.md` | Giảm nhầm lẫn với CICD.md — **cần Bảo xác nhận trước khi đổi**, vì mọi doc khác đang link tới tên cũ |
| `JOURNAL.md` | *(cần quyết định)* gộp vào `WORKLOG.md` hoặc giữ | Trùng vai trò với WORKLOG.md — **hỏi Bảo** |
| `web/vercel.json` | *(cần quyết định)* xoá hoặc giữ | Có thể là tàn dư sau khi chuyển sang VM — **hỏi Bảo** |

Không có file mã nguồn nào (`src/`, `web/src/`, `flink/`) cần `git mv` trong đề xuất này.

---

## 23. File đề xuất xoá — bằng chứng

**Không đề xuất xoá file nào ngay trong lần audit này.** Ba ứng viên duy nhất (`JOURNAL.md`,
`web/vercel.json`, `.github/modernize/java-upgrade/`) đều cần xác nhận từ Bảo trước (mục 13, 14) vì
mục đích không chắc chắn 100% — đúng nguyên tắc "Ask for confirmation before deleting any file whose
purpose is uncertain". Không có dataset, model binary, credential, hay build artifact nào bị track
cần xoá (đã xác minh sạch ở mục 16–17).

---

## 24. Rủi ro và chiến lược rollback

| Rủi ro | Mức độ | Giảm thiểu |
|---|---|---|
| Nhầm cấu trúc mục tiêu (áp `ml/behavioral`+`ml/graph` không có chủ) tạo thư mục rỗng vô nghĩa | Cao nếu bỏ qua mục 0.1 | Dừng lại, hỏi Bảo trước khi tạo bất kỳ thư mục `ml/` nào |
| Đổi tên `docs/CI.md` làm vỡ link chéo trong các tài liệu khác | Trung bình | `grep -rn "CI.md"` trước khi đổi, cập nhật toàn bộ link trong cùng commit |
| Xoá nhầm `JOURNAL.md`/`vercel.json` đang được dùng ngầm (vd. Vercel preview vẫn chạy cho demo) | Trung bình | Không xoá cho tới khi Bảo xác nhận |
| Thêm CODEOWNERS với username GitHub sai/không tồn tại | Thấp | Dùng placeholder + TODO cho username chưa xác minh, theo đúng Phase 13 |
| Toàn bộ thay đổi chỉ dừng ở docs/hygiene, không chạm `src/`/`web/`/`flink/` | — | Rủi ro vỡ chức năng ở lần chạy này gần như bằng 0 vì chưa di chuyển mã nguồn nào |

**Rollback:** mọi thay đổi đề xuất nằm trên nhánh `chore/repository-standardization-v1`, chưa merge
vào `develop`. Rollback = không merge PR, hoặc `git revert` từng commit nhỏ nếu đã merge một phần.
Không có thay đổi nào ảnh hưởng schema DB, event schema, hay API public trong phạm vi audit này.

---

## Tổng kết cho Bảo

Repo này đã ở trạng thái tốt hơn nhiều so với giả định "cần đại tu" trong yêu cầu gốc. Việc còn lại
chủ yếu là **hygiene cấp repo** (CODEOWNERS, PR template, LICENSE, vài file `.md` thiếu) và **hai
quyết định cần Bảo** (mục 0.1 team/ML workstream, mục 0.2 mức độ áp cấu trúc monorepo lớn). Đề nghị
xác nhận hai điểm đó trước khi mình làm tiếp Phase 2 trở đi (CODEOWNERS thật, PR template, ADR, và
các file hygiene còn thiếu ở mục 21).
