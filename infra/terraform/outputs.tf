output "public_ip" {
  description = "IP tĩnh của máy CI"
  value       = aws_eip.ci.public_ip
}

output "ssh_command" {
  description = "Lệnh SSH vào máy"
  value       = "ssh -i ${var.ssh_public_key_path == "" ? "~/.ssh/id_ed25519" : replace(var.ssh_public_key_path, ".pub", "")} ubuntu@${aws_eip.ci.public_ip}"
}

output "jenkins_url" {
  description = "Giao diện Jenkins (sau khi dựng bằng jenkins/docker-compose.yml)"
  value       = "http://${aws_eip.ci.public_ip}:8080"
}

output "staging_urls" {
  description = "Địa chỉ môi trường staging"
  value = {
    api     = "http://${aws_eip.ci.public_ip}:8000"
    console = "http://${aws_eip.ci.public_ip}:5173"
  }
}

output "prodlike_urls" {
  description = "Địa chỉ môi trường production-like"
  value = {
    api     = "http://${aws_eip.ci.public_ip}:8001"
    console = "http://${aws_eip.ci.public_ip}:5174"
  }
}

output "instance_id" {
  description = "Mã máy, dùng cho lệnh start/stop khi cần tiết kiệm chi phí"
  value       = aws_instance.ci.id
}

output "cost_note" {
  description = "Nhắc về chi phí"
  value = join(" ", [
    "Máy ${var.instance_type} bật 24/7 tốn khoảng 60 USD/tháng.",
    "Dừng khi không dùng: aws ec2 stop-instances --instance-ids ${aws_instance.ci.id}",
    "Khi dừng vẫn tính tiền đĩa ${var.root_volume_gb} GB và Elastic IP, khoảng 9 USD/tháng.",
    "Xoá sạch: terraform destroy"
  ])
}
