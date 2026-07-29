terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State cục bộ là mặc định để lệnh `apply` đầu tiên không bị chặn bởi
  # chuyện con-gà-quả-trứng: bucket lưu state phải tồn tại trước khi
  # terraform chạy được.
  #
  # Khi nhiều người cùng chạy terraform thì state cục bộ hỏng: hai người
  # apply song song sẽ ghi đè hạ tầng của nhau mà không ai biết. Lúc đó
  # chuyển sang state từ xa:
  #
  #   1. cd bootstrap && terraform init && terraform apply
  #   2. bỏ chú thích khối backend bên dưới, điền tên bucket bootstrap in ra
  #   3. terraform init -migrate-state
  #
  # backend "s3" {
  #   bucket       = "fin07-tfstate-<hậu tố bootstrap in ra>"
  #   key          = "ci/terraform.tfstate"
  #   region       = "ap-southeast-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}
