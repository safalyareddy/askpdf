#!/usr/bin/env bash
# ==============================================================================
# AskPDF — Verified Backup Restoration Script
# Restores: Uploaded PDFs, ChromaDB Vectorstore, Document Registry
# ==============================================================================

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path_to_backup_archive.tar.gz>"
    echo "Example: $0 /opt/askpdf/backups/askpdf_backup_20261030_120000.tar.gz"
    exit 1
fi

ARCHIVE="$1"
CHECKSUM="${ARCHIVE}.sha256"

if [ ! -f "$ARCHIVE" ]; then
    echo "[ERROR] Archive file '$ARCHIVE' does not exist." >&2
    exit 1
fi

echo "=========================================================="
echo " Starting AskPDF Storage Restoration"
echo " Archive: $ARCHIVE"
echo " Date: $(date)"
echo "=========================================================="

# 1. Verify Checksum if present
if [ -f "$CHECKSUM" ]; then
    echo "[1/4] Verifying SHA-256 archive checksum..."
    if command -v sha256sum &> /dev/null; then
        sha256sum -c "$CHECKSUM"
    elif command -v shasum &> /dev/null; then
        shasum -a 256 -c "$CHECKSUM"
    fi
    echo "Checksum verified successfully!"
else
    echo "[WARNING] No .sha256 checksum file found. Proceeding with archive test."
    tar -tzf "$ARCHIVE" > /dev/null
fi

# 2. Safely stop backend container
echo "[2/4] Stopping AskPDF container to prevent concurrent database writes..."
cd /opt/askpdf
docker compose stop askpdf-backend || true

# 3. Create a safety backup of existing storage
if [ -d "/opt/askpdf/storage" ]; then
    SAFETY_DIR="/opt/askpdf/storage_pre_restore_$(date +%Y%m%d_%H%M%S)"
    echo "Creating safety backup of current storage at $SAFETY_DIR..."
    mv /opt/askpdf/storage "$SAFETY_DIR"
fi

# 4. Extract archive
echo "[3/4] Extracting backup into /opt/askpdf/storage..."
tar -xzf "$ARCHIVE" -C "/opt/askpdf"

# 5. Restart backend container and verify health
echo "[4/4] Restarting AskPDF container..."
docker compose up -d askpdf-backend

echo "Waiting for healthcheck to pass..."
RETRY_COUNT=0
MAX_RETRIES=15
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s -f http://127.0.0.1:8000/health > /dev/null; then
        echo "[SUCCESS] AskPDF Backend is healthy and operational after restoration!"
        curl -s http://127.0.0.1:8000/health
        echo ""
        exit 0
    fi
    sleep 3
    RETRY_COUNT=$((RETRY_COUNT+1))
done

echo "[WARNING] Healthcheck did not pass immediately. Check logs with: docker compose logs askpdf-backend"
