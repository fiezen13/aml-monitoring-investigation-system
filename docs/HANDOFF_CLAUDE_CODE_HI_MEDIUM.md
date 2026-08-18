# Handoff cho Claude Code — MEGA-PNA HI-Medium

> Cập nhật: 17/08/2026, Asia/Ho_Chi_Minh  
> Mục tiêu: hoàn thành benchmark HI-Medium độc lập, lấy artifact từ EC2 GPU, nạp release vào Cloud
> SQL mới và cutover production có rollback. Không dùng hoặc so sánh với dataset khác.

## 1. Việc cần làm ngay

EC2 GPU đang **running** và tính phí khoảng **2,24208 USD/giờ** cho compute, chưa gồm EBS.
Không để máy idle trong khi đọc tài liệu hoặc sửa code lâu.

```bash
export AWS_REGION=us-east-1
aws ec2 describe-instances \
  --instance-ids i-0592158c0876d3ac4 \
  --query 'Reservations[0].Instances[0].{State:State.Name,IP:PublicIpAddress}'
```

Nếu chưa bắt đầu smoke/training ngay, dừng máy:

```bash
aws ec2 stop-instances --instance-ids i-0592158c0876d3ac4 --region us-east-1
aws ec2 wait instance-stopped --instance-ids i-0592158c0876d3ac4 --region us-east-1
```

Sau stop/start, public IP có thể đổi. Lấy IP mới bằng AWS CLI rồi cập nhật lệnh SSH. Security group
chỉ cho IP người vận hành hiện tại; nếu IP nhà đổi, sửa
`infra/terraform/gpu/terraform.tfvars:allowed_ssh_cidr` và apply lại Terraform.

## 2. Trạng thái hạ tầng đã hoàn thành

### AWS GPU

| Mục | Giá trị |
|---|---|
| Instance ID | `i-0592158c0876d3ac4` |
| Tên | `fin07-hi-medium-gpu` |
| Region/AZ | `us-east-1` / `us-east-1a` |
| Instance type | `g6e.2xlarge`, On-Demand |
| GPU | NVIDIA L40S, 46.068 MiB VRAM |
| RAM | 64 GiB danh nghĩa, Linux thấy khoảng 61 GiB |
| Root disk | gp3 mã hóa 200 GB; lần kiểm cuối còn khoảng 152 GB |
| AMI | `ami-012ba162b9cd2729c`, Deep Learning PyTorch Ubuntu 22.04 |
| Security group | `sg-070f66962bb9aa9d1`, SSH duy nhất một CIDR `/32` |
| Termination protection | bật |
| Idle alarm | `fin07-hi-medium-gpu-idle-stop`: CPU ≤ 1% liên tục 6 giờ thì stop |
| Terraform | `infra/terraform/gpu/` |

Public IP tại thời điểm handoff là `3.231.162.199`:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@3.231.162.199
```

Không có private key mới trong repo. EC2 dùng public key tương ứng với `~/.ssh/id_ed25519`.

Trên EC2:

- workspace: `/workspace/P-022`;
- image: `fin07-mega-pna:cuda118`;
- image ID: `sha256:d446951ca8d5bbad0f72cb93826cac911ba926f60234873e157b9cc2d88d3ca2`;
- PyTorch `2.2.2`, CUDA `11.8`;
- `torch-sparse 0.6.18+pt22cu118`, `torch-geometric 2.5.2`;
- container đã nhận đúng GPU L40S;
- `tests/test_mega_pna`: **4 passed**.

Dữ liệu đã nằm trên EC2:

```text
/workspace/P-022/data/processed/mega-pna/Medium_HI/formatted_transactions.csv
/workspace/P-022/data/processed/mega-pna/Medium_HI/formatted_transactions.manifest.json
```

Thông số đã xác nhận:

```text
rows:           31,898,238
positives:      35,230
self_transfers: 2,561,860
CSV SHA-256:    bfbd8847a3215826360dad60b9ef930308d5929c1725b846d43dd5547de9995e
```

### GCP staging

- VM production cũ: `fin07-vm`, vẫn đang phục vụ hệ thống; boot disk đã tăng lên 100 GB.
- Cloud SQL cũ: `fin07-postgres-sg`; production hiện vẫn dùng, phải giữ làm rollback.
- Cloud SQL mới: `fin07-hi-medium-v1`, PostgreSQL 16 Enterprise, `db-custom-2-7680`, SSD 50 GB,
  autoresize tối đa 100 GB, backup + PITR + deletion protection.
- Instance mới đã áp migration `001`–`021`.
- Role `fin07_agent` đã tạo và đã kiểm: đọc được schema `agent`, không đọc được `label`/`public`,
  không ghi được.
- Terraform GCP cuối cùng báo `No changes`.

Không xóa VM hoặc Cloud SQL cũ trước khi release mới đã nạp, cutover và qua smoke test production.

## 3. Blocker hiện tại trong code

Hạ tầng/runtime/data đã đủ để chạy **smoke 2 epoch**, nhưng chưa được phép chạy job 5 seed chính
thức vì `scripts/benchmark_mega_pna.py` chưa có suite HI-Medium độc lập.

Hiện tại:

```python
choices=("gate", "medium", "all", "summarize")
```

`--suite medium` vẫn gọi `write_summary()` cho `Small_HI`/`Small_LI` và chặn Medium_HI nếu small
gate chưa đạt. Điều này trái yêu cầu hiện tại: **chỉ HI-Medium, không chạy và không tạo báo cáo cho
dataset khác**.

## 4. Thứ tự công việc bắt buộc

### A. Thêm suite `hi-medium` độc lập

Sửa `scripts/benchmark_mega_pna.py` để lệnh sau chạy được:

```bash
python scripts/benchmark_mega_pna.py \
  --suite hi-medium \
  --device cuda \
  --seeds 42 43 44 45 46 \
  --epochs 80
```

Suite phải:

1. chỉ chạy `Medium_HI`;
2. bắt buộc đúng 5 seed;
3. không kiểm hoặc ghi dòng `Small_HI`/`Small_LI`;
4. tổng hợp F1, precision, recall và PR-AUC;
5. ghi F1 thấp nhất và số seed hoàn tất;
6. trả exit code khác 0 nếu thiếu seed hoặc không đạt gate;
7. tái sử dụng seed đã hoàn tất nếu `epochs` và `batch_size` khớp;
8. có test cho CLI, danh sách dataset, gate đạt và gate thất bại.

Gate release trong `docs/KE_HOACH_HI_MEDIUM.md`:

| Chỉ số | Điều kiện |
|---|---:|
| F1 trung bình 5 seed | ≥ 0,75 |
| F1 thấp nhất | ≥ 0,73 |
| Độ lệch chuẩn F1 | ≤ 0,01 |
| Precision trung bình | ≥ 0,70 |
| Recall trung bình | ≥ 0,70 |
| Seed hoàn tất | 5/5 |

Không chọn seed theo test. Chọn seed có validation F1 cao nhất; nếu hòa thì chọn seed nhỏ hơn.

### B. Test local rồi đồng bộ code lên EC2

Không chép `.env`, Terraform state hoặc credentials lên EC2.

```bash
python -m pytest tests/test_mega_pna -q

rsync -az \
  -e 'ssh -i ~/.ssh/id_ed25519' \
  scripts src tests docker requirements-mega-pna-cuda118.txt \
  ubuntu@<CURRENT_GPU_IP>:/workspace/P-022/
```

Sau khi code đổi, rebuild image:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<CURRENT_GPU_IP>
cd /workspace/P-022
docker build -f docker/mega-pna/Dockerfile -t fin07-mega-pna:cuda118 .
```

### C. Chạy smoke 2 epoch trước

```bash
cd /workspace/P-022

docker run --rm --name fin07-hi-medium-smoke --gpus all \
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

Theo dõi ở SSH session khác:

```bash
watch -n 2 nvidia-smi
free -h
df -h /
```

Chỉ chạy chính thức nếu:

- load đủ dataset, không bị Linux `Killed`;
- không CUDA OOM;
- loss hữu hạn;
- train/validation F1 được ghi;
- GPU utilization khác 0;
- sinh đủ `.pt`, `.parquet`, `.json`;
- ghi lại thời gian mỗi epoch và ước tính thời gian/chi phí 5 seed.

Máy hiện không có swap. Nếu bị `Killed` do RAM, không âm thầm giảm dữ liệu. Ghi bằng chứng, dừng
job và chọn giải pháp hạ tầng phù hợp trước khi chạy lại.

### D. Chạy 5 seed × 80 epoch

Sau khi smoke đạt, chuyển/xóa riêng thư mục smoke để không lẫn artifact. Sau đó:

```bash
cd /workspace/P-022

docker run -d --name fin07-hi-medium --gpus all \
  --restart no \
  -v "$PWD/data:/workspace/data" \
  -v "$PWD/models:/workspace/models" \
  -v "$PWD/reports:/workspace/reports" \
  fin07-mega-pna:cuda118 \
  --suite hi-medium \
  --device cuda \
  --seeds 42 43 44 45 46 \
  --epochs 80

docker logs -f fin07-hi-medium
```

Không đổi neighbor, layer hoặc epoch giữa các seed. Nếu phải đổi batch size vì OOM, ghi rõ vào
report và dùng cùng một batch size cho cả 5 seed.

### E. Khóa và tải artifact về

Kết quả phải có:

```text
models/mega-pna/Medium_HI/paper/seed_{42..46}.pt
models/mega-pna/Medium_HI/paper/seed_{42..46}_test.parquet
reports/mega-pna/Medium_HI/paper/seed_{42..46}.json
reports/mega-pna/benchmark.json
```

Sinh manifest chứa đường dẫn, kích thước và SHA-256 của 5 checkpoint, 5 predictions, 5 report,
`benchmark.json`, CSV format và manifest dữ liệu. Không chỉ sinh một file checksum không có size.

Tải về bằng `rsync -avP`, kiểm checksum trên local, rồi sao lưu artifact ở nơi thứ hai. Chỉ sau đó
mới stop EC2.

### F. Production release

Phần này chưa được viết:

- `scripts/load_mega_pna_release.py`;
- dry-run kiểm checksum/count/positive/threshold;
- dựng DuckDB và release score;
- nạp transaction test, score, alert, ít nhất 3 `alert_reason` mỗi alert;
- ghi và kích hoạt `edge_model_release` theo transaction;
- staging UI/API smoke;
- backup production;
- đổi `DATABASE_URL` và `MONITORING_PG_DSN` sang Cloud SQL mới;
- rollback về database cũ nếu kiểm thử thất bại.

Không cutover chỉ vì đã có checkpoint. `infer_mega_pna.py` hiện chỉ chấm split test; đây là
production batch cho demo, chưa phải inference giao dịch live.

## 5. Kiểm tra Terraform

AWS:

```bash
cd infra/terraform/gpu
set -a; source ../../../.env; set +a
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
terraform validate
terraform plan -detailed-exitcode
```

GCP:

```bash
cd infra/terraform
terraform validate
terraform plan -detailed-exitcode
```

Không commit:

- `.env`;
- `terraform.tfvars`;
- `terraform.tfstate*`;
- `tfplan*`;
- database URL/password;
- private SSH key;
- file prediction/data lớn.

## 6. Trạng thái Git và phạm vi thay đổi

Working tree đang có thay đổi chưa commit từ việc chuẩn bị GCP/AWS và viết kế hoạch. Không dùng
`git reset --hard`, không checkout đè và không xóa thay đổi ngoài phạm vi.

Các file hạ tầng/tài liệu liên quan:

```text
docs/KE_HOACH_HI_MEDIUM.md
docs/HUONG_DAN_DUNG_LAI_MODEL.md
infra/terraform/database.tf
infra/terraform/database_hi_medium.tf
infra/terraform/outputs.tf
infra/terraform/variables.tf
infra/terraform/terraform.tfvars.example
infra/terraform/gpu/*
.gitignore
```

Các file `reports/edge-benchmark/li_small*` đang untracked và không thuộc việc handoff này; không
xóa hoặc sửa chúng nếu chưa được người dùng yêu cầu.

## 7. Điều kiện hoàn tất toàn bộ handoff

- [ ] Suite `hi-medium` độc lập và test qua.
- [ ] Smoke 2 epoch qua trên EC2.
- [ ] 5/5 seed × 80 epoch hoàn tất.
- [ ] Benchmark đạt toàn bộ gate mục 4A.
- [ ] Artifact manifest và checksum hợp lệ sau khi tải về.
- [ ] Chọn checkpoint bằng validation, không chọn bằng test.
- [ ] Loader dry-run qua trên Cloud SQL HI-Medium.
- [ ] Nạp staging và UI/API smoke qua.
- [ ] Backup production và cutover có rollback.
- [ ] Giữ Cloud SQL cũ qua hết demo.
- [ ] Stop EC2 GPU và xác nhận trạng thái `stopped`.
