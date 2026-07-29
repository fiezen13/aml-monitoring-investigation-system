provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Gắn nhãn cho mọi tài nguyên. Không có nhãn thì ba tháng nữa nhìn hoá đơn
  # AWS sẽ không ai biết máy nào của dự án nào, và cũng không xoá dọn được
  # bằng một lệnh lọc.
  default_tags {
    tags = {
      Project     = "FIN-07"
      Environment = "ci"
      ManagedBy   = "terraform"
      Repository  = "AI20K-Build-Phase-Cohort-3/P-022"
    }
  }
}
