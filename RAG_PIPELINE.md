# AskPDF — RAG Retrieval & Inference Pipeline Specification (v2.0)

This document provides an exhaustive, engineering-level breakdown of the Retrieval-Augmented Generation (RAG) architecture implemented in **AskPDF**.

---

## 1. High-Level Ingestion & Retrieval Pipeline

```
[ Upload PDF ]
      │
      ▼
[ Validation & Sanitization ]
  • Magic byte signature check (b"%PDF-")
  • File size ceiling enforcement (20 MB)
  • Filename normalization (directory traversal protection)
      │
      ▼
[ PDF Structural Extraction ] (core/pdf_processor.py)
  • Page-by-page text stream reading (pypdf)
  • Physical page indexing (1..N)
  • Header/footer regex for printed page numbers (Arabic & Roman numerals)
  • Table of Contents (TOC) & Index classification (is_toc = True/False)
  • Section heading detection (e.g. Abstract, Introduction, Architecture)
      │
      ▼
[ Page-Aware Chunking ]
  • Recursive character text splitter (chunk_size=1000, chunk_overlap=100)
  • Rich metadata binding:
    - document_id (e.g. doc_73a35d9771)
    - document_name / source (e.g. 23MIS0125_ListLocal_Safalya.pdf)
    - physical_page_number (1..N)
    - printed_page_number ("3", "iv", or null)
    - section_heading ("Abstract", "Conclusion")
    - is_toc (boolean)
    - ingestion_version ("2.0.0")
      │
      ▼
[ Dense Embedding Generation ] (core/vector_store.py)
  • Model: BAAI/bge-small-en-v1.5 (384-dimensional dense vectors)
  • Normalized cosine distance space
  • Memory-safe batching (32 chunks per batch) with garbage collection
      │
      ▼
[ Persistent Storage ]
  • ChromaDB collection: documind_documents (persisted in db/)
  • Document Registry: db/documents_registry.json (upload order, pages, chunks)
```

---

## 2. Query Understanding & Routing Architecture

When a query is received via `POST /ask`, AskPDF applies multi-stage preprocessing:

```
[ User Query ] (e.g. "GIVE ME ABSTRACT IN THIS PROJECT")
      │
      ▼
[ Intent Classifier ] (core/retrieval.py: classify_query_intent)
  • ABSTRACT: Direct section routing to narrative Abstract
  • SUMMARIZATION: Structural multi-page chunk sampling
  • COMPARISON: Multi-document segmented retrieval
  • FACTUAL_QA: Focused similarity search
      │
      ▼
[ Document Scope Resolution ] (core/retrieval.py: resolve_document_scope)
  • Pass 1: Explicit filename matching ("23MIS0125_ListLocal_Safalya.pdf")
  • Pass 2: Ordinal mention resolution ("first document" -> Upload Order 1)
  • Pass 3: Distinctive keyword token matching ("listlocal", "freshcart")
  • Pass 4: Conversational session memory (session_id context inheritance)
  • Pass 5: Interactive Disambiguation Trigger (needs_document_selection: True)
      │
      ▼
[ Scope-Filtered Retrieval & Guardrails ]
  • Chroma Filter: where={"source": target_doc}
  • Anti-TOC Guardrail: Rejects pages marked is_toc=True
  • Similarity Search: Cosine distance top-k retrieval
      │
      ▼
[ Context Synthesis & Dual-Attribution Citations ]
  • Prompt Template: Task-specific instruction (QA, Abstract, Summary, Compare)
  • Balanced Grounding Policy: Synthesize facts, explicitly note missing details
  • Exact Citation Formatter: Document.pdf — PDF page X (printed page Y)
```

---

## 3. Specialized Retrieval Strategies

### Strategy A: Abstract Extraction
- **Problem Solved:** Table of Contents pages often contain the isolated word "Abstract ......... 3", scoring highest in similarity and eclipsing the actual substantive narrative.
- **Solution:** 
  1. Searches for chunks where `section_heading == "Abstract"` AND `is_toc == False`.
  2. If direct section chunks are found, they take absolute priority.
  3. If not found, filters candidate chunks to discard pages with dot leaders (`....`).

### Strategy B: Full-Document Summarization ("Summarize the first document")
- **Problem Solved:** Traditional RAG embeds the prompt string "Summarize the first document" and retrieves 4 random chunks containing those words, resulting in "answer not found" refusals.
- **Solution:**
  1. Resolves ordinal target to the first registered document.
  2. Performs **structural chunk sampling**:
     - Samples the introduction and abstract (Pages 1–3).
     - Samples key technical/methodology sections from the middle pages.
     - Samples the conclusion and evaluation from the final pages.
  3. Assembles a 5-part executive summary: Objectives, System Architecture, Key Features/Findings, Methodology, and Limitations.

### Strategy C: Cross-Document Comparison
- **Problem Solved:** Unstructured queries mix citations and attribute findings from Document A to Document B.
- **Solution:**
  1. Retrieves top chunks independently from each registered document.
  2. Builds isolated context sections: `=== DOCUMENT: [Doc A] ===` and `=== DOCUMENT: [Doc B] ===`.
  3. Uses a comparison prompt instructing Llama 3 to structure the response under separate document headers before synthesizing comparative insights.

---

## 4. Dual-Page Attribution Specification

DocuMind AI rigorously distinguishes between two coordinate spaces:
1. **Physical PDF Page Number:** The 1-based index corresponding directly to page rendering in viewers (Adobe Acrobat, Apple Preview).
2. **Printed Report Page Number:** The printed page number appearing in headers/footers (e.g., page 3 on physical page 4, or Roman numerals `iv` on front matter).

Citations are rendered as:
```
[Document Name] — PDF page [Physical] (printed page [Printed])
```
*If printed page numbering cannot be determined with certainty, the fallback cleanly displays only the physical PDF page number.*
