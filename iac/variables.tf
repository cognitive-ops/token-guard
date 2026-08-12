variable "aws_region" {
  description = "AWS region for the instance."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use."
  type        = string
  default     = "your-aws-profile"
}

variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "token-guard"
}

variable "instance_type" {
  description = "EC2 instance type. Default matches the current hand-run box (2 vCPU / ~7.6GB, ARM64)."
  type        = string
  default     = "t4g.large"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB. Sized for Prometheus (15GB cap) + Loki + Postgres + Grafana + docker images."
  type        = number
  default     = 80
}

variable "assign_eip" {
  description = "Attach an Elastic IP so the public address survives stop/start."
  type        = bool
  default     = true
}

# --- Application ports (docker-compose.yml), see repo CLAUDE.md "Services & ports" ---
# grafana:3000, claude-roi-web:3001, otel-collector:4317 (gRPC)/4318 (HTTP)/13133 (health).
# prometheus/loki/postgres/exporters stay internal-only (not opened here).
variable "app_ports" {
  description = "TCP ports the stack needs reachable from allowed_cidr_blocks."
  type        = list(number)
  default     = [3000, 3001, 4317, 4318, 13133]
}

variable "allowed_cidr_blocks" {
  description = <<-EOT
    CIDR blocks allowed to reach app_ports. Defaults to open internet to match the
    current box (no on-box reverse proxy/TLS today). Restrict this to known IPs/VPN
    ranges, or drop app_ports entirely, once traffic moves behind an ALB/Cloudflare.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ssh_key_name" {
  description = "Existing EC2 key pair name for SSH fallback. Leave null to keep SSM-only access (no port 22 opened)."
  type        = string
  default     = null
}

variable "ssh_allowed_cidr_blocks" {
  description = "CIDR blocks allowed to reach port 22. Only used when ssh_key_name is set."
  type        = list(string)
  default     = []
}
