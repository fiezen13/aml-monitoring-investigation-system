# Hướng dẫn chạy hệ thống FIN-07 · Financial City AML

Tài liệu này hướng dẫn dựng và chạy toàn bộ hệ thống trên máy cá nhân bằng
Docker, kể cả bước sinh dữ liệu ABM theo tài liệu thiết kế
[`docs/design/ABM-thanh-pho-tai-chinh-v2.0.pdf`](design/ABM-thanh-pho-tai-chinh-v2.0.pdf).

Đối tượng: người vừa `git clone` xong và muốn thấy hệ thống chạy.

---

## 1. Yêu cầu

| Thành phần | Phiên bản | Ghi chú |
| --- | --- | --- |
| Docker Desktop | 24 trở lên | Phải bật trước khi chạy lệnh nào |
| Docker Compose | v2 | Đi kèm Docker Desktop |
| RAM trống | ≥ 4 GB | Toàn bộ stack chiếm khoảng 2,5 GB |
| Đĩa trống | ≥ 3 GB | Image và volume PostgreSQL |

Kiểm tra nhanh:

```bash
docker compose version
```

Không cần cài Python hay Node trên máy — mọi thứ chạy trong container. Chỉ khi
muốn phát triển giao diện với hot reload thì mới cần Node (xem mục 7).

---

## 2. Chạy lần đầu

Từ thư mục gốc của repo:

```bash
docker compose up -d --build
```

Lệnh này dựng image và khởi động sáu dịch vụ:

| Dịch vụ | Vai trò | Cổng |
| --- | --- | --- |
| `postgres` | Cơ sở dữ liệu | 5432 |
| `redis` | Hàng đợi công việc nền | 6379 |
| `seed` | Nạp dữ liệu mẫu rồi tự thoát | — |
| `api` | FastAPI | 8000 |
| `worker` | Xử lý nền | — |
| `web` | Giao diện + nginx proxy `/api` | **5173** |

Lần đầu mất khoảng 3–6 phút tuỳ tốc độ mạng. Khi xong:

```bash
docker compose ps
```

Cả sáu dòng phải ở trạng thái `running` và các dịch vụ có healthcheck phải là
`healthy`. Nếu có dòng nào `unhealthy`, xem mục 8.

### Mở giao diện

Truy cập **<http://localhost:5173>**.

Màn hình đăng nhập có sẵn danh sách tài khoản demo ở cột phải — nhấp vào một
tài khoản là tự điền, rồi bấm *Truy cập hệ thống*. Sáu vai trò có quyền khác
nhau:

| Tài khoản | Vai trò | Thấy được gì |
| --- | --- | --- |
| Nguyễn Quang Hưng | Compliance Officer | Cảnh báo, vụ việc, soạn SAR |
| Đàm Minh Tuấn | MLRO | Thêm quyền phê duyệt SAR |
| Lê Minh Khiêm | Auditor | Chỉ đọc, đầy đủ nhật ký kiểm toán |
| Đinh Huy Mạnh | Administrator | Thêm quản trị người dùng và cấu hình |
| Lê Anh Tuấn | Senior Analyst | Điều tra, không phê duyệt |

---

## 3. Sinh dữ liệu ABM — kịch bản VN-CA-03

Bước ở mục 2 mới chỉ nạp dữ liệu mẫu chung. Để có case theo đúng thiết kế ABM
(đánh bạc trực tuyến kết hợp rửa tiền), chạy thêm:

```bash
make abm
```

Muốn xem trước sẽ sinh ra bao nhiêu bản ghi mà chưa ghi gì xuống cơ sở dữ liệu:

```bash
make abm-dry
```

Kết quả một lần chạy (quy mô nhỏ, cố ý — đây là case để chạy thử đường ống,
không phải bộ dữ liệu huấn luyện):

```
entity                     39     ← thực thể: tài khoản, người, ví, thiết bị…
relationship               61     ← quan hệ, trong đó 12 cạnh là suy luận
corridor_flow              10     ← hành lang dòng tiền cho World Monitor
crypto_transfer            12     ← giao dịch USDT trên chuỗi
observation_event           7     ← nhật ký mở quyền truy cập bằng chứng
agent_step                  8     ← các bước agent đã chạy
benchmark_result            6     ← chỉ số kiểm định
gt_gambling_ledger         60     ← ledger cược (ẩn, chỉ để chấm điểm)
→ transaction              54     ← chiếu sang bảng vận hành
→ alert                     3
→ evidence                  5
```

Cuối lệnh phải in ra:

```
Kiểm tra rò rỉ (phụ lục D): đạt cả 6 điều kiện.
Đã nạp xong lần chạy SIM-VNCA03-001.
```

Nếu dòng này báo lỗi thì **dữ liệu không dùng được** — xem mục 8.4.

### Dữ liệu này gồm những gì

Điểm cốt lõi của thiết kế v2.0 là tách hai lớp (chương 4 và 10.3 của tài liệu):

- **Thế giới ẩn** (schema `fc_gt`) — nền tảng cá cược, người chơi, vai trò thật
  của từng thực thể, và ledger cược. Những thứ này **tồn tại trong thực tế**
  nhưng ngân hàng không nhìn thấy trước khi có điều tra. Chúng chỉ dùng để chấm
  điểm, không bao giờ được làm đặc trưng đầu vào.
- **Bằng chứng quan sát được** (schema `fc`) — nhiều người nạp tiền vào một cụm
  tài khoản, fan-in/fan-out, dùng chung thiết bị, chuyển đổi sang USDT. Đây là
  toàn bộ những gì mô hình được phép học.

Nhờ tách như vậy, chỉ số "phát hiện sớm bao nhiêu ngày" mới có nghĩa: nó là
khoảng cách giữa lúc hành vi bắt đầu (thế giới ẩn biết) và lúc có tín hiệu đầu
tiên quan sát được.

Dữ liệu sinh ra **tất định**: cùng `--seed` cho ra cùng kết quả. Đổi quy mô
bằng `--scale` (mặc định 1, là nhỏ nhất):

```bash
docker compose run --rm seed python scripts/abm_generate.py --force --scale 3
```

---

## 4. Đi một vòng hệ thống

Sau khi chạy `make abm`, thứ tự dưới đây đi đúng theo đường công việc của một
analyst và chạm vào mọi màn hình.

1. **Tổng quan** — hàng KPI, xu hướng cảnh báo, hành lang rủi ro nhất, hàng đợi
   ưu tiên. Thẻ *Trạng thái hệ thống* phải hiện `SIM-VNCA03-001` và `VN-CA-03`.

2. **World Monitor** — bản đồ dòng tiền. Thử: bấm **3D** để chuyển sang quả cầu,
   tắt bớt layer ở cột trái, bấm **Chỉ đáng ngờ**, nhấp vào một cung để mở
   inspector. Kéo thanh trượt dưới cùng để phát lại theo thời gian.

3. **Alert Center** — hàng đợi cảnh báo. Các mã `ALR-ABM-*` là cảnh báo do ABM
   sinh; phần còn lại từ dữ liệu mẫu.

4. **Network Graph** — đồ thị toàn mạng lưới. **Nhấp vào một cạnh nét đứt**: cột
   phải sẽ nói rõ đây là quan hệ *suy luận*, kèm độ tin cậy và diễn giải. Ví dụ
   "cùng IP tĩnh trong 9 phiên, không loại trừ được NAT của nhà mạng" có độ tin
   cậy thấp hơn hẳn "cùng IMEI trong 41 phiên". Ba đỉnh hình thoi màu xanh là
   *hard negative* — thực thể hợp pháp cố ý đưa vào để đo tỷ lệ gắn cờ nhầm.

5. **Transaction Explorer** — giao dịch thô, lọc và phân trang phía máy chủ.

6. **Crypto Tracing** — chuyển động USDT và nhãn phơi nhiễm. Chú ý biểu đồ *Độ
   tin cậy liên kết bank ↔ chain*: phần lớn nằm ở khoảng 0.6–0.8, nghĩa là các
   liên kết này chỉ là **ứng viên**, không phải bằng chứng.

7. **Project Risk** — dự án token LUXP với các đặc trưng quan sát công khai.

8. **Agent Runs → RUN-2026-0341-01** — nhật ký 8 bước của agent. Bước
   `request_vasp_records` có trạng thái **blocked**: vai trò tổ chức tài chính
   không có thẩm quyền yêu cầu dữ liệu VASP. Lần chạy kết thúc ở
   `needs_human` chứ không phải `succeeded` — agent đề xuất, con người quyết định.

9. **Benchmarks** — sáu chỉ số kiểm định. Không có accuracy, và mục cuối trang
   giải thích vì sao.

10. **Model Monitoring** — PSI đang trôi lên khoảng 0.238, ở trạng thái *cần
    theo dõi*. Biểu đồ có vẽ sẵn hai đường ngưỡng 0.20 và 0.25.

11. **Data Quality** — ba tab. Tab *Nhật ký mở quyền* trả lời câu hỏi "tại thời
    điểm ra quyết định, agent được phép nhìn thấy những gì". Tab *Source
    registry* ghi rõ mỗi nguồn dữ liệu **không được dùng để** làm gì.

12. **Phê duyệt SAR → Audit Logs** — khép lại quy trình.

Phím tắt **⌘K** (hoặc **Ctrl+K**) mở bảng lệnh, tìm được cả màn hình lẫn thực thể.

---

## 5. Các lệnh thường dùng

```bash
make help              # liệt kê toàn bộ lệnh có sẵn
```

| Lệnh | Việc |
| --- | --- |
| `make up` | Khởi động stack |
| `make down` | Dừng stack, giữ dữ liệu |
| `make ps` | Trạng thái các container |
| `make logs` | Xem log trực tiếp |
| `make health` | Kiểm tra API sẵn sàng chưa |
| `make seed` | Nạp lại dữ liệu mẫu |
| `make abm` | Sinh và nạp case ABM |
| `make abm-dry` | Xem trước, không ghi |
| `make migrate` | Áp lược đồ mới, **giữ nguyên dữ liệu** |
| `make migrate-status` | File lược đồ nào đã áp |
| `make db-shell` | Mở `psql` |
| `make db-reset` | Xoá sạch và dựng lại (mất dữ liệu) |
| `make test` | Chạy bộ kiểm thử |

---

## 6. Cập nhật lược đồ mà không mất dữ liệu

PostgreSQL chỉ chạy các file trong `db/init/` khi volume còn **rỗng**. Trên máy
đã chạy rồi, thêm một file lược đồ mới sẽ không có tác dụng gì.

Dùng bộ áp migration thay vì xoá cơ sở dữ liệu:

```bash
make migrate-status   # xem file nào còn chờ
make migrate          # áp các file còn thiếu
```

Nó giữ một bảng `schema_migration` ghi nhận file nào đã áp, và chạy mỗi file
trong một transaction riêng. Lần chạy đầu trên cơ sở dữ liệu cũ, các file
`001`–`004` được nhận là đã áp từ trước chứ không chạy lại.

> **Lưu ý về bảng chỉ ghi thêm.** Ba bảng `evidence`, `audit_log` và `approval`
> bị chặn xoá ở tầng cơ sở dữ liệu (`db/init/002_audit_immutability.sql`). Đó là
> ràng buộc pháp lý, không phải trở ngại kỹ thuật để đi vòng. Vì vậy `make abm`
> chạy lại sẽ giữ nguyên bằng chứng đã ghi. Nếu cần xoá thật sự thì phải
> `make db-reset`.

---

## 7. Phát triển giao diện với hot reload

Cách trên đã phục vụ giao diện ở bản build sẵn. Khi sửa code frontend và muốn
thấy thay đổi ngay:

```bash
docker compose stop web        # nhường cổng 5173
cd web && npm install          # chỉ lần đầu
npm run dev
```

Vite chạy ở <http://localhost:5173> và tự proxy `/api` sang `localhost:8000`, nên
backend trong Docker vẫn dùng được bình thường.

Trước khi commit:

```bash
cd web && npm run typecheck
```

### Một chi tiết dễ vấp

Các engine đồ hoạ trong `web/src/vendor/fc/` là **custom element** lấy nguyên
từ prototype thiết kế. Với custom element, React 18 biến prop `className` thành
một attribute tên `classname` mà CSS không nhìn thấy — element sẽ cao 0px và
canvas im lặng không vẽ gì mà cũng không báo lỗi. Vì vậy các wrapper trong
`web/src/components/fc/` định vị bằng `style`, không bằng `className`. Giữ
nguyên quy ước đó khi thêm engine mới.

---

## 8. Khi có trục trặc

### 8.1. Cổng 5173 đã bị chiếm

Triệu chứng: `web` khởi động được nhưng trình duyệt không mở được trang, hoặc
mở ra bản cũ.

Thường là do Vite dev server đang chạy song song. Dừng một trong hai. Hoặc đổi
cổng của container:

```bash
WEB_PORT=5174 docker compose up -d web
```

### 8.2. Container `unhealthy`

```bash
docker compose logs api      # hoặc web, worker, postgres
```

`api` thường `unhealthy` vì chưa nối được PostgreSQL. Kiểm tra:

```bash
curl -s http://localhost:8000/health/ready
```

Phản hồi phải là `{"status":"ready","database":true,"redis":true}`.

### 8.3. Màn hình mới trống trơn

World Monitor, Crypto Tracing, Benchmarks… hiện "Chưa có dữ liệu" nghĩa là chưa
chạy generator:

```bash
make abm
```

Nếu vẫn trống, kiểm tra lược đồ đã có chưa:

```bash
docker compose exec postgres psql -U fin07 -d fin07 \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('fc','fc_gt');"
```

Phải ra **19**. Nếu ra 0 thì chạy `make migrate`.

### 8.4. Generator báo lỗi kiểm tra rò rỉ

Ví dụ:

```
Kiểm tra rò rỉ thất bại:
  - 2 bằng chứng tầng điều tra lọt vào hồ sơ vụ việc của ngân hàng.
```

Đây không phải lỗi vặt. Nó nghĩa là dữ liệu vừa sinh vi phạm ranh giới quyền
quan sát, và mọi chỉ số đo trên dữ liệu đó sẽ sai theo hướng đẹp một cách giả
tạo. Vì bảng `evidence` không xoá được, cách xử lý là dựng lại:

```bash
make db-reset
make seed
make abm
```

### 8.5. `make test` báo `No module named 'psycopg2'`

Bộ kiểm thử chạy trên máy chủ (không trong container) và đọc `DATABASE_URL` từ
`.env`. Nếu giá trị đó thiếu phần `+psycopg`, SQLAlchemy sẽ mặc định dùng driver
`psycopg2` vốn không được cài — dự án dùng psycopg 3.

Sửa dòng `DATABASE_URL` trong `.env` cho khớp `.env.example`:

```
DATABASE_URL=postgresql+psycopg://fin07:fin07_dev_password@localhost:5432/fin07
```

Hoặc truyền thẳng cho một lần chạy:

```bash
DATABASE_URL="postgresql+psycopg://fin07:fin07_dev_password@localhost:5432/fin07" \
  python -m pytest -q
```

Kết quả mong đợi: **301 passed**. Lỗi này chỉ ảnh hưởng bộ kiểm thử chạy trên
máy chủ; các container dùng biến riêng trong `docker-compose.yml` nên không bị.

### 8.6. Xoá sạch làm lại từ đầu

```bash
docker compose down -v      # xoá cả volume
docker compose up -d --build
make abm
```

---

## 9. Bản đồ mã nguồn

```
db/init/
  001_schema.sql              lược đồ nghiệp vụ AML
  002_audit_immutability.sql  chặn sửa/xoá evidence, audit_log, approval
  004_console_runtime.sql     người dùng, phiên, cấu hình
  005_financial_city.sql      lược đồ ABM: schema fc và fc_gt (19 bảng)

scripts/
  seed_data.py                dữ liệu mẫu chung
  migrate.py                  áp lược đồ mới, giữ nguyên dữ liệu
  abm_generate.py             sinh case ABM + kiểm tra rò rỉ

src/api/
  routes.py                   API quy trình AML sẵn có
  fc_routes.py                API các màn hình Thành phố tài chính

web/src/
  vendor/fc/                  engine canvas lấy nguyên từ prototype thiết kế
  components/fc/              wrapper React cho các engine đó + primitives
  design/palette.ts           bảng màu cho canvas (khớp tailwind.config.js)
  config/nav.ts               cấu trúc điều hướng
  pages/                      16 màn hình
```

---

## 10. Giới hạn cần biết

Toàn bộ dữ liệu trong hệ thống là **tổng hợp từ mô phỏng**. Không có khách hàng
thật, không có tên thật trong danh sách trừng phạt, không có địa chỉ ví thật.

Theo đúng phạm vi khẳng định của tài liệu thiết kế v2.0: bộ dữ liệu này đủ để
dựng PoC và benchmark có căn cứ, nhưng **chưa đủ để khẳng định mô hình sẵn sàng
triển khai sản xuất**. Việc đó còn cần hiệu chỉnh và kiểm định trên dữ liệu thật
đã được bảo vệ tại ít nhất một tổ chức tài chính hoặc cơ quan có thẩm quyền.

Ngoài ra, không có thiết kế dataset nào bảo đảm phát hiện đầy đủ giao dịch tiền
mặt hoặc tài sản tăng cường ẩn danh không đi qua điểm on/off-ramp quan sát được.
Hệ thống đo và báo cáo độ phủ của mình, không quảng cáo phát hiện toàn diện.

---

## 11. Triển khai lên máy chủ

Phần này chưa thực hiện trong lần bàn giao hiện tại. Khi cần đưa lên VM và tên
miền, xem `docs/DEPLOY_VM.md`; lưu ý hai điểm:

- Bản ghi A của tên miền phải trỏ về IP công cộng của VM thì Caddy mới xin được
  chứng chỉ Let's Encrypt.
- Trên VM đã có dữ liệu, dùng `make migrate` chứ không dùng `make db-reset`.
