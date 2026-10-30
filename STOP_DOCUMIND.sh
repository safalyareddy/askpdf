#!/usr/bin/env bash
# =====================================================================
# DocuMind AI — Safe Shutdown Script
# Terminates only DocuMind AI server and its ngrok tunnel.
# =====================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[Note] DocuMind AI has evolved into AskPDF — 'Your documents. Your answers.'"
exec "$SCRIPT_DIR/STOP_ASKPDF.sh" "$@"
SERVER_PID=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[*] Stopping DocuMind AI backend (PID: $SERVER_PID)..."
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

echo "[✓] DocuMind AI services successfully shut down."
