# Vận hành — FIN-07

Dựng máy cá nhân, dựng hạ tầng GCP, triển khai lên VM, cổng CI/CD và giám sát. Đọc theo thứ tự mục lục là đi được từ máy trống tới production.

- [Runbook — dựng và vận hành FIN-07 trên máy cá nhân](#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân) — gốc: `docs/operations/RUNBOOK.md`
- [Dựng hạ tầng GCP — từng bước](#dựng-hạ-tầng-gcp-từng-bước) — gốc: `docs/operations/GCP_SETUP.md`
- [Triển khai lên VM GCP — https://amlmonitoring.site/](#triển-khai-lên-vm-gcp-httpsamlmonitoringsite) — gốc: `docs/operations/DEPLOY_VM.md`
- [CI/CD — cổng chặn merge và pipeline giao hàng](#cicd-cổng-chặn-merge-và-pipeline-giao-hàng) — gốc: `docs/operations/CICD.md`
- [Giám sát — Prometheus và Grafana](#giám-sát-prometheus-và-grafana) — gốc: `docs/operations/MONITORING.md`
- [FIN-07 — Runbook LI-Small end-to-end](#fin-07-runbook-li-small-end-to-end) — gốc: `docs/operations/LI_SMALL_E2E_RUNBOOK.md`

## Runbook — dựng và vận hành FIN-07 trên máy cá nhân

Đối tượng: bất kỳ ai vừa clone repo và cần hệ thống chạy trong vòng vài phút.

### 1. Yêu cầu

| Thứ cần có | Bản tối thiểu | Kiểm tra |
|---|---|---|
| Docker Engine | 24+ | `docker --version` |
| Docker Compose | v2.24+ (cần `env_file.required`) | `docker compose version` |
| RAM trống | ~2 GB | |

Không cần Python, không cần Node, không cần `.env`. Ba thứ đó chỉ cần khi
chạy ngoài Docker.

### 2. Một lệnh

```bash
docker compose up
```

Lệnh này dựng năm dịch vụ và một tác vụ nâng lược đồ. PostgreSQL phải có batch
LI-Small đã nạp nếu muốn console hiển thị dữ liệu nghiệp vụ:

| Dịch vụ | Vai trò | Cổng | Xanh khi |
|---|---|---|---|
| `postgres` | PostgreSQL 16, lược đồ nạp từ `db/init/` | 5432 | `pg_isready` qua TCP |
| `redis` | Hàng đợi tác vụ | 6379 | `redis-cli ping` |
| `migrate` | Áp migration còn thiếu rồi thoát | — | thoát với mã 0 |
| `api` | FastAPI | 8000 | `/health/ready` trả 200 |
| `worker` | Tiêu thụ hàng đợi | — | nhịp tim trong Redis còn hạn |
| `web` | Console React qua nginx | 5173 | `/healthz` trả 200 |

Chờ đến khi mọi thứ xanh rồi mới trả về:

```bash
docker compose up -d --wait
```

Sau đó mở:

- Console — <http://localhost:5173>
- API docs — <http://localhost:8000/docs>
- Readiness — <http://localhost:8000/health/ready>

### 3. Thứ tự khởi động

Không có `sleep` ở bất kỳ đâu. Mỗi bước chờ healthcheck của bước trước:

```
postgres ─┐
          ├─→ migrate (chạy một lần, thoát 0) ─→ api ──→ web
redis ────┘                                   └─→ worker
```

`api` và `worker` chờ `migrate` **thoát thành công**. Bước này chỉ nâng lược đồ,
không sinh hoặc ghi đè dữ liệu nghiệp vụ. Nếu lược đồ hỏng, cả stack không lên
thay vì trả lỗi 500 muộn khi người dùng mở giao diện.

### 4. Việc thường làm

```bash
make help          # danh sách lệnh
make up            # dựng và chờ mọi healthcheck xanh
make health        # trạng thái sức khoẻ từng container
make logs          # theo dõi log
make db-shell      # mở psql
make down          # dừng, giữ dữ liệu
make db-reset      # xoá volume và dựng lại lược đồ từ đầu
```

### 5. Dữ liệu LI-Small

Ứng dụng không còn đường sinh dữ liệu demo. Dữ liệu vận hành duy nhất là IBM
AML LI-Small được chuẩn hoá thành CSV Behaviour, nạp qua batch runner, sau đó
bổ sung địa lý ngân hàng bằng `scripts/load_bank_geography.py`. `db-reset` chỉ
tạo lại lược đồ; sau lệnh đó phải nạp lại LI-Small trước khi dùng console.

### 6. Những ràng buộc đã cưỡng chế ở tầng dữ liệu

Không phải quy ước trong mã nguồn — quy ước thì sơ suất là vi phạm được
(QD6). Những thứ dưới đây bị chặn bởi chính PostgreSQL:

| Ràng buộc | Cơ chế | Kiểm thử |
|---|---|---|
| `audit_log` chỉ ghi thêm | trigger chặn UPDATE/DELETE/TRUNCATE | `tests/test_db/test_audit_immutability.py` |
| `evidence` bất biến | như trên | như trên |
| Phê duyệt ghi một lần | trigger `approval_write_once` | như trên |
| Phê duyệt phải có lý do | CHECK `approval_decided_needs_reason` | như trên |
| Agent không đọc được nhãn | vai trò `fin07_agent`, schema `agent` | `tests/test_db/test_agent_role_isolation.py` |
| Trạng thái vụ việc hợp lệ | CHECK trên `aml_case.state` | `tests/test_db/test_case_state_machine.py` |

Thử bằng tay cho vui:

```bash
make db-shell
```
```sql
UPDATE audit_log SET actor = 'ai đó' WHERE audit_id = 1;
-- ERROR: Bảng audit_log chỉ cho phép ghi thêm ...
```

### 7. Chạy ngoài Docker

Khi cần chạy `--reload` cho vòng lặp sửa mã nhanh:

```bash
docker compose up -d postgres redis     # chỉ hạ tầng
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                    # sửa host thành localhost
make run                                # API
make worker                             # worker, ở cửa sổ khác
cd web && npm install && npm run dev    # console
```

### 8. Sự cố

Hai điểm hay mất thời gian nhất:

**Sửa file trong `db/init/` mà không thấy tác dụng.** Script khởi tạo chỉ chạy
khi volume PostgreSQL còn rỗng. Volume đã có dữ liệu thì lần khởi động sau
container bỏ qua toàn bộ thư mục đó và không nói gì. `make db-reset`.

**Cổng đã bị chiếm.** Đổi trong `.env`: `API_PORT`, `WEB_PORT`,
`POSTGRES_PORT`, `REDIS_PORT`. Đổi `WEB_PORT` thì nhớ đổi cả `CORS_ORIGINS`.

### 9. Liên quan

- [`.env.example`](../../.env.example) — mọi biến môi trường, có test bắt buộc khai báo
- [#cicd-cổng-chặn-merge-và-pipeline-giao-hàng](#cicd-cổng-chặn-merge-và-pipeline-giao-hàng) — pipeline chạy gì trên mỗi pull request
- [`contracts/ingestion/README.md`](../../contracts/ingestion/README.md) — đường ống Kafka/Flink/HDFS: lệnh, ba giao diện, bẫy khi chạy lần đầu
- [PRODUCTION_ARCHITECTURE](../architecture/README.md#kiến-trúc-production-fin-07-aml-level-1) — hiện trạng triển khai và kiến trúc đích
- FIN-07-ARC-001 — tài liệu kiến trúc
- FIN-07-DAT-001 — đặc tả dữ liệu

---

## Dựng hạ tầng GCP — từng bước

Danh sách việc để đi từ máy chưa có gì tới một VM có IP cố định và một Cloud SQL có sao lưu.

Làm theo thứ tự. Mỗi bước có một **mốc kiểm tra** — thấy đúng thứ đó mới đi tiếp, đừng chạy hết một
lượt rồi mới gỡ lỗi ngược.

| Tài liệu | Khi nào cần |
|---|---|
| File này | Trình tự và lệnh |
| [`infra/terraform/README.md`](../../infra/terraform/README.md) | Terraform tạo gì và vì sao, cách import, cách gỡ |
| [`#triển-khai-lên-vm-gcp-httpsamlmonitoringsite`](#triển-khai-lên-vm-gcp-httpsamlmonitoringsite) | Phần dựng Docker và Caddy trên VM |

---

### Bước 0 — Cần có gì

| | Kiểm tra | Nếu thiếu |
|---|---|---|
| Terraform ≥ 1.6 | `terraform version` | `brew install terraform` |
| gcloud CLI | `gcloud version` | Bước 1 |
| Tài khoản GCP có quyền tạo tài nguyên | | |
| Thẻ thanh toán đã bật trên dự án | | Cloud SQL không tạo được nếu chưa bật |

**Chi phí sẽ phát sinh:** Cloud SQL `db-f1-micro` khoảng 10–20 USD/tháng, chạy liên tục kể cả khi
không ai dùng. IP tĩnh miễn phí khi còn gắn vào VM đang chạy, **có tính phí khi để không**.

---

### Bước 1 — Cài gcloud

```bash
brew install --cask gcloud-cli
```

#### Nếu nó hỏng ở bước "Virtual env setup failed"

Triệu chứng: log có `Failed to establish a new connection` khi tải
`cryptography-...whl` từ `github.com`, rồi Homebrew **xoá sạch** những gì vừa cài.

Đây là lỗi mạng ở bước hậu cài đặt, không phải lỗi gói. Phần virtualenv đó chỉ cần cho vài lệnh ít
dùng — nhưng Homebrew coi nó là lỗi nghiêm trọng và rollback tất cả.

Ba đường vòng, thử theo thứ tự:

**a. Thử lại khi mạng ổn.** Kiểm tra trước:

```bash
ping -c 2 github.com
curl -sI https://github.com | head -1
```

Không phân giải được tên miền thì đổi DNS trong Cài đặt mạng của macOS sang `8.8.8.8` hoặc
`1.1.1.1`, rồi cài lại.

**b. Bộ cài chính thức của Google** — tải từ máy chủ Google, không đụng tới github.com:

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud version
```

**c. Google Cloud Shell** — không cài gì cả. Mở <https://console.cloud.google.com> rồi bấm biểu
tượng terminal ở góc trên phải. `gcloud`, `terraform` và `git` đều có sẵn:

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-022.git
cd P-022/infra/terraform
```

Cloud Shell đã đăng nhập sẵn nên **bỏ qua bước 2**. Lưu ý: thư mục home của Cloud Shell bị xoá sau
120 ngày không dùng, nên nếu chạy Terraform từ đây thì hãy bật GCS backend
([`versions.tf`](../../infra/terraform/versions.tf) đã viết sẵn, chỉ cần bỏ chú thích) — mất state
là mất bản đồ những gì đang tồn tại.

**Mốc kiểm tra:** `gcloud version` in ra số phiên bản.

---

### Bước 2 — Đăng nhập

Hai lệnh, hai mục đích khác nhau. Chỗ này hay nhầm:

```bash
gcloud auth login                      # cho bạn, để chạy lệnh gcloud
gcloud auth application-default login  # cho Terraform và các thư viện
```

Chỉ chạy lệnh đầu thì `terraform plan` vẫn báo không tìm thấy credential. Cả hai đều mở trình duyệt.

**Mốc kiểm tra:** `gcloud auth list` hiện email của bạn kèm dấu `*`.

---

### Bước 3 — Chọn dự án

```bash
gcloud projects list          # PROJECT_ID khác với tên hiển thị
gcloud config set project <PROJECT_ID>
```

**Mốc kiểm tra:** `gcloud config get-value project` trả về đúng ID.

---

### Bước 4 — VM

Terraform **không tạo VM** — nó tra cứu VM đã có. Nên VM phải tồn tại trước.

```bash
gcloud compute instances list
```

**Nếu VM cũ còn đó:** ghi lại `NAME` và `ZONE`, sang bước 5.

**Nếu chưa có, tạo mới:**

```bash
gcloud compute instances create fin07-vm \
    --zone us-central1-a \
    --machine-type e2-standard-2 \
    --image-family ubuntu-2404-lts-amd64 \
    --image-project ubuntu-os-cloud \
    --boot-disk-size 30GB \
    --boot-disk-type pd-balanced \
    --tags fin07
```

`e2-standard-2` (2 vCPU, 8 GB): stack đặt giới hạn ~3,6 GB cho các container, cộng hệ điều hành và
chỗ thở lúc build image. Sau khi chuyển sang Cloud SQL, VM nhẹ đi 1,5 GB.

**Đừng thêm `--address` ở đây.** Để Terraform tạo IP tĩnh trước rồi gán sau; làm ngược lại sẽ thừa
một IP ephemeral phải gỡ.

Đường ống AML (Kafka + Flink + HDFS) **không** chạy trên VM này — nó cần thêm ~4 GB và chạy ở máy
cá nhân.

**Mốc kiểm tra:** `gcloud compute instances list` hiện VM ở trạng thái `RUNNING`.

---

### Bước 5 — Terraform

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Sửa `terraform.tfvars`, điền `project_id`, `vm_name`, `zone` lấy từ bước 3 và 4.

```bash
terraform init
terraform plan
```

**Đọc kế hoạch trước khi apply.** Phải chỉ thấy `create`, **không một dòng `destroy` nào**. Thấy
`destroy` là state đang lệch với thực tế — dừng lại và hỏi.

Nếu báo lỗi tường lửa `fin07-web` đã tồn tại (do [`#triển-khai-lên-vm-gcp-httpsamlmonitoringsite`](#triển-khai-lên-vm-gcp-httpsamlmonitoringsite) từng tạo bằng tay),
đưa nó vào quản lý thay vì xoá:

```bash
terraform import google_compute_firewall.web projects/<PROJECT_ID>/global/firewalls/fin07-web
```

Rồi:

```bash
terraform apply
```

Cloud SQL mất khoảng 10–15 phút để dựng. Đó là bình thường, đừng ngắt giữa chừng.

**Mốc kiểm tra:** `terraform output static_ip` in ra một địa chỉ IP.

---

### Bước 6 — Gán IP tĩnh vào VM

Terraform không làm được vì VM chỉ được tra cứu.

```bash
terraform output buoc_tiep_theo    # in ra đúng lệnh kèm giá trị thật
```

Nội dung của nó:

```bash
gcloud compute instances delete-access-config <VM> \
    --zone <ZONE> --access-config-name "external-nat"

gcloud compute instances add-access-config <VM> \
    --zone <ZONE> --access-config-name "external-nat" \
    --address $(terraform output -raw static_ip)
```

Giữa hai lệnh, VM mất kết nối ra ngoài vài giây. Đừng chạy khi đang có người xem.

Gắn thẻ cho luật tường lửa có hiệu lực (bỏ qua nếu đã tạo VM kèm `--tags fin07`):

```bash
gcloud compute instances add-tags <VM> --zone <ZONE> --tags fin07
```

**Mốc kiểm tra:** `terraform output vm_current_ip` và `terraform output static_ip` **trùng nhau**.

---

### Bước 7 — DNS

Tại nơi quản lý tên miền, trỏ hai bản ghi về IP tĩnh:

| Loại | Tên | Giá trị |
|---|---|---|
| A | `@` | IP từ `terraform output -raw static_ip` |
| A | `www` | như trên |

```bash
dig +short amlmonitoring.site A     # phải ra đúng IP đó
```

Caddy xin chứng chỉ qua HTTP-01: Let's Encrypt gọi ngược vào cổng 80 của máy. DNS chưa trỏ đúng thì
chứng chỉ không cấp được. **Giới hạn 5 chứng chỉ/tuần cho một tên miền** — nên chờ DNS lan truyền
xong rồi mới dựng stack, đừng thử đi thử lại.

**Mốc kiểm tra:** `dig` trả về đúng IP tĩnh.

---

### Bước 8 — Đưa mã nguồn lên VM

```bash
gcloud compute ssh <VM> --zone <ZONE> --command "curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker \$USER"
```

Đăng nhập lại sau lệnh đó thì `docker` chạy không cần `sudo`.

**Repo là private**, nên `git clone` trên VM sẽ đòi thông tin đăng nhập GitHub mà máy đó không có.
Hai đường:

**a. Chép mã nguồn từ máy bạn** — không cần credential trên VM, và chỉ gửi file đã theo dõi trong
git (không kèm `.git`, `node_modules`, hay `data/raw` nặng vài GB):

```bash
git archive --format=tar.gz -o /tmp/fin07.tar.gz HEAD
gcloud compute scp /tmp/fin07.tar.gz <VM>:~/fin07.tar.gz --zone <ZONE>
gcloud compute ssh <VM> --zone <ZONE> --command "mkdir -p ~/P-022 && tar xzf ~/fin07.tar.gz -C ~/P-022"
```

Gói khoảng 1,7 MB. Đổi lại: `vm-deploy.sh` sẽ không `git pull` được ở lần sau — khối đó được bọc
trong `if [[ -d .git ]]` nên nó bỏ qua chứ không hỏng, và mỗi lần cập nhật bạn chép lại gói mới.

**b. Tạo deploy key hoặc Personal Access Token** rồi `git clone` như bình thường. Đáng làm nếu VM
cần tự cập nhật, nhưng là thêm một bí mật nữa phải quản lý.

Sửa `.env`. Khác [`#triển-khai-lên-vm-gcp-httpsamlmonitoringsite`](#triển-khai-lên-vm-gcp-httpsamlmonitoringsite) ở **hai** dòng, vì giờ dùng Cloud SQL thay cho
container `postgres`:

```dotenv
USE_CLOUD_SQL=true
DATABASE_URL=<lấy từ: terraform output -raw database_url>
FIN07_AGENT_DB_PASSWORD=<chuỗi ngẫu nhiên: openssl rand -base64 32>
ACME_EMAIL=<email của bạn>
SITE_DOMAIN=amlmonitoring.site
```

**`USE_CLOUD_SQL=true` là bắt buộc, không phải tuỳ chọn.** Thiếu nó thì `DATABASE_URL` trong `.env`
**không có tác dụng gì**: `docker-compose.yml` đặt `DATABASE_URL` trong khối `environment:`, mà
Compose cho `environment:` quyền cao hơn `env_file:`. Stack sẽ lên bình thường, không báo lỗi, và
lặng lẽ đọc ghi vào container `postgres` cũ trong khi bạn tin nó đang dùng Cloud SQL.

Bật cờ đó khiến `vm-deploy.sh` thêm lớp phủ [`deploy/docker-compose.cloudsql.yml`](../../deploy/docker-compose.cloudsql.yml):
container `postgres` không dựng, và ba service ứng dụng nhận đúng `DATABASE_URL` của bạn.

`POSTGRES_PASSWORD` không còn tác dụng khi bật cờ này — script bỏ qua nó.

**Chưa dựng stack vội** — lược đồ phải có trước. Sang bước 9.

---

### Bước 9 — Nạp lược đồ lên Cloud SQL, TRƯỚC khi dựng stack

Thứ tự này quan trọng và ngược với trực giác.

Với container `postgres`, lược đồ tự dựng lúc khởi tạo volume nên không ai phải nghĩ tới nó. Cloud
SQL bắt đầu **rỗng hoàn toàn**. Dịch vụ `migrate` phải áp lược đồ thành công trước khi `api` và
`worker` khởi động; bước này không sinh dữ liệu nghiệp vụ.

Đó là hành vi đúng, cố ý: hỏng lược đồ biến thành *"cả stack không lên"* chứ không phải *"mọi thứ
xanh, lỗi 500 lúc bấm vào"*. Nhưng nó có nghĩa là lược đồ phải đi trước.

Nạp bằng image ứng dụng đã build, không cần cài Python trên VM:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml \
               -f deploy/docker-compose.cloudsql.yml \
    run --rm --no-deps migrate python scripts/migrate.py
```

Lệnh đó áp `001`, `002`, `004`, `005` — **nhưng không áp `003_agent_readonly_role.sh`**, vì đó là
shell script cần thay biến mật khẩu, thứ `psql` không làm được bên trong chuỗi `$$...$$`. Hệ quả nếu
bỏ qua: vai trò `fin07_agent` và schema `agent` không tồn tại, và ranh giới *"agent không đọc được
nhãn"* (ND1/RD1) không được cưỡng chế. `migrate.py` **cảnh báo to** khi thiếu.

Áp bằng tay, chạy từ trong container để không phải cài `psql` lên VM:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml \
               -f deploy/docker-compose.cloudsql.yml \
    run --rm --no-deps --entrypoint bash migrate -c '
      apt-get update -qq && apt-get install -y -qq postgresql-client >/dev/null
      PGHOST=$(python -c "import os,urllib.parse as u; print(u.urlparse(os.environ[\"DATABASE_URL\"].replace(\"+psycopg\",\"\")).hostname)")
      PGPASSWORD=$(python -c "import os,urllib.parse as u; print(u.urlparse(os.environ[\"DATABASE_URL\"].replace(\"+psycopg\",\"\")).password)")
      PGSSLMODE=require POSTGRES_USER=fin07 POSTGRES_DB=fin07 \
      PGHOST=$PGHOST PGPASSWORD=$PGPASSWORD bash db/init/003_agent_readonly_role.sh'
```

**Mốc kiểm tra:** `... run --rm --no-deps migrate python scripts/migrate.py --status` hiện toàn bộ
file SQL ở trạng thái `đã áp`, cùng dòng `003_agent_readonly_role.sh`.

---

### Bước 10 — Dựng stack

Giờ mới dựng, khi lược đồ đã có:

```bash
bash deploy/vm-deploy.sh
```

Script kiểm tra trước khi dựng: `DATABASE_URL` có tồn tại không, có lỡ trỏ vào `@postgres:` không,
và có thiếu `?sslmode=require` không.

**Mốc kiểm tra:** `docker compose ps` **không** có dòng nào tên `postgres`, và `migrate` thoát mã 0.

---

### Bước 11 — Kiểm tra cuối

```bash
curl -sI https://amlmonitoring.site/ | head -1        # HTTP/2 200
curl -s  https://amlmonitoring.site/health/ready      # database + redis = true
curl -s  https://amlmonitoring.site/api/v1/dashboard  # số liệu đếm từ DB
```

Trên trình duyệt, đi hết luồng: `/login` → Tổng quan → Cảnh báo → mở một cảnh báo → Mở vụ việc →
**Chạy bước điều tra** → Audit trail hiện dòng mới.

---

### Sự cố thường gặp

**`terraform plan` báo không tìm thấy credential.** Bạn mới chạy `gcloud auth login`, còn thiếu
`gcloud auth application-default login`. Hai thứ khác nhau.

**`terraform plan` báo không tìm thấy VM.** Sai `vm_name` hoặc sai `zone` trong `terraform.tfvars`.
Đối chiếu lại bằng `gcloud compute instances list`.

**Cloud SQL từ chối kết nối từ VM.** Kiểm tra ba thứ, theo thứ tự: IP tĩnh đã gán vào VM chưa
(`terraform output vm_current_ip` phải khớp `static_ip`), chuỗi kết nối có `?sslmode=require` chưa,
và bạn đang dùng đúng `db_public_ip`.

**Chứng chỉ không cấp được.** Gần như luôn là một trong ba: DNS chưa trỏ đúng máy, cổng 80 chưa mở ở
tường lửa, hoặc đã chạm giới hạn 5 chứng chỉ/tuần của Let's Encrypt.

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml logs caddy --tail 50
```

**Nút "Chạy bước điều tra" không làm gì.** Vụ việc đã ở `ChoNguoiPheDuyet`. Đó là đúng: bước kế tiếp
cần quyết định của người phê duyệt, không phải một lượt chạy tự động (NT3). API trả 409 kèm lời giải
thích.

---

### Dừng tính tiền

Cloud SQL tính tiền kể cả khi không ai dùng.

```bash
# Tạm dừng — giữ dữ liệu, vẫn tốn tiền lưu trữ
gcloud sql instances patch fin07-postgres --activation-policy NEVER

# Bật lại
gcloud sql instances patch fin07-postgres --activation-policy ALWAYS
```

Gỡ hẳn thì phải hai bước có chủ ý — xem [`infra/terraform/README.md`](../../infra/terraform/README.md)
mục 8. Xoá một cơ sở dữ liệu chứa nhật ký kiểm toán không nên làm được bằng một lệnh gõ nhầm.

---

## Triển khai lên VM GCP — https://amlmonitoring.site/

Toàn bộ hệ thống chạy trên một máy ảo Compute Engine, sau Caddy làm reverse
proxy và lo chứng chỉ TLS. Trước đây giao diện nằm trên Vercel, nhưng Vercel
chỉ phục vụ được tệp tĩnh: không có chỗ cho PostgreSQL, Redis và worker nền —
tức là không có chỗ cho phần hệ thống làm ra việc.

```
Internet
   │  :80 → chuyển hướng :443
   ▼
Caddy ─────────────────────────────── chứng chỉ Let's Encrypt, tự gia hạn
   │  amlmonitoring.site
   ▼
web (nginx)  ── /            → tệp tĩnh React
   │            /api/*       → api
   │            /health/*    → api
   │            /docs        → api (Swagger)
   ▼
api (FastAPI) ──► PostgreSQL   dữ liệu vụ việc, cảnh báo, nhật ký kiểm toán
   │          └─► Redis        hàng đợi tác vụ
   ▼
worker ───────► PostgreSQL     chạy bước điều tra, ghi nhật ký
```

Chỉ Caddy mở cổng ra ngoài. PostgreSQL và Redis **không** publish cổng nào —
ở bản dev chúng mở ra máy chủ cho tiện gỡ lỗi, nhưng trên một máy có IP công
cộng thì "cho tiện" nghĩa là một cơ sở dữ liệu ai quét cũng thấy.

### Chuẩn bị một lần

#### 1. DNS

Tại nơi quản lý tên miền `amlmonitoring.site`, **xoá bản ghi trỏ về Vercel**
rồi thêm:

| Loại | Tên | Giá trị |
|---|---|---|
| A | `@` | `34.60.101.204` |
| A | `www` | `34.60.101.204` |

Kiểm tra đã lan truyền chưa:

```bash
dig +short amlmonitoring.site A     # phải ra 34.60.101.204
```

Caddy xin chứng chỉ qua HTTP-01: Let's Encrypt gọi ngược vào cổng 80 của
chính máy này. DNS chưa trỏ đúng thì chứng chỉ không cấp được, và stack vẫn
chạy nhưng chỉ truy cập được bằng IP.

#### 2. Firewall GCP

```bash
gcloud compute firewall-rules create fin07-web \
    --allow tcp:80,tcp:443 \
    --target-tags fin07 \
    --description "HTTP/HTTPS cho FIN-07 AML Console"

gcloud compute instances add-tags <TÊN_VM> --zone <ZONE> --tags fin07
```

Hoặc làm trong Console: VPC network → Firewall → Create rule.

#### 3. Cài Docker trên VM

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker            # hoặc đăng xuất rồi vào lại
```

#### 4. Lấy mã nguồn và tạo `.env`

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-022.git
cd P-022
git checkout develop
cp .env.example .env
```

Sửa `.env`, ba biến bắt buộc:

```dotenv
POSTGRES_PASSWORD=<chuỗi ngẫu nhiên dài>
FIN07_AGENT_DB_PASSWORD=<chuỗi ngẫu nhiên khác>
ACME_EMAIL=nguyengiabao762004@gmail.com
```

Sinh mật khẩu: `openssl rand -base64 32`

Script deploy từ chối chạy nếu `POSTGRES_PASSWORD` vẫn là mật khẩu mặc định
của môi trường dev.

### Dựng và cập nhật

```bash
bash deploy/vm-deploy.sh
```

Script kéo code mới trên `develop`, dựng image, khởi động stack, chờ tất cả
healthcheck xanh rồi tự kiểm tra lại qua HTTPS. Chạy lại bao nhiêu lần cũng
được; dữ liệu trong volume giữ nguyên.

Lệnh tương đương nếu muốn gõ tay:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml up -d --wait
```

### Kiểm tra sau khi dựng

```bash
curl -sI https://amlmonitoring.site/ | head -1          # HTTP/2 200
curl -s  https://amlmonitoring.site/health/ready        # database + redis = true
curl -s  https://amlmonitoring.site/api/v1/dashboard    # số liệu đếm từ DB
```

Trên trình duyệt, luồng demo đi được đầu–cuối:

1. `/login` — chọn một tài khoản demo, bấm **Truy cập hệ thống**
2. **Tổng quan** — KPI, phân bổ typology, tình trạng PostgreSQL/Redis/worker
3. **Cảnh báo** — hàng đợi thật, lọc theo typology
4. Mở một cảnh báo — yếu tố đóng góp, hồ sơ chủ thể, giao dịch
5. **Mở vụ việc** → bấm **Chạy bước điều tra**
6. Vụ việc tiến một bước trên máy trạng thái; **Audit trail** hiện dòng mới

### Xử lý sự cố

**Chứng chỉ không cấp được**

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml logs caddy --tail 50
```

Nguyên nhân hầu như luôn là một trong ba: DNS chưa trỏ về máy này, cổng 80
chưa mở ở firewall GCP, hoặc đã chạm giới hạn 5 chứng chỉ/tuần của Let's
Encrypt cho cùng một tên miền.

**Giao diện lên nhưng không có định dạng**

Tailwind đã không chạy lúc build. `web/Dockerfile` có một bước kiểm tra chặn
đúng lỗi này, nên nếu image dựng thành công thì nguyên nhân nằm ở chỗ khác —
kiểm tra cache trình duyệt trước.

**Bảng tình trạng hệ thống báo "không phản hồi"**

Giao diện đọc `/health/ready`, đường này phải được nginx proxy sang api. Kiểm
tra bằng `curl -s https://amlmonitoring.site/health/ready` — nếu trả về HTML
thay vì JSON thì `web/nginx.conf` đang thiếu khối `location /health`.

**Nút "Chạy bước điều tra" không làm gì**

Vụ việc đã ở `ChoNguoiPheDuyet`. Đó là đúng: bước kế tiếp cần quyết định của
người phê duyệt, không phải một lượt chạy tự động (NT3). API trả 409 kèm lời
giải thích và giao diện hiện nó thành thông báo.

**Xem log**

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml logs -f api worker
```

### Còn lại gì

Luồng nối vào dữ liệu thật là: đăng nhập → tổng quan → cảnh báo → chi tiết
cảnh báo → vụ việc → chạy bước điều tra → nhật ký kiểm toán.

Console đọc batch IBM AML LI-Small mới nhất đã nạp vào PostgreSQL. Điểm rủi ro
đến từ release fusion Isolation Forest + Graph hiện hành; stack không tự tạo
dữ liệu mô phỏng khi khởi động.

Luồng nạp dữ liệu IBM AML (Kafka → Flink → HDFS) nằm trong profile `aml` và
không chạy cùng stack này — xem [contracts/ingestion/README.md](../../contracts/ingestion/README.md). Nó cần
khoảng 4 GB RAM riêng, nên kiểm tra dung lượng VM trước khi bật.

---

## CI/CD — cổng chặn merge và pipeline giao hàng

Gộp từ `docs/CI.md` và `docs/CICD.md`. Hai file cũ tách nhau vì lý do lịch sử, nhưng người đọc gần
như luôn cần cả hai cùng lúc.

| | GitHub Actions | Jenkins |
|---|---|---|
| Vai trò | **Cổng chặn merge** | **Pipeline giao hàng** |
| Chạy khi | Mọi pull request, push lên `main`/`develop` | Mọi nhánh và pull request |
| Làm gì | lint, kiểm thử, hợp đồng, build image, `compose up` trên máy sạch | thêm: triển khai staging, phê duyệt, triển khai production-like, kiểm tra khói, quay lui |
| File | `.github/workflows/ci.yml` | `Jenkinsfile` |

**Cả hai gọi cùng các script trong `ci/`.** Không có logic CI nào viết hai lần, nên hai hệ thống
không lệch nhau được — và máy cá nhân chạy đúng những script đó.

```
                 ci/lint.sh   ci/test.sh   ci/build-images.sh
                 ci/smoke.sh  ci/deploy.sh ci/apply-schema.sh
                        ▲            ▲              ▲
                        │            │              │
              GitHub Actions     Jenkins       Máy cá nhân
```

---

### 1. Vì sao hai hệ thống

**Vì sao Jenkins.** FIN-07 là hệ thống giám sát AML; tài liệu đóng dấu "Nội bộ — Hạn chế". Tổ chức
tài chính nhận bàn giao sẽ chạy pipeline trong mạng của họ, không đẩy mã nguồn và bí mật lên runner
của bên thứ ba. Pipeline Jenkins bàn giao được nguyên trạng.

**Vì sao vẫn giữ GitHub Actions.** Yêu cầu nghiệm thu là "PR không đạt CI thì không merge được".
Cơ chế đó là branch protection của GitHub và nó cần một status check của GitHub. Bắt Jenkins báo
trạng thái ngược về PR thì Jenkins phải phơi ra Internet — rủi ro không đáng đổi.

---

### 2. Các job của cổng chặn merge

| Job | Kiểm cái gì | Thời gian điển hình |
|---|---|---|
| `lint` | `ruff check` và `ruff format --check` | ~40 giây |
| `test` | pytest với PostgreSQL và Redis thật, kèm độ phủ. Bao gồm kiểm chứng hợp đồng dữ liệu (`tests/test_contracts/`) | ~1,5 phút |
| `web` | `tsc --noEmit` và `vite build` | ~1 phút |
| `images` | Build và đẩy image api/worker và web lên GHCR | ~2–3 phút (có cache) |
| `compose-smoke` | `docker compose up` trên máy sạch, mọi healthcheck phải xanh | ~1,5 phút |
| `ci` | Cổng tổng hợp, gom kết quả các job trên | ~5 giây |

Tổng thời gian tường ≈ **4–5 phút**. Mỗi job đặt `timeout-minutes: 8`.

Ba thứ giữ pipeline nhanh: cache pip theo `requirements-dev.txt`, cache npm theo
`web/package-lock.json`, cache lớp Docker (`type=gha`) tách scope từng image, và `compose-smoke`
**kéo** image mà `images` vừa đẩy thay vì build lại.

#### Job `test` chạy gì

Kiểm thử tích hợp dùng PostgreSQL và Redis thật, không mock. Lý do: những ràng buộc quan trọng nhất
của FIN-07 nằm ở tầng cơ sở dữ liệu — nhật ký bất biến, phê duyệt ghi một lần, cách ly vai trò
agent. Mock một cơ sở dữ liệu rồi kiểm tra mock không chứng minh được gì.

1. Dựng service container `postgres:16-alpine` và `redis:7-alpine` (cổng động — runner của ban tổ
   chức đã có thứ gì đó nghe trên 5432).
2. Áp lược đồ bằng **chính** các file trong `db/init/`.
3. `pytest` toàn bộ trên lược đồ sạch, kèm báo cáo độ phủ tải lên artifact.

---

### 3. Image đẩy đi đâu

```
ghcr.io/<org>/<repo>/app:sha-<commit>      # api và worker
ghcr.io/<org>/<repo>/web:sha-<commit>      # console
```

Kèm tag di động: `pr-<số>` với pull request, hoặc tên nhánh với push.

```bash
APP_IMAGE=ghcr.io/<org>/<repo>/app:sha-<commit> \
WEB_IMAGE=ghcr.io/<org>/<repo>/web:sha-<commit> \
docker compose up -d --wait --no-build
```

PR từ fork chỉ có token chỉ đọc nên không đẩy được: `images` vẫn build để bắt lỗi Dockerfile, còn
`compose-smoke` bị bỏ qua.

---

### 4. Bật chặn merge — việc phải làm một lần trên GitHub

CI chạy đỏ **không** tự chặn merge. Phải bật branch protection, và đây là thao tác trên giao diện
GitHub, không nằm trong repo: `Settings → Branches → Add branch ruleset`.

| Mục | Giá trị |
|---|---|
| Target branches | `main`, `develop` |
| Require a pull request before merging | bật |
| Require status checks to pass | bật |
| Status check bắt buộc | **`CI`** — đúng một cái |
| Require branches to be up to date | bật |
| Block force pushes | bật |

```bash
gh api -X PUT repos/:owner/:repo/branches/develop/protection \
  -F required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=CI' \
  -F enforce_admins=false \
  -F required_pull_request_reviews[required_approving_review_count]=1 \
  -F restrictions=null
```

Chỉ chọn **một** status check tên `CI` — job cổng gom kết quả mọi job khác. Thêm job mới thì chỉ cần
thêm vào `needs` của job `ci`, không phải vào GitHub sửa lại cấu hình.

> **Chưa bật.** Cho tới khi bật, CI đỏ vẫn merge được như thường.

---

### 5. Luồng giao hàng

```
  Nhánh feature  →  pull request
       │
       ▼  GitHub Actions — đỏ thì không merge được
       │  merge vào develop
       ▼  Jenkins: chất lượng → build → triển khai STAGING (tự động) → khói → hỏng thì QUAY LUI
       │  merge vào main
       ▼  Jenkins: ⏸ CHỜ NGƯỜI PHÊ DUYỆT (bắt buộc có lý do) → PRODUCTION-LIKE → khói → quay lui
```

Cổng phê duyệt không phải thủ tục hành chính. Nguyên tắc NT3 của dự án là con người quyết định cuối
cùng ở mọi đường dẫn có hậu quả. Jenkins bắt người phê duyệt nhập lý do, và lý do đó vào nhật ký
build — cùng tinh thần với việc hệ thống bắt MLRO nêu lý do khi duyệt hồ sơ nghi vấn.

---

### 6. Ba môi trường

| | Phát triển | Staging | Production-like |
|---|---|---|---|
| Dùng để | máy cá nhân | kiểm thử tích hợp, demo nội bộ | đánh giá cuối, nghiệm thu |
| Triển khai bởi | `docker compose up` | Jenkins, tự động khi merge `develop` | Jenkins, sau khi có người duyệt |
| Lớp phủ compose | không | `deploy/docker-compose.staging.yml` | `deploy/docker-compose.prodlike.yml` |
| PostgreSQL, Redis | mở cổng ra máy chủ | **không mở** | **không mở** |
| Image | build tại chỗ | chỉ kéo image đã qua kiểm thử | chỉ kéo image đã qua kiểm thử |
| `APP_ENV` | `development` | `staging` | `production` |
| Dữ liệu nghiệp vụ | LI-Small đã nạp | LI-Small đã nạp | LI-Small đã nạp |

Pipeline không có bước xoá hay sinh dữ liệu nghiệp vụ. Dữ liệu LI-Small được
nạp bằng quy trình vận hành riêng và được giữ nguyên giữa các lần triển khai.

Không build tại chỗ ở staging và production-like, vì build tại chỗ nghĩa là thứ đang chạy không
phải thứ CI vừa kiểm.

---

### 7. Dựng Jenkins

Controller và agent đều dựng từ mã nguồn trong `jenkins/`. Không bấm qua giao diện.

```bash
cd jenkins
cp .env.example .env          # điền bí mật
docker compose up -d controller
# mở http://localhost:8080, đăng nhập bằng JENKINS_ADMIN_ID/PASSWORD

# lấy secret ở http://localhost:8080/computer/fin07-agent-1/
# điền vào JENKINS_AGENT_SECRET trong jenkins/.env
docker compose --profile agent up -d
```

**Agent phải chạy trên Linux.** Nó dùng `network_mode: host`, và đó không phải tuỳ chọn: agent build
image bằng Docker daemon của máy chủ, nên container mà pipeline dựng lên publish cổng ra máy chủ chứ
không ra mạng của agent. Không dùng mạng máy chủ thì bước kiểm tra khói gọi `localhost:8000` sẽ gọi
vào chính agent và luôn thất bại.

`jenkins/casc.yaml` là nguồn sự thật duy nhất: người dùng, phân quyền, credentials, node, job
multibranch. Sửa qua giao diện web thì lần khởi động lại tiếp theo ghi đè — đó là chủ ý. Controller
đặt `numExecutors: 0`: tiến trình đang giữ toàn bộ credentials không nên là tiến trình chạy mã đến
từ pull request.

#### Credentials

Jenkins đọc bí mật từ biến môi trường qua JCasC. Không giá trị nào nằm trong repo.

| ID | Dùng ở đâu |
|---|---|
| `fin07-registry` | đẩy image lên GHCR |
| `fin07-github` | đọc mã nguồn, quét nhánh |
| `fin07-staging-*` (postgres, agent-db, google-api-key) | triển khai staging |
| `fin07-prodlike-*` (postgres, agent-db, google-api-key) | triển khai production-like |

Staging và production-like **không dùng chung mật khẩu**. Dùng chung thì việc tách hai môi trường
chỉ còn là hình thức.

---

### 8. Quay lui

`ci/deploy.sh` tự quay lui:

1. Đọc image đang chạy **trên máy đích** (không đọc từ workspace Jenkins — workspace bị xoá giữa các
   lượt build, máy đích thì luôn biết chính nó đang chạy gì).
2. Triển khai phiên bản mới, chờ mọi healthcheck xanh.
3. Chạy `ci/smoke.sh`.
4. Hỏng ở bước 2 hoặc 3 → triển khai lại image cũ, và build đỏ.

Healthcheck xanh mới chỉ nói tiến trình còn sống. Kiểm tra khói mới là thứ quyết định giữ hay quay
lui: nó đi qua đường dữ liệu thật và chứng minh chuỗi API → Redis → worker → PostgreSQL thông.

---

### 9. Chạy đúng những gì CI chạy, trước khi mở PR

```bash
make check                              # lint + test, tương đương job `lint` + `test`
docker compose up -d --build --wait     # tương đương compose-smoke
cd web && npm run typecheck && npm run build
```

Mọi script trong `ci/` chạy độc lập được — đây cũng là cách gỡ lỗi nhanh nhất khi pipeline đỏ:

```bash
./ci/lint.sh
./ci/test.sh                 # tự dựng PostgreSQL và Redis, chạy kiểm thử, dọn sạch
./ci/build-images.sh
./ci/smoke.sh
./ci/deploy.sh staging
```

---

### 10. Tự động đồng bộ production (`deploy/autodeploy.sh`)

Mục 5 mô tả luồng giao hàng qua Jenkins, dùng khi bàn giao cho tổ chức tự vận
hành. Bản đang chạy tại <https://www.amlmonitoring.site> dùng một cơ chế khác,
và lý do là một ràng buộc thật chứ không phải sở thích kiến trúc.

#### Vì sao máy chủ *kéo* thay vì CI *đẩy*

Cách quen thuộc là GitHub Actions ssh vào máy chủ rồi triển khai. Cách đó cần
secret trong repo — khoá SSH hoặc service account — mà **thêm secret đòi quyền
Admin trên repo**, quyền nhóm này không có vì repo thuộc org của khoá học (xem
mục 4: cũng chính vì lý do đó mà branch protection tới nay vẫn chưa bật được).

Nên đảo chiều. Máy chủ tự hỏi GitHub hai câu — "nhánh phát hành đang ở commit
nào" và "CI của commit đó xanh chưa" — rồi tự kéo về. Thứ duy nhất cần là một
**fine-grained token chỉ đọc** do cá nhân tạo trong phần cài đặt tài khoản, với
quyền `Contents: Read` và `Actions: Read`. Không đụng tới quyền repo.

Đổi lại là độ trễ: thay đổi lên production sau tối đa một chu kỳ hẹn giờ, hiện
là hai phút.

#### Hai điều kiện phải cùng đúng

1. Commit đầu nhánh khác commit đang chạy.
2. Commit ấy có **ít nhất một** lượt kiểm tra, và **mọi** lượt đều `success`
   (hoặc `skipped`/`neutral`).

Điều kiện 2 cố ý chặt hơn mức cần thiết: commit chưa từng chạy CI cũng bị từ
chối, không chỉ commit CI đỏ. Nếu chỉ chặn CI đỏ, một lỗi cấu hình khiến
workflow không kích hoạt sẽ âm thầm biến cơ chế này thành "triển khai mọi thứ
được đẩy lên" — đúng cái mà nó sinh ra để ngăn.

#### Nhánh phát hành đang là `develop`, không phải `main`

Tính tới 16/08/2026, `main` còn lùi **110 commit** so với `develop` và commit
mới nhất của nó là một lần revert về trạng thái ban đầu. Trỏ agent vào `main`
lúc này sẽ ghi đè production bằng một bản cũ.

Chuyển sang `main` sau khi gộp `develop` vào `main` ở cuối chương trình, và chỉ
sau khi đã thấy CI xanh trên `main`. Sửa `DEPLOY_BRANCH` trong
`/etc/fin07/autodeploy.env`.

#### Cài đặt

```bash
sudo bash deploy/install-autodeploy.sh
sudo nano /etc/fin07/autodeploy.env      # điền GITHUB_TOKEN
sudo /opt/fin07/autodeploy.sh            # chạy thử một lượt, đọc log
sudo systemctl enable --now fin07-autodeploy.timer
```

#### Vận hành

```bash
journalctl -u fin07-autodeploy.service -f      # nhật ký
systemctl list-timers fin07-autodeploy.timer   # lịch chạy
cat /opt/fin07/state/deployed-sha              # commit đang phục vụ
sudo /opt/fin07/autodeploy.sh --force          # triển khai lại dù SHA không đổi
```

#### Quay lui

Sau khi dựng lại dịch vụ, agent gọi tên miền thật để kiểm tra khói — không phải
`localhost`, vì Caddy, chứng chỉ TLS và nginx trong container web đều là những
chỗ hỏng được mà container vẫn xanh. Kiểm tra khói hỏng thì agent tự `checkout`
lại commit trước và dựng lại, rồi thoát với mã lỗi khác 0.

#### Điều cần biết trước khi tin vào nó

- **Token hết hạn thì việc triển khai lặng lẽ dừng.** Không có gì trên giao
  diện báo điều đó. Đặt lịch thay token trước ngày hết hạn.
- **`.env` không nằm trong repo.** Agent chạy `git clean -fdx` nhưng chừa
  `.env`; máy chủ mới phải được chép `.env` vào `APP_DIR` trước lượt đầu tiên.
- **Chưa có kênh thông báo khi triển khai hỏng** — cùng lý do đã nêu ở mục 10.

### 11. Những chỗ chưa làm, nói rõ ra

- **Chưa bật branch protection** — mục 4. Chưa bật thì CI đỏ vẫn merge được.
- **Chưa có quét bảo mật image** (Trivy/Grype).
- **Hạ tầng dưới dạng mã: mới một phần.** [`infra/terraform/`](../../infra/terraform/) quản lý IP
  tĩnh, tường lửa và Cloud SQL. **VM thì không** — nó vẫn dựng bằng tay và Terraform chỉ tra cứu,
  cố ý: VM giữ dữ liệu trong volume Docker, để Terraform nắm vòng đời của nó nghĩa là một lần
  `destroy` lỡ tay xoá cả cơ sở dữ liệu. Pipeline triển khai lên máy chủ *đã tồn tại* qua
  `docker context`, không tự tạo ra máy chủ. Hệ quả còn lại: dựng lại **máy** từ đầu vẫn chưa tái
  lập được từ repo.
- **Chưa có kênh thông báo khi build hỏng.** Khối `post { failure { } }` trong `Jenkinsfile` để
  trống có chủ ý: một webhook giả cắm sẵn mà không tới nơi còn tệ hơn không có thông báo.
- **Chưa có kiểm tra tải** và **chưa có sao lưu/diễn tập khôi phục**.
- **Triển khai tự động chạy theo nhịp hẹn giờ, không theo sự kiện.** Máy chủ hỏi GitHub mỗi
  hai phút thay vì được webhook đánh thức, vì nhận webhook đòi mở cổng vào và một endpoint
  công khai để xác thực chữ ký. Hệ quả: độ trễ tối đa hai phút, và khoảng 720 lượt gọi API
  mỗi ngày.

---

## Giám sát — Prometheus và Grafana

Profile `obs`, không chạy cùng `make up`. Toàn bộ nằm ngoài đường phục vụ người dùng: tắt hết cụm
này thì hệ thống vẫn chạy y nguyên.

```bash
make obs-up        # dựng và chờ xanh
make obs-status    # mục tiêu nào đang scrape được
make obs-logs      # log Prometheus + Grafana
make obs-down      # dừng, giữ số liệu đã thu
```

Grafana <http://localhost:3000> · Prometheus <http://localhost:9090>

---

### 1. Thu thập gì, và vì sao chỉ chừng đó

| Nguồn | Trả lời câu hỏi |
|---|---|
| `node-exporter` | Máy còn chỗ không — CPU, RAM, đĩa, mạng, tải |
| `caddy` | **Người dùng thật thấy gì** — tốc độ, mã lỗi |
| `redis-exporter` | Hàng đợi tác vụ có bị ứ không |
| `postgres-exporter` | Cloud SQL còn nhận kết nối không |

Danh sách ngắn có chủ ý. Thu thập cho đủ bộ rồi không ai nhìn là cách nhanh nhất biến giám sát thành
chi phí thuần — tốn đĩa, tốn CPU, và làm chậm mọi truy vấn về sau.

Số liệu Caddy là thứ đáng tin nhất trong năm nguồn: nó đo ở rìa hệ thống, nên phản ánh đúng cái
người dùng nhận được, không phải cái ứng dụng *nghĩ* rằng nó đã trả về.

#### Không có: số liệu theo từng container

Bộ này **cố ý không dùng cAdvisor**, dù đó là lựa chọn mặc định của hầu hết hướng dẫn.

Docker 29 trên VM dùng containerd snapshotter (`Storage Driver: overlayfs`,
`driver-type: io.containerd.snapshotter.v1`) và bỏ hẳn bố cục
`/var/lib/docker/image/overlay2/layerdb` mà cAdvisor dựa vào để nhận diện container. Nó khởi động
được, endpoint `/metrics` trả lời bình thường, nhưng không đăng ký nổi container nào:

```
Failed to create existing container: … failed to identify the read-write layer ID … no such file
```

Đã thử `v0.49.1` và `v0.52.1`, cả hai cho **0 chuỗi** có nhãn `name`, kể cả khi trỏ thẳng vào
containerd bằng `--containerd-namespace=moby`.

Hệ quả chấp nhận được: `node-exporter` vẫn cho toàn bộ tài nguyên máy, và đây là VM chạy đúng một
hệ thống — biết máy sắp hết RAM quan trọng hơn biết container nào chiếm phần lớn. Thà thiếu một tầng
số liệu còn hơn để một thành phần hỏng nằm trong stack, ngốn CPU và bộ nhớ mà không cho lại gì.

Cần số liệu theo container thật thì hai đường: hạ Docker xuống bản dùng graphdriver `overlay2`, hoặc
chờ cAdvisor hỗ trợ containerd snapshotter.

#### Chưa có: số liệu tầng ứng dụng

`src/` chưa expose `/metrics`. Nghĩa là chưa đo được độ trễ **theo từng endpoint**, số vụ việc
chuyển trạng thái, hay thời gian một lượt điều tra. Hiện tất cả đo gián tiếp qua Caddy — biết
`/api/v1/alerts` chậm, nhưng không biết chậm ở truy vấn nào.

Bổ sung được bằng `prometheus-fastapi-instrumentator`: thêm một phụ thuộc và vài dòng trong
`src/main.py`, rồi thêm một job scrape `api:8000/metrics`. Chưa làm vì nó chạm vào ứng dụng đang
chạy, và số liệu hạ tầng đã đủ trả lời phần lớn câu hỏi vận hành.

---

### 2. Vì sao Caddy có một cổng riêng cho metrics

Caddy có sẵn metrics ở **admin API** cổng 2019. Nhưng admin API còn cho phép **đổi cấu hình đang
chạy** — mở nó ra mạng compose để Prometheus scrape nghĩa là bất kỳ container nào trong mạng cũng
định tuyến lại được cả site.

Nên [`deploy/Caddyfile`](../../deploy/Caddyfile) dựng một listener riêng ở cổng 2020 làm đúng một
việc: trả về `/metrics`. Cổng đó không publish ra máy chủ, chỉ với tới được từ trong mạng compose.

---

### 3. Dashboard

Một dashboard, năm nhóm, đọc từ trên xuống. Hàng đầu trả lời *"có đang hỏng không"*, các hàng dưới
trả lời *"hỏng ở đâu"*.

| Nhóm | Nội dung |
|---|---|
| Tình trạng chung | 7 ô số: dịch vụ sống, CPU, RAM, đĩa, p95, tỷ lệ 5xx, uptime |
| Lưu lượng người dùng | Request/giây theo nhóm mã trạng thái; p50/p95/p99 |
| Máy chủ | CPU theo loại tải, bộ nhớ, mạng |
| Tải máy chủ và đĩa | Tải trung bình so với số nhân CPU, tốc độ đọc/ghi đĩa |
| Hàng đợi và Cloud SQL | Độ sâu hàng đợi Redis, kết nối, commit/rollback |
| (cuối) | Bảng mục tiêu Prometheus — hàng nào `CHẾT` là scrape hỏng |

Dashboard nạp từ file, không bấm tay: [`monitoring/grafana/dashboards/`](../../monitoring/grafana/dashboards/).
Sửa trên giao diện được, nhưng file trong repo là nguồn sự thật — mỗi 30 giây Grafana nạp lại và ghi
đè thay đổi chưa commit. Muốn giữ thì xuất JSON rồi commit.

Vài chỗ đọc dễ sai:

**p95 chứ không phải trung bình.** Trung bình che mất đúng những request làm người dùng khó chịu:
99 request 50 ms và 1 request 5 giây cho trung bình 100 ms, nghe rất ổn.

**Ba đường phân vị tách xa nhau** nghĩa là có một nhóm nhỏ request rất chậm — thường là truy vấn nặng
hoặc chờ Cloud SQL, không phải hệ thống chậm đều.

**`iowait` cao mà `user` thấp** nghĩa là đang chờ đĩa hoặc mạng, không phải thiếu CPU. Nâng cấu hình
máy sẽ không giúp gì.

**Độ sâu hàng đợi Redis đi lên đều mà không tụt** nghĩa là worker đã chết hoặc chậm hơn tốc độ API
đẩy tác vụ vào.

---

### 4. Cảnh báo

Bảy luật trong [`monitoring/prometheus/rules/fin07.yml`](../../monitoring/prometheus/rules/fin07.yml):
dịch vụ không phản hồi, đĩa sắp đầy, RAM sắp cạn, tỷ lệ 5xx cao, phản hồi chậm, hàng đợi ứ, mất kết
nối Cloud SQL.

**Chưa nối Alertmanager.** Cảnh báo hiện lên ở tab Alerts của Prometheus và ở Grafana, không gửi đi
đâu. Cắm sẵn một webhook không tới nơi còn tệ hơn không có thông báo — cùng lý do khối
`post { failure { } }` trong `Jenkinsfile` để trống.

---

### 5. Trên VM

Cổng Grafana và Prometheus **bind vào `127.0.0.1`**, không ra Internet. Một Grafana mở công khai với
mật khẩu `admin` là chuyện không được phép xảy ra trên máy có IP công cộng.

Xem bằng đường hầm SSH:

```bash
gcloud compute ssh fin07-vm --zone asia-southeast1-a -- -L 3000:localhost:3000 -L 9090:localhost:9090
```

Giữ cửa sổ đó mở, rồi mở <http://localhost:3000> trên máy mình.

Dựng trên VM cần thêm lớp phủ như phần còn lại của stack:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.vm.yml \
               -f deploy/docker-compose.cloudsql.yml --profile obs \
    up -d --wait prometheus grafana node-exporter redis-exporter postgres-exporter
```

`MONITORING_PG_DSN` trong `.env` phải trỏ tới Cloud SQL và **không có tiền tố `+psycopg`** —
exporter dùng libpq, không hiểu cú pháp của SQLAlchemy:

```dotenv
MONITORING_PG_DSN=postgresql://fin07:<mật khẩu>@<db_public_ip>:5432/fin07?sslmode=require
```

#### Muốn mở Grafana ra ngoài

Đừng chỉ đổi binding. Thêm một khối vào `deploy/Caddyfile` để có TLS và một tên miền riêng:

```caddyfile
grafana.{$SITE_DOMAIN} {
	reverse_proxy grafana:3000
}
```

Kèm ba việc: thêm bản ghi A cho `grafana.<tên miền>`, **đổi `GRAFANA_ADMIN_PASSWORD`**, và bỏ
`127.0.0.1:` ở phần `ports` của service `grafana`.

---

### 6. Chi phí tài nguyên

VM `e2-medium` chỉ có 4 GB, nên mọi service đều có trần bộ nhớ:

| | Trần |
|---|---|
| prometheus | 512 MB |
| grafana | 320 MB |
| postgres-exporter | 96 MB |
| node-exporter | 96 MB |
| redis-exporter | 64 MB |

Tổng trần khoảng 1,1 GB; thực tế thấp hơn nhiều khi hệ thống rảnh.

Prometheus giữ **15 ngày và trần 2 GB**. Đặt cả hai chứ không chỉ một: giới hạn theo thời gian không
cứu được khi một đợt số liệu bất thường làm đầy đĩa trước hạn xoá.

Chật quá thì hạ `PROMETHEUS_RETENTION` xuống trước — mất chiều sâu lịch sử, giữ được toàn bộ số liệu
hiện tại.

---

### 7. Liên quan

- [`#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân`](#runbook-dựng-và-vận-hành-fin-07-trên-máy-cá-nhân) — dựng và vận hành trên máy cá nhân
- [`#dựng-hạ-tầng-gcp-từng-bước`](#dựng-hạ-tầng-gcp-từng-bước) — dựng hạ tầng GCP từng bước
- [Kiến trúc production — FIN-07 AML Level 1](../architecture/README.md#kiến-trúc-production-fin-07-aml-level-1) mục 7 — quan sát hệ thống ở mức production

---

## FIN-07 — Runbook LI-Small end-to-end

Tài liệu này là thứ tự chạy chuẩn để dựng lại hệ thống FIN-07 từ bộ dữ liệu
IBM AML **LI-Small**, huấn luyện hai nhánh Behaviour và Graph, hợp nhất score,
nạp dữ liệu vận hành vào PostgreSQL, rồi kiểm tra Console, Grafana, Loki và
Jaeger.

> Chạy từ thư mục gốc của repo. Không chạy `make db-reset` trừ khi thật sự muốn
> xoá toàn bộ dữ liệu PostgreSQL. Task 1 bên dưới **ghi lại**
> `data/processed/aml.duckdb`, vì vậy hãy sao lưu file đó nếu cần giữ bản cũ.

### 0. Trạng thái hiện tại cần biết

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

### 1. Kiểm tra môi trường và giữ nguyên mã nguồn

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

### 2. Kiểm tra đúng ba file LI-Small

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

### 3. Chạy cổng chất lượng trước khi xử lý dữ liệu

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

### 4. Build image và áp migration PostgreSQL

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

### 5. Dựng lại DuckDB đầy đủ và chia train/val/test

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

### 6. Dựng ground truth typology

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

### 7. Huấn luyện nhánh Behaviour — Isolation Forest 7 ngày

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

### 8. Chạy nhánh Graph và benchmark độc lập

#### 8.1. Tạo Graph features

```bash
cd /Users/nguyenbao/P-022
source .venv/bin/activate
python scripts/run_graph_features.py \
  --db data/processed/aml.duckdb \
  --cutoffs data/processed/split_cutoffs.json \
  --out data/processed/graph_features_v1.parquet
```

#### 8.2. Chạy FAN, GATHER_SCATTER và CYCLE

```bash
GRAPH_FEATURE_SHA="$(shasum -a 256 data/processed/graph_features_v1.parquet | awk '{print $1}')"
python scripts/run_graph_pipeline.py \
  --features data/processed/graph_features_v1.parquet \
  --feature-checksum "$GRAPH_FEATURE_SHA" \
  --manifest reports/graph_pipeline_manifest_v2.json
```

#### 8.3. Đánh giá detector theo IBM Patterns

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

#### 8.4. Chạy baseline Graph

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

### 9. Retrain chung, hiệu chỉnh và khóa champion fusion v2

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

### 10. Nạp release vào PostgreSQL và gắn geography cho UI

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

### 11. Khởi động ứng dụng và observability

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

### 12. Tiêu chí hoàn thành

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
