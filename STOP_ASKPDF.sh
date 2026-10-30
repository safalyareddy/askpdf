#!/usr/bin/env bash
# =====================================================================
# AskPDF — Safe Shutdown Script
# Product: AskPDF — "Your documents. Your answers."
# Terminates only AskPDF server and its ngrok tunnel.
# =====================================================================
set -e

echo "Stopping AskPDF services..."

# 1. Stop backend on port 8000
SERVER_PID=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[*] Stopping AskPDF backend (PID: $SERVER_PID)..."
    kill $SERVER_PID 2>/dev/null || true
    sleep 1
    # Force kill if still lingering
    if kill -0 $SERVER_PID 2>/dev/null; then
        kill -9 $SERVER_PID 2>/dev/null || true
    fi
    echo "[✓] Backend on port 8000 stopped."
else
    echo "[-] No process found listening on port 8000."
fi

# 2. Stop ngrok if tunneling port 8000
NGROK_PIDS=$(pgrep -f "ngrok http 8000" 2>/dev/null || true)
if [ -n "$NGROK_PIDS" ]; then
    echo "[*] Stopping ngrok port 8000 tunnel (PID(s): $NGROK_PIDS)..."
    kill $NGROK_PIDS 2>/dev/null || true
    echo "[✓] ngrok tunnel stopped."
else
    echo "[-] No ngrok tunnel active on port 8000."
fi

echo "[✓] AskPDF services successfully shut down."
