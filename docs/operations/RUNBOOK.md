# Runbook — dựng và vận hành FIN-07 trên máy cá nhân

Đối tượng: bất kỳ ai vừa clone repo và cần hệ thống chạy trong vòng vài phút.

## 1. Yêu cầu

| Thứ cần có | Bản tối thiểu | Kiểm tra |
|---|---|---|
| Docker Engine | 24+ | `docker --version` |
| Docker Compose | v2.24+ (cần `env_file.required`) | `docker compose version` |
| RAM trống | ~2 GB | |

Không cần Python, không cần Node, không cần `.env`. Ba thứ đó chỉ cần khi
chạy ngoài Docker.

## 2. Một lệnh

```bash
docker compose up
```

Đó là toàn bộ. Lệnh này dựng năm dịch vụ và một tác vụ nạp dữ liệu:

| Dịch vụ | Vai trò | Cổng | Xanh khi |
|---|---|---|---|
| `postgres` | PostgreSQL 16, lược đồ nạp từ `db/init/` | 5432 | `pg_isready` qua TCP |
| `redis` | Hàng đợi tác vụ | 6379 | `redis-cli ping` |
| `seed` | Nạp dữ liệu mẫu rồi thoát | — | thoát với mã 0 |
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

## 3. Thứ tự khởi động

Không có `sleep` ở bất kỳ đâu. Mỗi bước chờ healthcheck của bước trước:

```
postgres ─┐
          ├─→ seed (chạy một lần, thoát 0) ─→ api ──→ web
redis ────┘                                └─→ worker
```

Điểm đáng chú ý: `api` và `worker` chờ `seed` **thoát thành công**, nên không
tồn tại khoảnh khắc nào giao diện mở ra mà cơ sở dữ liệu còn rỗng. Nếu lược đồ
hỏng, `seed` thoát khác 0 và cả stack không lên — hỏng thành ồn ào thay vì
thành lỗi 500 lúc ai đó bấm vào.

## 4. Việc thường làm

```bash
make help          # danh sách lệnh
make up            # dựng và chờ mọi healthcheck xanh
make health        # trạng thái sức khoẻ từng container
make logs          # theo dõi log
make seed          # nạp lại dữ liệu mẫu
make db-shell      # mở psql
make down          # dừng, giữ dữ liệu
make db-reset      # xoá volume và dựng lại lược đồ từ đầu
```

## 5. Dữ liệu mẫu

`scripts/seed_data.py` sinh dữ liệu tổng hợp: khách hàng theo bốn nguyên mẫu,
giao dịch trong 90 ngày, và các kịch bản rửa tiền T01–T05, T10 được cài có chủ
đích, kèm cảnh báo, vụ việc, bằng chứng và một hồ sơ đang chờ duyệt.

Cùng `SEED_VALUE` cho ra cùng dữ liệu, kể cả mốc thời gian (ND5):

```bash
make seed-verify   # in vân tay; chạy hai lần phải giống nhau
```

**Đây không phải dataset đánh giá.** Việc nạp IBM LI-Small (7 triệu giao dịch,
tỷ lệ rửa tiền ~0,05%) là hạng mục của Hiển ở Sprint 1 theo FIN-07-DAT-001.
Tỷ lệ nhãn trong fixture này được đặt cao hơn thực tế để mỗi màn hình đều có
dữ liệu nhìn thấy được.

## 6. Những ràng buộc đã cưỡng chế ở tầng dữ liệu

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

## 7. Chạy ngoài Docker

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

## 8. Sự cố

Hai điểm hay mất thời gian nhất:

**Sửa file trong `db/init/` mà không thấy tác dụng.** Script khởi tạo chỉ chạy
khi volume PostgreSQL còn rỗng. Volume đã có dữ liệu thì lần khởi động sau
container bỏ qua toàn bộ thư mục đó và không nói gì. `make db-reset`.

**Cổng đã bị chiếm.** Đổi trong `.env`: `API_PORT`, `WEB_PORT`,
`POSTGRES_PORT`, `REDIS_PORT`. Đổi `WEB_PORT` thì nhớ đổi cả `CORS_ORIGINS`.

## 9. Liên quan

- [`.env.example`](../../.env.example) — mọi biến môi trường, có test bắt buộc khai báo
- [CICD.md](CICD.md) — pipeline chạy gì trên mỗi pull request
- [`contracts/ingestion/README.md`](../../contracts/ingestion/README.md) — đường ống Kafka/Flink/HDFS: lệnh, ba giao diện, bẫy khi chạy lần đầu
- [PRODUCTION_ARCHITECTURE.md](../architecture/PRODUCTION_ARCHITECTURE.md) — hiện trạng triển khai và kiến trúc đích
- FIN-07-ARC-001 — tài liệu kiến trúc
- FIN-07-DAT-001 — đặc tả dữ liệu
