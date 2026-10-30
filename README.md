# 📄 AskPDF — Your documents. Your answers.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store%20v2.0-FF6F00?style=flat)](https://trychroma.com)
[![Ollama](https://img.shields.io/badge/Ollama-Llama--3%20(Local)-white?style=flat&logo=ollama&logoColor=black)](https://ollama.com)
[![ngrok](https://img.shields.io/badge/ngrok-Public%20Tunnel-blue?style=flat&logo=ngrok&logoColor=white)](https://ngrok.com)
[![Tests](https://img.shields.io/badge/Tests-32%20Passed%20(100%25)-brightgreen?style=flat)](TEST_RESULTS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade, locally deployed document intelligence platform that allows users to upload PDF documents, ask natural-language questions, retrieve relevant information, and receive answers strictly grounded in document evidence.

Powered by **FastAPI**, **ChromaDB**, **Sentence Transformers (`BAAI/bge-small-en-v1.5`)**, and local **Ollama (`llama3:latest`)** running natively on Apple Silicon.

---

## 📑 Core Documentation Index

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Modular design specification, 9-layer system diagram, and data flow.
- **[RAG_PIPELINE.md](RAG_PIPELINE.md)**: Ingestion, page-aware chunking, dense vector indexing, and structural sampling strategies.
- **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)**: Complete REST API documentation for public and admin endpoints.
- **[EVALUATION_REPORT.md](EVALUATION_REPORT.md)**: Real retrieval evaluation benchmarks (Recall@5, MRR, Citation Precision, Latency).
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: End-to-end setup, environment parameters, startup scripts, and port conflict resolution.
- **[SECURITY_AUDIT.md](SECURITY_AUDIT.md)**: Vulnerability assessment, constant-time authentication, rate limiting, and defensive response parsing.
- **[TEST_RESULTS.md](TEST_RESULTS.md)**: 32-test automated test suite execution logs and coverage breakdown.
- **[BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)**: Cold/hot snapshot procedures, disaster recovery runbooks, and vector re-indexing.
- **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)**: Hardware boundaries on Apple Silicon M4 16GB, OCR boundaries, and context window limits.
- **[CHANGELOG.md](CHANGELOG.md)**: Complete version history and upgrade milestones.

---

## ✨ Key Capabilities

- **100% Local Inference & Data Privacy**: Executes entirely on your local machine using Ollama (`llama3`). Your sensitive documents, queries, and vectors never leave your device.
- **Accurate Dual-Page Citations**: Never confuses physical PDF page index with printed report page numbers:
  - *Physical PDF Page Number*: The 1-indexed page position in standard PDF readers (Apple Preview, Adobe Acrobat).
  - *Printed Page Number*: The number printed on headers or footers (Arabic numbers or Roman numerals `i, ii, iii`).
  - *Attribution format*: `Document.pdf — PDF page 4 (printed page 3)`.
- **Table of Contents (TOC) Pollution Filtering**: Filters table-of-contents entries (`Abstract ......... 3`) from abstract queries, routing directly to substantive narrative sections.
- **Intent Classification & Structural Summarization**: 
  - Resolves ordinal requests (e.g. *"Summarize the first document"* -> Upload Order 1).
  - Samples structural sections (Introduction, Architecture, Prototypes, and Conclusion) to synthesize complete 5-part executive summaries.
- **Multi-Document Disambiguation & Conversational Memory**:
  - Interactive clickable selection cards when a question is ambiguous across multiple PDFs.
  - Multi-turn conversational memory (`session_id`) retains document scope across follow-up queries.
- **Hardened Security Architecture**:
  - Administrative endpoints require header authentication via `X-Admin-Key` with constant-time verification (`secrets.compare_digest`).
  - Magic-byte (`%PDF-`) verification and filename sanitization prevent malicious disguised uploads and path traversal.
  - Per-IP sliding-window rate limiting (30 requests/minute).
  - Defensive API response parsing (`parseApiResponse`) prevents UI crashes on HTML edge proxy errors.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                │
│   • index.html: Marked.js Markdown, Document Pills, Disambiguation Cards    │
│   • admin.html: Defensive API Parsing, Session Tokens, Document Table       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / JSON
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               API LAYER                                     │
│   • main.py: FastAPI 0.115+, Lifespan Ingestion Sync, Sliding Rate Limiter  │
│   • Endpoints: /health, /documents, /ask, /admin/upload-pdf, /admin/*       │
│   • Multi-Turn Conversational Memory (session_id)                           │
└───────────────────┬───────────────────────────────────────┬─────────────────┘
                    │                                       │
                    ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│     DOCUMENT MANAGEMENT LAYER        │  │       SECURITY LAYER              │
│   • core/doc_registry.py             │  │   • Fail-Closed Admin Gatekeeper  │
│   • Stable Upload Order (1st, 2nd)   │  │   • secrets.compare_digest()      │
│   • Persistent Metadata Registry     │  │   • Magic-Byte (%PDF) Check       │
└───────────────────┬──────────────────┘  └───────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PDF PROCESSING LAYER                               │
│   • core/pdf_processor.py: pypdf Engine, Password/Decryption Guardrails     │
│   • Dual Page Numbering: Physical Index (1..N) vs Header/Footer Printed     │
│   • Table of Contents (TOC) Detection & Section Heading Extraction          │
└───────────────────┬───────────────────────────────────────┬─────────────────┘
                    │                                       │
                    ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│           RETRIEVAL LAYER            │  │        PERSISTENCE LAYER          │
│   • core/retrieval.py                │  │   • core/vector_store.py          │
│   • Intent Classifier (Abstract,     │  │   • ChromaDB Persistent Storage   │
│     Summary, Compare, Factual QA)    │  │   • BAAI/bge-small-en-v1.5 Vectors│
│   • Document Scope Isolation         │  │   • Schema Versioning (v2.0.0)    │
│   • Anti-TOC Filtering Guardrail     │  │   • 32-Chunk Batching + GC Collect│
└───────────────────┬──────────────────┘  └───────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GENERATION LAYER                                  │
│   • core/generation.py: Ollama llama3:latest with num_ctx=4096              │
│   • Specialized Prompts: QA, Abstract, Summarization, Comparison            │
│   • Exact Citation Builder: Document.pdf — PDF page X (printed page Y)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **macOS** with Apple Silicon (M1/M2/M3/M4, 16 GB unified RAM recommended).
- **Python 3.11** installed.
- **Ollama** installed with `llama3:latest` pulled (`ollama pull llama3:latest`).
- **ngrok CLI** installed and authenticated.

### 2. Configure Environment
Copy `.env.example` to `.env` and set your secure admin key:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest
OLLAMA_NUM_CTX=4096
SUPER_USER_KEY=your_secure_random_key_here
```

### 3. One-Click Startup
Launch the entire AskPDF stack (Ollama validation, Uvicorn on port 8000, and ngrok public tunnel):
```bash
./START_ASKPDF.sh
```

### 4. Safe Shutdown
Stop Uvicorn and ngrok gracefully without terminating unrelated processes:
```bash
./STOP_ASKPDF.sh
```

---

## 🧪 Automated Testing & Evaluation

### Run Automated Test Suite (32 tests):
```bash
.venv/bin/pytest -v
```

### Run Ground Truth Retrieval Benchmark:
```bash
.venv/bin/python scratch/evaluate_benchmark.py
```

**Measured Benchmark Summary:**
- **Recall@5:** 57.1%
- **Mean Reciprocal Rank (MRR):** 0.571
- **Citation Precision:** 49.0%
- **Page Attribution Accuracy:** 100.0%
- **Session Memory Retention:** 100.0% (Passed)
- **TOC Pollution Rate:** 0.0% (Zero TOC entries cited)

---

## 🌐 Public Tunnel & Local Endpoints

- **Public Q&A Interface**: [https://yer-superindifferent-lore.ngrok-free.dev](https://yer-superindifferent-lore.ngrok-free.dev)
- **Public Document Management**: [https://yer-superindifferent-lore.ngrok-free.dev/admin](https://yer-superindifferent-lore.ngrok-free.dev/admin)
- **Local Q&A Interface**: [http://localhost:8000](http://localhost:8000)
- **Local Document Management**: [http://localhost:8000/admin](http://localhost:8000/admin)
- **Local Backend Health**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.