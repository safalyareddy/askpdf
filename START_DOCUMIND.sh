#!/usr/bin/env bash
# =====================================================================
# DocuMind AI — Autonomous Local + ngrok Startup Script
# Platform: macOS Apple Silicon (M-Series)
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[Note] DocuMind AI has evolved into AskPDF — 'Your documents. Your answers.'"
exec "$SCRIPT_DIR/START_ASKPDF.sh" "$@"

# 1. Dependency checks
if [ ! -d ".venv" ]; then
    echo "[-] Virtual environment (.venv) not found. Creating..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
UVICORN_BIN="$SCRIPT_DIR/.venv/bin/uvicorn"

if [ ! -f "$UVICORN_BIN" ]; then
    echo "[-] Installing dependencies into virtual environment..."
    .venv/bin/pip install -r requirements.txt
fi

# Ensure data and db directories exist
mkdir -p data db logs

# 2. Check Ollama (if provider is set to ollama)
if command -v ollama >/dev/null 2>&1; then
    if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[*] Ollama service not running. Attempting to start in background..."
        ollama serve > logs/ollama.log 2>&1 &
        sleep 2
    else
        echo "[✓] Local Ollama service active on http://127.0.0.1:11434"
    fi
else
    echo "[!] Ollama CLI not found in PATH. Ensure Ollama is running or Groq LLM_API_KEY is configured."
fi

# 3. Start or check DocuMind AI backend (Port 8000)
SERVER_PID=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[✓] DocuMind AI backend is already running (PID: $SERVER_PID) on port 8000."
else
    echo "[*] Launching DocuMind AI backend server on port 8000..."
    nohup "$UVICORN_BIN" main:app --host 0.0.0.0 --port 8000 > logs/server.log 2>&1 &
    NEW_PID=$!
    echo "[*] Waiting for backend initialization (PID: $NEW_PID)..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "[✓] DocuMind AI backend successfully initialized!"
            break
        fi
        sleep 1
    done
fi

# 4. Start or check ngrok Public Tunnel
if ! command -v ngrok >/dev/null 2>&1; then
    echo "[!] ngrok is not installed or not in PATH."
    echo "    Install with: brew install ngrok"
    echo "    Your backend remains available locally at: http://localhost:8000"
    exit 0
fi

NGROK_URL=""
# Check if ngrok is already running and tunneling port 8000
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
echo "    DocuMind AI is ONLINE and OPERATIONAL"
echo "======================================================"
echo "  • Local Q&A UI       : http://localhost:8000"
echo "  • Local Admin Portal : http://localhost:8000/admin"
echo "  • Local Health API   : http://localhost:8000/health"
if [ -n "$NGROK_URL" ]; then
echo "  • Public ngrok URL   : $NGROK_URL"
echo "  • Public Admin       : $NGROK_URL/admin"
else
echo "  • Public ngrok URL   : Tunnel starting... run 'curl http://127.0.0.1:4040/api/tunnels' to inspect."
fi
echo "======================================================"
echo "  Logs: tail -f logs/server.log logs/ngrok.log"
echo "  To stop: ./STOP_DOCUMIND.sh"
echo "======================================================"
