#!/usr/bin/env bash
# =====================================================================
# AskPDF — Autonomous Local Startup Script
# Product: AskPDF — "Your documents. Your answers."
# Platform: macOS Apple Silicon (M-Series)
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================"
echo "    AskPDF — Your documents. Your answers."
echo "    Local Runtime + ngrok Public Tunnel Launcher"
echo "======================================================"

# 1. Dependency and Environment Checks
if [ ! -d ".venv" ]; then
    echo "[-] Virtual environment (.venv) not found. Creating..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
UVICORN_BIN="$SCRIPT_DIR/.venv/bin/uvicorn"

if [ ! -f "$UVICORN_BIN" ]; then
    echo "[-] Installing requirements into .venv..."
    .venv/bin/pip install -r requirements.txt
fi

# Ensure runtime directories exist
mkdir -p data db logs

# 2. Check and Validate Ollama and Llama-3 Model
if command -v ollama >/dev/null 2>&1; then
    if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[*] Ollama service not running. Starting in background..."
        ollama serve > logs/ollama.log 2>&1 &
        sleep 2
    else
        echo "[✓] Local Ollama service active on http://127.0.0.1:11434"
    fi

    # Verify model
    if curl -s http://127.0.0.1:11434/api/tags | grep -q "llama3"; then
        echo "[✓] Llama-3 model verified in Ollama."
    else
        echo "[*] Pulling llama3:latest model into Ollama (one-time setup)..."
        ollama pull llama3:latest
    fi
else
    echo "[!] Ollama CLI not detected in system PATH. Ensure Ollama daemon is active."
fi

# 3. Check and Start AskPDF Backend (Port 8000)
SERVER_PID=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[✓] AskPDF backend is already running (PID: $SERVER_PID) on port 8000."
else
    echo "[*] Launching AskPDF backend server on port 8000..."
    nohup "$UVICORN_BIN" main:app --host 0.0.0.0 --port 8000 > logs/server.log 2>&1 &
    NEW_PID=$!
    echo "[*] Waiting for AskPDF backend initialization (PID: $NEW_PID)..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "[✓] AskPDF backend successfully initialized!"
            break
        fi
        sleep 1
    done
fi

# 4. Check and Start ngrok Public Tunnel
if ! command -v ngrok >/dev/null 2>&1; then
    echo "[!] ngrok is not installed or not in PATH."
    echo "    Install with: brew install ngrok"
    echo "    Your backend remains available locally at: http://localhost:8000"
    exit 0
fi

NGROK_URL=""
# Check if ngrok is already tunneling port 8000
if curl -s http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
    NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels | grep -o 'https://[^"]*ngrok[^"]*' | head -n 1 || true)
fi

if [ -z "$NGROK_URL" ]; then
    echo "[*] Starting ngrok public tunnel on port 8000..."
    nohup ngrok http 8000 --log=stdout > logs/ngrok.log 2>&1 &
    sleep 3
    for i in {1..10}; do
        if curl -s http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
            NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels | grep -o 'https://[^"]*ngrok[^"]*' | head -n 1 || true)
            if [ -n "$NGROK_URL" ]; then break; fi
        fi
        sleep 1
    done
fi

echo ""
echo "======================================================"
echo "    AskPDF is ONLINE and OPERATIONAL"
echo "    Tagline: Your documents. Your answers."
echo "======================================================"
echo "  • Local Q&A UI       : http://localhost:8000"
echo "  • Local Admin Portal : http://localhost:8000/admin"
echo "  • Local Health API   : http://localhost:8000/health"
if [ -n "$NGROK_URL" ]; then
echo "  • Public ngrok URL   : $NGROK_URL"
echo "  • Public Admin Portal: $NGROK_URL/admin"
echo "  • Public Health API  : $NGROK_URL/health"
fi
echo "  • Log Files          : logs/server.log, logs/ngrok.log"
echo "======================================================"
echo "  To stop all services: ./STOP_ASKPDF.sh"
echo "======================================================"
