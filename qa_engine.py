import os
import sys
import logging
from typing import List, Dict, Any, Tuple, Optional
import httpx
from langchain_core.documents import Document
from langchain_ollama import OllamaLLM

from core.config import load_config
from core.doc_registry import registry, DocumentRegistry
from core.pdf_processor import (
    extract_pdf_documents as _extract_pdf_docs,
    detect_printed_page_number,
    is_table_of_contents_page,
    extract_section_heading
)
from core.vector_store import (
    get_embedding_function,
    build_or_load_vectorstore,
    CHROMA_COLLECTION_NAME
)
from core.retrieval import (
    QueryIntent,
    classify_query_intent,
    RetrievalEngine
)
from core.generation import (
    OpenAILikeLLM,
    GenerationEngine
)

logger = logging.getLogger("documind.engine")


def check_ollama_status(ollama_url: str, timeout: float = 2.0) -> Tuple[bool, str]:
    """Checks whether the Ollama server is reachable and active."""
    try:
        url = ollama_url.rstrip("/") + "/api/tags"
        resp = httpx.get(url, timeout=timeout)
        if resp.status_code == 200:
            return True, "Ollama is reachable and responding."
        return False, f"Ollama returned unexpected status code: {resp.status_code}"
    except Exception as e:
        return False, f"Could not connect to Ollama at {ollama_url}: {str(e)}"


def extract_pdf_documents(
    pdf_path: str,
    chunk_size: int = 600,
    chunk_overlap: int = 120
) -> Tuple[List[Document], int, int]:
    """
    Backwards-compatible wrapper returning (documents, total_pages, total_chars).
    Also updates document registry with printed pages and section headings.
    """
    docs, pages, chars, printed_map, sections = _extract_pdf_docs(pdf_path, chunk_size, chunk_overlap)
    filename = os.path.basename(pdf_path)
    size_kb = round(os.path.getsize(pdf_path) / 1024, 1) if os.path.exists(pdf_path) else 0.0

    if docs:
        registry.register(
            filename=filename,
            pages=pages,
            chunks=len(docs),
            size_kb=size_kb,
            printed_pages=printed_map,
            sections=sections
        )

    return docs, pages, chars


class RAGPipeline:
    def __init__(self, vectorstore: Any, llm: Any, top_k: int = 5):
        self.vectorstore = vectorstore
        self.llm = llm
        self.top_k = top_k
        self.registry = registry
        self.retrieval_engine = RetrievalEngine(vectorstore=vectorstore, doc_registry=self.registry)
        self.generation_engine = GenerationEngine(llm=llm)

    def answer_query(
        self,
        query: str,
        session_selected_doc: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes complete RAG workflow:
        1. Classifies query intent.
        2. Resolves document scope (ordinal, name, active session, or all).
        3. Checks if user document selection is required.
        4. Retrieves relevant chunks (with anti-TOC filtering).
        5. Generates grounded answer with physical and printed page citations.
        """
        if not self.vectorstore:
            return {
                "answer": "No documents are currently indexed in DocuMind AI. Please upload a PDF in the Document Admin panel to begin.",
                "sources": []
            }

        all_docs = self.registry.get_all()

        # 1. Classify query intent
        intent = classify_query_intent(query)
        logger.info(f"Classified query intent: {intent.value} for query: '{query}'")

        # 2. Resolve document scope
        target_doc, is_multi_doc, is_ambiguous = self.retrieval_engine.resolve_document_scope(
            query=query,
            session_selected_doc=session_selected_doc
        )

        # 3. Handle ambiguous document scope when multiple documents exist
        if is_ambiguous and len(all_docs) > 1 and not session_selected_doc:
            doc_options = [
                {
                    "document_id": d["document_id"],
                    "filename": d["filename"],
                    "display_name": f"{d['upload_order']}. {d['display_name']} ({d['pages']} pages)",
                    "upload_order": d["upload_order"]
                }
                for d in all_docs
            ]
            doc_options.append({
                "document_id": "all",
                "filename": "all",
                "display_name": "All Indexed Documents (Cross-Document Search)",
                "upload_order": 999
            })

            return {
                "needs_document_selection": True,
                "message": (
                    f"You have {len(all_docs)} documents indexed. Please select which document you would "
                    "like to inquire about, or choose 'All Documents':"
                ),
                "options": doc_options,
                "answer": "",
                "sources": []
            }

        # If ordinal was resolved, log confirmation
        if target_doc:
            logger.info(f"Scoped query to document '{target_doc['filename']}' (upload order: {target_doc.get('upload_order')}).")

        # 4. Retrieve chunks
        context_chunks = self.retrieval_engine.retrieve_relevant_chunks(
            query=query,
            target_doc=target_doc,
            intent=intent,
            top_k=self.top_k
        )

        if not context_chunks:
            doc_scope_str = f" in '{target_doc['filename']}'" if target_doc else ""
            return {
                "answer": f"I could not find relevant information{doc_scope_str} to answer your question.",
                "sources": []
            }

        # 5. Generate grounded response with physical & printed citations
        result = self.generation_engine.generate_response(
            query=query,
            context_docs=context_chunks,
            intent=intent
        )

        # Attach active document resolution to response metadata
        if target_doc:
            result["active_document"] = target_doc["filename"]
            result["active_document_id"] = target_doc["document_id"]

        return result


def initialize_qa_engine(config_path: str = "config.yaml") -> Tuple[Optional[RAGPipeline], Dict[str, Any]]:
    """
    Scans PDF directory, indexes all documents, configures registry, and builds RAGPipeline.
    """
    config = load_config(config_path)
    pdf_dir = config["pdf_dir"]
    persist_dir = config["persist_dir"]
    chunk_size = config.get("chunk_size", 600)
    chunk_overlap = config.get("chunk_overlap", 120)
    provider = config.get("llm_provider", "ollama").lower()
    model_name = config.get("llm_model", "llama3")
    embedding_model = config.get("embedding_model", "BAAI/bge-small-en-v1.5")
    timeout_sec = float(config.get("ollama_timeout_seconds", 90))
    num_ctx = int(config.get("ollama_num_ctx", 4096))

    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(persist_dir, exist_ok=True)

    pdf_files = [f for f in sorted(os.listdir(pdf_dir)) if f.lower().endswith(".pdf")]
    all_documents: List[Document] = []

    for pdf_file in pdf_files:
        full_path = os.path.join(pdf_dir, pdf_file)
        docs, pages, chars = extract_pdf_documents(full_path, chunk_size, chunk_overlap)
        all_documents.extend(docs)

    embedding_fn = get_embedding_function(embedding_model)
    vectorstore = build_or_load_vectorstore(all_documents, embedding_fn, persist_dir)

    # Initialize appropriate LLM provider
    ollama_url = config.get("ollama_base_url", "http://localhost:11434")
    if provider in ["openai", "groq", "together", "openrouter", "openai_compatible"]:
        base_url = config.get("llm_base_url") or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        api_key = config.get("llm_api_key") or os.getenv("LLM_API_KEY", "")
        if not api_key:
            is_ollama_up, _ = check_ollama_status(ollama_url, timeout=1.0)
            if is_ollama_up:
                logger.info(f"Using active local Ollama on MacBook ({ollama_url})...")
                provider = "ollama"
                model_name = "llama3"
                llm = OllamaLLM(
                    base_url=ollama_url,
                    model=model_name,
                    temperature=0.1,
                    num_ctx=num_ctx,
                    timeout=timeout_sec
                )
            else:
                logger.info(f"Configuring hosted inference client at {base_url}...")
                llm = OpenAILikeLLM(
                    base_url=base_url,
                    api_key="",
                    model=model_name,
                    temperature=0.1,
                    timeout_sec=timeout_sec
                )
        else:
            logger.info(f"Configuring hosted inference client at {base_url} (model: {model_name})...")
            llm = OpenAILikeLLM(
                base_url=base_url,
                api_key=api_key,
                model=model_name,
                temperature=0.1,
                timeout_sec=timeout_sec
            )
    else:
        logger.info(f"Configuring Ollama client at {ollama_url} (model: '{model_name}', num_ctx: {num_ctx})...")
        llm = OllamaLLM(
            base_url=ollama_url,
            model=model_name,
            temperature=0.1,
            num_ctx=num_ctx,
            timeout=timeout_sec
        )

    pipeline = RAGPipeline(vectorstore=vectorstore, llm=llm, top_k=5) if vectorstore else None
    return pipeline, config
