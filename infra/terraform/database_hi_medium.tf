# Cloud SQL song song cho release MEGA-PNA HI-Medium.
#
# Không thay thế `google_sql_database_instance.main`. Instance cũ tiếp tục
# phục vụ cho tới khi instance này đã nạp dữ liệu, qua smoke test và VM được
# chuyển DATABASE_URL có chủ đích.

resource "random_password" "hi_medium_db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Mật khẩu riêng cho role chỉ đọc của agent. Không dùng chung tài khoản ứng
# dụng vì role này bị giới hạn vào schema `agent` và không được đọc nhãn.
resource "random_password" "hi_medium_agent" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_sql_database_instance" "hi_medium" {
  name             = var.hi_medium_db_instance_name
  region           = var.region
  database_version = var.db_version

  deletion_protection = var.hi_medium_db_deletion_protection

  settings {
    # PostgreSQL 16 mặc định sang Enterprise Plus nếu bỏ trống; tier
    # db-custom-* bên dưới thuộc Enterprise nên phải khai báo tường minh.
    edition               = "ENTERPRISE"
    tier                  = var.hi_medium_db_tier
    availability_type     = "ZONAL"
    disk_type             = "PD_SSD"
    disk_size             = var.hi_medium_db_disk_size_gb
    disk_autoresize       = true
    disk_autoresize_limit = var.hi_medium_db_disk_autoresize_limit_gb

    # Bảo vệ ở API ngoài lớp deletion_protection của Terraform.
    deletion_protection_enabled = true

    backup_configuration {
      enabled                        = true
      start_time                     = var.db_backup_start_time
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"

      authorized_networks {
        name  = "fin07-vm"
        value = google_compute_address.web.address
      }
    }

    maintenance_window {
      day          = 7
      hour         = 18
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  # Autoresize chỉ tăng đĩa. Không để một lần plan sau đó cố đưa kích thước
  # về giá trị ban đầu và đề xuất thay instance.
  lifecycle {
    ignore_changes = [settings[0].disk_size]
  }

  depends_on = [google_project_service.sqladmin]
}

resource "google_sql_database" "hi_medium" {
  name     = var.db_name
  instance = google_sql_database_instance.hi_medium.name
}

resource "google_sql_user" "hi_medium_app" {
  name     = var.db_user
  instance = google_sql_database_instance.hi_medium.name
  password = random_password.hi_medium_db.result
}
