# DocuMind AI — System Architecture & Design Specification

DocuMind AI is a private, locally-run document intelligence system designed for accurate, grounded Question Answering over PDF documents with page-level citation verification.

---

## 1. High-Level Architecture

```
                      ┌──────────────────────────────────────┐
                      │          Web Browser Client          │
                      │  - Ask Interface (index.html)        │
                      │  - Document Admin Panel (admin.html) │
                      └──────────────────┬───────────────────┘
                                         │ HTTP (JSON / HTML)
                                         ▼
                      ┌──────────────────────────────────────┐
                      │       FastAPI Application Server      │
                      │               (main.py)              │
                      │  - Lifespan Ingestion Manager        │
                      │  - X-Admin-Key Auth Gatekeeper       │
                      │  - Magic-Byte & Path Sanitizer       │
                      │  - Grounded QA Query Dispatcher      │
                      └───────────┬──────────────┬───────────┘
                                  │              │
                    Embeddings &  │              │ Prompt & Context
                    Similarity    │              │ (Local Inference)
                                  ▼              ▼
           ┌─────────────────────────────┐   ┌─────────────────────────────┐
           │      ChromaDB Engine        │   │      Ollama LLM Engine      │
           │        (Local Disk)         │   │       (Llama 3 8B)          │
           │  - Persistent Vector Store  │   │  - Zero data leaves machine │
           │  - BAAI/bge-small-en-v1.5   │   │  - Apple Silicon GPU Metal  │
           │  - Page-numbered chunk maps │   │    acceleration on host     │
           └─────────────────────────────┘   └─────────────────────────────┘
```

---

## 2. Ingestion & Retrieval Data Flow

### A. Document Ingestion Pipeline
1. **Upload & Validation**:
   - The user submits a PDF via the Document Admin portal (`/admin`).
   - The request must provide an `X-Admin-Key` header matching `SUPER_USER_KEY`.
   - File validation verifies the `%PDF-` magic byte header, restricts file size (default 20 MB limit), and sanitizes the filename to prevent directory traversal attacks.
   - The file is saved safely under `data/<sanitized_name>.pdf`.
2. **Text Extraction & Page-Aware Chunking**:
   - `pypdf.PdfReader` iterates page-by-page.
   - `RecursiveCharacterTextSplitter` segments text chunks (500 characters, 100 character overlap) while preserving exact page numbers in chunk metadata: `{"source": "<filename>", "page": <int>}`.
   - If a PDF is a scanned image with no extractable text, ingestion logs a warning noting OCR requirements.
3. **Local Embedding & Vector Storage**:
   - `sentence-transformers` generates 384-dimensional dense vectors using `BAAI/bge-small-en-v1.5`.
   - Chunks are inserted into persistent ChromaDB storage (`db/`).

### B. Retrieval-Augmented Generation (RAG) Flow
1. **Query Submission**: User enters a natural-language query at `POST /ask`.
2. **Vector Similarity Search**: ChromaDB performs cosine/L2 distance search retrieving top $k$ relevant passages ($k=4$).
3. **Strict Grounding Prompt**:
   - The retrieved context is formatted with explicit document names and page references.
   - The prompt instructs the LLM:
     > *"Use ONLY the following retrieved context passages to answer the user's question. If the context does not contain enough information to answer, truthfully say: 'I cannot find the answer to this question in the provided documents.' Do NOT make up facts or extrapolate beyond what is stated in the context."*
4. **Local Generation & Citation Extraction**:
   - Prompt is dispatched to local Ollama (`llama3`).
   - The response is returned to the user alongside verified citation cards containing document name, page number, and text excerpt.

### C. Invalidation & Deletion Flow
1. **Removal**: When an authorized user deletes a document via `DELETE /admin/delete-pdf`, the physical file is removed from `data/`.
2. **Vector Store Invalidation**: The Chroma collection invalidates chunks corresponding to that document and re-indexes the clean state to prevent ghost citations.

---

## 3. Security Boundaries & Hardening

| Security Domain | Mitigation / Control Implemented |
| :--- | :--- |
| **Authentication** | Sensitive admin actions require `X-Admin-Key` header authentication. URL query key authentication is rejected to prevent secrets being recorded in proxy/browser logs. |
| **File Traversal** | Filenames are sanitized through `re.sub(r"[^a-zA-Z0-9_.-]", "_", basename)` to prevent directory traversal (`../../etc/passwd`). |
| **MIME / Magic Bytes** | Every upload is inspected for the standard `%PDF` file header signature before disk writing, rejecting renamed executables or scripts. |
| **Resource Limits** | Strict file size limit (20 MB default) enforced chunk-by-chunk to prevent denial-of-service via disk exhaustion. |
| **Information Disclosure** | Internal stack traces and raw error exceptions are caught and logged server-side; safe generic error responses are returned to the client. |
| **Data Privacy** | All inference runs 100% locally on your machine via Ollama and HuggingFace models. No external cloud APIs are invoked. |

---

## 4. Current Constraints & Assumptions

1. **Text-Only Extraction**: Scanned documents consisting solely of raster images require an Optical Character Recognition (OCR) engine like Tesseract. Documents without embedded digital text extract 0 chunks.
2. **Local Ollama Dependency**: Ollama must be active (`ollama serve`) with the specified model (`llama3`) pulled locally.
3. **Single-Node Storage**: File storage is local filesystem-based (`./data`) and vector storage is SQLite/parquet-based (`./db`). Multi-node clustering is outside current single-instance design.
