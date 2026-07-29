// AMI tra theo tên chứ không ghim mã cứng: mã AMI khác nhau ở mỗi vùng, và
// Canonical phát hành bản mới khi có vá bảo mật. most_recent = true nghĩa là
// dựng lại máy sẽ lấy bản đã vá.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] // Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "ci" {
  key_name   = "${var.project}-ci"
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))

  tags = {
    Name = "${var.project}-ci"
  }
}

resource "aws_instance" "ci" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ci.id]
  key_name               = aws_key_pair.ci.key_name

  user_data                   = file("${path.module}/cloud-init.yaml")
  user_data_replace_on_change = false // Sửa cloud-init không huỷ máy đang chạy

  root_block_device {
    volume_size           = var.root_volume_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name = "${var.project}-ci-root"
    }
  }

  // Bắt buộc IMDSv2. IMDSv1 cho phép lấy thông tin máy qua một request GET
  // đơn giản, và đó là đường leo thang quen thuộc khi ứng dụng có lỗ hổng
  // SSRF — chính là loại lỗ hổng mà một hệ thống nhận dữ liệu từ bên ngoài
  // như FIN-07 phải đề phòng.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2 // 2 để tiến trình trong container vẫn hỏi được
  }

  tags = {
    Name = "${var.project}-ci"
    Role = "jenkins-controller,jenkins-agent,staging,prodlike"
  }
}

// IP tĩnh. Không có nó thì mỗi lần stop/start máy là đổi IP công cộng, kéo
// theo phải sửa URL Jenkins, sửa security group, sửa cấu hình triển khai.
// Stop máy để tiết kiệm tiền là việc sẽ làm thường xuyên, nên đây không phải
// tình huống hiếm.
resource "aws_eip" "ci" {
  domain   = "vpc"
  instance = aws_instance.ci.id

  tags = {
    Name = "${var.project}-ci-eip"
  }

  depends_on = [aws_internet_gateway.main]
}
