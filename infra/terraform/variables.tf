variable "aws_profile" {
  description = "Profile trong ~/.aws/credentials dùng để chạy terraform"
  type        = string
  default     = "default"
}

variable "region" {
  description = "Vùng AWS. ap-southeast-1 (Singapore) gần Việt Nam nhất."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Tiền tố tên cho mọi tài nguyên"
  type        = string
  default     = "fin07"
}

variable "instance_type" {
  description = <<-EOT
    Loại máy. t3.large = 2 vCPU, 8 GB.

    t3.medium (4 GB) chạy được nhưng chật: Jenkins là một JVM, build image
    langchain khá nặng, cộng thêm hai môi trường mỗi cái năm container.
  EOT
  type        = string
  default     = "t3.large"
}

variable "root_volume_gb" {
  description = "Dung lượng đĩa gốc, GB. Image của dự án chiếm chỗ nhanh."
  type        = number
  default     = 50

  validation {
    condition     = var.root_volume_gb >= 30
    error_message = "Dưới 30 GB thì hết đĩa giữa chừng khi build image."
  }
}

variable "allowed_cidr_blocks" {
  description = <<-EOT
    Dải IP được phép vào máy. Bắt buộc phải khai báo tường minh.

    Không có giá trị mặc định là có chủ ý: nếu để mặc định 0.0.0.0/0 thì sớm
    muộn cũng có người apply mà quên sửa, và một Jenkins phơi ra Internet sẽ
    bị dò mật khẩu trong vài giờ.
  EOT
  type        = list(string)

  validation {
    condition     = !contains(var.allowed_cidr_blocks, "0.0.0.0/0")
    error_message = "Không được mở cho toàn Internet. Dùng <IP của bạn>/32."
  }
}

variable "ssh_public_key_path" {
  description = "Đường dẫn tới khoá SSH công khai sẽ nạp vào máy"
  type        = string
  default     = "~/Downloads/fin07_ci.pub"
}

variable "service_ports" {
  description = <<-EOT
    Cổng mở vào máy, kèm lý do. Đổi cổng ở đây thì security group đổi theo.

    Staging và production-like dùng cổng khác nhau vì chúng chạy song song
    trên cùng một máy (xem docs/CICD.md mục 5).

    Mô tả viết KHÔNG DẤU: AWS từ chối mọi ký tự ngoài ASCII trong mô tả của
    security group và của từng quy tắc.
  EOT
  type        = map(string)
  default = {
    22   = "SSH"
    8080 = "Giao dien Jenkins"
    8000 = "API staging"
    5173 = "Console staging"
    8001 = "API production-like"
    5174 = "Console production-like"
  }

  validation {
    condition     = alltrue([for d in values(var.service_ports) : can(regex("^[[:ascii:]]+$", d))])
    error_message = "Mô tả cổng phải là ASCII thuần — AWS từ chối ký tự có dấu."
  }
}
