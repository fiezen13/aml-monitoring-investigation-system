# Hạ tầng CI/CD — Terraform

Dựng máy chủ chạy Jenkins, staging và production-like cho FIN-07 trên AWS.

Ranh giới có chủ ý:

| Tầng | Ai lo | Ở đâu |
|---|---|---|
| Máy, mạng, tường lửa, đĩa | Terraform | thư mục này |
| Docker, Node, công cụ dòng lệnh | cloud-init | `cloud-init.yaml` |
| Jenkins | Docker Compose | `jenkins/` |
| Môi trường ứng dụng | Docker Compose | `deploy/` |

Terraform **không** cài Jenkins. Nếu nó cài, thì Jenkins chỉ dựng được trên
AWS — mà `jenkins/` hiện chạy được trên bất kỳ máy Linux nào, kể cả máy trong
mạng nội bộ của tổ chức nhận bàn giao. Đó là điều kiện đã nêu ở
[docs/CICD.md](../../docs/CICD.md) mục 1.

## Chạy lần đầu

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Sửa `terraform.tfvars`:

- `allowed_cidr_blocks` — IP của bạn kèm `/32`, lấy bằng:

  ```bash
  curl -s https://checkip.amazonaws.com
  ```

  **Đừng dùng `ifconfig.me`.** Nhà mạng có thể đi ra bằng IP khác nhau tuỳ
  đích đến, nên hai dịch vụ trả về hai kết quả khác nhau và bạn mở cổng cho
  IP sai. Triệu chứng là SSH timeout trong khi mọi cấu hình AWS đều đúng.
  `checkip.amazonaws.com` chạy trên chính AWS nên nó thấy đúng cái AWS thấy.

- `aws_profile` — profile trong `~/.aws/credentials`

```bash
terraform init
terraform plan      # xem nó định tạo gì
terraform apply     # tạo thật, tính tiền thật
```

Xong, xem địa chỉ:

```bash
terraform output
```

## Yêu cầu về quyền AWS

IAM user chạy Terraform cần `AmazonEC2FullAccess`. Thêm `AmazonS3FullAccess`
nếu dùng state từ xa (xem `bootstrap/`).

**Đừng dùng khoá của tài khoản root.** Khoá root không giới hạn được phạm vi,
không thu hồi riêng lẻ được, và lộ ra là mất toàn bộ tài khoản. Tạo một IAM
user riêng cho việc này.

## Nó tạo ra gì

16 tài nguyên:

| Nhóm | Gồm |
|---|---|
| Mạng | VPC `10.20.0.0/16`, một subnet công khai, internet gateway, route table |
| Bảo mật | Một security group, sáu quy tắc vào (mỗi cổng một quy tắc), một quy tắc ra |
| Máy | EC2 `t3.large`, đĩa gp3 50 GB có mã hoá, cặp khoá SSH, Elastic IP |

Cổng mở, **chỉ cho IP đã khai báo**: 22 (SSH), 8080 (Jenkins), 8000 và 5173
(staging), 8001 và 5174 (production-like).

Biến `allowed_cidr_blocks` cố ý **không có giá trị mặc định**, và có kiểm tra
chặn `0.0.0.0/0`. Một Jenkins phơi ra Internet bị dò mật khẩu trong vài giờ.

## Chi phí

| | Bật 24/7 | Đã stop |
|---|---|---|
| t3.large | ~62 USD/tháng | 0 |
| Đĩa 50 GB gp3 | ~5 USD/tháng | ~5 USD/tháng |
| Elastic IP | 0 | ~4 USD/tháng |

Dừng máy khi không dùng:

```bash
aws ec2 stop-instances --instance-ids "$(terraform output -raw instance_id)"
```

```bash
aws ec2 start-instances --instance-ids "$(terraform output -raw instance_id)"
```

Elastic IP giữ nguyên qua stop/start, nên không phải sửa lại cấu hình gì.

Xoá sạch:

```bash
terraform destroy
```

## IP nhà thay đổi

Nhà mạng Việt Nam thường cấp IP động. Đổi IP là mất kết nối tới máy. Cập nhật:

```bash
curl -s ifconfig.me   # rồi sửa allowed_cidr_blocks trong terraform.tfvars
terraform apply
```

## State

Mặc định state nằm ở file cục bộ `terraform.tfstate`, đã bỏ qua trong git.

Đủ dùng khi chỉ một người chạy Terraform. Có người thứ hai thì phải chuyển
sang state từ xa, nếu không hai lượt `apply` song song sẽ ghi đè hạ tầng của
nhau mà không ai biết. Xem `bootstrap/main.tf`.

`.terraform.lock.hcl` **được commit** — nó ghim phiên bản provider, và đó là
thứ đảm bảo hai người chạy Terraform ra cùng một kết quả.

## Sau khi máy đã lên

```bash
ssh -i ~/Downloads/fin07_ci ubuntu@$(terraform output -raw public_ip)
```

Kiểm tra cloud-init đã xong chưa — có file này nghĩa là xong:

```bash
ls /opt/fin07/.provisioned
```

Chưa có mà SSH vào được thì cloud-init còn đang chạy hoặc đã hỏng:

```bash
sudo tail -50 /var/log/cloud-init-output.log
```

Rồi dựng Jenkins theo [docs/CICD.md](../../docs/CICD.md) mục 3.

## Chưa làm

- Không có HTTPS. Jenkins chạy HTTP trần, chấp nhận được vì chỉ mở cho một IP,
  nhưng trước khi có người ngoài nhóm dùng thì phải đặt sau reverse proxy có
  chứng chỉ.
- Không có sao lưu tự động. Đĩa mất là mất dữ liệu staging. Với dữ liệu tổng
  hợp sinh lại được bằng một lệnh thì chấp nhận được; với dữ liệu thật thì không.
- Một máy chạy cả Jenkins lẫn hai môi trường nó triển khai. Không đúng thực tế,
  nhưng đúng ngân sách. Tách máy thì thêm một `aws_instance` và một
  `docker context`.
