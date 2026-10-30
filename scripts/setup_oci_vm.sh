#!/usr/bin/env bash
# ==============================================================================
# AskPDF — Oracle Cloud Infrastructure (OCI) Always Free Automated Setup Script
# Architecture: ARM64 (Ampere A1 / aarch64) on Ubuntu 22.04 / 24.04 LTS
# Target Cost: ₹0 / month (100% Always Free Eligible)
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo " Starting AskPDF OCI Always Free Setup Pipeline"
echo " Date: $(date)"
echo " System Architecture: $(uname -m)"
echo "=========================================================="

# 1. Verify ARM64 Architecture
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
    echo "[WARNING] System architecture is $ARCH. This script is optimized for Ampere A1 ARM64."
fi

# 2. Update System Packages
echo "[1/7] Updating system packages..."
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    tar \
    gzip \
    cron \
    netfilter-persistent \
    iptables-persistent

# 3. Configure OCI Ubuntu Firewall / iptables for ports 80, 443, 22
echo "[2/7] Configuring firewall and iptables rules for HTTP/HTTPS..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT || sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save || true

# 4. Install Docker Engine & Docker Compose (Official Docker Repo for ARM64)
echo "[3/7] Installing Docker Engine for $ARCH..."
if ! command -v docker &> /dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable --now docker
    sudo usermod -aG docker "$USER" || true
else
    echo "Docker already installed: $(docker --version)"
fi

# 5. Set up Project Directory and Persistent Storage Structure
echo "[4/7] Setting up application directories at /opt/askpdf..."
sudo mkdir -p /opt/askpdf /opt/askpdf/storage /opt/askpdf/storage/data /opt/askpdf/storage/db /opt/askpdf/backups /opt/askpdf/logs
sudo chown -R "$USER":"$USER" /opt/askpdf

# 6. Deploy or Update AskPDF Source Code
if [ ! -d "/opt/askpdf/.git" ]; then
    echo "[5/7] Cloning repository safalyareddy/askpdf (branch: feature/askpdf-upgrade)..."
    git clone -b feature/askpdf-upgrade https://github.com/safalyareddy/askpdf.git /opt/askpdf_temp
    shopt -s dotglob
    cp -r /opt/askpdf_temp/* /opt/askpdf/
    rm -rf /opt/askpdf_temp
else
    echo "[5/7] Pulling latest updates from GitHub..."
    cd /opt/askpdf
    git fetch origin feature/askpdf-upgrade
    git reset --hard origin/feature/askpdf-upgrade
fi

cd /opt/askpdf

# 7. Configure Environment Variables
if [ ! -f "/opt/askpdf/.env" ]; then
    echo "Generating default production .env..."
    cp .env.example /opt/askpdf/.env
    # Set production defaults
    sed -i "s|LLM_PROVIDER=.*|LLM_PROVIDER=openai_compatible|g" /opt/askpdf/.env
    sed -i "s|LLM_BASE_URL=.*|LLM_BASE_URL=https://api.groq.com/openai/v1|g" /opt/askpdf/.env
    sed -i "s|LLM_MODEL=.*|LLM_MODEL=llama-3.3-70b-versatile|g" /opt/askpdf/.env
    sed -i "s|PERSIST_DIR=.*|PERSIST_DIR=/app/storage/db|g" /opt/askpdf/.env
    sed -i "s|PDF_DIR=.*|PDF_DIR=/app/storage/data|g" /opt/askpdf/.env
    echo "STORAGE_DIR=/app/storage" >> /opt/askpdf/.env
    echo "PORT=8000" >> /opt/askpdf/.env
fi

# Make maintenance scripts executable
chmod +x /opt/askpdf/scripts/*.sh || true

# 8. Configure Systemd Service for Auto-Start on VM Boot
echo "[6/7] Installing systemd service (askpdf.service)..."
cat << 'EOF' | sudo tee /etc/systemd/system/askpdf.service
[Unit]
Description=AskPDF Production Backend Stack (FastAPI + Caddy)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/askpdf
ExecStart=/usr/bin/docker compose up -d --build
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable askpdf.service

# 9. Configure Automated Daily Backup Cron Job (2:00 AM UTC)
echo "[7/7] Configuring automated daily backup cron job..."
CRON_JOB="0 2 * * * /opt/askpdf/scripts/backup.sh >> /opt/askpdf/logs/backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v "backup.sh" || true; echo "$CRON_JOB") | crontab -

# Configure Hourly Health Check Cron Job
HEALTH_JOB="*/15 * * * * /opt/askpdf/scripts/health_check.sh >> /opt/askpdf/logs/health.log 2>&1"
(crontab -l 2>/dev/null | grep -v "health_check.sh" || true; echo "$HEALTH_JOB") | crontab -

echo "=========================================================="
echo " Setup complete! Next steps:"
echo " 1. Edit /opt/askpdf/.env and add your LLM_API_KEY (Groq API key)."
echo " 2. Set DOMAIN in /opt/askpdf/.env (e.g. DOMAIN=<YOUR-PUBLIC-IP>.sslip.io)."
echo " 3. Start the stack: sudo systemctl start askpdf.service"
echo " 4. Check status: docker compose ps"
echo "=========================================================="
