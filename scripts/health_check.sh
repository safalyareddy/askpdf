#!/usr/bin/env bash
# ==============================================================================
# AskPDF — Automated Health Probe & Self-Healing Service
# Checks backend responsiveness and restarts container if unhealthy
# ==============================================================================

set -euo pipefail

LOG_FILE="/opt/askpdf/logs/health.log"
HEALTH_URL="http://127.0.0.1:8000/health"
MAX_FAILURES=3
STATE_FILE="/tmp/askpdf_health_failures"

mkdir -p /opt/askpdf/logs

FAILURES=0
if [ -f "$STATE_FILE" ]; then
    FAILURES=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi

STATUS_CODE=$(curl -s -o /tmp/health_out.json -w "%{http_code}" --max-time 10 "$HEALTH_URL" || echo "000")

if [ "$STATUS_CODE" -eq 200 ]; then
    # Reset failure count on success
    echo "0" > "$STATE_FILE"
    PROVIDER=$(grep -o '"provider":"[^"]*"' /tmp/health_out.json 2>/dev/null || echo "online")
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] [OK] Backend healthy (HTTP 200, $PROVIDER)" >> "$LOG_FILE"
else
    FAILURES=$((FAILURES + 1))
    echo "$FAILURES" > "$STATE_FILE"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] [WARNING] Health check failed with status $STATUS_CODE (Failure $FAILURES of $MAX_FAILURES)" >> "$LOG_FILE"

    if [ "$FAILURES" -ge "$MAX_FAILURES" ]; then
        echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] [ALERT] Consecutive failure threshold reached ($FAILURES). Triggering container restart..." >> "$LOG_FILE"
        cd /opt/askpdf
        docker compose restart askpdf-backend >> "$LOG_FILE" 2>&1
        echo "0" > "$STATE_FILE"
    fi
fi
