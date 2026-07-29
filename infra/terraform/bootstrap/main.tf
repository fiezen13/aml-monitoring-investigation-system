// Bootstrap cho state từ xa.
//
// Con gà và quả trứng: Terraform muốn lưu state vào S3, nhưng bucket S3 đó
// phải tồn tại trước khi Terraform chạy được. Cách giải quyết chuẩn là một
// stack nhỏ riêng, dùng state cục bộ, chỉ tạo đúng chỗ chứa state cho stack
// chính. Stack này chạy một lần rồi gần như không đụng tới nữa.
//
//   cd infra/terraform/bootstrap
//   terraform init && terraform apply
//   # chép tên bucket in ra vào khối backend ở ../versions.tf
//   cd .. && terraform init -migrate-state
//
// Khi nào cần: lúc có người thứ hai chạy terraform. State cục bộ nghĩa là hai
// người apply song song sẽ ghi đè hạ tầng của nhau mà không ai biết.
//
// Lưu ý quyền: IAM user chạy stack này cần quyền S3, mà AmazonEC2FullAccess
// không có. Gắn thêm AmazonS3FullAccess hoặc một policy hẹp hơn.

terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "FIN-07"
      ManagedBy = "terraform-bootstrap"
      Purpose   = "terraform-state"
    }
  }
}

variable "aws_profile" {
  type    = string
  default = "default"
}

variable "region" {
  type    = string
  default = "ap-southeast-1"
}

// Tên bucket S3 phải duy nhất trên toàn cầu, nên thêm hậu tố ngẫu nhiên.
resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "tfstate" {
  bucket = "fin07-tfstate-${random_id.suffix.hex}"

  // Chặn xoá nhầm: mất bucket state nghĩa là Terraform quên sạch những gì nó
  // đang quản, và phải import lại từng tài nguyên bằng tay.
  lifecycle {
    prevent_destroy = true
  }
}

// Bật phiên bản để lỡ ghi hỏng state còn quay lại được.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

// State chứa thông tin nhạy cảm về hạ tầng. Không có lý do gì để nó công khai.
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_name" {
  description = "Điền tên này vào khối backend ở ../versions.tf"
  value       = aws_s3_bucket.tfstate.bucket
}

output "backend_config" {
  description = "Dán nguyên khối này vào ../versions.tf"
  value       = <<-EOT
    backend "s3" {
      bucket       = "${aws_s3_bucket.tfstate.bucket}"
      key          = "ci/terraform.tfstate"
      region       = "${var.region}"
      encrypt      = true
      use_lockfile = true
    }
  EOT
}
