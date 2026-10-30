# 📄 AskPDF — Your documents. Your answers.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store%20v2.0-FF6F00?style=flat)](https://trychroma.com)
[![Vercel](https://img.shields.io/badge/Vercel-Frontend%20Hosting-000000?style=flat&logo=vercel&logoColor=white)](https://vercel.com)
[![Railway](https://img.shields.io/badge/Railway-Backend%20Cloud-0B0D0E?style=flat&logo=railway&logoColor=white)](https://railway.app)
[![Groq](https://img.shields.io/badge/Groq-Llama%203.1%20Inference-F05A28?style=flat)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Llama--3%20(Local)-white?style=flat&logo=ollama&logoColor=black)](https://ollama.com)
[![Tests](https://img.shields.io/badge/Tests-32%20Passed%20(100%25)-brightgreen?style=flat)](TEST_RESULTS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade document intelligence platform that allows users to upload PDF documents, ask natural-language questions, retrieve relevant passages, and receive answers strictly grounded in document evidence.

**AskPDF** is designed for high reliability across both **Production Cloud Deployment** (Vercel Frontend + Railway FastAPI Backend with Persistent Storage + Hosted Llama 3.1 Inference) and **Local Offline Deployment** (Apple Silicon macOS + Ollama + Local ChromaDB).

---

## 📑 Core Documentation Index

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Cloud and local system architecture, data flow, and 9-layer component specification.
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: Step-by-step production cloud setup for Vercel, Railway, and Groq Cloud.
- **[RAG_PIPELINE.md](RAG_PIPELINE.md)**: Page-aware PDF ingestion, dense vector indexing, and hybrid reranking pipeline.
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)**: Complete REST API specification for public and administrative endpoints.
- **[EVALUATION_REPORT.md](EVALUATION_REPORT.md)**: Verified ground-truth benchmark metrics (Recall@5: 100%, MRR: 0.905, Attribution: 100%).
- **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)**: Threat models, constant-time authentication, rate limiting, and defensive response parsing.
- **[TEST_RESULTS.md](TEST_RESULTS.md)**: 32-test automated pytest execution logs and coverage breakdown.
- **[BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)**: Disaster recovery runbooks and persistent volume snapshot procedures.
- **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**: Technical boundaries, context limits, and token constraints.
- **[CHANGELOG.md](CHANGELOG.md)**: Complete upgrade history and release notes.

---

## ✨ Key Capabilities

- **24/7 Cloud Architecture (Laptop Independent)**:
  - Deploys on **Vercel** (static frontend with dynamic API routing) and **Railway** (FastAPI backend in Docker container).
  - Uses hosted OpenAI-compatible inference (**Groq Cloud** or **OpenAI**) so the application works even when your computer is switched off.
- **Persistent Cloud Storage**:
  - Railway persistent volume mounted at `/app/data` (PDFs) and `/app/db` (ChromaDB vector store + registry).
  - Survives container restarts, code updates, and redeployments.
- **Accurate Dual-Page Citations**:
  - *Physical PDF Page Number*: The 1-indexed page position in standard PDF readers.
  - *Printed Page Number*: The page number printed on headers or footers.
  - *Citation format*: `Document.pdf — PDF page 4 (printed page 3)`.
- **Anti-TOC Pollution & Section Extraction**:
  - Automatically identifies and filters Table of Contents dot leaders (`Abstract ........ 3`), routing directly to substantive sections.
  - Dedicated intent recognition for abstracts, executive summaries, conclusions, and cross-document comparisons.
- **Hybrid Keyword Reranking**:
  - Combines dense vector similarity (`BAAI/bge-small-en-v1.5`) with lexical query-overlap scoring and metadata heading boosting to achieve 100% Recall@5.
- **Interactive Multi-Document Disambiguation**:
  - Displays interactive selection cards when queries are ambiguous across multiple uploaded documents.
  - Preserves document context across multi-turn follow-up queries using `session_id`.
- **Hardened Security Architecture**:
  - Administrative endpoints require header authentication (`X-Admin-Key`) verified with constant-time comparison (`secrets.compare_digest`).
  - Strict magic-byte (`%PDF-`) validation and path traversal sanitization.
  - Per-IP sliding-window rate limiting.

---

## 🏗️ Dual-Mode Architecture

```
                                  PUBLIC USERS (Browser)
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │                                           │
                       ▼                                           ▼
       ┌───────────────────────────────┐           ┌───────────────────────────────┐
       │   CLOUD PRODUCTION (Vercel)   │           │    LOCAL WORKSTATION (Mac)    │
       │    https://askpdf.vercel.app  │           │     http://localhost:8000     │
       └───────────────┬───────────────┘           └───────────────┬───────────────┘
                       │ HTTPS / CORS                              │ HTTP
                       ▼                                           ▼
       ┌───────────────────────────────┐           ┌───────────────────────────────┐
       │   RAILWAY FASTAPI CONTAINER   │           │    LOCAL FASTAPI INSTANCE     │
       │    FastAPI + Uvicorn ($PORT)  │           │   FastAPI + Uvicorn (Port 8000│
       ├───────────────────────────────┤           ├───────────────────────────────┤
       │ • Persistent Volume (/app/db) │           │ • Local Storage (./data, ./db)│
       │ • BGE-Small CPU Embeddings    │           │ • BGE-Small CPU Embeddings    │
       │ • Groq Cloud (Llama 3.1 8B)   │           │ • Ollama Local (Llama 3 8B)   │
       └───────────────────────────────┘           └───────────────────────────────┘
```

---

## 🚀 Cloud Deployment

### 1. Deploy Backend on Railway
1. Push to GitHub repo `https://github.com/safalyareddy/askpdf`.
2. Connect the repository in [Railway](https://railway.app).
3. Railway automatically builds via `Dockerfile` and `railway.json`.
4. Attach a **Persistent Volume** mounted at `/app/data` and `/app/db`.
5. Set environment variables:
   ```env
   PORT=8000
   LLM_PROVIDER=groq
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=llama-3.1-8b-instant
   LLM_API_KEY=gsk_your_groq_api_key_here
   SUPER_USER_KEY=your_secure_admin_key_here
   ```
6. Generate a public domain (e.g., `https://askpdf-production.up.railway.app`).

### 2. Deploy Frontend on Vercel
1. In [Vercel](https://vercel.com), import `safalyareddy/askpdf`.
2. Use Framework Preset `Other` with root directory `./`.
3. Click **Deploy**. Vercel serves the application according to `vercel.json`.
4. In the deployed frontend, click the system status badge to save your Railway backend domain in the settings modal.

---

## 💻 Local Apple Silicon Setup

```bash
# 1. Setup Virtual Environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Start Local Ollama
ollama serve &
ollama pull llama3:latest

# 3. Launch AskPDF
./START_ASKPDF.sh
```

- Web UI: `http://localhost:8000`
- Admin Portal: `http://localhost:8000/admin`
- Health: `http://localhost:8000/health`
- API Docs: `http://localhost:8000/docs`

---

## 🧪 Evaluation Benchmark Results

Tested against verified ground-truth student project reports (`23MIS0125_ListLocal_Safalya.pdf` and `23MIS0125_FreshCart_Lab_Assignment_8.pdf`):

| Metric | Target | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Recall@5** | ≥ 80.0% | **100.0%** | **PASS** |
| **Mean Reciprocal Rank (MRR)** | ≥ 0.70 | **0.905** | **PASS** |
| **Page Attribution Accuracy** | 100.0% | **100.0%** | **PASS** |
| **Session Memory Retention** | 100.0% | **100.0%** | **PASS** |
| **TOC Pollution Rate** | 0.0% | **0.0%** (Clean) | **PASS** |
| **Mean Latency (Local CPU)** | < 25.0s | **17.19s** | **PASS** |
| **Citation Precision** | Reference | **46.2%** | *Evaluated* |

> *Note on Citation Precision:* In multi-chunk dense retrieval, top-5 context windows naturally contain broader section evidence alongside targeted sentences. Furthermore, unanswerable queries return nearest background passages which the guardrail correctly refuses to synthesize, resulting in clean 0-citation refusals.

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.