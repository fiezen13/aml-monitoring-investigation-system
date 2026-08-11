output "static_ip" {
  description = "IP cố định. Trỏ bản ghi A của tên miền về đây, và gán nó vào VM."
  value       = google_compute_address.web.address
}

output "vm_current_ip" {
  description = "IP VM đang dùng. Khác static_ip nghĩa là chưa gán — xem README bước 4."
  value       = try(data.google_compute_instance.vm.network_interface[0].access_config[0].nat_ip, "không có IP ngoài")
}

output "db_connection_name" {
  description = "Dùng cho Cloud SQL Auth Proxy: <project>:<region>:<instance>"
  value       = google_sql_database_instance.main.connection_name
}

output "db_public_ip" {
  description = "Địa chỉ để đặt vào DATABASE_URL"
  value       = google_sql_database_instance.main.public_ip_address
}

output "database_url" {
  description = <<-EOT
    Chuỗi kết nối hoàn chỉnh, dán vào .env trên VM.

    `sslmode=require` không phải trang trí: instance đặt ssl_mode = ENCRYPTED_ONLY
    nên kết nối không mã hoá bị từ chối thẳng, và thông báo lỗi của libpq khi
    thiếu tham số này không nói rõ nguyên nhân.

    Đọc giá trị:  terraform output -raw database_url
  EOT
  sensitive   = true
  value = format(
    "postgresql+psycopg://%s:%s@%s:5432/%s?sslmode=require",
    google_sql_user.app.name,
    # urlencode BẮT BUỘC: mật khẩu sinh ngẫu nhiên chứa `?`, `&`, `=`, `%`,
    # `:` — đều là ký tự có nghĩa trong URL. Không mã hoá thì chuỗi kết nối
    # bị cắt sai chỗ, và thư viện nào chặt chẽ sẽ từ chối:
    #
    #   invalid port ":WUP7=d&3XlRcI)M%xIj-2X" after host
    #
    # Đã gặp thật với postgres-exporter. SQLAlchemy dễ tính hơn nên ứng dụng
    # vẫn nối được — đúng loại lỗi chỉ lộ ra ở thành phần thứ hai.
    urlencode(random_password.db.result),
    google_sql_database_instance.main.public_ip_address,
    google_sql_database.fin07.name,
  )
}

output "monitoring_pg_dsn" {
  description = <<-EOT
    Chuỗi kết nối cho postgres-exporter. Khác database_url ở chỗ KHÔNG có tiền
    tố `+psycopg`: exporter dùng libpq, không hiểu cú pháp phương ngữ của
    SQLAlchemy. Đặt vào MONITORING_PG_DSN trong .env.

    terraform output -raw monitoring_pg_dsn
  EOT
  sensitive   = true
  value = format(
    "postgresql://%s:%s@%s:5432/%s?sslmode=require",
    google_sql_user.app.name,
    urlencode(random_password.db.result),
    google_sql_database_instance.main.public_ip_address,
    google_sql_database.fin07.name,
  )
}

output "db_password" {
  description = "Mật khẩu tài khoản ứng dụng. terraform output -raw db_password"
  sensitive   = true
  value       = random_password.db.result
}

output "buoc_tiep_theo" {
  description = "Việc phải làm bằng tay sau khi apply"
  value       = <<-EOT

    1. Gán IP tĩnh vào VM (không làm được bằng Terraform vì VM chỉ được tra cứu):

       gcloud compute instances delete-access-config ${var.vm_name} \
           --zone ${var.zone} --access-config-name "external-nat"
       gcloud compute instances add-access-config ${var.vm_name} \
           --zone ${var.zone} --access-config-name "external-nat" \
           --address ${google_compute_address.web.address}

    2. Gắn thẻ để tường lửa có hiệu lực:

       gcloud compute instances add-tags ${var.vm_name} --zone ${var.zone} --tags fin07

    3. Trỏ DNS: bản ghi A của ${var.site_domain} và www → ${google_compute_address.web.address}

    4. Trên VM, đặt DATABASE_URL vào .env:

       terraform output -raw database_url

    5. Nạp lược đồ lên Cloud SQL — ĐỌC KỸ infra/terraform/README.md mục 5.
       `db/init/*.sql` KHÔNG tự chạy trên Cloud SQL như trong container.

  EOT
}
