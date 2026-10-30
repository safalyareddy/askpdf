# AskPDF — Cloud & Local Deployment Guide (v2.0)

> **Product Identity:** AskPDF  
> **Tagline:** *Your documents. Your answers.*  
> **Repository:** [https://github.com/safalyareddy/askpdf](https://github.com/safalyareddy/askpdf)

This guide documents the production cloud deployment architecture on **Vercel** and **Railway**, persistent storage configuration, hosted cloud LLM inference setup (independent of your local machine), and local Apple Silicon development workflows.

---

## 1. Production Cloud Architecture

AskPDF uses a decoupled, high-availability cloud architecture designed to remain operational 24/7 without requiring any local workstation to stay online:

```
                            ┌───────────────────────────────────────┐
                            │           PUBLIC CLIENT               │
                            │      Desktop & Mobile Browsers        │
                            └───────────────────┬───────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       │                                                 │
                       ▼ HTTPS                                           ▼ HTTPS
       ┌───────────────────────────────┐                 ┌───────────────────────────────┐
       │        VERCEL FRONTEND        │                 │        RAILWAY BACKEND        │
       │    https://askpdf.vercel.app  │                 │ https://askpdf.up.railway.app │
       │                               │                 │                               │
       │  • index.html (Q&A Interface) │◄────────────────┤  • FastAPI 0.115+ (Uvicorn)   │
       │  • admin.html (Document Mgt)  │  CORS-Enabled   │  • /health, /documents, /ask  │
       │  • vercel.json (Clean Routes) │   JSON REST     │  • /admin/* (Header Auth)     │
       │  • Dynamic Backend URL Config │                 │  • BAAI/bge-small-en-v1.5     │
       └───────────────────────────────┘                 └───────────────┬───────────────┘
                                                                         │
                                         ┌───────────────────────────────┴───────────────────────────────┐
                                         │                                                               │
                                         ▼ Persistent Storage                                            ▼ Cloud Inference API
                         ┌───────────────────────────────┐                               ┌───────────────────────────────┐
                         │   RAILWAY PERSISTENT VOLUME   │                               │       HOSTED LLM SERVICE      │
                         │      Mount: /app/data, /app/db│                               │      Groq Cloud or OpenAI     │
                         │                               │                               │                               │
                         │  • /app/data/*.pdf            │                               │  • llama-3.1-8b-instant       │
                         │  • /app/db/chroma.sqlite3     │                               │  • Ultra-low latency (<1.5s)  │
                         │  • documents_registry.json    │                               │  • Zero Mac dependency        │
                         └───────────────────────────────┘                               └───────────────────────────────┘
```

---

## 2. Decoupled Cloud LLM Inference

In the original local setup, AskPDF communicated with Ollama on `localhost:11434`. A cloud container running on Railway cannot access your local MacBook.

To guarantee that AskPDF works continuously even when your laptop is turned off:
1. **Embedding Model (`BAAI/bge-small-en-v1.5`):** Runs directly inside the Railway container on PyTorch CPU. It produces 384-dimensional dense vectors with zero external API dependencies and uses only ~130 MB of container RAM.
2. **LLM Synthesis:** Decoupled into an OpenAI-compatible cloud inference provider configured via environment variables:

### Recommended Cloud Provider: Groq Cloud (Free / Ultra-Fast)
- **Model:** `llama-3.1-8b-instant` or `llama-3.3-70b-versatile`
- **Cost:** Generous free tier (up to 30 requests/minute, zero credit card required).
- **Latency:** ~0.5 to 1.5 seconds (over 10x faster than local CPU inference).
- **Configuration:**
  ```env
  LLM_PROVIDER=groq
  LLM_BASE_URL=https://api.groq.com/openai/v1
  LLM_MODEL=llama-3.1-8b-instant
  LLM_API_KEY=gsk_your_groq_api_key_here
  ```

### Alternative Cloud Provider: OpenAI
- **Model:** `gpt-4o-mini`
- **Configuration:**
  ```env
  LLM_PROVIDER=openai
  LLM_BASE_URL=https://api.openai.com/v1
  LLM_MODEL=gpt-4o-mini
  LLM_API_KEY=sk-your_openai_api_key_here
  ```

---

## 3. Deploying the Backend on Railway

### Repository
- GitHub: `https://github.com/safalyareddy/askpdf`
- Branch: `feature/askpdf-upgrade` (or `main`)

### Deployment Steps
1. Log in to [Railway](https://railway.app).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select `safalyareddy/askpdf`.
4. Railway automatically detects `railway.json` and builds using the production `Dockerfile`.
5. **Attach Persistent Storage Volume:**
   - In your Railway service dashboard, click **Volumes** → **Add Volume**.
   - Set the mount path to: `/app/data` (for uploaded PDFs).
   - Add a second volume or mount a single volume at `/data` with subdirectories:
     - Set environment variable `PDF_DIR=/app/data/`
     - Set environment variable `PERSIST_DIR=/app/db`
   - *Result:* Uploaded documents and ChromaDB vector embeddings persist permanently across container restarts, code updates, and redeployments.
6. **Configure Environment Variables:**
   Under the **Variables** tab, set:
   ```env
   PORT=8000
   LLM_PROVIDER=groq
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=llama-3.1-8b-instant
   LLM_API_KEY=gsk_your_groq_api_key_here
   SUPER_USER_KEY=your_strong_random_admin_key_here
   EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
   EMBEDDING_DEVICE=cpu
   DATA_DIRECTORY=/app/data
   CHROMA_PERSIST_DIRECTORY=/app/db
   RATE_LIMIT_PER_MINUTE=60
   ```
7. **Generate Domain:**
   Under **Settings** → **Networking** → **Generate Domain**.
   Railway will assign an HTTPS endpoint, for example: `https://askpdf-production.up.railway.app`.
8. **Verify Backend Health:**
   ```bash
   curl https://your-railway-domain.up.railway.app/health
   ```
   Expect:
   ```json
   {
     "status": "healthy",
     "app": "AskPDF",
     "tagline": "Your documents. Your answers.",
     "version": "2.0.0",
     "engine_ready": true,
     "model_online": true,
     "admin_auth_configured": true
   }
   ```

---

## 4. Deploying the Frontend on Vercel

### Repository
- GitHub: `https://github.com/safalyareddy/askpdf`

### Deployment Steps
1. Log in to [Vercel](https://vercel.com).
2. Click **Add New...** → **Project** → Import `safalyareddy/askpdf`.
3. In Project Settings:
   - **Framework Preset:** `Other`
   - **Root Directory:** `./`
   - **Build Command:** *(Leave empty)*
   - **Output Directory:** `./`
4. Click **Deploy**.
5. Vercel deploys the application using `vercel.json`:
   - `/` serves `index.html` (AskPDF Question Answering Portal)
   - `/admin` cleanly routes to `admin.html` (Document Management Portal) without 404s
   - Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`) are applied automatically.

### Connecting Frontend to Railway Backend
AskPDF features dynamic zero-recompile backend routing:
- **Option A (UI Modal):** On your deployed Vercel site, click the system status badge in the header (`Connecting...` or `Offline` with the gear icon). Enter your Railway backend domain (e.g., `https://askpdf-production.up.railway.app`), and click **Save & Connect**. The setting persists in `localStorage` across all browser sessions.
- **Option B (Window Global):** Inject `window.ASKPDF_API_URL = "https://your-railway-app.up.railway.app";` if using custom domain scripts.

---

## 5. Local Development & Offline Inference

AskPDF preserves full offline privacy on Apple Silicon:

### Prerequisites
- macOS 14+ (Apple Silicon M1/M2/M3/M4)
- Python 3.11.x
- Ollama with `llama3:latest`

### Startup Commands
```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Start local Ollama daemon
ollama serve &
ollama pull llama3:latest

# 3. Launch AskPDF local backend
./START_ASKPDF.sh
```

Local endpoints:
- Homepage & Q&A: `http://localhost:8000`
- Document Management: `http://localhost:8000/admin`
- Health check: `http://localhost:8000/health`
- OpenAPI Docs: `http://localhost:8000/docs`

### Graceful Shutdown
```bash
./STOP_ASKPDF.sh
```

---

## 6. Security & Admin Operations

### Admin Authorization
- All `/admin/*` operations (`/admin/list-pdfs`, `/admin/upload-pdf`, `/admin/delete-pdf`) strictly require the `X-Admin-Key` request header.
- Verification uses constant-time comparison (`secrets.compare_digest`) to prevent timing side-channel attacks.
- Query parameter authentication is forbidden.
- Keys are kept in browser `sessionStorage` and never logged or exposed in client bundles.

### Rate Limiting
- Public endpoints are protected by an in-memory sliding-window rate limiter (default: 30–60 req/min/IP).

---

## 7. Cost Control & Estimation

| Service | Tier | Estimated Cost | Notes |
| :--- | :--- | :--- | :--- |
| **Vercel** | Hobby / Free | **$0.00 / month** | 100 GB bandwidth, unlimited deployments. |
| **Railway** | Starter / Trial | **$0.00 to ~$5.00 / month** | $5 free monthly credit. Container uses ~250MB RAM with PyTorch CPU. |
| **Groq Cloud** | Free Tier | **$0.00 / month** | 30 requests/min, 14,400 requests/day free. |
| **Total Cloud Operating Cost** | | **$0.00 / month** (within free tier) | |
