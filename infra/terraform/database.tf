# Cloud SQL cho PostgreSQL.
#
# Vì sao chuyển khỏi container trong VM: bảng `audit_log`, `approval` và
# `evidence` là bằng chứng pháp lý, đã được cưỡng chế chỉ-ghi-thêm bằng trigger
# (db/init/002). Nhưng cưỡng chế không cho SỬA mà không bảo vệ khỏi MẤT là một
# sự bất cân xứng: hiện tất cả nằm trên một đĩa của một VM, không bản sao,
# không sao lưu. Cloud SQL cho sao lưu tự động và khôi phục theo thời điểm.
#
# Đây KHÔNG phải kho dữ liệu. Giao dịch thô nằm ở HDFS/object store; ở đây chỉ
# có vụ việc, cảnh báo, bằng chứng và nhật ký — tính bằng nghìn dòng.

# Mật khẩu sinh tại chỗ thay vì người tự nghĩ: mật khẩu người nghĩ ra thường
# yếu, và thường bị chép sang chỗ khác. Giá trị nằm trong state Terraform, nên
# state phải được coi là bí mật — xem README.
resource "random_password" "db" {
  length  = 32
  special = true
  # Cloud SQL từ chối vài ký tự trong mật khẩu; giới hạn tập ký tự đặc biệt để
  # không gặp lỗi ở giữa lần apply.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_sql_database_instance" "main" {
  name             = var.db_instance_name
  region           = var.region
  database_version = var.db_version

  deletion_protection = var.db_deletion_protection

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = var.db_disk_size_gb
    # Hết dung lượng giữa đêm là sự cố không đáng có.
    disk_autoresize = true

    backup_configuration {
      enabled    = true
      start_time = var.db_backup_start_time
      # Khôi phục theo thời điểm. Sao lưu hằng ngày chỉ cứu được tới mốc gần
      # nhất; PITR cứu được tới từng phút, và đó là khác biệt giữa mất một
      # ngày nhật ký kiểm toán và mất vài phút.
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      # IP công cộng kèm danh sách cho phép, KHÔNG phải Private IP. Private IP
      # cần VPC peering qua servicenetworking — đúng hơn về lâu dài, nhưng
      # thêm một lớp phải hiểu và gỡ lỗi. Với đúng một máy được phép nối vào,
      # danh sách cho phép một địa chỉ đạt cùng mức an toàn thực tế.
      #
      # Và đây chính là chỗ IP tĩnh trả công: không có nó, danh sách này trỏ
      # vào một địa chỉ sẽ đổi sau lần khởi động lại kế tiếp.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"

      authorized_networks {
        name  = "fin07-vm"
        value = google_compute_address.web.address
      }
    }

    maintenance_window {
      day          = 7 # chủ nhật
      hour         = 18
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [google_project_service.sqladmin]
}

resource "google_sql_database" "fin07" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = var.db_user
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}
