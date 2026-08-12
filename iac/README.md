# token-guard EC2 infra

Terraform for a fresh EC2 box to run `docker-compose.yml` (this repo's root). Provisions
infra only — app files are copied on separately (see below), matching the current
hand-run box's workflow (`CLAUDE.md` → "Production deployment": no git checkout on box).

## What this creates

- EC2 instance, Amazon Linux 2023 **ARM64**, default `t4g.large` (2 vCPU / 8GB, matches
  the current box). gp3 root volume, IMDSv2 required.
- IAM role + instance profile: `AmazonSSMManagedInstanceCore` only (SSM Session Manager
  access, no SSH key needed) + read access to the deploy S3 bucket below.
- Security group: inbound `app_ports` (3000 grafana, 3001 web, 4317/4318/13133 otel)
  from `allowed_cidr_blocks` (default `0.0.0.0/0` — restrict this). No inbound needed
  for SSM. Port 22 stays closed unless `ssh_key_name` is set.
- S3 bucket for staging compose files/configs onto the box without opening SSH.
- Optional Elastic IP (`assign_eip`, default true) so the public address is stable.
- user_data: installs Docker + the `docker-compose-plugin`, starts Docker, creates
  `/home/ec2-user/claude-analytics`.

Out of scope (add later if needed): ALB/ACM/Route53 (the current box has none —
HTTPS is terminated upstream per `CLAUDE.md`), CloudWatch alarms (already covered by
`../alarms/cloudformation.yaml` against the existing instance), Postgres port exposure
(deliberately never opened — see `CLAUDE.md` gotchas on `user_prompts`).

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # edit aws_profile/region, lock down allowed_cidr_blocks
terraform init
terraform plan
terraform apply
```

## First deploy

1. Wait for the instance to finish user_data (Docker installed): poll via
   `aws ssm start-session --target <instance_id> --profile your-aws-profile` then
   `docker --version`.
2. Stage app files from the repo root (compose file + configs), skipping secrets you'll
   set directly on the box:

   ```bash
   aws s3 sync . s3://<deploy_bucket>/ \
     --exclude ".git/*" --exclude ".env" --exclude ".secrets/*" \
     --profile your-aws-profile
   ```
3. Pull them onto the box and bring the stack up (via SSM, no SSH):

   ```bash
   aws ssm send-command --profile your-aws-profile \
     --instance-ids <instance_id> \
     --document-name AWS-RunShellScript \
     --parameters commands='["aws s3 sync s3://<deploy_bucket>/ /home/ec2-user/claude-analytics/","cd /home/ec2-user/claude-analytics && docker compose up -d"]'
   ```
4. Create `.env` and `.secrets/admin-key` directly on the box (via an SSM session) —
   never through S3/user_data, per `.env.example`'s instructions.

## Subsequent config changes

Same as the current box's process (`CLAUDE.md`): re-sync the changed file to S3, pull it
down, restart the affected container — e.g. `docker compose up -d --force-recreate
prometheus` after a `prometheus.yml` edit (plain `restart` doesn't pick it up).

## Notes

- `allowed_cidr_blocks` defaults to open internet because the current box has no
  reverse-proxy/TLS in front of Grafana/otel either — same exposure, now codified.
  Restrict it, or drop `app_ports` to `[]` and front everything with an ALB, before
  this holds real credentials/customer data.
- `postgres` (5432) is intentionally never opened here — keep it internal-only, per
  `CLAUDE.md`'s gotcha about unredacted prompt text.
