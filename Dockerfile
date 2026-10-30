FROM python:3.11-slim

LABEL maintainer="AskPDF"
LABEL description="AskPDF — Your documents. Your answers."

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU wheel (compatible with both ARM64 aarch64 and x86_64)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu || \
    pip install --no-cache-dir torch

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
RUN chmod +x /app/entrypoint.sh

# Ensure data, db, and storage directories exist
RUN mkdir -p /app/data /app/db /app/storage

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["/app/entrypoint.sh"]
