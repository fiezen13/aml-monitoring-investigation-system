# FIN-07 — AML Operations Console

FIN-07 là console giám sát và điều tra phòng, chống rửa tiền Level 1. Bản demo hiện tại phục vụ
release `fin07_currency_native_policy_edge_v1` trên IBM AML HI-Medium, giữ nguyên amount và
currency gốc, không cộng hoặc quy đổi tĩnh nhiều loại tiền thành USD.

- Console: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health/ready>
- Bản triển khai: <https://amlmonitoring.site/>

## Chạy lần đầu với dữ liệu đầy đủ

`git pull` chỉ tải mã nguồn, model và báo cáo nhỏ. PostgreSQL dump chứa 5,8 triệu giao dịch không
nằm trong Git; thành viên phải tải riêng từ Google Drive rồi restore theo hướng dẫn dưới đây.

### 1. Yêu cầu máy

- Git.
- Docker Desktop hoặc Docker Engine có Compose v2.
- Ít nhất 12 GB dung lượng đĩa trống cho image, dump và PostgreSQL sau restore.
- Khuyến nghị từ 8 GB RAM.
- Các cổng mặc định chưa bị chiếm: `5173`, `8000`, `5432`, `6379`.

Không cần cài Python hoặc Node nếu chỉ chạy bằng Docker. `.env` cũng không bắt buộc trong môi
trường development.

### 2. Lấy code mới nhất

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-022.git
cd P-022
git switch develop
git pull --ff-only origin develop
```

Nếu đã clone repo trước đó:

```bash
cd P-022
git switch develop
git pull --ff-only origin develop
```

### 3. Tải PostgreSQL dump

Mở thư mục handoff:

**[FIN-07 data handoff trên Google Drive](https://drive.google.com/drive/folders/1UEPEPSYW7ytWu0V8ke7vx1K5lP41lVPh?hl=vi)**

Tải đúng hai file:

```text
fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump
fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump.sha256
```

Đặt chúng vào:

```text
P-022/artifacts/db/
```

Cấu trúc đúng sau khi tải:

```text
P-022/
├── artifacts/
│   └── db/
│       ├── fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump
│       └── fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump.sha256
├── docker-compose.yml
└── README.md
```

Dump có kích thước `436.514.448` bytes, SHA-256:

```text
5e2de5b536fd9e1f61974ae1d9227d74eb369ce2c32f2ef752cd36a6bb788c96
```

### 4. Kiểm tra checksum

macOS:

```bash
cd artifacts/db
shasum -a 256 -c fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump.sha256
cd ../..
```

Linux:

```bash
cd artifacts/db
sha256sum -c fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump.sha256
cd ../..
```

Kết quả bắt buộc:

```text
fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump: OK
```

Không restore nếu checksum sai. Hãy xóa bản tải lỗi và tải lại từ Drive.

### 5. Khởi động PostgreSQL và restore

> `pg_restore --clean` thay toàn bộ dữ liệu nghiệp vụ hiện có trong database `fin07`. Nếu máy đã
> có dữ liệu cần giữ, hãy tạo backup riêng trước khi chạy.

Dừng các tiến trình có thể đang đọc database, rồi bật PostgreSQL:

```bash
docker compose stop api worker web
docker compose up -d --wait postgres
```

Restore dump bằng `pg_restore` bên trong container, vì vậy máy host không cần cài PostgreSQL CLI:

```bash
docker compose exec -T postgres pg_restore \
  -U fin07 \
  -d fin07 \
  --clean \
  --if-exists \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  < artifacts/db/fin07_REL-EDGE-039b4b0fd5fb669a_20260815.dump
```

Lệnh không in tiến độ trong lúc chạy. Hãy chờ tới khi terminal trả prompt và exit code bằng `0`.
Dump loại trừ `app_session`, nên không mang token đăng nhập từ máy tạo dump sang máy khác.

### 6. Khởi động toàn bộ stack

```bash
docker compose up -d --build --wait
docker compose ps
```

Các service `postgres`, `redis`, `api`, `worker`, `web` phải có trạng thái `healthy`. Service
`migrate` chạy xong rồi `Exited (0)` là bình thường.

### 7. Kiểm tra dữ liệu sau restore

```bash
docker compose exec -T postgres psql -U fin07 -d fin07 -Atc "
SELECT 'transactions=' || count(*) FROM transaction;
SELECT 'scores=' || count(*) FROM transaction_model_score;
SELECT 'alerts=' || count(*) FROM alert;
SELECT 'release=' || release_id FROM edge_model_release WHERE status='active';
SELECT 'country_hubs=' || count(*) FROM edge_country_hub;
SELECT 'country_flows=' || count(*) FROM edge_country_flow;
"
```

Kết quả chuẩn:

```text
transactions=5866610
scores=5866610
alerts=6541
release=REL-EDGE-039b4b0fd5fb669a
country_hubs=34
country_flows=1289
```

Kiểm tra API:

```bash
curl -fsS http://localhost:8000/health/ready
curl -fsS 'http://localhost:8000/api/v1/alerts/page?page=1&page_size=1'
curl -fsS 'http://localhost:8000/api/v1/fc/graph?limit=20'
```

Sau đó mở <http://localhost:5173>. Tài khoản mặc định được điền sẵn trên màn hình đăng nhập:

```text
Email:    hung.nq@velrix.vn
Password: demo-password
```

## Dữ liệu hiển thị trên console

Sau khi restore đúng dump, các màn chính có dữ liệu:

| Màn hình | Dữ liệu |
|---|---|
| Dashboard | Population, alert rate, top alerts và active release |
| Trung tâm cảnh báo | 6.541 cảnh báo, phân trang 50 dòng và tìm kiếm trên PostgreSQL |
| Tra cứu giao dịch | 5.866.610 giao dịch, amount/currency gốc và model score |
| World Monitor | 34 country hubs và 1.289 country/currency corridors |
| Network Graph | Tách từng connected component, không trộn mạng độc lập trên cùng canvas |
| Crypto | Giao dịch Bitcoin trong IBM ledger; không giả là dữ liệu on-chain |
| Models / Benchmarks | Release currency-native, threshold và kết quả 5 seed |
| Data Quality | Kiểm tra coverage, validity và danh mục nguồn |

Cases, SAR/Approvals và Agent Runs chỉ có dữ liệu sau khi chuyên viên thực hiện workflow. Console
không tạo case, kết luận điều tra hoặc dữ liệu on-chain giả để lấp màn hình.

## Lệnh vận hành thường dùng

```bash
# Xem trạng thái
docker compose ps

# Theo dõi log API và worker
docker compose logs -f api worker

# Build lại sau khi pull code mới
docker compose up -d --build --wait

# Dừng stack nhưng giữ PostgreSQL volume
docker compose down

# Chạy kiểm thử và lint
make check

# Xem toàn bộ lệnh Makefile
make help
```

Không chạy `docker compose down -v` hoặc xóa volume `fin07_postgres_data` nếu chưa có backup; hai
thao tác đó xóa database đã restore.

## Xử lý sự cố

### UI mở được nhưng không có cảnh báo/giao dịch

Kiểm tra active release và số dòng:

```bash
docker compose exec -T postgres psql -U fin07 -d fin07 -Atc "
SELECT count(*) FROM transaction;
SELECT release_id, status FROM edge_model_release;
"
```

Nếu transaction bằng `0`, dump chưa được restore hoặc restore nhầm database.

### `pg_restore` báo database đang được sử dụng

```bash
docker compose stop api worker web
```

Sau đó chạy lại lệnh restore. Không cần dừng container `postgres`.

### Cổng đã bị chiếm

Đổi cổng trong `.env`, ví dụ:

```env
WEB_PORT=5174
API_PORT=8001
POSTGRES_PORT=5433
REDIS_PORT=6380
```

Sau đó chạy lại:

```bash
docker compose up -d --build --wait
```

### Web vẫn hiện bundle cũ

```bash
docker compose up -d --build web
```

Sau đó hard refresh trình duyệt (`Cmd+Shift+R` trên macOS, `Ctrl+Shift+R` trên Windows/Linux).

### Google Drive không cho tải

Người quản lý folder phải bật quyền xem/tải cho thành viên hoặc chế độ “Anyone with the link”.
Không upload dataset, dump hoặc credential vào Git để thay thế.

## Phát triển ngoài Docker

```bash
docker compose up -d postgres redis

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

make run       # API
make worker    # chạy ở terminal khác

cd web
npm ci
npm run dev
```

Trong `.env`, đổi host của `DATABASE_URL` từ `postgres` thành `localhost` khi API chạy trực tiếp
trên máy host.

## Kiểm thử

```bash
make check
make contracts-check

cd web
npm run typecheck
npm test -- --run
npm run build
```

## Cấu trúc chính

```text
src/api/            FastAPI routes
src/worker/         Worker nền và workflow
src/models/         Feature contract và model runtime
src/fusion/         IF + Graph fusion
src/mega_pna/       MEGA-PNA implementation
web/                React + Vite console
db/init/            PostgreSQL schema và migrations
scripts/            Training, scoring, release loader và vận hành
models/             Model joblib nhỏ được version hóa
reports/            Benchmark/manifest nhỏ được version hóa
contracts/          Data/event/tool contracts
docs/               Kiến trúc, ML và runbook chuyên sâu
artifacts/          Dump và artifact lớn, bị loại khỏi Git
```

## Quy tắc dữ liệu và model

- Không commit `.env`, credential, raw IBM AML, DuckDB, score parquet hoặc PostgreSQL dump.
- Amount Paid/Received và Payment/Receiving Currency được giữ nguyên.
- Chuẩn hóa theo currency chỉ fit trên train; không dùng static FX trong model.
- Chỉ quy đổi USD cho luật nghiệp vụ/pháp lý có nguồn tỷ giá và đúng `as_of_ts`.
- Model score dùng để xếp hàng ưu tiên, không phải xác suất rửa tiền hay kết luận pháp lý.
- Agent không được đọc ground-truth label; mọi kết luận cần bằng chứng và human review.

Xem thêm [`SECURITY.md`](SECURITY.md), [`contracts/README.md`](contracts/README.md) và
[`docs/ml/CURRENCY_NATIVE_EDGE_MVP.md`](docs/ml/CURRENCY_NATIVE_EDGE_MVP.md).

## Tài liệu chuyên sâu

| Tài liệu | Nội dung |
|---|---|
| [`docs/architecture/PRODUCTION_ARCHITECTURE.md`](docs/architecture/PRODUCTION_ARCHITECTURE.md) | Kiến trúc triển khai production |
| [`docs/operations/RUNBOOK.md`](docs/operations/RUNBOOK.md) | Vận hành và xử lý sự cố |
| [`docs/operations/DEPLOY_VM.md`](docs/operations/DEPLOY_VM.md) | Triển khai VM |
| [`docs/operations/CICD.md`](docs/operations/CICD.md) | CI/CD và merge gates |
| [`docs/ml/CURRENCY_NATIVE_EDGE_MVP.md`](docs/ml/CURRENCY_NATIVE_EDGE_MVP.md) | Release đang phục vụ UI |
| [`docs/ml/FIN-07-FUSION-001.md`](docs/ml/FIN-07-FUSION-001.md) | Fusion IF + Graph |
| [`docs/ml/FIN-07-ML-004_Ke_hoach_MEGA_PNA.md`](docs/ml/FIN-07-ML-004_Ke_hoach_MEGA_PNA.md) | Kế hoạch MEGA-PNA |
| [`docs/ml/MEGA_PNA_RUNBOOK.md`](docs/ml/MEGA_PNA_RUNBOOK.md) | Huấn luyện và benchmark MEGA-PNA |
| [`contracts/ingestion/README.md`](contracts/ingestion/README.md) | Kafka/Flink/HDFS ingestion tùy chọn |
| [`data/raw/ibm-aml/README.md`](data/raw/ibm-aml/README.md) | Nguồn và cách tải raw IBM AML |

## License

Mã nguồn dùng giấy phép MIT. IBM AML là dữ liệu tổng hợp và tiếp tục tuân theo
CDLA-Sharing-1.0.
