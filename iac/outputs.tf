output "instance_id" {
  value = aws_instance.app.id
}

output "public_ip" {
  description = "EIP if assign_eip=true, else the instance's ephemeral public IP."
  value       = var.assign_eip ? aws_eip.app[0].public_ip : aws_instance.app.public_ip
}

output "ssm_connect_command" {
  value = "aws ssm start-session --target ${aws_instance.app.id} --profile ${var.aws_profile}"
}

output "deploy_bucket" {
  description = "S3 bucket for staging compose files/configs onto the box (see README)."
  value       = aws_s3_bucket.deploy.bucket
}

output "app_urls" {
  value = {
    grafana = "http://${var.assign_eip ? aws_eip.app[0].public_ip : aws_instance.app.public_ip}:3000"
    web     = "http://${var.assign_eip ? aws_eip.app[0].public_ip : aws_instance.app.public_ip}:3001"
  }
}
