# AskPDF — Known Limitations & System Boundaries (v2.0)

This document transparently details the technical limitations, hardware boundaries, and architectural trade-offs of **AskPDF** as of version 2.0.

---

## 1. Document Extraction & OCR Boundaries

### A. Scanned (Raster Image) PDFs
- **Current Behavior:** The extraction engine utilizes `pypdf` to extract digital text streams and fonts embedded in the PDF. If a PDF is a raw scan or photographed document without an OCR text layer, `pypdf` extracts 0 characters.
- **System Safeguard:** `core/pdf_processor.py` inspects extracted text density. If pages are empty or contain under 10 characters, it emits a diagnostic warning:
  `"Page X contains no extractable text. Document appears to be a scanned image requiring OCR."`
- **Mitigation / Workaround:** Pre-process scanned documents using Adobe Acrobat OCR, Apple Preview text recognition, or an external OCR tool (e.g., `ocrmypdf`) before ingestion into DocuMind AI.

### B. Multi-Column & Complex Scientific Layouts
- **Current Behavior:** Two-column academic papers are read in line-stream order. In some complex multi-column layouts where bounding boxes overlap, text flow across columns may interleave sentence fragments.
- **System Safeguard:** Chunk overlap (100 characters) and sentence-boundary splitting mitigate fragmentation.
- **Future Roadmap:** Integrate layout-aware PDF parsers (e.g., `pdfplumber` or `marker-pdf`) to reconstruct visual reading order.

### C. Mathematical Formulas & Tables
- **Current Behavior:** Complex mathematical expressions (fractions, matrices, integrals) are extracted as raw ASCII characters, which may lose mathematical LaTeX syntax.
- **System Safeguard:** Tables are extracted as row-separated plain text. Tabular dot leaders are filtered to prevent Table of Contents pollution.

---

## 2. LLM & Hardware Boundaries (Apple Silicon M4 16 GB)

### A. Context Window Size (`OLLAMA_NUM_CTX=4096`)
- **Current Behavior:** Ollama is configured with a 4,096-token context window. This accommodates the system prompt, retrieval context (4–8 dense chunks totaling ~2,500 tokens), and room for a 1,000-token generation.
- **Boundary:** Setting `OLLAMA_NUM_CTX` to 8,192 or 16,384 on a 16 GB unified memory machine increases memory pressure and may cause swapping to SSD during concurrent browser/IDE tasks.
- **System Safeguard:** Full-document summarization uses **structural chunk sampling** (sampling the abstract, introduction, section headings, and conclusion) rather than cramming 50+ pages into a single prompt.

### B. Sequential LLM Inference Queue
- **Current Behavior:** Ollama processes LLM inferences sequentially on the unified GPU/Neural Engine. If two users submit questions simultaneously, the second question waits in Ollama's inference queue until the first completes (typically 2–5 seconds per query).
- **System Safeguard:** Sliding-window rate limiting (30 requests/minute per IP) prevents queue flooding and denial-of-service.

---

## 3. Printed Page Number Detection Boundaries

### A. Non-Standard Page Number Placement
- **Current Behavior:** `detect_printed_page_number()` scans the top 3 and bottom 3 lines of each page for numeric patterns (`Page 14`, `- 14 -`, `14`) and Roman numerals (`i, ii, iii, iv, v`).
- **Boundary:** If a document places page numbers in rotated margin callouts, watermark backgrounds, or artistic SVG headers, printed page detection may fall back to the physical page index.
- **System Safeguard:** Citations always guarantee the **Physical PDF Page Number** (the exact index in any standard PDF reader like Apple Preview or Adobe Acrobat). When the printed page cannot be determined with certainty, only the physical page is cited to prevent misleading the user.

---

## 4. Multi-Tenancy & Authorization Boundaries

### A. Single-Tenant Shared Document Workspace
- **Current Behavior:** All documents uploaded through the Admin Portal reside in a shared vector database collection (`documind_documents`). Any user accessing the frontend can query any uploaded document or select "All Documents".
- **Boundary:** DocuMind AI is designed as a team-shared or personal document intelligence system. It does not provide per-user document isolation, row-level access control, or department-level permissions out of the box.
- **System Safeguard:** Administrative endpoints (`/admin/upload-pdf`, `/admin/delete-pdf`, `/admin/list-pdfs`) are strictly protected behind a fail-closed `SUPER_USER_KEY` gatekeeper with constant-time verification.

---

## 5. Network & Public Tunnel Boundaries

### A. ngrok Free Tier Limitations
- **Current Behavior:** The public URL (`https://yer-superindifferent-lore.ngrok-free.dev`) is proxied through ngrok.
- **Boundary:** The ngrok free tier imposes connection bandwidth limits and occasional interstitial verification pages for first-time browser sessions.
- **System Safeguard:** The frontend features defensive API response parsing (`parseApiResponse(res)`) that gracefully detects non-JSON error pages and surfaces actionable notifications rather than crashing with JavaScript syntax errors.
