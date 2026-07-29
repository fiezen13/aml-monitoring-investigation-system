# Biến môi trường — FIN-07

Tài liệu này liệt kê **mọi** biến môi trường hệ thống đọc, kèm giá trị mặc
định, dịch vụ nào dùng, và hậu quả khi đặt sai.

Hai quy tắc:

1. **Không biến nào bắt buộc để chạy `docker compose up`.** Máy vừa clone
   repo, chưa có `.env`, chạy được ngay. Mặc định nằm trong
   `docker-compose.yml` dưới dạng `${TÊN_BIẾN:-giá trị}`.
2. **Thêm biến mới thì phải cập nhật file này.** Kiểm thử
   `tests/test_config_documented.py` đối chiếu ba nguồn — `src/config.py`,
   `.env.example`, và file này — và làm CI đỏ nếu lệch. Đây là cách duy nhất
   giữ tài liệu không lạc hậu.

Nguồn giá trị, theo thứ tự ưu tiên tăng dần:

```
mặc định trong src/config.py  →  mặc định trong docker-compose.yml  →  .env  →  biến môi trường của shell
```

---

## 1. Ứng dụng

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `APP_NAME` | `FIN-07 AML Agent` | api, worker | Tên hiển thị trong log và trang OpenAPI. |
| `APP_ENV` | `development` | api, worker, seed | Một trong `development`, `staging`, `production`, `test`. Đặt `production` sẽ **chặn** script seed xoá dữ liệu. |
| `APP_HOST` | `0.0.0.0` | api | Địa chỉ uvicorn lắng nghe. Trong container phải là `0.0.0.0`, nếu không cổng publish ra ngoài sẽ không nối được. |
| `APP_PORT` | `8000` | api | Cổng uvicorn lắng nghe **bên trong** container. Đổi cổng phát ra máy chủ thì sửa `API_PORT`. |
| `LOG_LEVEL` | `INFO` | api, worker, seed | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `CORS_ORIGINS` | `http://localhost:5173` | api | Danh sách origin, phân tách bằng dấu phẩy. Phải khớp địa chỉ trình duyệt mở console, nếu không trình duyệt chặn mọi request. |

## 2. Cổng phát ra máy chủ

Chỉ ảnh hưởng phía máy chủ. Cổng bị chiếm thì đổi ở đây, không sửa
`docker-compose.yml`.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `API_PORT` | `8000` | `http://localhost:$API_PORT/docs` |
| `WEB_PORT` | `5173` | `http://localhost:$WEB_PORT` |
| `POSTGRES_PORT` | `5432` | Để `psql` hoặc DBeaver nối vào được. |
| `REDIS_PORT` | `6379` | Để `redis-cli` nối vào được. |

## 3. PostgreSQL

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `POSTGRES_USER` | `fin07` | postgres | Chủ sở hữu cơ sở dữ liệu. |
| `POSTGRES_PASSWORD` | `fin07_dev_password` | postgres | **Chỉ dùng cho máy cá nhân.** Staging và production lấy từ kho bí mật, không từ file. |
| `POSTGRES_DB` | `fin07` | postgres | Tên cơ sở dữ liệu. |
| `FIN07_AGENT_DB_PASSWORD` | `fin07_agent_dev_password` | postgres | Mật khẩu vai trò `fin07_agent` — vai trò chỉ đọc, chỉ thấy schema `agent`, không có quyền nào trên schema `label` (QD1, NT5, RD1). Để trống thì khởi tạo cơ sở dữ liệu **thất bại có chủ ý**. |
| `DATABASE_URL` | trong Docker trỏ tới host `postgres` | api, worker, seed | Chuỗi kết nối SQLAlchemy. Chạy ngoài Docker phải đổi host thành `localhost`. |
| `DB_POOL_SIZE` | `5` | api, worker | Số kết nối giữ thường trực mỗi tiến trình. |
| `DB_POOL_MAX_OVERFLOW` | `5` | api, worker | Số kết nối mở thêm lúc cao điểm. Tổng kết nối tối đa của cả stack phải nhỏ hơn `max_connections` của PostgreSQL (mặc định 100). |

> Ba biến `POSTGRES_*` và `DATABASE_URL` phải khớp nhau. Sửa mật khẩu ở một
> chỗ mà quên chỗ kia là nguyên nhân phổ biến nhất khiến `api` không lên.
> `docker-compose.yml` dựng `DATABASE_URL` từ `POSTGRES_*` nên trong Docker
> chúng luôn khớp; chỉ khi chạy ngoài Docker mới phải tự giữ đồng bộ.

## 4. Redis và worker

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` trong Docker | api, worker | Chuỗi kết nối Redis. |
| `WORKER_QUEUE` | `fin07:jobs` | api, worker | Tên list Redis dùng làm hàng đợi. API và worker phải dùng **cùng** giá trị, lệch nhau thì tác vụ đẩy vào một nơi và worker nghe một nơi khác — không có thông báo lỗi nào, chỉ là hàng đợi đầy dần. |
| `WORKER_POLL_INTERVAL` | `1.0` | worker | Số giây `BLPOP` chờ mỗi vòng. Đây cũng là nhịp worker làm mới nhịp tim. |
| `WORKER_HEARTBEAT_KEY` | `fin07:worker:heartbeat` | api, worker | Khoá Redis chứa nhịp tim. Healthcheck của container worker đọc đúng khoá này. |
| `WORKER_HEARTBEAT_TTL` | `30` | worker | Giây. Phải lớn hơn `WORKER_POLL_INTERVAL` một khoảng an toàn, nếu không worker khoẻ vẫn bị báo unhealthy giữa hai vòng lặp. |

## 5. Mô hình ngôn ngữ

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `GOOGLE_API_KEY` | rỗng | api, worker | Khoá Gemini — nhà cung cấp đang dùng. Để trống thì hệ thống vẫn lên xanh; chỉ các endpoint gọi agent trả lỗi. |
| `OPENAI_API_KEY` | rỗng | api, worker | Giữ lại cho phương án dự phòng. |
| `MODEL_NAME` | `gemini-1.5-flash` | api, worker | Mã mô hình. |
| `LLM_TEMPERATURE` | `0.7` | api, worker | Trong khoảng 0–2. Với phần soạn hồ sơ nghi vấn nên hạ về gần 0. |

## 6. Dữ liệu mẫu

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `SEED_VALUE` | `20260728` | seed | Seed ngẫu nhiên. Cùng giá trị cho ra **cùng** dữ liệu, kể cả mốc thời gian (ND5). Kiểm chứng: `python scripts/seed_data.py --verify` chạy hai lần phải in cùng vân tay. |
| `SEED_CUSTOMERS` | `48` | seed | Số khách hàng sinh ra. Nhỏ hơn 12 thì không đủ tài khoản để cài đủ các kịch bản T01–T04. |
| `SEED_DAYS` | `90` | seed | Độ dài cửa sổ dữ liệu, tính bằng ngày. Cũng là cửa sổ để chia tập 60/20/20 theo thời gian. |

## 7. Vector store

| Biến | Mặc định | Dịch vụ | Ý nghĩa |
|---|---|---|---|
| `CHROMA_PERSIST_DIR` | `./data/chroma` | api, worker | Thư mục lưu vector danh sách trừng phạt. Trong Docker nằm trên volume `app_data`. |

## 8. Tên image

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `APP_IMAGE` | `fin07/app:local` | Image dùng chung cho `api`, `worker`, `seed`. CI ghi đè bằng tag GHCR để chạy đúng image vừa build thay vì build lại. |
| `WEB_IMAGE` | `fin07/web:local` | Image của console React. |

## 9. Nhật ký

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LANGCHAIN_API_KEY` | rỗng | Khoá LangSmith. Để trống thì không gửi trace đi đâu cả. |
| `LANGCHAIN_PROJECT` | `fin07-aml-agent` | Tên project trên LangSmith. |
| `LANGCHAIN_TRACING_V2` | `false` | Bật trace. Chỉ bật khi đã có khoá. |
| `AI_LOG_SERVER` | endpoint của giảng viên | Máy chủ nhận nhật ký AI hook. |
| `AI_LOG_API_KEY` | do giảng viên cung cấp | Khoá nhật ký AI hook. |
| `AI_LOG_DIR` | `.ai-log` | Thư mục đệm nhật ký cục bộ. |

---

## 10. Bí mật: cách xử lý theo môi trường

| Môi trường | Bí mật lấy từ đâu | Ai đặt |
|---|---|---|
| Phát triển | `.env` trên máy cá nhân, sao từ `.env.example` | Từng thành viên |
| CI | GitHub Actions secrets; job kiểm thử dùng mật khẩu dùng một lần của service container | Bảo |
| Staging / Production-like | Kho bí mật của hạ tầng, tiêm lúc triển khai | Bảo |

Không có giá trị mặc định nào trong repo được mang sang môi trường có dữ
liệu thật. Chúng tồn tại để một máy mới chạy được ngay, và chỉ để làm việc đó.

## 11. Kiểm tra nhanh khi có sự cố

```bash
# Compose thực sự nhìn thấy những giá trị nào (đã gộp mặc định và .env)
docker compose config

# Biến bên trong một container đang chạy
docker compose exec api env | sort

# Vì sao một dịch vụ chưa xanh
docker compose ps
docker compose logs api --tail=50
```

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| `api` mãi `starting` rồi `unhealthy` | `DATABASE_URL` trỏ `localhost` thay vì `postgres`. Trong container, `localhost` là chính container đó. |
| Trình duyệt báo lỗi CORS | `CORS_ORIGINS` không chứa địa chỉ đang mở console. Đổi `WEB_PORT` thì phải đổi cả biến này. |
| `worker` unhealthy nhưng log không có lỗi | `WORKER_HEARTBEAT_TTL` quá nhỏ so với `WORKER_POLL_INTERVAL`. |
| postgres thoát ngay lúc khởi tạo | `FIN07_AGENT_DB_PASSWORD` rỗng — `db/init/003` cố tình dừng thay vì tạo vai trò không mật khẩu. |
| Đổi lược đồ trong `db/init/` mà không thấy tác dụng | Script khởi tạo chỉ chạy khi volume còn rỗng. Chạy `make db-reset`. |
