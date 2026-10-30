# AskPDF — Deployment & Operations Guide (v2.0)

This guide provides end-to-end instructions for deploying, configuring, operating, and troubleshooting **AskPDF** on local Apple Silicon hardware (macOS M1/M2/M3/M4) exposed securely via an ngrok public tunnel.

---

## 1. System Requirements

### Hardware Requirements
- **Architecture:** Apple Silicon (ARM64: M1, M2, M3, M4).
- **RAM:** 16 GB Unified Memory recommended (minimum 8 GB).
- **Disk Storage:** At least 10 GB free SSD storage (for Ollama model weights, embedding models, and ChromaDB vector store).

### Software Requirements
- **Operating System:** macOS 14 (Sonoma) or macOS 15 (Sequoia).
- **Python:** Python 3.11.x (verified on Python 3.11.15).
- **Ollama:** Version 0.1.30 or higher (with `llama3:latest` pulled).
- **ngrok CLI:** Version 3.x with authenticated account.

---

## 2. Architecture Overview & Network Flow

```
   Public Internet (Browser / Client)
                   │
                   ▼ HTTPS (TLS Termination)
    https://yer-superindifferent-lore.ngrok-free.dev
                   │
                   ▼ ngrok Secure Tunnel Agent (Port 4040 web UI)
        127.0.0.1:8000 (FastAPI Backend)
             ├── /health (Health & Status)
             ├── /documents (Active Document Registry)
             ├── /ask (RAG Ingestion, Retrieval, & Generation)
             └── /admin/* (Fail-Closed Admin Management)
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  ChromaDB (Port 8000)   Ollama Service
  BAAI/bge-small-en-v1.5  http://127.0.0.1:11434
  (384-dim dense vectors) (llama3:latest 8B)
```

---

## 3. Environment Configuration (`.env`)

Create or update the `.env` file in the project root directory. Use `.env.example` as a template:

```bash
# -----------------------------------------------------------------------------
# DocuMind AI — Environment Configuration
# -----------------------------------------------------------------------------

# Primary LLM Provider: 'ollama' (local inference) or 'openai_like' (cloud hosted)
LLM_PROVIDER=ollama

# Ollama Configuration (Local Apple Silicon)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_NUM_CTX=4096

# Embedding Model Configuration
EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
EMBEDDING_DEVICE=cpu

# Storage Directories
DATA_DIRECTORY=data
CHROMA_PERSIST_DIRECTORY=db
MAX_UPLOAD_SIZE_MB=20

# Admin Security Gatekeeper
# CRITICAL: Set a strong, random key in production. Never leave empty!
SUPER_USER_KEY=your_generated_super_secret_key_here

# Network & Rate Limiting
HOST=0.0.0.0
PORT=8000
RATE_LIMIT_PER_MINUTE=30
```

### Environment Variable Reference

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | string | `ollama` | Engine used for text generation (`ollama` or `openai_like`). |
| `OLLAMA_BASE_URL` | string | `http://localhost:11434` | Endpoint for the local Ollama daemon. |
| `OLLAMA_MODEL` | string | `llama3:latest` | Target Ollama model name. |
| `OLLAMA_NUM_CTX` | int | `4096` | Context window size in tokens. |
| `EMBEDDING_MODEL_NAME` | string | `BAAI/bge-small-en-v1.5` | HuggingFace embedding model ID. |
| `EMBEDDING_DEVICE` | string | `cpu` | Device for embedding inference (`cpu` or `mps`). |
| `SUPER_USER_KEY` | string | *(required)* | Secret bearer token required for all `/admin/*` operations. |
| `RATE_LIMIT_PER_MINUTE` | int | `30` | Maximum requests permitted per IP per 60-second sliding window. |
| `PORT` | int | `8000` | Local port for FastAPI Uvicorn server. |

---

## 4. Step-by-Step Installation

### Step 1: Set Up Python Environment
Ensure Python 3.11 is active:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Step 2: Configure Ollama
Verify Ollama is installed and running:
```bash
# Check Ollama version
ollama --version

# Pull the primary Llama 3 model
ollama pull llama3:latest

# Verify the model is available
ollama list
```

### Step 3: Configure ngrok
Authenticate ngrok if not already completed:
```bash
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
```

---

## 5. Startup & Shutdown Operations

AskPDF provides production-ready shell scripts for one-click startup and graceful shutdown:

#### Start All Services
```bash
./START_ASKPDF.sh
```
*(Also callable via `./START_DOCUMIND.sh` for backward compatibility).*

This script automatically:
1. Validates prerequisites (Python 3.11 venv, Ollama CLI, ngrok CLI).
2. Verifies `.env` exists and contains a non-empty `SUPER_USER_KEY`.
3. Checks for and starts the Ollama daemon if inactive.
4. Checks for and pulls `llama3:latest` if missing.
5. Frees port 8000 if occupied by a stale process.
6. Launches Uvicorn on `http://127.0.0.1:8000`.
7. Waits for backend health check (`/health`) to pass.
8. Launches ngrok on port 8000 with your static domain.
9. Displays active local and public endpoints.

#### Stop All Services
```bash
./STOP_ASKPDF.sh
```
*(Also callable via `./STOP_DOCUMIND.sh`).*

This script gracefully stops:
- The Uvicorn FastAPI backend process.
- The ngrok tunnel process.
*(Ollama daemon is left running for system efficiency).*

---

### Alternative: Manual Process Management

If you prefer to run services in separate terminal sessions:

#### Terminal 1 — Ollama Daemon:
```bash
ollama serve
```

#### Terminal 2 — FastAPI Backend:
```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### Terminal 3 — ngrok Tunnel:
```bash
ngrok http 8000 --domain=yer-superindifferent-lore.ngrok-free.dev
```

---

## 6. Verifying the Deployment

Run the following checks to confirm end-to-end functionality:

### Check 1: Health Endpoint
```bash
curl -s http://localhost:8000/health | jq .
```
Expected response:
```json
{
  "status": "healthy",
  "pipeline_ready": true,
  "documents_indexed": 2,
  "ollama": {
    "status": "healthy",
    "provider": "ollama",
    "model": "llama3:latest"
  }
}
```

### Check 2: Active Documents Endpoint
```bash
curl -s http://localhost:8000/documents | jq .
```
Expected response:
```json
{
  "documents": [
    {
      "document_id": "doc_73a35d9771",
      "filename": "23MIS0125_FreshCart_Lab_Assignment_8.pdf",
      "display_name": "23MIS0125 FreshCart Lab Assignment 8",
      "upload_order": 1,
      "pages": 22,
      "chunks": 61,
      "size_kb": 5738.2
    },
    {
      "document_id": "doc_91a1737480",
      "filename": "23MIS0125_ListLocal_Safalya.pdf",
      "display_name": "23MIS0125 ListLocal Safalya",
      "upload_order": 2,
      "pages": 37,
      "chunks": 124,
      "size_kb": 2304.5
    }
  ],
  "total": 2
}
```

### Check 3: Admin Authentication Enforcement
```bash
# Request without key must return HTTP 403
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/admin/list-pdfs
# Output: 403

# Request with valid key must return HTTP 200
curl -s -H "X-Admin-Key: $(grep SUPER_USER_KEY .env | cut -d= -f2)" http://localhost:8000/admin/list-pdfs | jq .
```

### Check 4: Public ngrok Verification
```bash
curl -s https://yer-superindifferent-lore.ngrok-free.dev/health | jq .
```

---

## 7. Network & Port Conflict Troubleshooting

### Port 8000 Conflict (`Address already in use`)
If port 8000 is occupied by a stale server:
```bash
# Identify the process occupying port 8000
lsof -i :8000

# Terminate the process
kill -9 $(lsof -ti :8000)
```

### Ollama Port 11434 Unavailable
If Ollama fails to respond:
```bash
# Verify process status
pgrep -fl ollama

# Restart Ollama on macOS
killall ollama
ollama serve &
```

### ngrok Tunnel Reconnect Issues
If ngrok encounters `ERR_NGROK_3200` or fails to bind the domain:
1. Ensure only one ngrok instance is running: `killall ngrok`.
2. Inspect the local dashboard at `http://localhost:4040`.
3. Check ngrok account status for tunnel limits.

### High Memory Usage on Apple Silicon
If `llama3` causes unified memory pressure:
1. Ensure `OLLAMA_NUM_CTX=4096` in `.env` (avoid setting to 8192+ on 16 GB machines).
2. The chunk batcher in `core/vector_store.py` processes 32 chunks per batch with explicit `gc.collect()`.
3. Close unused memory-intensive applications when indexing documents exceeding 100 pages.
