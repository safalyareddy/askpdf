#!/bin/bash
set -e

PORT="${PORT:-8000}"
PDF_DIR="${PDF_DIR:-./data/}"
PERSIST_DIR="${PERSIST_DIR:-./db}"

echo "Starting DocuMind AI Document Intelligence Service on port ${PORT}..."
mkdir -p "$PDF_DIR" "$PERSIST_DIR"

exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
