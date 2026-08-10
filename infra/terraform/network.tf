# IP tĩnh và tường lửa.
#
# Vấn đề đang giải: VM dựng bằng tay nhận IP ephemeral. IP đó đổi mỗi lần
# stop/start máy, kéo theo hai thứ hỏng cùng lúc — bản ghi DNS trỏ sai, và
# danh sách IP được phép nối vào Cloud SQL trỏ vào một địa chỉ không còn là
# của mình nữa. Cái thứ hai đáng sợ hơn: nó có thể mở quyền truy cập cơ sở dữ
# liệu cho bất kỳ ai vô tình nhận được IP cũ đó.

# ---- Bật API cần dùng -----------------------------------------------
# Áp trên một dự án mới sẽ hỏng ở tài nguyên đầu tiên nếu chưa bật API. Khai
# báo tường minh để lần chạy đầu không cần ai vào Console bấm tay.

resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

# ---- IP tĩnh --------------------------------------------------------

resource "google_compute_address" "web" {
  name        = "fin07-web-ip"
  region      = var.region
  description = "IP cố định của VM chạy FIN-07. Gắn vào VM là bước thủ công — xem README."

  depends_on = [google_project_service.compute]
}

# ---- Tường lửa ------------------------------------------------------
#
# Chỉ 80 và 443. Cổng 80 KHÔNG thừa: Let's Encrypt xác thực ACME bằng cách gọi
# ngược vào đúng cổng đó, đóng nó lại là Caddy không xin được chứng chỉ.
#
# Cố ý KHÔNG mở 5432, 6379, 8081, 9870, 8082. Trên máy cá nhân chúng mở ra cho
# tiện gỡ lỗi; trên một máy có IP công cộng thì "cho tiện" nghĩa là một cơ sở
# dữ liệu ai quét cũng thấy.

resource "google_compute_firewall" "web" {
  name        = "fin07-web"
  network     = "default"
  description = "HTTP/HTTPS cho FIN-07 AML Console"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["fin07"]

  depends_on = [google_project_service.compute]
}

# VM đang chạy được tra cứu chứ không tạo mới: nó có sẵn dữ liệu trong volume
# Docker, và để Terraform quản lý vòng đời của nó nghĩa là một lần `destroy`
# lỡ tay sẽ xoá cả cơ sở dữ liệu. Terraform ở đây chỉ lo phần hạ tầng quanh VM.
data "google_compute_instance" "vm" {
  name = var.vm_name
  zone = var.zone

  depends_on = [google_project_service.compute]
}
