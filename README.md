# 📄 AskPDF — Your documents. Your answers.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store%20v2.0-FF6F00?style=flat)](https://trychroma.com)
[![Render](https://img.shields.io/badge/Render-Unified%20Hosting-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)
[![Groq](https://img.shields.io/badge/Groq-Llama%203.1%20Inference-F05A28?style=flat)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Ollama-Llama--3%20(Local)-white?style=flat&logo=ollama&logoColor=black)](https://ollama.com)
[![Tests](https://img.shields.io/badge/Tests-34%20Passed%20(100%25)-brightgreen?style=flat)](TEST_RESULTS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade document intelligence platform that allows users to upload PDF documents, ask natural-language questions, retrieve relevant passages, and receive answers strictly grounded in document evidence.

**AskPDF** is unified into a single zero-cost deployment on **Render** (serving both the interactive single-page web app and the FastAPI RAG backend with Groq Llama 3.1 inference) as well as **Local Offline Deployment** (macOS + Ollama + Local ChromaDB).

---

## 📑 Core Documentation Index

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Cloud and local system architecture, data flow, and 9-layer component specification.
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: Production cloud setup for Render and Groq Cloud.
- **[RAG_PIPELINE.md](RAG_PIPELINE.md)**: Page-aware PDF ingestion, dense vector indexing, and hybrid reranking pipeline.
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)**: Complete REST API specification for public and administrative endpoints.
- **[EVALUATION_REPORT.md](EVALUATION_REPORT.md)**: Verified ground-truth benchmark metrics (Recall@5: 100%, MRR: 0.905, Attribution: 100%).
- **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)**: Threat models, constant-time authentication, rate limiting, and defensive response parsing.
- **[TEST_RESULTS.md](TEST_RESULTS.md)**: 34-test automated pytest execution logs and coverage breakdown.
- **[BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)**: Disaster recovery runbooks and data snapshot procedures.
- **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**: Technical boundaries, context limits, and token constraints.
- **[CHANGELOG.md](CHANGELOG.md)**: Complete upgrade history and release notes.

---

## ✨ Key Capabilities

- **Zero-Cost Unified Cloud Architecture (₹0/month)**:
  - Deploys frontend Single Page Application and FastAPI backend together on **Render**.
  - Direct same-origin requests eliminate CORS latency, Vercel build drifts, and environment configuration headaches.
  - Hosted OpenAI-compatible inference (**Groq Cloud Llama 3.1**) provides instant Q&A without requiring local GPU/compute.
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

## 🏗️ System Architecture

```
                                  PUBLIC USERS (Browser)
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │                                           │
                       ▼                                           ▼
       ┌───────────────────────────────┐           ┌───────────────────────────────┐
       │     RENDER (Unified Cloud)    │           │    LOCAL WORKSTATION (Mac)    │
       │ https://documind-ai-ddt8.     │           │     http://localhost:8000     │
       │ onrender.com                  │           │                               │
       ├───────────────────────────────┤           ├───────────────────────────────┤
       │ • Static SPA (index, admin)   │           │ • Static SPA (index, admin)   │
       │ • FastAPI REST Engine         │           │ • FastAPI REST Engine         │
       │ • ChromaDB Vector Index       │           │ • ChromaDB Vector Index       │
       │ • BGE-Small CPU Embeddings    │           │ • BGE-Small CPU Embeddings    │
       │ • Groq Cloud (Llama 3.1 8B)   │           │ • Ollama Local (Llama 3 8B)   │
       └───────────────────────────────┘           └───────────────────────────────┘
```

---

## 🚀 Live Production Deployment

The unified application is live and publicly accessible:
- **Web App**: [https://documind-ai-ddt8.onrender.com](https://documind-ai-ddt8.onrender.com)
- **Document Management Portal**: [https://documind-ai-ddt8.onrender.com/admin](https://documind-ai-ddt8.onrender.com/admin)
- **Health Check**: [https://documind-ai-ddt8.onrender.com/health](https://documind-ai-ddt8.onrender.com/health)
- **Interactive API Docs**: [https://documind-ai-ddt8.onrender.com/docs](https://documind-ai-ddt8.onrender.com/docs)

### Deployment Setup (Render)
1. Push to GitHub repo `https://github.com/safalyareddy/askpdf`.
2. Connect repo to [Render](https://render.com) using the root `render.yaml` or create a Web Service using the repo's `Dockerfile`.
3. Set environment variables in Render Dashboard:
   ```env
   PORT=8000
   LLM_PROVIDER=groq
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=llama-3.1-8b-instant
   LLM_API_KEY=gsk_your_groq_api_key_here
   SUPER_USER_KEY=your_secure_admin_key_here
   ```
4. Render builds the Docker image and serves both the frontend SPA and FastAPI backend under your public `.onrender.com` domain.

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