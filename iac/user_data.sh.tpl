#!/bin/bash
set -euxo pipefail

dnf update -y
dnf install -y docker

systemctl enable --now docker
usermod -aG docker ec2-user

# docker compose v2 plugin (dnf package name on AL2023)
dnf install -y docker-compose-plugin

mkdir -p /home/ec2-user/claude-analytics
chown ec2-user:ec2-user /home/ec2-user/claude-analytics
