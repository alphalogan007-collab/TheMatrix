#!/usr/bin/env bash
# ==============================================================================
# MindAI — Push local docker image to EC2 and restart Prophet
# ==============================================================================
# Use this for updates (after initial setup-ec2.sh).
# Run from project root: bash infra/push-image.sh <EC2_IP> [EC2_USER]
# ==============================================================================
set -euo pipefail

EC2_IP="${1:-}"
EC2_USER="${2:-ubuntu}"
DEPLOY_DIR="/opt/mindai"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

if [[ -z "$EC2_IP" ]]; then
  echo "Usage: bash infra/push-image.sh <EC2_IP> [EC2_USER]"
  exit 1
fi

echo "▶ Building image locally..."
docker build -t mindai_backend:latest ./backend/

echo "▶ Pushing image to EC2 $EC2_IP..."
docker save mindai_backend:latest | ssh $SSH_OPTS "$EC2_USER@$EC2_IP" "docker load"

echo "▶ Restarting Prophet + Worker on EC2..."
ssh $SSH_OPTS "$EC2_USER@$EC2_IP" "cd $DEPLOY_DIR && docker compose up -d --no-deps prophet worker"

echo ""
echo "Done. Prophet restarted with latest image."
echo "Check status: ssh $EC2_USER@$EC2_IP 'cd $DEPLOY_DIR && docker compose ps'"
