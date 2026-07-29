resource "aws_security_group" "ci" {
  name = "${var.project}-ci"
  # AWS chi chap nhan ASCII trong mo ta security group. Moi mo ta trong file
  # nay va trong bien service_ports deu viet khong dau vi ly do do — khong
  # phai vi lam bieng.
  description = "FIN-07 CI/CD - chi cho phep truy cap tu dai IP da khai bao"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project}-ci-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

// Mỗi cổng × mỗi dải IP là một quy tắc riêng, sinh bằng for_each thay vì
// viết tay. Thêm một cổng vào biến service_ports là xong; không có chuyện
// thêm cổng mà quên một dải IP nào đó.
locals {
  ingress_rules = {
    for pair in setproduct(keys(var.service_ports), var.allowed_cidr_blocks) :
    "${pair[0]}-${pair[1]}" => {
      port        = tonumber(pair[0])
      cidr        = pair[1]
      description = var.service_ports[pair[0]]
    }
  }
}

resource "aws_vpc_security_group_ingress_rule" "ci" {
  for_each = local.ingress_rules

  security_group_id = aws_security_group.ci.id
  description       = "${each.value.description} tu ${each.value.cidr}"
  cidr_ipv4         = each.value.cidr
  from_port         = each.value.port
  to_port           = each.value.port
  ip_protocol       = "tcp"
}

// Đi ra thì mở: máy cần kéo image, cài gói, và gọi API của nhà cung cấp mô
// hình ngôn ngữ.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.ci.id
  description       = "Cho phep moi ket noi di ra"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
