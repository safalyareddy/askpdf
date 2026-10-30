#!/bin/bash
set -e

PORT="${PORT:-8000}"

if [ -n "$STORAGE_DIR" ]; then
    PDF_DIR="${PDF_DIR:-$STORAGE_DIR/data}"
    PERSIST_DIR="${PERSIST_DIR:-$STORAGE_DIR/db}"
else
    PDF_DIR="${PDF_DIR:-./data/}"
    PERSIST_DIR="${PERSIST_DIR:-./db}"
fi

export PDF_DIR
export PERSIST_DIR

echo "Starting AskPDF Document Intelligence Service on port ${PORT}..."
echo "PDF Directory: ${PDF_DIR}"
echo "Persistent Vectorstore & Registry Directory: ${PERSIST_DIR}"
mkdir -p "$PDF_DIR" "$PERSIST_DIR"

exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
