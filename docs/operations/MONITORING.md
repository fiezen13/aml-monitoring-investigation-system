# Giám sát — Prometheus và Grafana

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

## 1. Thu thập gì, và vì sao chỉ chừng đó

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

### Không có: số liệu theo từng container

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

### Chưa có: số liệu tầng ứng dụng

`src/` chưa expose `/metrics`. Nghĩa là chưa đo được độ trễ **theo từng endpoint**, số vụ việc
chuyển trạng thái, hay thời gian một lượt điều tra. Hiện tất cả đo gián tiếp qua Caddy — biết
`/api/v1/alerts` chậm, nhưng không biết chậm ở truy vấn nào.

Bổ sung được bằng `prometheus-fastapi-instrumentator`: thêm một phụ thuộc và vài dòng trong
`src/main.py`, rồi thêm một job scrape `api:8000/metrics`. Chưa làm vì nó chạm vào ứng dụng đang
chạy, và số liệu hạ tầng đã đủ trả lời phần lớn câu hỏi vận hành.

---

## 2. Vì sao Caddy có một cổng riêng cho metrics

Caddy có sẵn metrics ở **admin API** cổng 2019. Nhưng admin API còn cho phép **đổi cấu hình đang
chạy** — mở nó ra mạng compose để Prometheus scrape nghĩa là bất kỳ container nào trong mạng cũng
định tuyến lại được cả site.

Nên [`deploy/Caddyfile`](../../deploy/Caddyfile) dựng một listener riêng ở cổng 2020 làm đúng một
việc: trả về `/metrics`. Cổng đó không publish ra máy chủ, chỉ với tới được từ trong mạng compose.

---

## 3. Dashboard

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

## 4. Cảnh báo

Bảy luật trong [`monitoring/prometheus/rules/fin07.yml`](../../monitoring/prometheus/rules/fin07.yml):
dịch vụ không phản hồi, đĩa sắp đầy, RAM sắp cạn, tỷ lệ 5xx cao, phản hồi chậm, hàng đợi ứ, mất kết
nối Cloud SQL.

**Chưa nối Alertmanager.** Cảnh báo hiện lên ở tab Alerts của Prometheus và ở Grafana, không gửi đi
đâu. Cắm sẵn một webhook không tới nơi còn tệ hơn không có thông báo — cùng lý do khối
`post { failure { } }` trong `Jenkinsfile` để trống.

---

## 5. Trên VM

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

### Muốn mở Grafana ra ngoài

Đừng chỉ đổi binding. Thêm một khối vào `deploy/Caddyfile` để có TLS và một tên miền riêng:

```caddyfile
grafana.{$SITE_DOMAIN} {
	reverse_proxy grafana:3000
}
```

Kèm ba việc: thêm bản ghi A cho `grafana.<tên miền>`, **đổi `GRAFANA_ADMIN_PASSWORD`**, và bỏ
`127.0.0.1:` ở phần `ports` của service `grafana`.

---

## 6. Chi phí tài nguyên

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

## 7. Liên quan

- [`RUNBOOK.md`](RUNBOOK.md) — dựng và vận hành trên máy cá nhân
- [`GCP_SETUP.md`](GCP_SETUP.md) — dựng hạ tầng GCP từng bước
- [`../architecture/PRODUCTION_ARCHITECTURE.md`](../architecture/PRODUCTION_ARCHITECTURE.md) mục 7 — quan sát hệ thống ở mức production
