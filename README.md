# 🧠 DocuMind AI — Grounded Document Intelligence Platform

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-FF6F00?style=flat)](https://trychroma.com)
[![Ollama](https://img.shields.io/badge/Ollama-Llama--3%20(Local)-white?style=flat&logo=ollama&logoColor=black)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A private, locally-run document intelligence system featuring **Retrieval-Augmented Generation (RAG)** over PDF documents. Powered by **FastAPI**, **ChromaDB**, **Sentence Transformers (`BAAI/bge-small-en-v1.5`)**, and **Ollama (`llama3`)**. 

Answers are strictly grounded in your documents with verified, interactive **page-level citations** and zero cloud data leakage.

---

## ✨ Features

- **100% Local & Confidential**: Executes entirely on your local machine using Ollama (`llama3`). Your sensitive documents, queries, and vectors never leave your device.
- **Accurate Page-Level Citations**: PDF text is indexed per page. Every retrieved response provides interactive citation cards showing the source document name, exact page number, and quoted excerpt.
- **Strict Anti-Hallucination Guardrails**: Prompts enforce truthful grounding. If retrieved passages do not contain the answer, the model explicitly states that the answer cannot be found.
- **Hardened Security Architecture**:
  - Administrative endpoints require header authentication via `X-Admin-Key` (URL query parameter keys are strictly rejected to avoid leakage in access logs).
  - Magic-byte (`%PDF-`) verification and filename sanitization prevent malicious file disguised uploads and path traversal.
  - Enforced 20 MB file size limit protects against disk exhaustion attacks.
  - Safe error masking prevents stack traces or sensitive paths from leaking to clients.
- **Apple Silicon GPU Acceleration**: Connects seamlessly from Docker to native Mac Ollama via `host.docker.internal:11434`, unlocking full Metal GPU performance without redownloading 4.7 GB model weights inside Docker.
- **Automated Test Coverage**: 20 comprehensive unit and integration tests covering security, authentication, PDF extraction, ChromaDB vector search, and model failure handling.

---

## 🏗️ System Architecture

```
[ Browser / Client ]
        │
   ┌────┴───────────────────────────────┐
   ▼                                    ▼
GET / (index.html)             GET /admin (admin.html)
Ask Question (POST /ask)       Manage PDFs (POST/DELETE /admin/*)
   │                                    │
   └───────────────┬────────────────────┘
                   ▼
        [ FastAPI Application: documind-app ]
                   │
    ┌──────────────┴──────────────┐
    ▼                             ▼
[ ChromaDB: ./db ]        [ Host Ollama: host.docker.internal:11434 ]
BAAI/bge-small-en-v1.5    Llama-3 Apple Silicon Metal Inference
```

For comprehensive details on data flow, components, and security boundaries, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **macOS** (Apple Silicon or Intel) or Linux.
- **Ollama** installed and running on your host machine:
  ```bash
  # Check if Ollama is running and has llama3
  ollama list
  ```
  *(If llama3 is not present, pull it natively: `ollama pull llama3`)*
- **Docker Desktop** (optional, for containerized execution) OR **Python 3.10 / 3.11** (for native execution).

### 2. Configure Environment
Copy the configuration template:
```bash
cp .env.example .env
```
Open `.env` and set your secure admin key:
```env
SUPER_USER_KEY=your-secure-random-admin-key
OLLAMA_BASE_URL=http://localhost:11434
```

---

## 💻 Option A: Running Locally with Python

1. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Start the application**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access the application**:
   - **Question Answering UI**: [http://localhost:8000](http://localhost:8000)
   - **Document Admin Portal**: [http://localhost:8000/admin](http://localhost:8000/admin)
   - **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🐳 Option B: Running with Docker Compose

1. **Build and start the container**:
   ```bash
   docker compose up --build -d
   ```

2. **Inspect container logs**:
   ```bash
   docker compose logs -f documind-app
   ```

3. **Stop the container**:
   ```bash
   docker compose down
   ```

---

## 🧪 Automated Testing & Evaluation

DocuMind AI includes a comprehensive regression suite covering API endpoints, upload validation, security policies, and RAG retrieval.

### Run tests natively:
```bash
.venv/bin/pytest -v
```

### Run tests inside Docker:
```bash
docker compose exec documind-app pytest -v
```

---

## 🔒 Configuration Reference

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `SUPER_USER_KEY` | `documind-dev-supersecretkey-change-in-prod` | Administrative key required for uploading and deleting documents via `X-Admin-Key` header. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` (host) / `http://host.docker.internal:11434` (Docker) | Endpoint to local Ollama instance. |
| `LLM_MODEL` | `llama3` | Ollama model identifier. |
| `EMBEDDING_MODEL`| `BAAI/bge-small-en-v1.5` | Hugging Face embedding model. |
| `PERSIST_DIR` | `./db` | Storage path for ChromaDB vector store. |
| `PDF_DIR` | `./data/` | Storage path for uploaded PDF files. |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximum allowed file upload size. |

---

## 🗺️ Project Roadmap & Limitations

- **Digital vs. Scanned Documents**: DocuMind AI currently extracts embedded digital text from PDF files via `pypdf`. Scanned image-only PDFs require an Optical Character Recognition (OCR) engine (such as Tesseract or Surya), which is slated for a future release.
- **Multi-Document Comparative Reasoning**: Planned enhancement for cross-document synthesis across dozens of indexed files simultaneously.
- **Role-Based Access Control (RBAC)**: Fine-grained permissions per collection or department.

---

## ❓ Troubleshooting

1. **"Could not connect to Ollama"**:
   - Ensure Ollama is active on your host: `ollama serve` or open the Ollama menu bar app.
   - Verify that `curl http://localhost:11434/api/tags` returns your model list.
   - If running inside Docker, ensure `OLLAMA_BASE_URL` is set to `http://host.docker.internal:11434`.

2. **"Unauthorized: Invalid admin key"**:
   - Provide the key in the `X-Admin-Key` request header or input it in the Document Admin UI header input.
   - Note: Query parameter keys (`?super_user_key=...`) are rejected by design to prevent credential leaks in URL logs.