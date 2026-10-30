# AskPDF — Backup, Snapshot & Disaster Recovery Plan (v2.0)

This document defines the enterprise backup, data retention, integrity verification, and disaster recovery procedures for **AskPDF**.

---

## 1. Storage & State Inventory

AskPDF maintains state across three critical directories:

| Component | Filesystem Path | Data Description | Criticality |
| :--- | :--- | :--- | :--- |
| **PDF Storage** | `data/` | Original source PDF files uploaded via Admin or seeded. | **CRITICAL** (Original source of truth) |
| **Metadata Registry** | `db/documents_registry.json` | Document IDs, upload order, printed page maps, chunk counts, section headings. | **CRITICAL** (Ordinal and citation mapping) |
| **Vector Database** | `db/` (ChromaDB) | Persistent embeddings (`chroma.sqlite3`, segment indices, vector payloads). | **HIGH** (Can be reconstructed from `data/`) |
| **Configuration** | `.env` | Secret keys (`SUPER_USER_KEY`), Ollama parameters, model definitions. | **HIGH** (Contains credentials) |
| **Application Logs** | `logs/` | Daily rotated execution and audit logs. | **MEDIUM** (Operational diagnostics) |

---

## 2. Backup Strategies

### A. Snapshot Backup (Cold Backup — Recommended)
To prevent SQLite database lock contention during active Chroma writes, perform cold backups while the FastAPI backend is paused or idle:

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="$HOME/DocuMind_Backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TARGET_DIR="${BACKUP_ROOT}/documind_backup_${TIMESTAMP}"

mkdir -p "${TARGET_DIR}"

echo "Starting cold snapshot to ${TARGET_DIR}..."

# 1. Stop backend if running
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "Pausing FastAPI backend..."
    pkill -f "uvicorn main:app" || true
    sleep 2
fi

# 2. Archive data directory
tar -czf "${TARGET_DIR}/data.tar.gz" -C "/Users/safalyareddy/Downloads/pdf-QA-main" data/

# 3. Archive db directory (ChromaDB + registry)
tar -czf "${TARGET_DIR}/db.tar.gz" -C "/Users/safalyareddy/Downloads/pdf-QA-main" db/

# 4. Copy configuration template (sanitized)
grep -v "SUPER_USER_KEY" "/Users/safalyareddy/Downloads/pdf-QA-main/.env" > "${TARGET_DIR}/env_sanitized.txt"

# 5. Restart backend
echo "Restarting backend..."
cd "/Users/safalyareddy/Downloads/pdf-QA-main"
nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > logs/uvicorn.log 2>&1 &

echo "Backup complete: ${TARGET_DIR}"
```

---

### B. Hot Backup (Active System)
If zero-downtime backup is required:
1. SQLite WAL checkpointing: SQLite operates in WAL mode; copy `db/chroma.sqlite3`, `db/chroma.sqlite3-wal`, and `db/chroma.sqlite3-shm` atomically.
2. Back up `db/documents_registry.json` using atomic read.
3. Back up `data/` directory.

---

## 3. Disaster Recovery Procedures

### Scenario 1: Complete System or Disk Loss
**Goal:** Restore DocuMind AI on a fresh machine or reconstructed directory.

1. **Clone Repository & Set Up Virtual Environment:**
   ```bash
   git clone https://github.com/safalyareddy/askpdf.git askpdf
   cd askpdf
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Restore Files from Backup Archive:**
   ```bash
   tar -xzf /path/to/backup/data.tar.gz -C .
   tar -xzf /path/to/backup/db.tar.gz -C .
   ```

3. **Recreate `.env` Configuration:**
   Restore `.env` with the original `SUPER_USER_KEY` and target model parameters.

4. **Verify Ollama Availability:**
   ```bash
   ollama pull llama3:latest
   ```

5. **Start Application & Verify:**
   ```bash
   ./START_ASKPDF.sh
   curl http://localhost:8000/health
   curl http://localhost:8000/documents
   ```

---

### Scenario 2: Vector Database Corruption (`db/` corrupted)
**Goal:** Full reconstruction of vector database from source PDFs without loss of document order.

Because `data/` preserves the original source PDF files and `db/documents_registry.json` preserves document metadata:

1. **Stop Application:**
   ```bash
   ./STOP_ASKPDF.sh
   ```

2. **Remove Corrupted Chroma Store:**
   ```bash
   # Move corrupted db directory to trash
   mv db db_corrupted_$(date +%s)
   mkdir -p db
   ```

3. **Trigger Ingestion Re-index via Python CLI:**
   ```bash
   source .venv/bin/activate
   python -c "
   from core.config import settings
   from core.doc_registry import DocumentRegistry
   from core.vector_store import VectorStoreManager
   from core.pdf_processor import PDFProcessor

   print('Rebuilding Chroma collection from source PDFs...')
   vsm = VectorStoreManager()
   registry = DocumentRegistry()
   registry.reconcile_with_disk(settings.DATA_DIR)
   print(f'Successfully restored {len(registry.list_documents())} registered documents.')
   "
   ```

4. **Verify Integrity:**
   ```bash
   ./START_ASKPDF.sh
   curl http://localhost:8000/documents
   ```

---

### Scenario 3: Accidental Document Deletion via Admin UI
**Goal:** Recover an accidentally deleted PDF and restore its vector index.

1. Locate the PDF file in your local backup archive (`data.tar.gz`).
2. Extract the deleted PDF to the `data/` directory.
3. Authenticate to the Admin Portal (`/admin`).
4. Re-upload the PDF through the Admin Portal with `X-Admin-Key`.
5. The system will:
   - Re-extract pages and headings.
   - Detect physical and printed page numbers.
   - Assign the next stable upload order.
   - Re-index chunks into Chroma with batching.

---

## 4. Integrity Verification Checklist

After performing any recovery action, verify that:

- [ ] `/health` returns `"status": "healthy"` and `"pipeline_ready": true`.
- [ ] `/documents` returns all expected documents with correct page and chunk counts.
- [ ] Abstract query for `23MIS0125_ListLocal_Safalya.pdf` returns substantive text from PDF page 3.
- [ ] Summarization query ("Summarize the first document") generates executive summary for `23MIS0125_FreshCart_Lab_Assignment_8.pdf`.
- [ ] Admin portal (`/admin`) lists all documents with upload order.
- [ ] Dual-page citations display correctly: `Document.pdf — PDF page X (printed page Y)`.
