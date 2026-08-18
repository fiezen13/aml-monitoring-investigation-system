# EC2 GPU cho MEGA-PNA HI-Medium

Module này tạo đúng một máy On-Demand ở `us-east-1`, vì quota G/VT hiện là 8 vCPU và quota Spot là
0. Cấu hình mặc định là `g6e.2xlarge`, 64 GiB RAM, GPU L40S 48 GB và gp3 mã hóa 200 GB.

```bash
cd infra/terraform/gpu
terraform init
terraform plan -out=tfplan
terraform apply tfplan
terraform output -raw ssh_command
```

`terraform.tfvars` chứa IP nhà được phép SSH và bị Git bỏ qua. Khi IP thay đổi, sửa CIDR `/32` rồi
apply lại; không mở SSH bằng `0.0.0.0/0`.

Tắt máy ngay khi không huấn luyện:

```bash
aws ec2 stop-instances --instance-ids "$(terraform output -raw instance_id)" --region us-east-1
aws ec2 wait instance-stopped --instance-ids "$(terraform output -raw instance_id)" --region us-east-1
```

Máy bật lại vẫn giữ EBS và checkpoint nhưng public IP có thể đổi. Chạy `terraform refresh` hoặc
`terraform apply` để cập nhật output. API termination protection được bật để tránh xóa nhầm trước
khi tải checkpoint và báo cáo về. Alarm `fin07-hi-medium-gpu-idle-stop` sẽ dừng máy nếu CPU trung
bình không quá 1% trong sáu giờ liên tiếp; đây là hàng rào khi bị quên máy, không thay cho việc chủ
động kiểm tra và dừng EC2 sau khi tải artifact.
