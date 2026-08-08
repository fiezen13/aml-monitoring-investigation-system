# Triển khai lên VM GCP — https://amlmonitoring.site/

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

## Chuẩn bị một lần

### 1. DNS

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

### 2. Firewall GCP

```bash
gcloud compute firewall-rules create fin07-web \
    --allow tcp:80,tcp:443 \
    --target-tags fin07 \
    --description "HTTP/HTTPS cho FIN-07 AML Console"

gcloud compute instances add-tags <TÊN_VM> --zone <ZONE> --tags fin07
```

Hoặc làm trong Console: VPC network → Firewall → Create rule.

### 3. Cài Docker trên VM

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker            # hoặc đăng xuất rồi vào lại
```

### 4. Lấy mã nguồn và tạo `.env`

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

## Dựng và cập nhật

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

## Kiểm tra sau khi dựng

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

## Xử lý sự cố

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

## Còn lại gì

Luồng nối vào dữ liệu thật là: đăng nhập → tổng quan → cảnh báo → chi tiết
cảnh báo → vụ việc → chạy bước điều tra → nhật ký kiểm toán.

Các trang **Phê duyệt SAR**, **Người dùng**, **Cấu hình** và đồ thị mạng
lưới vẫn chạy bằng dữ liệu mô phỏng trong `web/src/data/`. Điểm rủi ro đến
từ bộ luật và heuristic trong `scripts/seed_data.py`, chưa phải mô hình đã
huấn luyện.

Luồng nạp dữ liệu IBM AML (Kafka → Flink → HDFS) nằm trong profile `aml` và
không chạy cùng stack này — xem [contracts/ingestion/README.md](../../contracts/ingestion/README.md). Nó cần
khoảng 4 GB RAM riêng, nên kiểm tra dung lượng VM trước khi bật.
