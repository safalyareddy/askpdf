import os
import sys
import yaml
import logging
import functools
from typing import List, Dict, Any, Tuple, Optional
import httpx
import pypdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.language_models.llms import LLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("documind.engine")


class OpenAILikeLLM(LLM):
    """Universal OpenAI-compatible chat completions wrapper (Groq, Together, OpenRouter, vLLM, OpenAI)."""
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "llama-3.1-8b-instant"
    temperature: float = 0.1
    timeout_sec: float = 60.0

    @property
    def _llm_type(self) -> str:
        return "openai_compatible"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature
        }
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                res = client.post(url, json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Inference error calling {url} (model {self.model}): {e}")
            raise


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Loads configuration with defaults and environment variable overrides."""
    config: Dict[str, Any] = {
        "llm_provider": "ollama",
        "llm_model": "llama3",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": "",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "ollama_base_url": "http://localhost:11434",
        "pdf_dir": "./data/",
        "chunk_size": 500,
        "chunk_overlap": 100,
        "persist_dir": "./db",
        "history_length": 5,
        "use_gpu": False,
        "max_upload_size_mb": 20,
        "ollama_timeout_seconds": 60
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if loaded and isinstance(loaded, dict):
                    config.update(loaded)
        except Exception as e:
            logger.warning(f"Error loading {config_path}: {e}. Utilizing fallback defaults.")

    # Environment variable overrides
    if os.getenv("LLM_PROVIDER"):
        config["llm_provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_MODEL"):
        config["llm_model"] = os.getenv("LLM_MODEL")
    if os.getenv("LLM_BASE_URL"):
        config["llm_base_url"] = os.getenv("LLM_BASE_URL")
    if os.getenv("LLM_API_KEY"):
        config["llm_api_key"] = os.getenv("LLM_API_KEY")
    if os.getenv("EMBEDDING_MODEL"):
        config["embedding_model"] = os.getenv("EMBEDDING_MODEL")
    if os.getenv("OLLAMA_BASE_URL"):
        config["ollama_base_url"] = os.getenv("OLLAMA_BASE_URL")
    if os.getenv("PDF_DIR"):
        config["pdf_dir"] = os.getenv("PDF_DIR")
    if os.getenv("PERSIST_DIR"):
        config["persist_dir"] = os.getenv("PERSIST_DIR")
    if os.getenv("MAX_UPLOAD_SIZE_MB"):
        try:
            config["max_upload_size_mb"] = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
        except ValueError:
            pass

    return config


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
    chunk_size: int = 500,
    chunk_overlap: int = 100
) -> Tuple[List[Document], int, int]:
    """
    Extracts text page-by-page from a PDF and segments it into metadata-tagged chunks.
    Returns: (documents, total_pages, total_chars_extracted)
    """
    filename = os.path.basename(pdf_path)
    logger.info(f"Extracting text from PDF: {filename}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    documents: List[Document] = []

    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception as e:
        logger.error(f"Failed to parse PDF structure of '{filename}': {e}")
        return [], 0, 0

    num_pages = len(reader.pages)
    if num_pages == 0:
        logger.warning(f"PDF '{filename}' contains 0 pages.")
        return [], 0, 0

    total_chars = 0
    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        try:
            page_text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page {page_num} of '{filename}': {e}")
            page_text = ""

        page_text = page_text.strip()
        total_chars += len(page_text)
        if not page_text:
            continue

        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            chunk_clean = chunk.strip()
            if chunk_clean:
                documents.append(
                    Document(
                        page_content=chunk_clean,
                        metadata={"source": filename, "page": page_num}
                    )
                )

    logger.info(
        f"Extracted {len(documents)} chunks ({total_chars} chars) across {num_pages} pages from '{filename}'."
    )
    return documents, num_pages, total_chars


@functools.lru_cache(maxsize=4)
def get_embedding_function(model_name: str) -> HuggingFaceEmbeddings:
    """Initializes and caches the local HuggingFace embedding model."""
    logger.info(f"Loading embedding model: {model_name}")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )


def build_or_load_vectorstore(
    documents: List[Document],
    embedding_function: HuggingFaceEmbeddings,
    persist_dir: str
) -> Optional[Chroma]:
    """
    Builds or updates a Chroma vectorstore in persist_dir.
    Resets existing collection before inserting new documents to prevent stale chunks.
    """
    os.makedirs(persist_dir, exist_ok=True)

    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding_function
    )

    try:
        vectorstore.delete_collection()
    except Exception as e:
        logger.debug(f"Collection reset notice: {e}")

    # Recreate clean collection
    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding_function
    )

    if documents:
        logger.info(f"Indexing {len(documents)} document chunks into Chroma vectorstore at '{persist_dir}'...")
        vectorstore.add_documents(documents)
        return vectorstore

    logger.info("No documents provided; vectorstore initialized as empty.")
    return None


class RAGPipeline:
    def __init__(self, vectorstore: Optional[Chroma], llm: Any, top_k: int = 4):
        self.vectorstore = vectorstore
        self.llm = llm
        self.top_k = top_k
        self.qa_prompt = PromptTemplate(
            template=(
                "You are DocuMind AI, an intelligent, precise enterprise document assistant.\n"
                "Use ONLY the following retrieved context passages to answer the user's question.\n"
                "If the context does not contain enough information to answer, truthfully say:\n"
                "'I cannot find the answer to this question in the provided documents.'\n"
                "Do NOT make up facts or extrapolate beyond what is explicitly stated in the context.\n\n"
                "Retrieved Context:\n"
                "---------------------\n"
                "{context}\n"
                "---------------------\n\n"
                "Question: {question}\n"
                "Detailed Grounded Answer:"
            ),
            input_variables=["context", "question"]
        )

    def answer_query(self, query: str) -> Dict[str, Any]:
        """Performs similarity retrieval, formats strict context, and invokes the LLM."""
        if not self.vectorstore:
            return {
                "answer": "No documents are currently indexed. Please upload a PDF in the Admin Panel to begin.",
                "sources": []
            }

        try:
            docs = self.vectorstore.similarity_search(query, k=self.top_k)
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return {
                "answer": "A vector search error occurred while retrieving document passages.",
                "sources": []
            }

        if not docs:
            return {
                "answer": "I could not find any relevant passages in the indexed documents to answer your question.",
                "sources": []
            }

        context_parts = []
        sources = []
        seen_citations = set()

        for doc in docs:
            source = doc.metadata.get("source", "Unknown Document")
            page = doc.metadata.get("page", 1)
            content = doc.page_content.strip()

            context_parts.append(f"[Document: {source}, Page: {page}]\n{content}")

            citation_key = (source, page, content[:80])
            if citation_key not in seen_citations:
                seen_citations.add(citation_key)
                sources.append({
                    "source": source,
                    "page": page,
                    "snippet": content
                })

        formatted_context = "\n\n".join(context_parts)
        prompt = self.qa_prompt.format(context=formatted_context, question=query)

        try:
            response = self.llm.invoke(prompt)
            answer_text = response.strip() if isinstance(response, str) else str(response).strip()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            err_msg = str(e).lower()
            if "connection refused" in err_msg or "connect" in err_msg:
                return {
                    "answer": "Unable to connect to model service. Please verify your configured endpoint and credentials.",
                    "sources": sources
                }
            elif "timed out" in err_msg or "timeout" in err_msg:
                return {
                    "answer": "The language model timed out while processing your request. Please try again or query a shorter passage.",
                    "sources": sources
                }
            return {
                "answer": "Failed to generate answer from the language model. Please verify that the inference provider is operational.",
                "sources": sources
            }

        return {
            "answer": answer_text,
            "sources": sources
        }


def initialize_qa_engine(config_path: str = "config.yaml") -> Tuple[Optional[RAGPipeline], Dict[str, Any]]:
    """
    Initializes embeddings, scans pdf_dir, builds the vectorstore, and configures RAGPipeline.
    Supports local Ollama and hosted OpenAI-compatible providers (Groq, Together, OpenRouter, etc.).
    """
    config = load_config(config_path)
    pdf_dir = config["pdf_dir"]
    persist_dir = config["persist_dir"]
    chunk_size = config.get("chunk_size", 500)
    chunk_overlap = config.get("chunk_overlap", 100)
    provider = config.get("llm_provider", "ollama").lower()
    model_name = config.get("llm_model", "llama3")
    embedding_model = config.get("embedding_model", "BAAI/bge-small-en-v1.5")
    timeout_sec = float(config.get("ollama_timeout_seconds", 60))

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
    if provider in ["openai", "groq", "together", "openrouter", "openai_compatible"]:
        base_url = config.get("llm_base_url") or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        api_key = config.get("llm_api_key") or os.getenv("LLM_API_KEY", "")
        logger.info(f"Configuring hosted inference client ({provider}) at {base_url} (model: '{model_name}')...")
        llm = OpenAILikeLLM(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            temperature=0.1,
            timeout_sec=timeout_sec
        )
    else:
        ollama_url = config.get("ollama_base_url", "http://localhost:11434")
        logger.info(f"Configuring Ollama client at {ollama_url} (model: '{model_name}', timeout: {timeout_sec}s)...")
        llm = OllamaLLM(
            base_url=ollama_url,
            model=model_name,
            temperature=0.1,
            timeout=timeout_sec
        )

    pipeline = RAGPipeline(vectorstore=vectorstore, llm=llm) if vectorstore else None
    return pipeline, config
