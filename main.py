import os
import sys
import shutil
import re
import logging
import asyncio
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, Form, Header, Query, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from qa_engine import initialize_qa_engine, load_config, check_ollama_status, extract_pdf_documents, RAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("documind.server")

# Load configuration
config = load_config()
PDF_DIR = config["pdf_dir"]
PERSIST_DIR = config["persist_dir"]
MAX_UPLOAD_SIZE_BYTES = int(config.get("max_upload_size_mb", 20)) * 1024 * 1024

# Environment variable for admin authorization
SUPER_USER_KEY = os.getenv("SUPER_USER_KEY")
if not SUPER_USER_KEY:
    SUPER_USER_KEY = "documind-dev-supersecretkey-change-in-prod"
    logger.warning("No SUPER_USER_KEY specified in environment. Using development-only fallback key. Set SUPER_USER_KEY in production.")

# Global pipeline instance protected by an async lock
rag_pipeline: Optional[RAGPipeline] = None
engine_lock = asyncio.Lock()


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
    URL query parameter keys are strictly rejected to prevent credentials from being logged in URLs.
    """
    provided_key = header_key or form_key
    if not provided_key or provided_key != SUPER_USER_KEY:
        return False
    return True


async def reinitialize_qa_engine():
    """Reindexes all PDFs in PDF_DIR into PERSIST_DIR."""
    global rag_pipeline
    async with engine_lock:
        logger.info("Reinitializing DocuMind AI QA Engine...")
        os.makedirs(PDF_DIR, exist_ok=True)
        os.makedirs(PERSIST_DIR, exist_ok=True)

        try:
            pipeline, _ = await asyncio.to_thread(initialize_qa_engine, "config.yaml")
            rag_pipeline = pipeline
            logger.info("DocuMind AI QA Engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to reinitialize QA engine: {e}", exc_info=True)
            rag_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)
    await reinitialize_qa_engine()
    yield


app = FastAPI(
    title="DocuMind AI API",
    description="Enterprise Document Intelligence & Grounded Question Answering Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Restrict CORS to standard web methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=".")


class Question(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Question text cannot be empty.")


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker, orchestration, and monitoring."""
    pdf_count = len([f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]) if os.path.exists(PDF_DIR) else 0
    ollama_url = config.get("ollama_base_url", "http://localhost:11434")
    ollama_ok, ollama_msg = await asyncio.to_thread(check_ollama_status, ollama_url)

    return {
        "status": "healthy" if (rag_pipeline is not None or pdf_count == 0) else "initializing",
        "app": "DocuMind AI",
        "engine_ready": rag_pipeline is not None,
        "indexed_pdfs": pdf_count,
        "ollama_online": ollama_ok,
        "ollama_status": ollama_msg,
        "ollama_url": ollama_url,
        "model": config.get("llm_model")
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serves the main DocuMind AI question answering UI."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/ask")
async def ask_question(question: Question):
    """Processes user queries against indexed documents and returns answers with citations."""
    global rag_pipeline
    clean_query = question.query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if rag_pipeline is None:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")] if os.path.exists(PDF_DIR) else []
        if not pdf_files:
            return {
                "answer": "No documents are currently indexed in DocuMind AI. Please upload a PDF in the Document Admin panel to begin.",
                "sources": []
            }
        raise HTTPException(
            status_code=503,
            detail="DocuMind AI engine is initializing or re-indexing. Please retry in a few moments."
        )

    try:
        result = await asyncio.to_thread(rag_pipeline.answer_query, clean_query)
        return result
    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while generating the answer. Please check server logs."
        )


@app.get("/admin", response_class=HTMLResponse)
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

    # Re-index pipeline
    await reinitialize_qa_engine()

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
    pdf_list = []
    for f in sorted(os.listdir(PDF_DIR)):
        if f.lower().endswith(".pdf"):
            full_path = os.path.join(PDF_DIR, f)
            size_kb = round(os.path.getsize(full_path) / 1024, 1)
            pdf_list.append({"filename": f, "size_kb": size_kb})

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
        logger.info(f"Deleted document from storage: {safe_name}")
        await reinitialize_qa_engine()
        return JSONResponse(content={"message": f"'{safe_name}' deleted and vector index updated."})
    except Exception as e:
        logger.error(f"Failed to delete document '{safe_name}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete document.")
