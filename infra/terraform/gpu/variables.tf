variable "aws_region" {
  description = "AWS region có quota GPU đã được duyệt."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Availability Zone có g6e.2xlarge và default subnet."
  type        = string
  default     = "us-east-1a"
}

variable "instance_name" {
  description = "Tên hiển thị của máy huấn luyện."
  type        = string
  default     = "fin07-hi-medium-gpu"
}

variable "instance_type" {
  description = "g6e.2xlarge có 8 vCPU, 64 GiB RAM và một GPU L40S 48 GB."
  type        = string
  default     = "g6e.2xlarge"

  validation {
    condition     = contains(["g6e.2xlarge", "g5.2xlarge"], var.instance_type)
    error_message = "Chỉ dùng g6e.2xlarge hoặc phương án dự phòng g5.2xlarge trong plan."
  }
}

variable "ami_id" {
  description = "Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04), AWS owner 898082745236."
  type        = string
  default     = "ami-012ba162b9cd2729c"
}

variable "root_volume_size_gb" {
  description = "Dung lượng gp3 cho source, image Docker, dữ liệu và artifact huấn luyện."
  type        = number
  default     = 200

  validation {
    condition     = var.root_volume_size_gb >= 150
    error_message = "HI-Medium cần tối thiểu 150 GB disk."
  }
}

variable "allowed_ssh_cidrs" {
  description = <<-EOT
    Danh sách địa chỉ IPv4 được SSH vào máy, mỗi phần tử dạng x.x.x.x/32.

    Trước đây đây là một chuỗi duy nhất. Thực tế phá vỡ giả định ấy: nhà mạng của
    người vận hành xoay vòng giữa nhiều địa chỉ ra, quan sát được ít nhất hai địa
    chỉ khác dải nhau, và đổi ngay giữa hai kết nối liên tiếp. Với một
    ô /32, SSH lúc vào được lúc không, mà mỗi lần mất kết nối lại phải sửa hạ tầng.

    Liệt kê từng /32 vẫn giữ nguyên tinh thần ban đầu: chỉ những địa chỉ biết trước
    mới vào được cổng 22. Nó khác hẳn việc mở cả dải /16 của nhà mạng — 65 nghìn
    địa chỉ — điều đã từng phải làm tạm để chẩn đoán và đã thu hồi ngay sau đó.
  EOT
  type        = list(string)

  validation {
    condition = length(var.allowed_ssh_cidrs) > 0 && alltrue([
      for cidr in var.allowed_ssh_cidrs : can(cidrhost(cidr, 0)) && endswith(cidr, "/32")
    ])
    error_message = "allowed_ssh_cidrs phải là danh sách không rỗng gồm các IPv4 CIDR /32."
  }
}

variable "ssh_public_key_path" {
  description = "Public key hiện có; private key không đi vào Terraform state."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}
