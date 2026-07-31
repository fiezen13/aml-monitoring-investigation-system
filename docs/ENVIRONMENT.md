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

---

## 12. Luồng nạp dữ liệu AML (profile `aml`)

Các biến dưới đây chỉ có tác dụng với luồng `CSV IBM AML → Kafka → Flink →
HDFS`. Chúng **không** ảnh hưởng gì tới `api`, `worker` hay `web`, và profile
`aml` không khởi động cùng `docker compose up`.

Ba tiến trình đọc chúng:

| Ai đọc | Đọc gì |
|---|---|
| producer (`python -m src.aml`) | `AML_CSV_PATH`, `KAFKA_*`, `REPLAY_*`, giới hạn dữ liệu, điểm dừng |
| job Flink | `AML_HDFS_*`, `AML_FLINK_*`, `AML_CHECKPOINT_INTERVAL_MS`, `AML_WATERMARK_*` |
| compose | cổng, tên image, thư mục bộ dữ liệu |

### 12.1. Nguồn dữ liệu

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AML_CSV_PATH` | `data/raw/ibm-aml/HI-Small_Trans.csv` | Đường dẫn file `*_Trans.csv` khi chạy producer **từ máy chủ**. Đổi sang `LI-Small`, `HI-Medium`, `HI-Large`… chỉ cần đổi biến này; không chỗ nào trong mã ghi cứng tên file. |
| `AML_DATASET_DIR` | `./data/raw/ibm-aml` | Thư mục trên máy chủ được gắn **chỉ đọc** vào container producer tại `/data/raw/ibm-aml`. |
| `AML_DATASET_FILE` | `HI-Small_Trans.csv` | Tên file mà container producer đọc trong thư mục trên. Hai biến này là cặp tương ứng của `AML_CSV_PATH` khi chạy trong Docker. |
| `AML_SOURCE_DATASET` | rỗng | Tên bộ dữ liệu ghi vào sự kiện và dùng làm khoá phân vùng. Để trống thì suy ra từ tên file: `HI-Small_Trans.csv` → `HI-Small`. |
| `DATASET_TIMEZONE` | `UTC` | Múi giờ dùng để hiểu cột `Timestamp`. Bộ dữ liệu IBM **không** ghi múi giờ, nên đây là một giả định phải khai báo. Đổi biến này làm đổi `event_time_epoch_ms` và do đó đổi cả phân vùng ngày/giờ trên HDFS — không đổi giữa chừng một lần nạp. |

### 12.2. Kafka

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Danh sách broker. Trong mạng compose phải là `kafka:9092`; từ máy chủ là `localhost:29092`. Đây là lỗi cấu hình phổ biến nhất của luồng này. |
| `AML_KAFKA_PORT` | `29092` | Cổng broker phát ra máy chủ. |
| `AML_KAFKA_CLUSTER_ID` | `fin07-aml-local-cluster` | Mã cụm KRaft. Đổi giá trị này sau khi đã có dữ liệu sẽ làm broker từ chối khởi động — volume cũ mang mã cũ. |
| `AML_KAFKA_RETENTION_HOURS` | `168` | Thời gian giữ log ở mức broker (7 ngày). |
| `AML_RAW_TOPIC` | `aml.transactions.raw.v1` | Topic chứa sự kiện giao dịch hợp lệ. Producer ghi vào, Flink đọc ra — hai bên phải cùng giá trị. |
| `AML_DLQ_TOPIC` | `aml.transactions.dlq.v1` | Topic chứa dòng CSV không qua được kiểm tra ở producer. |
| `AML_TOPIC_PARTITIONS` | `3` | Số partition của topic dữ liệu. Đây là trần song song của phía tiêu thụ: Flink không thể chạy nhiều hơn số partition. |
| `AML_TOPIC_REPLICATION_FACTOR` | `1` | Trên máy cá nhân chỉ có một broker nên phải là 1. Cụm thật đặt 3. |
| `AML_TOPIC_RETENTION_MS` | `604800000` | Thời gian giữ dữ liệu của riêng hai topic AML (7 ngày). |
| `KAFKA_COMPRESSION_TYPE` | `lz4` | `none`, `gzip`, `snappy`, `lz4`, `zstd`. `lz4` nén tốt với JSON giao dịch mà tốn ít CPU. |
| `KAFKA_LINGER_MS` | `20` | Thời gian producer chờ gom batch. Tăng thì thông lượng tăng, độ trễ tăng theo. |
| `KAFKA_BATCH_SIZE` | `262144` | Kích thước batch, byte. |
| `KAFKA_QUEUE_BUFFERING_MAX_MESSAGES` | `100000` | Trần hàng đợi nội bộ của producer. **Đây là cơ chế backpressure**: chạm trần thì producer chờ chứ không phình bộ nhớ. Đặt quá lớn sẽ đổi một lỗi rõ ràng lấy một lần bị hệ điều hành giết vì hết RAM. |
| `KAFKA_MESSAGE_TIMEOUT_MS` | `120000` | Thời gian một message được phép nằm chờ trước khi bị coi là thất bại. |

### 12.3. Chế độ phát lại

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `REPLAY_MODE` | `max-throughput` | `max-throughput` gửi nhanh nhất có thể; `event-time` phát lại theo đúng khoảng cách thời gian giữa các giao dịch. |
| `REPLAY_SPEED_MULTIPLIER` | `1.0` | Chỉ có tác dụng ở chế độ `event-time`. `1` là tốc độ thật, `100` là nhanh gấp trăm lần, `0` là không chờ. |
| `REPLAY_MAX_SLEEP_SECONDS` | `5.0` | Trần thời gian chờ giữa hai sự kiện, để một khoảng trống dài trong dữ liệu không làm tiến trình đứng hình hàng giờ. |

### 12.4. Giới hạn dữ liệu khi phát triển

Bốn biến này để chạy thử trên một phần nhỏ của file lớn. `0` hoặc rỗng nghĩa
là không giới hạn.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `MAX_RECORDS` | `0` | Dừng sau bao nhiêu **sự kiện hợp lệ**. |
| `START_LINE` | `0` | Dòng vật lý đầu tiên được đọc; dòng tiêu đề là 1, nên dữ liệu bắt đầu từ 2. |
| `END_LINE` | `0` | Dòng vật lý cuối cùng được đọc, tính cả nó. |
| `FROM_TIMESTAMP` | rỗng | Chỉ phát sự kiện có event time từ mốc này trở đi, ISO-8601. Không ghi múi giờ thì hiểu theo `DATASET_TIMEZONE`. |
| `TO_TIMESTAMP` | rỗng | Mốc kết thúc, tính cả nó. |

### 12.5. Điểm dừng, dòng lỗi, nhật ký

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AML_CHECKPOINT_ENABLED` | `true` | Ghi điểm dừng để chạy tiếp sau khi producer bị ngắt. |
| `AML_CHECKPOINT_PATH` | `data/aml/checkpoints/producer.json` | File điểm dừng. Điểm dừng của file này không dùng được cho file khác — đổi bộ dữ liệu thì producer tự bỏ qua nó. |
| `AML_CHECKPOINT_INTERVAL_SECONDS` | `5.0` | Khoảng cách giữa hai lần ghi điểm dừng. Điểm dừng chỉ tiến khi Kafka đã **xác nhận**, không phải khi đọc xong dòng. |
| `AML_RESUME` | `true` | Đặt `false` để bỏ qua điểm dừng và chạy lại từ đầu. |
| `AML_DLQ_ENABLED` | `true` | Gửi dòng lỗi sang topic DLQ. Tắt thì lỗi chỉ còn trong file cục bộ. |
| `AML_ERROR_LOG_PATH` | `data/aml/rejected/producer-errors.jsonl` | File JSON Lines ghi dòng lỗi ngay trên máy. Tồn tại song song với DLQ có lý do: khi Kafka là thứ đang hỏng thì DLQ cũng hỏng theo. |
| `AML_PROGRESS_EVERY_SECONDS` | `10.0` | Nhịp in dòng tiến độ. Producer **không** log từng giao dịch ở mức INFO. |
| `AML_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` cho riêng producer. |

### 12.6. Flink

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AML_FLINK_IMAGE` | `fin07/flink-aml:local` | Image Flink kèm client Hadoop và jar của job. |
| `AML_FLINK_UI_PORT` | `8081` | Giao diện Flink trên máy chủ. |
| `AML_FLINK_PARALLELISM` | `2` | Mức song song mặc định. Không nên vượt `AML_TOPIC_PARTITIONS` — phần dư sẽ ngồi không. |
| `AML_FLINK_TASK_SLOTS` | `4` | Số slot của mỗi TaskManager. |
| `AML_FLINK_GROUP_ID` | `aml-hdfs-ingestion-v1` | Consumer group của job. Đổi giá trị này là bắt đầu đọc lại từ đầu topic. |
| `AML_KAFKA_OFFSET_RESET` | `earliest` | Vị trí đọc khi group chưa có offset đã commit: `earliest`, `latest`, `none`. |
| `AML_CHECKPOINT_INTERVAL_MS` | `30000` | Nhịp checkpoint của Flink. Với định dạng Parquet, **đây cũng là thứ quyết định kích thước file**: file chỉ được chốt tại checkpoint. |
| `AML_WATERMARK_OUT_OF_ORDER_SECONDS` | `120` | Mức trễ tối đa mà watermark cho phép. Giai đoạn này chưa có cửa sổ nào dùng tới, nhưng trục thời gian phải đúng từ lúc nạp. |

### 12.7. HDFS

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AML_HDFS_BASE_PATH` | `hdfs://namenode:8020/data/aml` | Gốc của vùng dữ liệu. Dữ liệu hợp lệ vào `<gốc>/bronze/transactions`, dữ liệu bị từ chối vào `<gốc>/rejected/transactions`. |
| `AML_HDFS_FORMAT` | `parquet` | `parquet` hoặc `json`. Xem docs/AML_INGESTION.md để biết khác biệt về cách cắt file. |
| `AML_HDFS_UI_PORT` | `9870` | Giao diện NameNode trên máy chủ. |

---
