# AskPDF — REST API Specification & Developer Guide (v2.0)

This document provides complete documentation for the HTTP REST API exposed by **AskPDF**.

---

## 1. Overview & Base URLs

- **Local Base URL:** `http://localhost:8000`
- **Public ngrok Base URL:** `https://yer-superindifferent-lore.ngrok-free.dev`
- **Specification Format:** OpenAPI 3.0 / RESTful JSON
- **Default Port:** `8000`
- **Rate Limit:** 30 requests per minute per IP (sliding window)

---

## 2. Authentication & Authorization

AskPDF enforces a strict role separation model:
- **Public Endpoints (`/health`, `/documents`, `/ask`, `/`):** Open access for document exploration and questioning.
- **Administrative Endpoints (`/admin/*`):** Protected by a mandatory, fail-closed `X-Admin-Key` header.
  - Verification uses constant-time comparison (`secrets.compare_digest`) to prevent timing attacks.
  - Query parameters (e.g., `?super_user_key=...`) are rejected by design to prevent credential exposure in edge proxy access logs.

---

## 3. Endpoint Reference

### A. Health & Diagnostics

#### `GET /health` & `GET /healthz`
Returns real-time status of the FastAPI backend, persistent vector index, and local Ollama inference service.

**Request:**
```bash
curl -X GET http://localhost:8000/health
```

**Response (HTTP 200 OK):**
```json
{
  "status": "healthy",
  "app": "AskPDF",
  "tagline": "Your documents. Your answers.",
  "version": "2.0.0",
  "engine_ready": true,
  "indexed_pdfs": 2,
  "provider": "ollama",
  "model_online": true,
  "ollama_online": true,
  "model_status": "Ollama is reachable and responding.",
  "model": "llama3",
  "admin_auth_configured": true
}
```

---

### B. Document Discovery

#### `GET /documents`
Returns the public registry of all indexed PDF documents, including stable upload orders, page counts, chunk totals, and storage sizes.

**Request:**
```bash
curl -X GET http://localhost:8000/documents
```

**Response (HTTP 200 OK):**
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

---

### C. Grounded Question Answering

#### `POST /ask`
Submits natural-language questions, abstract requests, full-document summaries, or comparison queries.

**Request Headers:**
- `Content-Type: application/json`

**Request Body Schema:**
```json
{
  "query": "What is the abstract of 23MIS0125_ListLocal_Safalya.pdf?",
  "document_id": "doc_91a1737480",
  "session_id": "client_session_xyz123"
}
```

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `query` | string | **Yes** | Natural language prompt (1 to 2,000 characters). |
| `document_id` | string | No | Optional target document ID, exact filename, or `"all"`. |
| `session_id` | string | No | Client session ID for multi-turn conversational context tracking. |

**Standard Answer Response (HTTP 200 OK):**
```json
{
  "answer": "The abstract of ListLocal discusses the development of a local business directory...",
  "sources": [
    {
      "source": "23MIS0125_ListLocal_Safalya.pdf",
      "physical_page": 3,
      "printed_page": "3",
      "citation_label": "23MIS0125_ListLocal_Safalya.pdf — PDF page 3 (printed page 3)",
      "snippet": "ABSTRACT: ListLocal is a web and mobile platform designed to empower small businesses...",
      "section_heading": "Abstract"
    }
  ],
  "active_document": "23MIS0125_ListLocal_Safalya.pdf"
}
```

**Disambiguation Response (HTTP 200 OK — Ambiguous Scope):**
```json
{
  "answer": "You have multiple documents available. Please select which document you would like to ask about, or choose 'All documents':",
  "needs_document_selection": true,
  "message": "Which document would you like to inspect?",
  "options": [
    {
      "document_id": "doc_73a35d9771",
      "filename": "23MIS0125_FreshCart_Lab_Assignment_8.pdf",
      "display_name": "1. 23MIS0125 FreshCart Lab Assignment 8"
    },
    {
      "document_id": "doc_91a1737480",
      "filename": "23MIS0125_ListLocal_Safalya.pdf",
      "display_name": "2. 23MIS0125 ListLocal Safalya"
    },
    {
      "document_id": "all",
      "filename": "all",
      "display_name": "All Documents"
    }
  ]
}
```

---

### D. Administrative Document Operations

#### `POST /admin/upload-pdf`
Uploads and indexes a new PDF document.

**Request Headers:**
- `X-Admin-Key: <SUPER_USER_KEY>`

**Request Body:** `multipart/form-data` with key `file`.

**Response (HTTP 200 OK):**
```json
{
  "message": "'Report.pdf' uploaded and indexed successfully (15 pages, 42 text chunks).",
  "filename": "Report.pdf",
  "pages": 15,
  "chunks": 42,
  "text_detected": true
}
```

#### `GET /admin/list-pdfs`
Returns complete administrative metadata for all stored PDFs.

**Request Headers:**
- `X-Admin-Key: <SUPER_USER_KEY>`

**Response (HTTP 200 OK):**
```json
{
  "pdfs": [
    {
      "document_id": "doc_73a35d9771",
      "filename": "23MIS0125_FreshCart_Lab_Assignment_8.pdf",
      "display_name": "23MIS0125 FreshCart Lab Assignment 8",
      "upload_order": 1,
      "pages": 22,
      "chunks": 61,
      "size_kb": 5738.2
    }
  ],
  "total": 1
}
```

#### `DELETE /admin/delete-pdf?filename=<filename>`
Deletes a PDF file from storage and purges its vector embeddings from ChromaDB.

**Request Headers:**
- `X-Admin-Key: <SUPER_USER_KEY>`

**Response (HTTP 200 OK):**
```json
{
  "message": "'Report.pdf' deleted and vector index updated."
}
```
