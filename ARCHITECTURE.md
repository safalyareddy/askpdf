# AskPDF — System Architecture & Design Specification (v2.0)

**AskPDF** (Tagline: *"Your documents. Your answers."*) is an enterprise-grade, locally deployed document intelligence system engineered for grounded Question Answering, Abstract extraction, full-document summarization, and cross-document comparison over complex PDF reports with exact physical and printed page citations.

---

## 1. Modular Architectural Layers

AskPDF is organized into nine cohesive logical layers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                │
│   • index.html (Marked.js Markdown, Document Pills, Disambiguation Cards)   │
│   • admin.html (Defensive API Parsing, Session Tokens, Document Metadata)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / JSON
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               API LAYER                                     │
│   • main.py (FastAPI, Lifespan Reconciliation, Pydantic Models)             │
│   • Endpoints: /health, /documents, /ask, /admin/upload-pdf, /admin/*       │
│   • Session Context Tracker (Multi-Turn Conversational Memory)              │
│   • In-Memory Sliding-Window Rate Limiter (30 req/min/IP)                   │
└───────────────────┬───────────────────────────────────────┬─────────────────┘
                    │                                       │
                    ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│     DOCUMENT MANAGEMENT LAYER        │  │       SECURITY LAYER              │
│   • core/doc_registry.py             │  │   • Fail-Closed Admin Gatekeeper  │
│   • Stable Upload Order (1st, 2nd)   │  │   • secrets.compare_digest()      │
│   • Persistent Metadata Registry     │  │   • Magic-Byte (%PDF) Verification│
│   • Ordinal & Mention Resolution     │  │   • Path Traversal Sanitization   │
└───────────────────┬──────────────────┘  └───────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PDF PROCESSING LAYER                               │
│   • core/pdf_processor.py (pypdf Engine, Decryption Guardrails)             │
│   • Dual Page Numbering (Physical PDF Index 1..N vs Printed Header/Footer)  │
│   • Table of Contents (TOC) & Index Detection (is_toc = True/False)         │
│   • Section Heading Detection (Abstract, Introduction, Architecture, etc.)  │
│   • Rich Chunk Metadata (doc_id, page, printed_page, heading, is_toc)       │
└───────────────────┬───────────────────────────────────────┬─────────────────┘
                    │                                       │
                    ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│           RETRIEVAL LAYER            │  │        PERSISTENCE LAYER          │
│   • core/retrieval.py                │  │   • core/vector_store.py          │
│   • Intent Classifier (Abstract,     │  │   • ChromaDB Persistent Storage   │
│     Summary, Compare, Factual QA)    │  │   • BAAI/bge-small-en-v1.5 Dense   │
│   • Document-Level Scope Filter      │  │     Vectors (384-dimensional)    │
│   • Anti-TOC Filtering Guardrail     │  │   • Incremental Document Sync     │
│   • Structural Chunk Sampler         │  │   • Schema Version Migration      │
└───────────────────┬──────────────────┘  └───────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GENERATION LAYER                                  │
│   • core/generation.py (Ollama llama3:latest with num_ctx=4096)             │
│   • Specialized Prompts (QA, Abstract, Summarization, Comparison)           │
│   • Balanced Grounding Policy (Answers with available context & notes gaps) │
└───────────────────┬─────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CITATION LAYER                                    │
│   • Exact Attribution: Document Name — PDF page X (printed page Y)          │
│   • Deduplicated Verified Evidence Snippets                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Ingestion & Retrieval Data Flow

### A. Document Ingestion Pipeline
1. **Upload & Magic-Byte Validation**:
   - The user submits a PDF via `/admin/upload-pdf` with `X-Admin-Key`.
   - File signature is validated (`b"%PDF"` header).
   - Filename is sanitized to eliminate directory traversal (`re.sub(r"[^a-zA-Z0-9_.-]", "_", base)`).
   - Stream size ceiling (20 MB) is enforced chunk by chunk.
2. **Page-by-Page Extraction & Heading Detection**:
   - `core/pdf_processor.py` processes each page individually.
   - Extracts physical page index (1..N).
   - Identifies printed page numbers (numeric or Roman numerals `i, ii, iii`) from headers/footers.
   - Evaluates whether the page is a Table of Contents (`is_toc: True`).
   - Identifies section headings (e.g., `Abstract`, `1. Introduction`, `Implementation`).
   - Generates chunks with schema `ingestion_version: 2.0.0`.
3. **Registry & Vector Synchronization**:
   - Updates `db/documents_registry.json` with upload order, page counts, chunk counts, and printed page maps.
   - Inserts chunks into persistent Chroma collection `documind_documents` with batching (32 chunks/batch) and garbage collection.

### B. Intelligent RAG Retrieval & Generation Flow
1. **Query Preprocessing & Intent Classification**:
   - `classify_query_intent()` detects:
     - `ABSTRACT`: User asks for abstract or executive summary.
     - `SUMMARIZATION`: User asks for an overview or full document summary.
     - `COMPARISON`: User asks to compare multiple documents.
     - `FACTUAL_QA`: User asks a targeted question.
2. **Document Scope Resolution**:
   - Explicit filename mentioned (e.g., `23MIS0125_ListLocal_Safalya.pdf` or `ListLocal`).
   - Ordinal reference resolved ("first document" -> order 1, "second document" -> order 2).
   - Active session context retained across follow-up queries.
   - If ambiguous and multiple documents exist: returns `needs_document_selection: True` with interactive choices.
3. **Anti-TOC Filtering**:
   - Excludes chunks where `is_toc == True` when seeking substantive content.
   - For `ABSTRACT`, retrieves direct substantive Abstract section chunks (`section_heading == "Abstract"` and `is_toc == False`).
4. **Structural Chunk Sampling for Summaries**:
   - When summarizing a document, samples representative structural passages across the entire document (Abstract/Intro on early pages, Architecture in middle pages, Conclusions/Limitations on end pages) rather than relying on top-k similarity against the word "summarize".
5. **Grounded Generation & Dual Page Citations**:
   - Dispatches structured context to Ollama (`llama3:latest`, `num_ctx=4096`).
   - Builds citations formatted as `Document Name — PDF page X (printed page Y)`.

---

## 3. Physical vs Printed Page Numbering

Academic and technical reports frequently diverge in page numbers:
- **Physical Page**: The 1-based index in the PDF viewer (e.g., Physical Page 3).
- **Printed Page**: The page number printed on the header/footer of the document (e.g., `Page 3` or `iii`).

DocuMind AI preserves both in chunk metadata and formats citations clearly:
```
23MIS0125_ListLocal_Safalya.pdf — PDF page 3 (printed page 3)
```
If a printed number is not detected (such as on cover pages), only the physical page number is presented.

---

## 4. Multi-Turn Session Tracking

- The web client generates a UUID `session_id` stored in `sessionStorage`.
- Every request transmits `session_id` and optional `document_id`.
- The backend caches the active document scope per session.
- Follow-up questions (e.g., *"What about its limitations?"*) seamlessly retain the document context of the preceding question without requiring re-selection.

---

## 5. Security Guardrails

| Security Control | Implementation |
| :--- | :--- |
| **Fail-Closed Admin** | If `SUPER_USER_KEY` is missing or placeholder, admin endpoints raise HTTP 503 rather than failing open. |
| **Timing Attack Defense** | `secrets.compare_digest()` validates admin keys in constant time. |
| **Rate Limiting** | Sliding window rate limiter enforces maximum 30 requests/minute per IP on `/ask` (HTTP 429). |
| **Token Safety** | Credentials in `admin.html` strictly use `sessionStorage` (cleared on tab close). |
| **Ollama Isolation** | Ollama is bound to `127.0.0.1:11434`. Only port 8000 is exposed via ngrok. |
