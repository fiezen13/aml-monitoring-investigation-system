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

variable "db_instance_name" {
  description = <<-EOT
    Tên instance Cloud SQL.

    Cẩn thận khi đổi: Google GIỮ CHỖ tên đã xoá trong khoảng một tuần. Nghĩa là
    xoá `fin07-postgres` rồi tạo lại ngay một instance cùng tên sẽ thất bại, và
    thất bại ở giữa một lần `terraform apply` — sau khi instance cũ đã biến mất.
    Chuyển vùng, đổi phiên bản, hay bất cứ thay đổi nào buộc phải dựng lại
    instance đều phải kèm một tên mới.
  EOT
  type        = string
  default     = "fin07-postgres"
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

# ---- Cloud SQL HI-Medium -------------------------------------------
#
# Instance song song để nạp và kiểm thử release MEGA-PNA trước khi đổi
# DATABASE_URL của VM. Không tái sử dụng resource `main`: giữ instance cũ
# nguyên vẹn là đường rollback trong suốt đợt chuyển dữ liệu.

variable "hi_medium_db_instance_name" {
  description = "Tên Cloud SQL mới phục vụ release HI-Medium; phải khác instance hiện tại."
  type        = string
  default     = "fin07-hi-medium-v1"
}

variable "hi_medium_db_tier" {
  description = "Tier Enterprise cho test split HI-Medium (~5,87 triệu giao dịch)."
  type        = string
  default     = "db-custom-2-7680"
}

variable "hi_medium_db_disk_size_gb" {
  description = "Đĩa SSD khởi điểm; cấp trước khi bulk load thay vì chờ autoresize."
  type        = number
  default     = 50

  validation {
    condition     = var.hi_medium_db_disk_size_gb >= 50
    error_message = "Cloud SQL HI-Medium cần tối thiểu 50 GB cho import, index, WAL và headroom."
  }
}

variable "hi_medium_db_disk_autoresize_limit_gb" {
  description = "Trần tự tăng đĩa của Cloud SQL HI-Medium."
  type        = number
  default     = 100

  validation {
    condition     = var.hi_medium_db_disk_autoresize_limit_gb >= var.hi_medium_db_disk_size_gb
    error_message = "Trần autoresize không được nhỏ hơn dung lượng đĩa khởi điểm."
  }
}

variable "hi_medium_db_deletion_protection" {
  description = "Giữ true cho tới khi release mới ổn định và đường rollback không còn cần thiết."
  type        = bool
  default     = true
}
