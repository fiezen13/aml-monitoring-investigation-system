# Kế hoạch huấn luyện và đưa MEGA-PNA HI-Medium lên production

Tài liệu này chốt một đường duy nhất:

> **Huấn luyện MEGA-PNA trên HI-Medium → lấy benchmark tốt → tải artifact từ máy GPU về →
> dựng lại production bằng release mới.**

Không chạy nhánh dữ liệu phụ và không dùng kết quả của bộ dữ liệu khác để so sánh trong báo cáo demo.

---

## 1. Kết quả cuối cùng cần đạt

Khi hoàn thành, nhóm phải có đủ bốn thứ:

1. Báo cáo benchmark HI-Medium trên đúng 5 seed.
2. Một checkpoint `.pt` được chọn bằng kết quả validation, không chọn bằng test.
3. File điểm của từng giao dịch trong tập test.
4. Một release production đang hoạt động trên console, có giao dịch, điểm mô hình và cảnh báo mới.

Luồng tổng thể:

```text
HI-Medium đã format
        ↓
Máy ảo GPU huấn luyện 5 seed
        ↓
checkpoint + predictions + report
        ↓ tải về máy local
kiểm checksum và chọn checkpoint
        ↓
dựng release + nạp PostgreSQL
        ↓
API và console dùng release mới
```

Production không gọi máy GPU mỗi khi người dùng mở một trang. Mô hình được chạy theo lô để tạo
điểm trước; API chỉ đọc điểm đã nạp trong PostgreSQL. Chạy xong và tải đủ artifact thì có thể tắt
máy GPU.

---

## 2. Máy GPU thực sự trả về cái gì?

Mỗi seed tạo ba artifact chính:

```text
models/mega-pna/Medium_HI/paper/
├── seed_42.pt
└── seed_42_test.parquet

reports/mega-pna/Medium_HI/paper/
└── seed_42.json
```

Sau 5 seed còn có báo cáo tổng hợp:

```text
reports/mega-pna/benchmark.json
```

### 2.1 Checkpoint `.pt`

Đây là **mô hình đã huấn luyện**. File chứa:

- trọng số của MEGA-PNA;
- epoch tốt nhất;
- seed;
- cấu hình mô hình;
- tên đặc trưng;
- ranh giới train, validation và test;
- thống kê bậc đồ thị cần để dựng lại mô hình.

Checkpoint là artifact quan trọng nhất để tái lập kết quả hoặc chạy suy luận lại. Nó không chứa
toàn bộ giao dịch và không tự nạp được vào PostgreSQL.

### 2.2 Predictions `.parquet`

Đây là kết quả chấm điểm trên tập test, gồm:

- `source_edge_id`: giao dịch nào đang được chấm;
- `score`: xác suất/risk score do mô hình trả ra;
- `is_laundering`: nhãn thật, chỉ dùng để đánh giá;
- `edge_position`: vị trí cạnh trong đồ thị.

File này dùng để tính benchmark và để tạo dữ liệu điểm đưa lên console. Production tuyệt đối không
dùng cột `is_laundering` làm đầu vào mô hình.

### 2.3 Báo cáo từng seed `.json`

Báo cáo chứa:

- F1, precision, recall và PR-AUC;
- confusion matrix;
- epoch tốt nhất;
- ngưỡng chọn trên validation;
- số cảnh báo tại từng alert budget;
- lịch sử metric theo epoch;
- thời gian chạy và phiên bản môi trường.

### 2.4 `benchmark.json`

Đây là báo cáo gộp 5 seed: trung bình, độ lệch chuẩn và kết quả từng seed. File này dùng để trình
bày với mentor và lưu vào metadata của release production.

Nói ngắn gọn:

| Artifact | Dùng để làm gì? |
|---|---|
| `.pt` | Giữ mô hình và chạy suy luận lại |
| `_test.parquet` | Điểm từng giao dịch test |
| `seed_*.json` | Chứng minh kết quả một lần chạy |
| `benchmark.json` | Chứng minh kết quả ổn định qua 5 seed |

---

## 3. Tiêu chí nghiệm thu benchmark

Không dùng accuracy làm chỉ số chính vì dữ liệu mất cân bằng. Bảng demo nên đặt F1, precision,
recall và PR-AUC cạnh nhau.

Release chỉ được đi tiếp khi đạt tất cả điều kiện sau:

| Chỉ số | Điều kiện |
|---|---:|
| F1 trung bình 5 seed | **≥ 0,75** |
| F1 thấp nhất trong 5 seed | **≥ 0,73** |
| Độ lệch chuẩn F1 | **≤ 0,01** |
| Precision trung bình | **≥ 0,70** |
| Recall trung bình | **≥ 0,70** |
| Số seed hoàn tất | **5/5** |

PR-AUC và các alert budget phải được báo cáo đầy đủ, nhưng chưa đặt ngưỡng cứng trước khi có lần
chạy đầu tiên. Sau lần chạy đầu, chọn alert budget phù hợp với số hồ sơ mà đội demo có thể rà.

Không chọn checkpoint có F1 test cao nhất. Quy tắc chọn release:

1. chọn seed có F1 validation cao nhất;
2. nếu bằng nhau, chọn seed có mã seed nhỏ hơn để quy tắc luôn tất định;
3. test chỉ được dùng để báo cáo kết quả cuối cùng.

Quy tắc này tránh việc nhìn test nhiều lần rồi chọn đúng seed đẹp nhất.

---

## 4. Ba thay đổi mã cần làm trước khi chạy chính thức

Code hiện tại chưa đi thẳng từ HI-Medium tới production. Cần hoàn thành ba thay đổi sau.

### 4.1 Cho phép chạy trực tiếp HI-Medium

`scripts/benchmark_mega_pna.py` hiện chặn HI-Medium nếu chưa chạy cổng dữ liệu nhỏ. Sửa script để
có lệnh độc lập:

```bash
python scripts/benchmark_mega_pna.py \
  --suite hi-medium \
  --device cuda \
  --seeds 42 43 44 45 46 \
  --epochs 80
```

Suite mới chỉ được:

- chạy `Medium_HI`;
- yêu cầu đúng 5 seed;
- tổng hợp metric theo tiêu chí ở mục 3;
- không tạo dòng báo cáo cho dataset khác;
- trả exit code khác 0 nếu thiếu seed hoặc không đạt tiêu chí.

### 4.2 Khóa manifest artifact

Sau khi chạy xong, cần sinh một manifest chứa đường dẫn, kích thước và SHA-256 của:

- 5 checkpoint;
- 5 file predictions;
- 5 báo cáo seed;
- `benchmark.json`;
- file dữ liệu đã format và manifest của nó.

Manifest giúp phát hiện file tải thiếu hoặc bị thay đổi giữa máy GPU và máy local.

### 4.3 Viết bộ nạp release MEGA-PNA từ đầu

`scripts/load_edge_scores.py` chỉ gắn điểm vào một PostgreSQL đã có giao dịch và không sinh cảnh
báo. Bộ nạp cũ từ đầu lại chỉ hiểu artifact của mô hình `.joblib`, không hiểu checkpoint `.pt`.

Cần tạo `scripts/load_mega_pna_release.py` với các trách nhiệm:

1. chỉ chạy trên database sạch hoặc staging mới;
2. kiểm checksum checkpoint, predictions, report và DuckDB;
3. nạp các giao dịch thuộc tập test HI-Medium;
4. nạp `transaction_model_score`;
5. tạo cảnh báo từ các dòng vượt ngưỡng validation;
6. tạo tối thiểu ba `alert_reason` cho mỗi cảnh báo;
7. ghi `edge_model_release` và chỉ chuyển sang `active` sau khi kiểm đủ số dòng;
8. dựng lại dữ liệu tổng hợp địa lý và metadata console;
9. rollback toàn bộ transaction nếu một bước thất bại.

Đây là bước bắt buộc nếu muốn nói “mô hình mới đang chạy trên production”, thay vì chỉ nói “đã
huấn luyện xong”.

---

## 5. Chuẩn bị dữ liệu HI-Medium

Repo hiện đã có dữ liệu format:

```text
data/processed/mega-pna/Medium_HI/formatted_transactions.csv
data/processed/mega-pna/Medium_HI/formatted_transactions.manifest.json
```

Manifest hiện ghi:

| Thuộc tính | Giá trị |
|---|---:|
| Giao dịch | 31.898.238 |
| Nhãn dương | 35.230 |
| Self-transfer | 2.561.860 |
| SHA-256 file format | `bfbd8847a3215826360dad60b9ef930308d5929c1725b846d43dd5547de9995e` |

Kiểm tra trên Linux/GPU:

```bash
sha256sum data/processed/mega-pna/Medium_HI/formatted_transactions.csv
```

Nếu cần format lại từ file gốc:

```bash
.venv/bin/python scripts/format_mega_pna.py --dataset Medium_HI
```

Không dùng `--force` nếu chưa lưu manifest cũ để đối chiếu.

---

## 6. Chuẩn bị máy ảo GPU

Khuyến nghị tối thiểu:

- GPU NVIDIA, VRAM từ 24 GB;
- RAM hệ thống từ 64 GB;
- đĩa trống từ 150 GB;
- CUDA tương thích với image `cuda11.8` của repo.

RAM hệ thống quan trọng vì bộ nạp hiện đọc 31,9 triệu dòng và dựng nhiều tensor đồ thị trước khi
huấn luyện. Nếu tiến trình bị `Killed` mà không có traceback CUDA, nguyên nhân thường là hết RAM
hệ thống, không phải hết VRAM.

Trên máy GPU:

```bash
git clone <URL_REPOSITORY> P-022
cd P-022
docker build -f docker/mega-pna/Dockerfile -t fin07-mega-pna:cuda118 .
nvidia-smi
```

Chuyển đúng hai file dữ liệu sang máy GPU:

```text
data/processed/mega-pna/Medium_HI/formatted_transactions.csv
data/processed/mega-pna/Medium_HI/formatted_transactions.manifest.json
```

Không cần chuyển raw CSV nếu chỉ huấn luyện.

---

## 7. Chạy thử trước khi tốn nhiều giờ GPU

Chạy 2 epoch vào thư mục riêng:

```bash
docker run --rm --gpus all \
  --entrypoint python \
  -v "$PWD/data:/workspace/data" \
  -v "$PWD/models:/workspace/models" \
  -v "$PWD/reports:/workspace/reports" \
  fin07-mega-pna:cuda118 \
  scripts/train_mega_pna.py \
  --dataset Medium_HI \
  --seed 42 \
  --epochs 2 \
  --device cuda \
  --output-dir models/mega-pna-smoke \
  --reports-dir reports/mega-pna-smoke
```

Chỉ đi tiếp khi:

- GPU có tải trong `nvidia-smi`;
- loss là số hữu hạn;
- train F1 và validation F1 được in sau mỗi epoch;
- có `.pt`, `.parquet` và `.json` trong thư mục smoke;
- thời gian một epoch nằm trong mức chi phí chấp nhận được.

Xóa hoặc chuyển thư mục smoke ra ngoài trước khi chạy chính thức để không bị nhầm artifact.

---

## 8. Chạy benchmark chính thức

Sau khi hoàn thành thay đổi ở mục 4.1:

```bash
docker run -d --name fin07-hi-medium --gpus all \
  -v "$PWD/data:/workspace/data" \
  -v "$PWD/models:/workspace/models" \
  -v "$PWD/reports:/workspace/reports" \
  fin07-mega-pna:cuda118 \
  --suite hi-medium \
  --device cuda \
  --seeds 42 43 44 45 46 \
  --epochs 80
```

Theo dõi:

```bash
docker logs -f fin07-hi-medium
nvidia-smi
```

Không giảm số neighbor, số layer hoặc số epoch giữa các seed. Nếu hết VRAM, thử giảm batch size
và ghi rõ giá trị mới trong báo cáo. Nếu hết RAM hệ thống, đổi sang VM có RAM lớn hơn.

Script hiện có tái sử dụng seed đã hoàn tất nếu report có cùng `epochs` và `batch_size`, nên có thể
chạy lại sau khi VM bị gián đoạn mà không phải huấn luyện lại các seed đã xong.

---

## 9. Tải output từ máy GPU về

Trên máy GPU, tạo checksum trước:

```bash
cd ~/P-022
find models/mega-pna/Medium_HI reports/mega-pna/Medium_HI \
  -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum \
  > reports/mega-pna/Medium_HI/SHA256SUMS
sha256sum reports/mega-pna/benchmark.json >> reports/mega-pna/Medium_HI/SHA256SUMS
```

Trên máy local, đặt địa chỉ và SSH key của VM:

```bash
export FIN07_GPU_HOST="ubuntu@<GPU_PUBLIC_IP>"
export FIN07_GPU_KEY="/duong-dan/toi/gpu-key.pem"
```

Tải artifact về bằng `rsync` để có thể tiếp tục nếu mạng đứt:

```bash
rsync -avP -e "ssh -i $FIN07_GPU_KEY" \
  "$FIN07_GPU_HOST:~/P-022/models/mega-pna/Medium_HI/" \
  models/mega-pna/Medium_HI/

rsync -avP -e "ssh -i $FIN07_GPU_KEY" \
  "$FIN07_GPU_HOST:~/P-022/reports/mega-pna/Medium_HI/" \
  reports/mega-pna/Medium_HI/

rsync -avP -e "ssh -i $FIN07_GPU_KEY" \
  "$FIN07_GPU_HOST:~/P-022/reports/mega-pna/benchmark.json" \
  reports/mega-pna/benchmark.json
```

Kiểm lại trên macOS:

```bash
shasum -a 256 -c reports/mega-pna/Medium_HI/SHA256SUMS
```

Chỉ tắt/xóa VM GPU sau khi:

- checksum đều `OK`;
- đủ 5 checkpoint, 5 predictions và 5 report;
- mở được `benchmark.json`;
- đã sao lưu artifact sang ít nhất một nơi thứ hai.

Checkpoint và báo cáo nhỏ có thể lưu trong Git nếu chính sách repo cho phép. Predictions, raw data,
DuckDB và database dump phải để ở kho artifact ngoài Git.

---

## 10. Kiểm chứng lại checkpoint đã tải về

Chọn checkpoint theo validation như mục 3. Ví dụ seed được chọn là `42`, chạy lại inference trên
máy GPU trước khi hủy VM hoặc trên một máy CUDA khác:

```bash
python scripts/infer_mega_pna.py \
  --dataset Medium_HI \
  --checkpoint models/mega-pna/Medium_HI/paper/seed_42.pt \
  --output models/mega-pna/Medium_HI/paper/seed_42_test_reproduced.parquet \
  --device cuda
```

Yêu cầu:

- metric tái lập khớp báo cáo seed;
- số dòng predictions khớp tập test;
- SHA-256 checkpoint khớp manifest;
- ngưỡng production lấy từ `test_validation_threshold`, không tối ưu lại trên test.

---

## 11. Dựng release cho production

### 11.1 Production demo dùng phần dữ liệu nào?

Production demo nên dùng **tập test HI-Medium**, không dùng các giao dịch đã tham gia train hoặc
validation. Đây là lý do console hiện chỉ cần khoảng 20% số giao dịch gốc.

### 11.2 Dựng DuckDB nguồn

```bash
.venv/bin/python scripts/load_ibm_dataset_duckdb.py \
  --csv data/raw/ibm-aml/HI-Medium_Trans.csv \
  --out data/processed/hi_medium.duckdb \
  --threads 8 \
  --memory-limit 24GB
```

### 11.3 Chuyển predictions sang release score

Ví dụ seed release là `42`:

```bash
.venv/bin/python scripts/build_mega_pna_release.py \
  --predictions models/mega-pna/Medium_HI/paper/seed_42_test.parquet \
  --report reports/mega-pna/Medium_HI/paper/seed_42.json \
  --benchmark reports/mega-pna/benchmark.json \
  --raw data/raw/ibm-aml/HI-Medium_Trans.csv \
  --db data/processed/hi_medium.duckdb \
  --scores-out data/processed/mega-pna/Medium_HI/pg_scores.parquet \
  --report-out reports/mega-pna/Medium_HI/release.json \
  --threads 8 \
  --memory-limit 24GB
```

Bước này nối `source_edge_id` của mô hình với `transaction_id` trong DuckDB, loại các self-transfer
mà schema vận hành không nhận, rồi ghi ngưỡng đã chọn trên validation.

### 11.4 Nạp vào staging sạch

Sau khi viết `scripts/load_mega_pna_release.py`, lệnh đích là:

```bash
.venv/bin/python scripts/load_mega_pna_release.py \
  --db data/processed/hi_medium.duckdb \
  --scores data/processed/mega-pna/Medium_HI/pg_scores.parquet \
  --report reports/mega-pna/Medium_HI/release.json \
  --benchmark reports/mega-pna/benchmark.json \
  --model models/mega-pna/Medium_HI/paper/seed_42.pt \
  --dry-run
```

`--dry-run` phải kiểm được checksum, số dòng, số nhãn dương, số dòng vượt ngưỡng và feature count
mà không ghi database.

Khi dry-run đạt, bỏ `--dry-run` và trỏ `DATABASE_URL` vào staging. Không chạy lần đầu trực tiếp
trên production.

---

## 12. Dự trù Cloud SQL mới cho HI-Medium

### 12.1 Không nạp chồng lên Cloud SQL hiện tại

Hệ thống đang có một VM GCP và một Cloud SQL chứa release cũ. Không nên nạp thêm release mới vào
instance đó vì:

- bảng `transaction_model_score` sẽ giữ đồng thời điểm cũ và điểm mới;
- index, WAL và bảng tạm lúc import cần thêm dung lượng ngoài kích thước dữ liệu cuối;
- nếu import thất bại giữa chừng, database đang demo có thể vừa chậm vừa khó dọn sạch;
- đổi dataset trong cùng database làm rollback phức tạp.

Phương án an toàn là tạo **Cloud SQL thứ hai chạy song song**, nạp và kiểm thử xong rồi mới đổi
`DATABASE_URL` trên VM. Cloud SQL cũ được giữ nguyên để rollback.

Không đổi `db_instance_name` của resource `google_sql_database_instance.main` hiện tại. Việc đổi
tên trên cùng resource có thể tạo kế hoạch thay thế instance cũ. Thay vào đó, thêm resource mới với
địa chỉ Terraform riêng, ví dụ `google_sql_database_instance.hi_medium`.

### 12.2 Đo instance hiện tại trước khi chốt cấu hình

Không đọc `terraform.tfstate` hoặc in `database_url` ra log vì state chứa mật khẩu. Chỉ lấy metadata
không nhạy cảm:

```bash
gcloud sql instances describe <CURRENT_INSTANCE> \
  --format='yaml(name,region,databaseVersion,settings.tier,settings.dataDiskSizeGb,settings.storageAutoResize)'
```

Đo dung lượng thật từ PostgreSQL:

```sql
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

Lưu kết quả vào báo cáo hạ tầng trước khi tạo instance mới. Đây là số đo để điều chỉnh bảng dự trù
bên dưới, không dùng kích thước file dump thay cho kích thước database sau khi tạo index.

**Đã đo ngày 17/08/2026:** instance cũ `fin07-postgres-sg` dùng PostgreSQL 16, tier
`db-f1-micro`, đĩa 15 GB có autoresize. Database đang chiếm khoảng **5,17 GiB**; hai bảng lớn
nhất là `transaction` khoảng 2,45 GiB và `transaction_model_score` khoảng 1,64 GiB. Cấu hình này
đủ giữ đường rollback nhưng không phù hợp để nạp thêm release HI-Medium.

### 12.3 Hai mức dung lượng dự trù

| Phương án | Dữ liệu phục vụ | Tier khởi điểm | Đĩa khởi điểm | Trần tự tăng | Khuyến nghị |
|---|---|---|---:|---:|---|
| **Demo** | Test split, khoảng 5,87 triệu giao dịch sau khi bỏ self-transfer | `db-custom-2-7680` | **50 GB SSD** | 100 GB | **Chọn phương án này** |
| Toàn bộ | Khoảng 29,34 triệu giao dịch vận hành sau khi bỏ self-transfer | `db-custom-4-15360` | **150 GB SSD** | 300 GB | Chỉ làm khi đã mở rộng inference/loader |

Các con số trên là ngân sách an toàn ban đầu, gồm headroom cho transaction, score, alert, index,
WAL và bảng tạm khi import. Chúng không phải cam kết kích thước cuối cùng; staging phải đo lại bằng
`pg_database_size` sau khi nạp.

Google khuyến nghị tăng kích thước đĩa thủ công **trước** một đợt import lớn thay vì trông chờ hoàn
toàn vào autoresize. Đĩa Cloud SQL có thể tăng nhưng không thể giảm, nên đặt mức khởi điểm đủ cho
import và đặt trần để tránh tăng không kiểm soát. Xem tài liệu chính thức về
[Cloud SQL instance settings](https://docs.cloud.google.com/sql/docs/postgres/instance-settings) và
[machine series](https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview).

Phương án “toàn bộ” chưa chạy được bằng code hiện tại: `infer_mega_pna.py` chỉ xuất test split và
loader ở mục 4.3 cũng được thiết kế cho test release. Muốn chọn phương án này phải bổ sung chế độ
score toàn bộ graph trước khi thuê thêm dung lượng Cloud SQL.

### 12.4 Thay đổi Terraform cần thực hiện

Module hiện tại mặc định `db-f1-micro` và đĩa 10 GB vì thiết kế cũ cho rằng không lưu hàng triệu
giao dịch trong Cloud SQL. Giả định đó không còn đúng với release mới.

Thêm các biến mới, không tái sử dụng biến của instance cũ:

```hcl
variable "hi_medium_db_instance_name" {
  type    = string
  default = "fin07-hi-medium-v1"
}

variable "hi_medium_db_tier" {
  type    = string
  default = "db-custom-2-7680"
}

variable "hi_medium_db_disk_size_gb" {
  type    = number
  default = 50
}

variable "hi_medium_db_disk_autoresize_limit_gb" {
  type    = number
  default = 100
}
```

Tạo `infra/terraform/database_hi_medium.tf` gồm các resource riêng cho release mới:

```text
random_password.hi_medium_db
random_password.hi_medium_agent
google_sql_database_instance.hi_medium
google_sql_database.hi_medium
google_sql_user.hi_medium_app
```

Instance mới giữ các chính sách đang dùng:

- PostgreSQL 16;
- `edition = "ENTERPRISE"` được khai báo tường minh;
- cùng region với VM;
- SSD;
- `disk_autoresize = true`, với giới hạn 100 GB cho bản demo hoặc 300 GB cho bản toàn bộ;
- backup tự động, PITR và giữ 7 backup;
- bảo vệ xóa ở cả Terraform và Cloud SQL API;
- chỉ cho IP tĩnh của VM truy cập;
- `ssl_mode = "ENCRYPTED_ONLY"`;
- Query Insights bật.

Phải đặt `edition = "ENTERPRISE"`: PostgreSQL 16 hiện mặc định sang Enterprise Plus nếu bỏ trống,
trong khi tier `db-custom-*` ở bảng trên thuộc Enterprise. Bỏ edition có thể làm lệnh tạo instance
thất bại vì tier không hợp lệ. Xem
[Cloud SQL editions](https://docs.cloud.google.com/sql/docs/postgres/editions-intro).

Trong resource mới, thêm:

```hcl
lifecycle {
  ignore_changes = [settings[0].disk_size]
}
```

Cloud SQL có thể tăng đĩa bằng autoresize nhưng không giảm được. Nếu không bỏ qua thay đổi
`disk_size`, một lần `terraform plan` sau khi đĩa tự tăng có thể đề xuất thay instance để đưa nó về
giá trị cũ trong file cấu hình.

Thêm output riêng:

```text
hi_medium_db_connection_name
hi_medium_db_public_ip
hi_medium_database_url       (sensitive)
hi_medium_monitoring_pg_dsn  (sensitive)
hi_medium_db_password        (sensitive)
hi_medium_agent_database_url (sensitive)
hi_medium_agent_password     (sensitive)
```

Không nâng đồng thời phiên bản provider Terraform trong đợt chuyển database. Giữ bản đang khóa,
chạy `terraform validate`, rồi nâng provider trong một thay đổi riêng sau demo.

### 12.5 Quy trình Terraform an toàn

```bash
cd infra/terraform
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan-hi-medium
```

Đọc plan. Kết quả hợp lệ phải:

- chỉ **thêm** instance, database, user, password và output mới;
- không destroy hoặc replace `google_sql_database_instance.main`;
- không đổi IP của VM;
- không đổi firewall production.

Nếu có bất kỳ dòng `destroy` hoặc `replace` đối với instance hiện tại, dừng lại và sửa resource
address/state trước khi apply.

Khi plan sạch:

```bash
terraform apply tfplan-hi-medium
```

Terraform state chứa mật khẩu chữ thường. Không commit `terraform.tfstate`, `terraform.tfvars`,
`tfplan-hi-medium` hoặc output nhạy cảm.

### 12.6 Khởi tạo Cloud SQL mới

Cloud SQL chỉ cho IP tĩnh của VM kết nối, vì vậy migration và bulk load nên chạy **trên VM GCP**,
không chạy từ laptop. Trước khi chuyển artifact lên VM, kiểm tra đĩa:

```bash
df -h
docker system df
```

Với đường test split, VM nên còn ít nhất **30–40 GB trống** cho raw CSV, DuckDB, score parquet,
file trung gian và Docker. Nếu không đủ, tăng persistent disk của VM hoặc dùng một bucket GCS làm
kho trung chuyển; không mở tạm Cloud SQL cho mọi IP.

Cloud SQL không tự chạy `db/init/*` như container PostgreSQL. Trên máy đang giữ Terraform state,
lấy output nhạy cảm và chuyển nó vào file `.env.hi-medium` trên VM bằng một kênh bảo mật. File này
không được commit và phải có quyền `600`.

Trên VM:

```bash
chmod 600 .env.hi-medium
set -a
source .env.hi-medium
set +a
DATABASE_URL="$HI_MEDIUM_DATABASE_URL" python scripts/migrate.py
```

Không ghi URL vào log hoặc commit vào file. Sau migration, tạo vai trò `fin07_agent` theo
`infra/terraform/README.md` và chạy bài kiểm tra cách ly agent.

Sau đó chạy bộ nạp release với `--dry-run`, nạp thật, `ANALYZE` các bảng lớn và đo lại:

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT count(*) FROM transaction;
SELECT count(*) FROM transaction_model_score;
SELECT count(*) FROM alert;
```

Trong lúc import, theo dõi dung lượng và CPU:

```bash
gcloud sql instances describe fin07-hi-medium-v1 \
  --format='yaml(settings.tier,settings.dataDiskSizeGb,settings.storageAutoResize)'
```

### 12.7 Chuyển VM sang Cloud SQL mới

Chỉ cutover sau khi mục 13 đạt toàn bộ:

1. lưu lại `DATABASE_URL` và `MONITORING_PG_DSN` cũ ở nơi bí mật;
2. cập nhật `.env` trên VM bằng output của instance mới;
3. giữ `USE_CLOUD_SQL=true`;
4. restart API, worker, web và postgres-exporter;
5. chạy health check và user flow demo;
6. nếu lỗi, khôi phục hai URL cũ và restart lại service.

Không cần thay VM, IP tĩnh hoặc DNS. Chỉ chuỗi kết nối database thay đổi.

### 12.8 Khi nào được xóa Cloud SQL cũ?

Không xóa ngay sau cutover. Giữ instance cũ trong ít nhất suốt thời gian kiểm thử và buổi demo.
Chỉ gỡ khi:

- release mới đã chạy ổn định;
- có dump và checksum của cả database cũ lẫn mới;
- rollback không còn cần thiết;
- đã cập nhật tài liệu vận hành;
- đã xác nhận chi phí hai instance không còn cần duy trì.

Cloud SQL có hai lớp bảo vệ xóa: thuộc tính Terraform và cờ bảo vệ ở API. Terraform Registry cũng
khuyến nghị bật deletion protection; xem
[`google_sql_database_instance`](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance).

### 12.9 Dự trù chi phí

Trong thời gian chuyển đổi sẽ có hai Cloud SQL cùng tồn tại, nên chi phí database tạm thời tăng gần
gấp đôi phần instance cũ, cộng thêm tier và đĩa lớn hơn của instance mới. Trước khi apply:

1. nhập đúng region, tier và SSD vào Google Cloud Pricing Calculator;
2. cộng chi phí backup/PITR và dung lượng tăng tự động;
3. đặt cảnh báo ngân sách ở 50%, 80% và 100%;
4. đặt ngày đánh giá để dừng hoặc xóa instance cũ sau khi hết nhu cầu rollback.

Không ghi một con số USD cố định vào kế hoạch vì giá phụ thuộc region và thay đổi theo thời điểm.
Sau demo có thể dừng instance cũ để giảm chi phí compute, nhưng storage vẫn tiếp tục tính phí cho
tới khi instance bị xóa.

---

## 13. Kiểm thử staging

Kiểm database:

```sql
SELECT release_id, model_version, dataset, status, transaction_rows,
       triggered_rows, threshold
FROM edge_model_release
ORDER BY created_at DESC;

SELECT count(*) FROM transaction;
SELECT count(*) FROM transaction_model_score;
SELECT count(*) FROM alert WHERE detector = 'ml';
SELECT count(*)
FROM alert a
LEFT JOIN alert_reason r USING (alert_id)
WHERE a.detector = 'ml'
GROUP BY a.alert_id
HAVING count(r.factor_code) < 3;
```

Truy vấn cuối phải trả về 0 dòng.

Kiểm giao diện:

1. Dashboard hiện đúng active release.
2. Trang Models hiện benchmark 5 seed.
3. Transactions có model score và bộ lọc hoạt động.
4. Alerts có cảnh báo mới từ MEGA-PNA.
5. Mở một cảnh báo thấy tối thiểu ba lý do.
6. Tạo vụ việc và chạy tác tử điều tra được.
7. World, Network và Data Quality không lỗi.

Chạy smoke test API và test phân quyền trước khi phát hành.

---

## 14. Đưa staging lên production

Quy trình phát hành:

1. Backup production hiện tại và kiểm checksum bản backup.
2. Đóng băng thao tác ghi trong thời gian chuyển đổi.
3. Xác nhận Cloud SQL HI-Medium candidate đã nạp xong migration, transactions, scores và alerts.
4. Chạy lại toàn bộ kiểm tra ở mục 13 lần cuối.
5. Đổi `DATABASE_URL` và `MONITORING_PG_DSN` của VM sang instance mới.
6. Restart service và chạy health check.
7. Giữ database cũ ở trạng thái chỉ đọc cho tới khi demo hoàn tất.

Không ghi đè trực tiếp database đang chạy nếu chưa có bản backup phục hồi được.

Sau khi production ổn định, tạo PostgreSQL dump mới, file SHA-256 và cập nhật README bằng đúng số
dòng của release mới.

---

## 15. Rollback

Rollback khi xảy ra một trong các trường hợp:

- số score không khớp số giao dịch test đã nạp;
- active release không duy nhất;
- cảnh báo thiếu lý do;
- API trả lỗi ở các màn chính;
- model score nằm ngoài `[0, 1]`;
- benchmark hiển thị khác file đã khóa;
- latency hoặc dung lượng database vượt giới hạn demo.

Cách rollback an toàn nhất là đổi kết nối API về database cũ. Không cố sửa hàng triệu dòng ngay
trên database release lỗi.

---

## 16. Production demo và production thời gian thực khác nhau

Kế hoạch trên đủ để demo một release batch trên HI-Medium: dữ liệu đã có sẵn, GPU chấm điểm, rồi
điểm được nạp vào PostgreSQL.

Nó **chưa** phải pipeline chấm giao dịch ngân hàng mới theo thời gian thực. Muốn làm mức đó cần thêm:

- formatter không có cột nhãn;
- cơ chế cấp ID ổn định cho tài khoản và cạnh mới;
- graph state/window chỉ dùng dữ liệu quá khứ;
- chuẩn hóa đặc trưng được fit từ train và lưu trong checkpoint;
- batch hoặc streaming inference service;
- giám sát drift, latency và tỷ lệ cảnh báo;
- quy trình shadow/canary trước khi thay release.

Code hiện tại còn khóa checkpoint vào đúng split của dataset và `infer_mega_pna.py` chỉ chấm tập
test đã giữ lại. Vì vậy không được tuyên bố mô hình đã hỗ trợ giao dịch live chỉ vì file `.pt` đã
được copy lên server.

Đối với buổi demo, chọn production batch là đủ, rõ ràng và ít rủi ro hơn.

---

## 17. Nội dung trình bày với mentor

Chỉ cần bốn slide:

1. **Dữ liệu và giao thức:** HI-Medium, chia theo thời gian, 5 seed.
2. **Kết quả:** F1, precision, recall, PR-AUC và độ lệch chuẩn.
3. **Khả năng vận hành:** alert budget và số cảnh báo thực tế trên console.
4. **Bằng chứng production:** release ID, model SHA-256, ảnh trang Models/Alerts/Transactions.

Không lấy accuracy làm tiêu đề. Không trộn kết quả của mô hình khác. Không gọi test predictions là
dữ liệu live.

---

## 18. Checklist thực hiện

### Môi trường GCP — hoàn thành ngày 17/08/2026

- [x] Chuẩn bị môi trường GCP riêng cho HI-Medium.
- [x] Tạo `fin07-hi-medium-v1`: PostgreSQL 16 Enterprise, `db-custom-2-7680`, SSD 50 GB,
  autoresize tối đa 100 GB, backup, PITR và bảo vệ xóa.
- [x] Áp đủ migration `001`–`021` và tạo role `fin07_agent`.
- [x] Kiểm tra role agent: đọc được schema `agent`, bị chặn schema `label`, bảng `public` và quyền ghi.
- [x] Tăng boot disk `fin07-vm` từ 30 GB lên 100 GB; còn khoảng 82 GB trống sau khi mở rộng.
- [x] Xác nhận API, web, worker và hệ thống quan sát vẫn chạy sau khi nâng đĩa.
- [x] Giữ VM và Cloud SQL cũ làm rollback; chưa xóa vì production hiện vẫn đang dùng chúng.

### Môi trường AWS GPU — hoàn thành ngày 17/08/2026

- [x] Tạo EC2 `fin07-hi-medium-gpu` tại `us-east-1a` bằng Terraform.
- [x] Dùng `g6e.2xlarge`: 8 vCPU, 64 GiB RAM và NVIDIA L40S khoảng 46 GiB VRAM.
- [x] Dùng Deep Learning PyTorch AMI Ubuntu 22.04 và gp3 mã hóa 200 GB.
- [x] Chỉ mở SSH từ một IP `/32`, dùng public key hiện có và bật chống terminate nhầm.
- [x] Dựng image `fin07-mega-pna:cuda118`; container nhận CUDA 11.8 và GPU L40S.
- [x] Chạy `tests/test_mega_pna`: 4 bài qua.
- [x] Chuyển đúng CSV + manifest HI-Medium lên EC2 và đối chiếu SHA-256 thành công.
- [x] Tạo alarm `fin07-hi-medium-gpu-idle-stop`, tự dừng sau 6 giờ CPU không quá 1%.

### Trước khi thuê GPU

- [ ] Thêm suite `hi-medium` chạy độc lập.
- [ ] Viết tiêu chí nghiệm thu và test cho suite mới.
- [ ] Viết manifest SHA-256 cho artifact.
- [ ] Viết hoặc hoàn thành `load_mega_pna_release.py`.
- [x] Đo dung lượng và tier của Cloud SQL hiện tại.
- [x] Thêm Cloud SQL HI-Medium song song vào Terraform.
- [x] `terraform plan` không destroy/replace instance hiện tại (`0 change, 0 destroy`).
- [x] Chuẩn bị staging sạch và phương án rollback.

### Trên GPU

- [x] Kiểm checksum dữ liệu format.
- [ ] Chạy smoke 2 epoch.
- [ ] Chạy đủ 5 seed × 80 epoch.
- [ ] Kiểm đủ checkpoint, predictions và report.
- [ ] Chạy inference tái lập checkpoint được chọn.
- [ ] Sinh SHA-256 trước khi tải về.

### Sau khi tải về

- [ ] Kiểm checksum local.
- [ ] Chọn seed bằng validation.
- [ ] Dựng DuckDB và release score.
- [x] Tạo Cloud SQL mới với đĩa 50 GB cho test split.
- [x] Chạy migration và kiểm cách ly `fin07_agent` trên instance mới.
- [ ] Dry-run bộ nạp.
- [ ] Nạp staging và kiểm console.
- [ ] Backup production.
- [ ] Cutover VM bằng cách đổi `DATABASE_URL` và `MONITORING_PG_DSN`.
- [ ] Smoke test và lưu bằng chứng demo.
- [ ] Giữ Cloud SQL cũ để rollback qua hết buổi demo.
- [ ] Tắt máy GPU.

---

## 19. Kết luận

Máy GPU trả về **mô hình, điểm dự đoán và báo cáo benchmark**. Sau khi tải các artifact đó về, còn
phải chuyển điểm sang định dạng release, nạp dữ liệu vào PostgreSQL, sinh cảnh báo và kích hoạt
release thì console mới thực sự dùng mô hình mới.

Với hạ tầng GCP hiện có, không cần tạo lại VM. Tạo một Cloud SQL HI-Medium mới bằng Terraform,
nạp và kiểm thử song song, rồi đổi chuỗi kết nối của VM. Cách này dự trù đủ dung lượng mà vẫn giữ
nguyên đường rollback về release cũ.

Đường ngắn nhất cho dự án hiện tại là:

> **HI-Medium 5 seed → chọn checkpoint bằng validation → phục vụ tập test theo batch → dựng lại
> production từ release đã kiểm trên staging.**

Đó là đủ để có benchmark mạnh, demo được đầu-cuối và không phải giả vờ rằng hệ thống đã hỗ trợ
suy luận giao dịch thời gian thực khi phần đó chưa được xây dựng.
