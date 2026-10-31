import os
import sys
import shutil
import re
import time
import logging
import asyncio
import secrets
import gc
from collections import defaultdict
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, Form, Header, Query, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.config import load_config
from core.doc_registry import registry
from core.vector_store import trim_process_memory
from qa_engine import (
    initialize_qa_engine,
    check_ollama_status,
    extract_pdf_documents,
    RAGPipeline
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("askpdf.server")

# Load configuration
config = load_config()
PDF_DIR = config["pdf_dir"]
PERSIST_DIR = config["persist_dir"]
MAX_UPLOAD_SIZE_BYTES = int(config.get("max_upload_size_mb", 20)) * 1024 * 1024
RATE_LIMIT_PER_MINUTE = int(config.get("rate_limit_per_minute", 30))

# Environment variable for admin authorization with fail-closed security
RAW_SUPER_USER_KEY = os.getenv("SUPER_USER_KEY", "").strip()
INSECURE_PLACEHOLDERS = {
    "documind-dev-supersecretkey-change-in-prod",
    "YOUR_SECRET_KEY",
    "changeme",
    "admin",
    ""
}
SUPER_USER_KEY: Optional[str] = None
if RAW_SUPER_USER_KEY and RAW_SUPER_USER_KEY not in INSECURE_PLACEHOLDERS:
    SUPER_USER_KEY = RAW_SUPER_USER_KEY
    logger.info("Admin authentication enabled with secure SUPER_USER_KEY.")
else:
    logger.warning("No secure SUPER_USER_KEY configured. Admin endpoints will fail closed.")

# Global pipeline instance protected by an async lock
rag_pipeline: Optional[RAGPipeline] = None
engine_lock = asyncio.Lock()

# In-memory sliding window rate limiter: IP -> list of request timestamps
rate_limit_records: Dict[str, List[float]] = defaultdict(list)

# In-memory session tracking for multi-turn conversation document context
session_store: Dict[str, Dict[str, Any]] = defaultdict(dict)


def sanitize_filename(filename: str) -> str:
    """Removes path components and restricts filename to safe alphanumeric characters."""
    base = os.path.basename(filename)
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe or "document.pdf"


def verify_admin_key(
    header_key: Optional[str] = None,
    form_key: Optional[str] = None
) -> bool:
    """
    Validates super user key against header or form payload.
    Uses constant-time comparison (secrets.compare_digest) to prevent timing attacks.
    URL query parameter keys are strictly rejected.
    """
    if not SUPER_USER_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin operations are disabled: SUPER_USER_KEY is not configured in the server environment."
        )

    provided_key = header_key or form_key
    if not provided_key:
        return False

    return secrets.compare_digest(provided_key.strip(), SUPER_USER_KEY)


def check_rate_limit(client_ip: str):
    """Enforces per-IP sliding window rate limiting."""
    now = time.time()
    window_start = now - 60.0
    timestamps = [t for t in rate_limit_records[client_ip] if t > window_start]
    timestamps.append(now)
    rate_limit_records[client_ip] = timestamps

    if len(timestamps) > RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute allowed."
        )


async def _reinitialize_qa_engine_unlocked():
    """Internal helper to reindex all PDFs into PERSIST_DIR without acquiring engine_lock."""
    global rag_pipeline
    logger.info("Reinitializing AskPDF QA Engine...")
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)
    registry.reconcile_with_disk(PDF_DIR)

    try:
        pipeline, _ = await asyncio.to_thread(initialize_qa_engine, "config.yaml")
        rag_pipeline = pipeline
        trim_process_memory()
        logger.info("AskPDF QA Engine initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to reinitialize QA engine: {e}", exc_info=True)
        rag_pipeline = None
        trim_process_memory()


async def reinitialize_qa_engine():
    """Reindexes all PDFs in PDF_DIR into PERSIST_DIR with lock protection."""
    async with engine_lock:
        await _reinitialize_qa_engine_unlocked()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)
    registry.reconcile_with_disk(PDF_DIR)
    
    # Give the container 2 seconds to settle its initial boot memory before starting QA engine indexing
    async def delayed_engine_init():
        await asyncio.sleep(2.0)
        await reinitialize_qa_engine()

    # Asynchronously initialize QA engine in background so Uvicorn binds immediately and health checks pass
    asyncio.create_task(delayed_engine_init())
    yield


app = FastAPI(
    title="AskPDF API",
    description="Your documents. Your answers. — AI-powered document intelligence and grounded question answering platform.",
    version="2.0.0",
    lifespan=lifespan
)

# Production CORS configuration: allow Render, Vercel, and local execution
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://documind-ai-ddt8.onrender.com",
        "https://askpdf-omega.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5500",
    ],
    allow_origin_regex=r"https://.*(\.onrender\.com|\.vercel\.app)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

templates = Jinja2Templates(directory=".")


class Question(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Question text cannot be empty.")
    document_id: Optional[str] = Field(None, description="Optional target document ID or 'all'")
    session_id: Optional[str] = Field(None, description="Client session ID for multi-turn conversational context")


@app.get("/health")
@app.get("/healthz")
@app.get("/api/status")
@app.get("/api/system/status")
async def health_check():
    """Health check endpoint for local monitoring, Docker, and ngrok."""
    pdf_count = len([f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]) if os.path.exists(PDF_DIR) else 0
    provider = config.get("llm_provider", "ollama").lower()
    model = config.get("llm_model", "llama3")

    model_online = True
    model_msg = f"Provider '{provider}' active."

    if provider == "ollama":
        ollama_url = config.get("ollama_base_url", "http://localhost:11434")
        model_online, model_msg = await asyncio.to_thread(check_ollama_status, ollama_url)
    else:
        api_key = config.get("llm_api_key") or os.getenv("LLM_API_KEY", "")
        if not api_key:
            model_online = False
            model_msg = "No LLM_API_KEY configured for hosted inference."
        else:
            model_online = True
            model_msg = f"Hosted provider '{provider}' ready (model: {model})."

    return {
        "status": "healthy",
        "app": "AskPDF",
        "tagline": "Your documents. Your answers.",
        "version": "2.0.0",
        "engine_ready": rag_pipeline is not None,
        "indexed_pdfs": pdf_count,
        "provider": provider,
        "model_online": model_online,
        "ollama_online": model_online,
        "model_status": model_msg,
        "model": model,
        "admin_auth_configured": SUPER_USER_KEY is not None
    }


@app.get("/models")
async def get_models():
    """Returns active model metadata, provider status, and supported options."""
    provider = config.get("llm_provider", "ollama").lower()
    model = config.get("llm_model", "llama3")
    return {
        "status": "online",
        "current_provider": provider,
        "current_model": model,
        "embedding_model": config.get("embedding_model", "BAAI/bge-small-en-v1.5"),
        "supported_providers": ["groq", "openai_compatible", "ollama"],
        "recommended_cloud_model": "llama-3.3-70b-versatile"
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serves the main AskPDF question answering UI."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/documents")
async def list_available_documents():
    """Returns public list of indexed documents with metadata for the UI document selector."""
    all_docs = registry.get_all()
    return {
        "documents": [
            {
                "document_id": d["document_id"],
                "filename": d["filename"],
                "display_name": d["display_name"],
                "upload_order": d["upload_order"],
                "pages": d["pages"],
                "chunks": d["chunks"],
                "size_kb": d["size_kb"]
            }
            for d in all_docs
        ],
        "total": len(all_docs)
    }


@app.post("/ask")
async def ask_question(question: Question, request: Request):
    """Processes user queries against indexed documents with session context and citations."""
    global rag_pipeline

    client_ip = request.client.host if request.client else "127.0.0.1"
    check_rate_limit(client_ip)

    clean_query = question.query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if rag_pipeline is None:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")] if os.path.exists(PDF_DIR) else []
        if not pdf_files:
            return {
                "answer": "No documents are currently indexed in AskPDF. Please upload a PDF in the Document Management panel to begin.",
                "sources": []
            }
        raise HTTPException(
            status_code=503,
            detail="AskPDF engine is initializing or re-indexing. Please retry in a few moments."
        )

    # Resolve session document context
    session_id = question.session_id or "default_session"
    active_session_doc = question.document_id

    # If document_id was explicitly passed (e.g. from UI selector), update session
    if active_session_doc:
        session_store[session_id]["selected_document"] = active_session_doc
    else:
        active_session_doc = session_store[session_id].get("selected_document")

    try:
        result = await asyncio.to_thread(
            rag_pipeline.answer_query,
            clean_query,
            session_selected_doc=active_session_doc
        )

        # If answer was scoped to a specific document, persist into session
        if result.get("active_document"):
            session_store[session_id]["selected_document"] = result["active_document"]

        return result
    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while generating the answer. Please check server logs."
        )


@app.post("/predict")
async def predict(question: Question, request: Request):
    """Alias for /ask to support standard prediction clients."""
    return await ask_question(question, request)


@app.get("/config.js")
async def get_config_js():
    """Serves runtime JavaScript configuration using the request's origin."""
    return Response(
        content='window.ASKPDF_API_URL = window.location.origin;\n',
        media_type="application/javascript"
    )


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Serves the Document Admin portal."""
    return templates.TemplateResponse(request=request, name="admin.html")


@app.post("/admin/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    super_user_key: Optional[str] = Form(None),
    x_admin_key: Optional[str] = Header(None)
):
    """Uploads, validates, and indexes a PDF document."""
    if not verify_admin_key(header_key=x_admin_key, form_key=super_user_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid admin key. Provide a valid X-Admin-Key header."
        )

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files (.pdf) are allowed.")

    safe_name = sanitize_filename(file.filename)
    os.makedirs(PDF_DIR, exist_ok=True)
    destination_path = os.path.join(PDF_DIR, safe_name)

    # Read initial chunk to inspect magic bytes
    first_chunk = await file.read(1024)
    if not first_chunk.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format: File header does not match PDF signature."
        )

    total_bytes = len(first_chunk)
    try:
        with open(destination_path, "wb") as buffer:
            buffer.write(first_chunk)
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    buffer.close()
                    if os.path.exists(destination_path):
                        os.remove(destination_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed upload size of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to write uploaded file '{safe_name}': {e}", exc_info=True)
        if os.path.exists(destination_path):
            os.remove(destination_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded file.")

    # Check for extractable digital text
    docs, pages, chars = extract_pdf_documents(destination_path)
    ocr_notice = ""
    if chars == 0:
        ocr_notice = " Note: No digital text was detected (scanned or image-only PDFs require an OCR engine, which is not currently enabled)."

    # Incremental indexing with memory-safe batches of 16
    async with engine_lock:
        if rag_pipeline and rag_pipeline.vectorstore and docs:
            try:
                await asyncio.to_thread(rag_pipeline.vectorstore.delete, where={"source": safe_name})
            except Exception:
                pass
            batch_size = 16
            for i in range(0, len(docs), batch_size):
                await asyncio.to_thread(rag_pipeline.vectorstore.add_documents, docs[i:i + batch_size])
                gc.collect()
        else:
            await _reinitialize_qa_engine_unlocked()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"'{safe_name}' uploaded and indexed successfully ({pages} pages, {len(docs)} text chunks).{ocr_notice}",
            "filename": safe_name,
            "pages": pages,
            "chunks": len(docs),
            "text_detected": chars > 0
        }
    )


@app.get("/admin/list-pdfs")
async def list_pdfs(
    x_admin_key: Optional[str] = Header(None)
):
    """Lists all indexed PDFs with metadata."""
    if not verify_admin_key(header_key=x_admin_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid admin key. Provide a valid X-Admin-Key header."
        )

    os.makedirs(PDF_DIR, exist_ok=True)
    registry.reconcile_with_disk(PDF_DIR)
    all_registered = registry.get_all()

    pdf_list = []
    for d in all_registered:
        pdf_list.append({
            "document_id": d["document_id"],
            "filename": d["filename"],
            "display_name": d["display_name"],
            "upload_order": d["upload_order"],
            "pages": d["pages"],
            "chunks": d["chunks"],
            "size_kb": d["size_kb"]
        })

    return {"pdfs": pdf_list, "total": len(pdf_list)}


@app.delete("/admin/delete-pdf")
async def delete_pdf(
    filename: str = Query(...),
    x_admin_key: Optional[str] = Header(None)
):
    """Deletes a PDF file and invalidates its vector embeddings."""
    if not verify_admin_key(header_key=x_admin_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid admin key. Provide a valid X-Admin-Key header."
        )

    safe_name = sanitize_filename(filename)
    path = os.path.join(PDF_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{safe_name}' not found.")

    try:
        os.remove(path)
        registry.remove(safe_name)
        logger.info(f"Deleted document from storage and registry: {safe_name}")

        async with engine_lock:
            if rag_pipeline and rag_pipeline.vectorstore:
                try:
                    await asyncio.to_thread(rag_pipeline.vectorstore.delete, where={"source": safe_name})
                except Exception:
                    await _reinitialize_qa_engine_unlocked()
            else:
                await _reinitialize_qa_engine_unlocked()

        return JSONResponse(content={"message": f"'{safe_name}' deleted and vector index updated."})
    except Exception as e:
        logger.error(f"Failed to delete document '{safe_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete document.")
