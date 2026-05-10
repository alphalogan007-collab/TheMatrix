#!/usr/bin/env bash
# ==============================================================================
# MindAI — One-command production deploy to a Hetzner (or any Ubuntu) VPS
# ==============================================================================
# Run this on your LOCAL machine (Windows: use Git Bash or WSL):
#
#   bash deploy/deploy.sh YOUR_SERVER_IP
#
# What it does:
#   1. Installs Docker + Docker Compose on the server (if not already installed)
#   2. Hardens the server (firewall, fail2ban, SSH key-only auth)
#   3. Copies production files to server
#   4. Generates strong secrets if not already present
#   5. Builds and starts all containers
#   6. Verifies health
# ==============================================================================
set -euo pipefail

SERVER_IP="${1:-}"
SERVER_USER="${2:-root}"
DEPLOY_DIR="/opt/mindai"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o BatchMode=yes"

# ─── Validation ───────────────────────────────────────────────────────────────
if [[ -z "$SERVER_IP" ]]; then
  echo "Usage: bash deploy/deploy.sh <SERVER_IP> [SERVER_USER]"
  echo "Example: bash deploy/deploy.sh 65.109.12.34"
  exit 1
fi

echo "======================================================================"
echo "  MindAI Production Deploy → $SERVER_USER@$SERVER_IP"
echo "======================================================================"

# ─── Step 1: Bootstrap server ─────────────────────────────────────────────────
echo ""
echo "▶ Step 1/5 — Bootstrapping server..."
ssh $SSH_OPTS "$SERVER_USER@$SERVER_IP" 'bash -s' << 'REMOTE'
set -euo pipefail

# Update system
apt-get update -q && apt-get upgrade -yq

# Install Docker
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$USER" 2>/dev/null || true
fi

# Install Docker Compose plugin
if ! docker compose version &>/dev/null; then
  apt-get install -yq docker-compose-plugin
fi

# Install security tools
apt-get install -yq ufw fail2ban unattended-upgrades

# Firewall — only SSH, HTTP, HTTPS
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (redirects to HTTPS via Caddy)
ufw allow 443/tcp   # HTTPS
ufw allow 443/udp   # HTTP/3
ufw --force enable

# Fail2ban — block brute force SSH
systemctl enable fail2ban
systemctl start fail2ban

# Disable root SSH password login (key only)
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload sshd

# Auto security updates
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "Server bootstrapped ✓"
REMOTE

# ─── Step 2: Copy files ───────────────────────────────────────────────────────
echo ""
echo "▶ Step 2/5 — Copying project files..."
ssh $SSH_OPTS "$SERVER_USER@$SERVER_IP" "mkdir -p $DEPLOY_DIR"

# Sync project — exclude dev artifacts, local .env, node_modules
rsync -az --progress \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude '.env.production' \
  --exclude 'mobile' \
  --exclude 'mindai_pgdata' \
  --exclude 'mindai_redisdata' \
  . "$SERVER_USER@$SERVER_IP:$DEPLOY_DIR/"

echo "Files synced ✓"

# ─── Step 3: Generate secrets ─────────────────────────────────────────────────
echo ""
echo "▶ Step 3/5 — Generating production secrets..."
ssh $SSH_OPTS "$SERVER_USER@$SERVER_IP" 'bash -s' << REMOTE
set -euo pipefail
cd $DEPLOY_DIR

if [[ ! -f .env.production ]]; then
  echo "Creating .env.production with generated secrets..."
  cp .env.production.template .env.production

  # Generate strong secrets
  SECRET_KEY=\$(openssl rand -hex 64)
  PG_PASS=\$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
  REDIS_PASS=\$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)

  sed -i "s|GENERATE_WITH_OPENSSL_RAND_HEX_64|\$SECRET_KEY|g" .env.production
  sed -i "s|GENERATE_WITH_OPENSSL_RAND_BASE64_32|\$PG_PASS|g" .env.production
  sed -i "s|GENERATE_WITH_OPENSSL_RAND_BASE64_24|\$REDIS_PASS|g" .env.production

  # Restrict permissions — only owner can read
  chmod 600 .env.production
  echo ".env.production created with generated secrets ✓"
  echo ""
  echo "  ⚠️  NEXT STEP: Edit .env.production and add your API keys:"
  echo "     nano $DEPLOY_DIR/.env.production"
  echo "     Set: OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY"
  echo "     Set: DOMAIN (your actual domain)"
else
  echo ".env.production already exists — skipping secret generation"
fi
REMOTE

# ─── Step 4: Build and start ──────────────────────────────────────────────────
echo ""
echo "▶ Step 4/5 — Building and starting containers..."
ssh $SSH_OPTS "$SERVER_USER@$SERVER_IP" 'bash -s' << REMOTE
set -euo pipefail
cd $DEPLOY_DIR

# Build fresh production image
docker build -t mindai_backend:latest ./backend/

# Start all services
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

echo "Containers started ✓"
REMOTE

# ─── Step 5: Health check ─────────────────────────────────────────────────────
echo ""
echo "▶ Step 5/5 — Verifying health..."
sleep 20
ssh $SSH_OPTS "$SERVER_USER@$SERVER_IP" 'bash -s' << REMOTE
set -euo pipefail
cd $DEPLOY_DIR

echo ""
echo "Container status:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "Backend health:"
curl -sf http://localhost:8000/health && echo " ← healthy ✓" || echo " ← UNHEALTHY ✗"

echo ""
echo "Database:"
docker exec mindai_db pg_isready -U mindai_user -d mindai && echo "PostgreSQL ready ✓"

echo ""
echo "Redis:"
docker exec mindai_redis redis-cli -a \$(grep REDIS_PASSWORD .env.production | cut -d= -f2) ping
REMOTE

echo ""
echo "======================================================================"
echo "  ✅  MindAI is deployed!"
echo ""
echo "  Backend:  http://$SERVER_IP:8000/health"
echo "  After DNS points to $SERVER_IP:"
echo "  API:      https://api.mindai.app/health"
echo "  Docs:     https://api.mindai.app/docs"
echo ""
echo "  IMPORTANT: Update your mobile app API_BASE_URL to:"
echo "  https://api.mindai.app"
echo "======================================================================"
