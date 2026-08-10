# Ghim phiên bản. Không ghim thì hai người chạy `terraform apply` cách nhau
# một tháng có thể nhận hai kế hoạch khác nhau trên cùng một file mã nguồn.
#
# Provider google 5.x là bản đầu tiên có `ssl_mode` cho Cloud SQL; bản cũ hơn
# chỉ có `require_ssl` đã bị khai tử.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State mặc định nằm ở máy đang chạy lệnh. Điều đó chấp nhận được khi chỉ
  # một người áp, nhưng KHÔNG ổn khi hai người cùng làm: state là nguồn sự
  # thật về những gì đang tồn tại, và hai bản state rời nhau sẽ dựng ra hai
  # bộ tài nguyên trùng lặp.
  #
  # Khi có người thứ hai chạm vào hạ tầng, tạo một bucket rồi bỏ chú thích:
  #
  #   gcloud storage buckets create gs://fin07-tfstate --location=us-central1
  #   gcloud storage buckets update gs://fin07-tfstate --versioning
  #
  # backend "gcs" {
  #   bucket = "fin07-tfstate"
  #   prefix = "fin07/infra"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
