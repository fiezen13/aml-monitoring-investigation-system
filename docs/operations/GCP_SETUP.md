# Dựng hạ tầng GCP — từng bước

Danh sách việc để đi từ máy chưa có gì tới một VM có IP cố định và một Cloud SQL có sao lưu.

Làm theo thứ tự. Mỗi bước có một **mốc kiểm tra** — thấy đúng thứ đó mới đi tiếp, đừng chạy hết một
lượt rồi mới gỡ lỗi ngược.

| Tài liệu | Khi nào cần |
|---|---|
| File này | Trình tự và lệnh |
| [`infra/terraform/README.md`](../../infra/terraform/README.md) | Terraform tạo gì và vì sao, cách import, cách gỡ |
| [`DEPLOY_VM.md`](DEPLOY_VM.md) | Phần dựng Docker và Caddy trên VM |

---

## Bước 0 — Cần có gì

| | Kiểm tra | Nếu thiếu |
|---|---|---|
| Terraform ≥ 1.6 | `terraform version` | `brew install terraform` |
| gcloud CLI | `gcloud version` | Bước 1 |
| Tài khoản GCP có quyền tạo tài nguyên | | |
| Thẻ thanh toán đã bật trên dự án | | Cloud SQL không tạo được nếu chưa bật |

**Chi phí sẽ phát sinh:** Cloud SQL `db-f1-micro` khoảng 10–20 USD/tháng, chạy liên tục kể cả khi
không ai dùng. IP tĩnh miễn phí khi còn gắn vào VM đang chạy, **có tính phí khi để không**.

---

## Bước 1 — Cài gcloud

```bash
brew install --cask gcloud-cli
```

### Nếu nó hỏng ở bước "Virtual env setup failed"

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

## Bước 2 — Đăng nhập

Hai lệnh, hai mục đích khác nhau. Chỗ này hay nhầm:

```bash
gcloud auth login                      # cho bạn, để chạy lệnh gcloud
gcloud auth application-default login  # cho Terraform và các thư viện
```

Chỉ chạy lệnh đầu thì `terraform plan` vẫn báo không tìm thấy credential. Cả hai đều mở trình duyệt.

**Mốc kiểm tra:** `gcloud auth list` hiện email của bạn kèm dấu `*`.

---

## Bước 3 — Chọn dự án

```bash
gcloud projects list          # PROJECT_ID khác với tên hiển thị
gcloud config set project <PROJECT_ID>
```

**Mốc kiểm tra:** `gcloud config get-value project` trả về đúng ID.

---

## Bước 4 — VM

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

## Bước 5 — Terraform

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

Nếu báo lỗi tường lửa `fin07-web` đã tồn tại (do [`DEPLOY_VM.md`](DEPLOY_VM.md) từng tạo bằng tay),
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

## Bước 6 — Gán IP tĩnh vào VM

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

## Bước 7 — DNS

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

## Bước 8 — Đưa mã nguồn lên VM

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

Sửa `.env`. Khác [`DEPLOY_VM.md`](DEPLOY_VM.md) ở **hai** dòng, vì giờ dùng Cloud SQL thay cho
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

## Bước 9 — Nạp lược đồ lên Cloud SQL, TRƯỚC khi dựng stack

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

## Bước 10 — Dựng stack

Giờ mới dựng, khi lược đồ đã có:

```bash
bash deploy/vm-deploy.sh
```

Script kiểm tra trước khi dựng: `DATABASE_URL` có tồn tại không, có lỡ trỏ vào `@postgres:` không,
và có thiếu `?sslmode=require` không.

**Mốc kiểm tra:** `docker compose ps` **không** có dòng nào tên `postgres`, và `migrate` thoát mã 0.

---

## Bước 11 — Kiểm tra cuối

```bash
curl -sI https://amlmonitoring.site/ | head -1        # HTTP/2 200
curl -s  https://amlmonitoring.site/health/ready      # database + redis = true
curl -s  https://amlmonitoring.site/api/v1/dashboard  # số liệu đếm từ DB
```

Trên trình duyệt, đi hết luồng: `/login` → Tổng quan → Cảnh báo → mở một cảnh báo → Mở vụ việc →
**Chạy bước điều tra** → Audit trail hiện dòng mới.

---

## Sự cố thường gặp

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

## Dừng tính tiền

Cloud SQL tính tiền kể cả khi không ai dùng.

```bash
# Tạm dừng — giữ dữ liệu, vẫn tốn tiền lưu trữ
gcloud sql instances patch fin07-postgres --activation-policy NEVER

# Bật lại
gcloud sql instances patch fin07-postgres --activation-policy ALWAYS
```

Gỡ hẳn thì phải hai bước có chủ ý — xem [`infra/terraform/README.md`](../../infra/terraform/README.md)
mục 8. Xoá một cơ sở dữ liệu chứa nhật ký kiểm toán không nên làm được bằng một lệnh gõ nhầm.
