# Biến đầu vào. Giá trị thật đặt trong terraform.tfvars — file đó KHÔNG commit.
# Xem terraform.tfvars.example.

variable "project_id" {
  description = "ID dự án GCP (không phải tên hiển thị)"
  type        = string
}

variable "region" {
  description = "Vùng đặt IP tĩnh và Cloud SQL. Phải cùng vùng với VM, nếu không IP không gán được."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone của VM đang chạy. Chỉ dùng để tra cứu VM, không tạo mới."
  type        = string
  default     = "us-central1-a"
}

variable "vm_name" {
  description = "Tên VM đã tồn tại, dựng bằng tay trước khi có Terraform"
  type        = string
}

variable "site_domain" {
  description = "Tên miền trỏ về VM. Dùng để nhắc trong output, Terraform không quản lý DNS."
  type        = string
  default     = "amlmonitoring.site"
}

# ---- Cloud SQL ------------------------------------------------------

variable "db_tier" {
  description = <<-EOT
    Cấu hình máy của Cloud SQL. db-f1-micro là bậc chia sẻ CPU, rẻ nhất, đủ cho
    dữ liệu vụ việc và cảnh báo — thứ nằm ở đây tính bằng nghìn dòng, không phải
    triệu. Giao dịch thô KHÔNG lưu ở đây (xem docs/architecture/PRODUCTION_ARCHITECTURE.md
    mục 8), nên đừng chọn bậc lớn vì sợ dữ liệu nhiều.
  EOT
  type        = string
  default     = "db-f1-micro"
}

variable "db_version" {
  description = "Phải khớp phiên bản đang chạy trong container: postgres:16-alpine"
  type        = string
  default     = "POSTGRES_16"
}

variable "db_name" {
  description = "Tên database. Giữ đúng tên đang dùng để không phải sửa chuỗi kết nối ở nơi khác."
  type        = string
  default     = "fin07"
}

variable "db_user" {
  description = "Tài khoản ứng dụng. Vai trò chỉ đọc của agent do db/init/003 tạo, không tạo ở đây."
  type        = string
  default     = "fin07"
}

variable "db_disk_size_gb" {
  description = "Dung lượng khởi điểm. Cloud SQL tự nới thêm khi cần (autoresize)."
  type        = number
  default     = 10
}

variable "db_backup_start_time" {
  description = "Giờ bắt đầu sao lưu, UTC. Mặc định 17:00 UTC = 0:00 giờ Việt Nam."
  type        = string
  default     = "17:00"
}

variable "db_deletion_protection" {
  description = <<-EOT
    Chặn xoá nhầm instance. Để `true` ở mọi lúc trừ khi đang cố ý gỡ bỏ.
    Muốn `terraform destroy` chạy được thì phải đặt `false` và `apply` một lần
    TRƯỚC, rồi mới destroy — đây là hai bước có chủ ý, không phải phiền phức.
  EOT
  type        = bool
  default     = true
}
