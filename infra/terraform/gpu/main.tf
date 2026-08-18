data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "selected" {
  availability_zone = var.availability_zone
  default_for_az    = true
}

resource "aws_key_pair" "gpu" {
  key_name   = "fin07-gpu-20260817"
  public_key = file(pathexpand(var.ssh_public_key_path))

  tags = {
    Project = "FIN-07"
    Purpose = "HI-Medium training"
  }
}

resource "aws_security_group" "gpu" {
  name        = "fin07-hi-medium-gpu-ssh"
  description = "SSH to the FIN-07 GPU trainer from one operator IP only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from known operator IPs"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
  }

  egress {
    description = "Package, repository and artifact downloads"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "fin07-hi-medium-gpu-ssh"
    Project = "FIN-07"
  }
}

resource "aws_instance" "gpu" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  availability_zone           = var.availability_zone
  subnet_id                   = data.aws_subnet.selected.id
  associate_public_ip_address = true
  key_name                    = aws_key_pair.gpu.key_name
  vpc_security_group_ids      = [aws_security_group.gpu.id]

  # Chỉ có thể terminate sau khi cố ý đổi cờ này và apply. Shutdown từ Linux
  # sẽ stop máy, không xóa checkpoint chưa tải về.
  disable_api_termination              = true
  instance_initiated_shutdown_behavior = "stop"

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    iops                  = 3000
    throughput            = 125
    encrypted             = true
    delete_on_termination = true
  }

  user_data = <<-CLOUD_INIT
    #!/bin/bash
    set -euxo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y git rsync tmux htop nvtop
    install -d -o ubuntu -g ubuntu /workspace
    touch /var/lib/fin07-gpu-bootstrap-complete
  CLOUD_INIT

  tags = {
    Name       = var.instance_name
    Project    = "FIN-07"
    Workload   = "MEGA-PNA-HI-Medium"
    ManagedBy  = "Terraform"
    AutoDelete = "false"
  }
}

# Hàng rào chi phí cuối cùng: nếu CPU trung bình <= 1% liên tục 6 giờ thì dừng
# instance. Training vẫn phải được theo dõi chủ động; alarm này chỉ cứu trường
# hợp máy bị bỏ quên khi không có tiến trình nào làm việc.
resource "aws_cloudwatch_metric_alarm" "idle_stop" {
  alarm_name          = "fin07-hi-medium-gpu-idle-stop"
  alarm_description   = "Stop the GPU instance after six consecutive idle hours"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 6
  datapoints_to_alarm = 6
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 3600
  statistic           = "Average"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = true
  alarm_actions       = ["arn:aws:automate:${var.aws_region}:ec2:stop"]

  dimensions = {
    InstanceId = aws_instance.gpu.id
  }

  tags = {
    Project = "FIN-07"
    Purpose = "GPU cost guardrail"
  }
}
