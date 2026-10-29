#!/bin/bash
set -e

echo "Starting DocuMind AI Document Intelligence Service..."
mkdir -p data db
exec uvicorn main:app --host 0.0.0.0 --port 8000
