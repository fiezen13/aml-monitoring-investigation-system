output "instance_id" {
  description = "EC2 instance ID dùng cho start/stop."
  value       = aws_instance.gpu.id
}

output "instance_type" {
  value = aws_instance.gpu.instance_type
}

output "availability_zone" {
  value = aws_instance.gpu.availability_zone
}

output "public_ip" {
  description = "Public IP hiện tại; IP sẽ đổi sau stop/start."
  value       = aws_instance.gpu.public_ip
}

output "ssh_command" {
  description = "Lệnh SSH bằng private key tương ứng với public key đã import."
  value       = "ssh -i ${pathexpand(trimsuffix(var.ssh_public_key_path, ".pub"))} ubuntu@${aws_instance.gpu.public_ip}"
}

output "stop_command" {
  value = "aws ec2 stop-instances --instance-ids ${aws_instance.gpu.id} --region ${var.aws_region}"
}

output "idle_stop_alarm" {
  description = "CloudWatch alarm dừng máy nếu CPU <= 1% liên tục 6 giờ."
  value       = aws_cloudwatch_metric_alarm.idle_stop.alarm_name
}
