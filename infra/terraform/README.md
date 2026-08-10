# Hạ tầng GCP dưới dạng mã

Terraform quản lý phần hạ tầng **quanh** VM: IP cố định, tường lửa, và Cloud SQL.

Nó **không** tạo và không xoá VM. VM đang chạy có dữ liệu trong volume Docker, và để Terraform nắm
vòng đời của nó nghĩa là một lần `destroy` lỡ tay sẽ xoá cả cơ sở dữ liệu lẫn máy. VM được tra cứu
bằng `data source`, chỉ đọc.

Trạng thái trước khi có thư mục này được ghi trong [`docs/operations/CICD.md`](../../docs/operations/CICD.md)
mục 10: *"Không có hạ tầng dưới dạng mã. VPS thuê ngoài, dựng bằng tay."* Đây là bước vá điều đó,
làm từng phần chứ không một lần.

---

## 1. Terraform tạo gì

| Tài nguyên | Vì sao |
|---|---|
| `google_compute_address.web` | IP cố định. VM đang dùng IP ephemeral — đổi sau mỗi lần stop/start |
| `google_compute_firewall.web` | Chỉ mở 80 và 443. Cổng 80 cần cho xác thực ACME của Let's Encrypt |
| `google_sql_database_instance.main` | PostgreSQL có sao lưu tự động và khôi phục theo thời điểm |
| `google_sql_database.fin07` + `google_sql_user.app` | Database và tài khoản ứng dụng |
| `random_password.db` | Mật khẩu sinh tại chỗ, 32 ký tự |

Không có load balancer. Với đúng một VM, LB không tăng tính sẵn sàng — vẫn một backend duy nhất —
mà tốn thêm khoảng 18–25 USD/tháng. Khi nào cần chứng chỉ do Google quản lý, Cloud Armor, hoặc
nhiều instance thì thêm sau; IP tĩnh làm bây giờ không cản bước đó.

**Chi phí phát sinh:** Cloud SQL `db-f1-micro` khoảng 10–20 USD/tháng kể cả khi không ai dùng. IP
tĩnh miễn phí khi còn gắn vào một VM đang chạy, **có tính phí khi để không** — nên đừng đặt trước
rồi quên gán.

---

## 2. Chuẩn bị

```bash
brew install terraform            # hoặc: https://developer.hashicorp.com/terraform/install
gcloud auth application-default login
gcloud config set project <PROJECT_ID>

cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # rồi điền project_id, vm_name, zone
```

Tra `vm_name` và `zone` nếu chưa nhớ:

```bash
gcloud compute instances list
```

---

## 3. Áp

```bash
terraform init
terraform plan      # ĐỌC kế hoạch trước khi apply
terraform apply
```

`plan` phải cho thấy **chỉ tạo mới, không xoá gì**. Thấy dòng `destroy` nào là dừng lại — nghĩa là
state đang lệch với thực tế.

### Nếu tường lửa `fin07-web` đã tồn tại

[`DEPLOY_VM.md`](../../docs/operations/DEPLOY_VM.md) có bước tạo nó bằng tay. Đã tạo rồi thì Terraform
sẽ báo lỗi "already exists". Đưa nó vào quản lý thay vì xoá đi tạo lại:

```bash
terraform import google_compute_firewall.web projects/<PROJECT_ID>/global/firewalls/fin07-web
```

---

## 4. Sau khi apply — bốn việc bằng tay

`terraform output buoc_tiep_theo` in ra kèm giá trị thật. Tóm tắt:

**Gán IP tĩnh vào VM.** Không làm được bằng Terraform vì VM chỉ được tra cứu:

```bash
gcloud compute instances delete-access-config <VM> --zone <ZONE> --access-config-name "external-nat"
gcloud compute instances add-access-config <VM> --zone <ZONE> --access-config-name "external-nat" \
    --address $(terraform output -raw static_ip)
```

Giữa hai lệnh, VM mất kết nối ra ngoài vài giây. Đừng chạy khi đang có người xem.

**Gắn thẻ** để luật tường lửa có hiệu lực: `gcloud compute instances add-tags <VM> --zone <ZONE> --tags fin07`

**Trỏ DNS** bản ghi A của tên miền và `www` về IP mới. Caddy xin lại chứng chỉ được ngay khi DNS lan
truyền — Let's Encrypt giới hạn 5 chứng chỉ/tuần cho một tên miền, nên đừng thử đi thử lại.

**Đặt `DATABASE_URL`** vào `.env` trên VM: `terraform output -raw database_url`

---

## 5. Nạp lược đồ lên Cloud SQL — đọc kỹ mục này

Đây là chỗ dễ sai nhất, và cái sai không báo lỗi.

`db/init/*.sql` được PostgreSQL chạy tự động **chỉ khi** cơ sở dữ liệu dựng từ image `postgres` với
volume còn rỗng (`docker-entrypoint-initdb.d`). Cloud SQL không có cơ chế đó. Lược đồ phải nạp bằng
`scripts/migrate.py`:

```bash
DATABASE_URL="$(terraform output -raw database_url)" python scripts/migrate.py
```

**Nhưng `migrate.py` chỉ áp `*.sql`.** File `db/init/003_agent_readonly_role.sh` là shell script —
nó cần thay biến mật khẩu vào câu lệnh, mà `psql` không thay biến bên trong chuỗi `$$...$$`. Trên
Cloud SQL nó sẽ **không bao giờ chạy**, và hệ quả là:

- schema `agent` không tồn tại
- vai trò `fin07_agent` không tồn tại
- ranh giới *"agent không đọc được nhãn"* (ND1/RD1) **không được cưỡng chế**

Không có dòng lỗi nào. Một ràng buộc an toàn biến mất trong im lặng còn tệ hơn một ràng buộc chưa
từng có — vì người ta tin rằng nó đang bảo vệ mình.

`migrate.py` nay kiểm tra và **cảnh báo to** khi thiếu vai trò này. Áp bằng tay:

```bash
PGHOST=$(terraform output -raw db_public_ip) \
PGPASSWORD=$(terraform output -raw db_password) \
POSTGRES_USER=fin07 POSTGRES_DB=fin07 \
FIN07_AGENT_DB_PASSWORD='<chuỗi ngẫu nhiên khác>' \
    bash db/init/003_agent_readonly_role.sh
```

Rồi xác minh — bài kiểm thử này tồn tại đúng để trả lời câu hỏi đó:

```bash
DATABASE_URL="$(terraform output -raw database_url)" pytest tests/test_db/test_agent_role_isolation.py -v
```

---

## 6. Chuyển VM sang dùng Cloud SQL

Trên VM, trong `.env`:

```dotenv
DATABASE_URL=<giá trị từ terraform output -raw database_url>
```

Rồi bỏ service `postgres` khỏi stack đang chạy. **Trước khi bỏ, chuyển dữ liệu**:

```bash
# Trên VM — sao lưu từ container hiện tại
docker compose exec -T postgres pg_dump -U fin07 fin07 > fin07-backup.sql

# Nạp lên Cloud SQL
PGPASSWORD=<mật khẩu> psql -h <db_public_ip> -U fin07 -d fin07 --set=sslmode=require < fin07-backup.sql
```

Nhắc lại: `audit_log`, `approval` và `evidence` bị trigger chặn `UPDATE`/`DELETE`. `pg_dump` sinh
lệnh `INSERT`/`COPY` nên nạp được bình thường — nhưng **nạp hai lần sẽ nhân đôi dữ liệu và không thể
xoá đi**. Nạp một lần, kiểm bằng `SELECT count(*)` trước khi làm gì tiếp.

---

## 7. State chứa bí mật

`terraform.tfstate` chứa mật khẩu cơ sở dữ liệu ở dạng chữ thường. Nó đã nằm trong `.gitignore`,
nhưng điều đó chỉ chặn git — đừng gửi file này qua chat, đừng để trong thư mục đồng bộ đám mây.

Khi có người thứ hai chạm vào hạ tầng, chuyển state sang GCS backend — khối `backend "gcs"` đã viết
sẵn ở [`versions.tf`](versions.tf), chỉ cần bỏ chú thích. Hai bản state rời nhau sẽ dựng ra hai bộ
tài nguyên trùng lặp và không ai biết cái nào là thật.

---

## 8. Gỡ bỏ

`deletion_protection = true` khiến `terraform destroy` thất bại ở Cloud SQL. Đó là chủ đích. Muốn gỡ
thật:

```bash
# 1. đặt db_deletion_protection = false trong terraform.tfvars
terraform apply
# 2. rồi mới
terraform destroy
```

Hai bước, không phải một. Xoá một cơ sở dữ liệu chứa nhật ký kiểm toán không nên là chuyện làm được
bằng một lệnh gõ nhầm.
