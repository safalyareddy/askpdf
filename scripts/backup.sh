#!/usr/bin/env bash
# ==============================================================================
# AskPDF — Automated Daily Storage Backup Script
# Targets: Uploaded PDFs, ChromaDB Vectorstore, Document Registry
# Retention: 30 days (older archives pruned automatically)
# ==============================================================================

set -euo pipefail

BACKUP_ROOT="/opt/askpdf/backups"
STORAGE_DIR="/opt/askpdf/storage"
DATE_STAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_NAME="askpdf_backup_${DATE_STAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_ROOT}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

mkdir -p "$BACKUP_ROOT" /opt/askpdf/logs

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Starting AskPDF persistent storage backup..."

# 1. Verify source storage exists
if [ ! -d "$STORAGE_DIR" ]; then
    echo "[ERROR] Storage directory $STORAGE_DIR not found. Aborting backup." >&2
    exit 1
fi

# 2. Create compressed archive of storage
echo "Archiving $STORAGE_DIR into $ARCHIVE_PATH..."
tar -czf "$ARCHIVE_PATH" -C "/opt/askpdf" "storage"

# 3. Compute SHA256 checksum for verification
echo "Computing SHA256 checksum..."
if command -v sha256sum &> /dev/null; then
    sha256sum "$ARCHIVE_PATH" > "$CHECKSUM_PATH"
elif command -v shasum &> /dev/null; then
    shasum -a 256 "$ARCHIVE_PATH" > "$CHECKSUM_PATH"
fi

ARCHIVE_SIZE=$(ls -lh "$ARCHIVE_PATH" | awk '{print $5}')
echo "[SUCCESS] Backup completed successfully: $ARCHIVE_NAME (Size: $ARCHIVE_SIZE)"

# 4. Prune backups older than 30 days to strictly honor Always Free storage quota
echo "Checking for expired backups older than 30 days..."
find "$BACKUP_ROOT" -name "askpdf_backup_*.tar.gz*" -type f -mtime +30 -exec rm -f {} +
echo "Pruning complete. Total remaining backup archives:"
ls -lh "$BACKUP_ROOT" | grep "askpdf_backup_" || echo "No older archives found."
