#!/usr/bin/env bash
# ==============================================================================
# AskPDF — Monthly Storage & Hosting Quota Check Script
# Verifies Always Free storage compliance and reports directory sizes
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo " AskPDF Storage & Resource Utilization Report"
echo " Date: $(date)"
echo " Host: $(hostname)"
echo "=========================================================="

echo "--- 1. Root / Boot Volume Disk Space ---"
df -h / | awk 'NR==1 || NR==2'

echo ""
echo "--- 2. AskPDF Storage Breakdown ---"
if [ -d "/opt/askpdf/storage" ]; then
    echo "Total /opt/askpdf/storage size:"
    du -sh /opt/askpdf/storage 2>/dev/null || true
    echo "  Uploaded PDFs (/opt/askpdf/storage/data):"
    du -sh /opt/askpdf/storage/data 2>/dev/null || echo "    0B"
    echo "  ChromaDB & Registry (/opt/askpdf/storage/db):"
    du -sh /opt/askpdf/storage/db 2>/dev/null || echo "    0B"
fi

echo ""
echo "--- 3. Backup Archives (/opt/askpdf/backups) ---"
if [ -d "/opt/askpdf/backups" ]; then
    du -sh /opt/askpdf/backups 2>/dev/null || true
    COUNT=$(ls -1 /opt/askpdf/backups/*.tar.gz 2>/dev/null | wc -l || echo 0)
    echo "Total backup archives present: $COUNT"
fi

echo ""
echo "--- 4. Active Docker Containers ---"
timeout 3 docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Docker daemon unreachable or not running."

echo ""
echo "--- 5. Quota Compliance Summary ---"
FREE_PERCENT=$(df / | awk 'NR==2 {print 100 - $5}' | tr -d '%')
if [ "$FREE_PERCENT" -lt 20 ]; then
    echo "[WARNING] Disk space is below 20%! Prune old backups or run 'docker system prune -f'."
else
    echo "[OK] Storage is healthy (${FREE_PERCENT}% free disk space remaining on boot volume)."
fi
