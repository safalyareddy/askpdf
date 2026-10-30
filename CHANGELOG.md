# AskPDF — Comprehensive Changelog

All notable changes, bug fixes, architectural upgrades, and rebranding milestones for **AskPDF** are documented in this file.

---

## [2.0.0] — 2026-10-30

### 🚀 Brand Transformation
- **Product Name:** Evolved product identity from *DocuMind AI / PDF-QA* to **AskPDF**.
- **Official Tagline:** *"Your documents. Your answers."*
- **Positioning:** An enterprise-grade, locally deployed document intelligence platform that allows users to upload PDF documents, ask natural-language questions, retrieve relevant information, and receive answers strictly grounded in document evidence.
- **Visual & UI Upgrade:** Modernized dark-mode interface with `marked.js` Markdown rendering, responsive table formatting, document selection pills, interactive disambiguation cards, and copy-to-clipboard functionality.

---

### 🛠️ Core Engineering & RAG Accuracy Fixes
- **Table of Contents (TOC) Pollution Elimination:**
  - *Root Cause:* Queries for "Abstract" matched isolated words and dot leaders on Table of Contents pages, retrieving Page 4 rather than the substantive narrative on Page 3.
  - *Fix:* Added algorithmic TOC detection (`is_toc: True/False`), anti-TOC filtering guardrails, and direct section-heading retrieval.
- **Ordinal Document Summarization ("Summarize the first document"):**
  - *Root Cause:* Vector similarity search attempted to embed the prompt string "Summarize the first document". No chunks contained that exact phrase, resulting in false "answer not found" refusals.
  - *Fix:* Implemented `QueryIntent.SUMMARIZATION`, ordinal upload resolution ("first document" -> Upload Order 1), and structural chunk sampling across introduction, architecture, prototypes, and conclusion.
- **Dual-Page Numbering Disambiguation:**
  - *Root Cause:* Ingestion recorded only the physical PDF index (1..N), discarding printed report numbers.
  - *Fix:* Integrated header/footer regex scanning to extract printed numbers (Arabic and Roman numerals) alongside physical viewer indices, formatting citations as: `Document.pdf — PDF page X (printed page Y)`.
- **Cross-Document Context Leaks:**
  - *Root Cause:* Unconstrained similarity search retrieved chunks across multiple uploaded files without scope isolation.
  - *Fix:* Implemented document-level metadata filtering (`where={"source": target_doc}`) and interactive disambiguation when target document is ambiguous.
- **Multi-Turn Conversational Memory:**
  - *Root Cause:* Backend had no session awareness; follow-up questions ("What about its limitations?") lost document context.
  - *Fix:* Added client session tracking (`session_id`) and backend session store preserving active document scope across dialogue turns.
- **Frontend Overflow & Layout Breakages:**
  - *Root Cause:* Plain text rendering without Markdown caused horizontal clipping, raw code escapes, and truncated summaries.
  - *Fix:* Integrated `marked.js` with responsive typography, scrollable cards, formatted tables, and defensive API parsing (`parseApiResponse`).

---

### 🔒 Security & Reliability Hardening
- **Constant-Time Admin Authentication:** Replaced standard string equality with `secrets.compare_digest()` to prevent timing side-channel attacks on `X-Admin-Key`.
- **Fail-Closed Gatekeeper:** Removed hardcoded fallback keys (`documind-dev-supersecretkey-change-in-prod`). Missing secrets now return HTTP 503 instead of falling open.
- **Per-IP Rate Limiting:** Enforced sliding-window limiter (30 requests/minute per client IP) to protect Ollama inference queues.
- **Defensive API Error Handling:** Replaced `res.json()` with `parseApiResponse(res)` to gracefully surface HTML proxy error pages (e.g. ngrok 502/503/413) without browser syntax errors.

---

### 📦 Operational Scripts & Testing
- **New Scripts:** Added `START_ASKPDF.sh` and `STOP_ASKPDF.sh` for one-click startup and graceful shutdown of Ollama, Uvicorn, and ngrok.
- **Backward Compatibility:** Maintained `START_DOCUMIND.sh` and `STOP_DOCUMIND.sh` aliases forwarding to AskPDF scripts.
- **Automated Regression Suite:** 32 unit and integration tests passing with 100% success rate across API, PDF processing, Chroma persistence, RAG retrieval, and rate limiting.
