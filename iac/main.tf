data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Amazon Linux 2023, ARM64 (Graviton) — matches the current box.
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

# --- IAM: SSM-managed access only, no SSH key required ---

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.name}-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Read-only access to the deploy-artifacts bucket, for pulling compose files/configs
# onto the box (see README: "Deploying app files" — manual copy via S3, no SSH).
data "aws_iam_policy_document" "deploy_bucket_read" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.deploy.arn, "${aws_s3_bucket.deploy.arn}/*"]
  }
}

resource "aws_iam_role_policy" "deploy_bucket_read" {
  name   = "${var.name}-deploy-bucket-read"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.deploy_bucket_read.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name}-instance"
  role = aws_iam_role.instance.name
}

# --- S3 staging bucket for manual deploys (compose files, configs) ---
# Workflow: `aws s3 sync . s3://<bucket>/ --exclude '.git/*' ...` from your machine,
# then on the box: `aws s3 sync s3://<bucket>/ /home/ec2-user/claude-analytics/`.
# Avoids opening SSH just to move files; SSM Session Manager handles the rest.

resource "aws_s3_bucket" "deploy" {
  bucket = "${var.name}-deploy-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket                  = aws_s3_bucket.deploy.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "deploy" {
  bucket = aws_s3_bucket.deploy.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_caller_identity" "current" {}

# --- Security group ---

resource "aws_security_group" "instance" {
  name        = "${var.name}-instance"
  description = "token-guard stack: app ports in, all out. SSM needs no inbound rule."
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.instance.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "app" {
  for_each = { for pair in setproduct(var.app_ports, var.allowed_cidr_blocks) : "${pair[0]}-${pair[1]}" => pair }

  security_group_id = aws_security_group.instance.id
  cidr_ipv4         = each.value[1]
  from_port         = each.value[0]
  to_port           = each.value[0]
  ip_protocol       = "tcp"
  description       = "app port ${each.value[0]}"
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each = toset(var.ssh_key_name != null ? var.ssh_allowed_cidr_blocks : [])

  security_group_id = aws_security_group.instance.id
  cidr_ipv4         = each.value
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  description       = "SSH fallback"
}

# --- Instance ---

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  key_name               = var.ssh_key_name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  user_data                   = templatefile("${path.module}/user_data.sh.tpl", {})
  user_data_replace_on_change = false

  tags = {
    Name = var.name
  }
}

resource "aws_eip" "app" {
  count    = var.assign_eip ? 1 : 0
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = {
    Name = var.name
  }
}
