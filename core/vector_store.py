import os
import gc
import logging
import functools
from typing import List, Dict, Any, Optional, Set
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

logger = logging.getLogger("documind.vectorstore")

CHROMA_COLLECTION_NAME = "documind_documents"


@functools.lru_cache(maxsize=4)
def get_embedding_function(model_name: str = "BAAI/bge-small-en-v1.5") -> HuggingFaceEmbeddings:
    """Initializes and caches the HuggingFace embedding model with memory-safe batch size."""
    logger.info(f"Loading embedding model: {model_name}")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 16}
    )


def build_or_load_vectorstore(
    documents: List[Document],
    embedding_function: HuggingFaceEmbeddings,
    persist_dir: str
) -> Optional[Chroma]:
    """
    Builds or loads a persistent Chroma vectorstore in persist_dir.
    Preserves existing embeddings across restarts without wiping the collection.
    Synchronizes new and deleted document chunks incrementally with garbage collection.
    """
    os.makedirs(persist_dir, exist_ok=True)

    vectorstore = Chroma(
        collection_name=CHROMA_COLLECTION_NAME,
        persist_directory=persist_dir,
        embedding_function=embedding_function
    )

    # Check which document sources and ingestion versions are currently in Chroma
    indexed_versions: Dict[str, str] = {}
    try:
        data = vectorstore.get(include=["metadatas"])
        if data and "metadatas" in data and data["metadatas"]:
            for m in data["metadatas"]:
                if m and "source" in m:
                    src = m["source"]
                    v = m.get("ingestion_version", "1.0.0")
                    indexed_versions[src] = v
    except Exception as e:
        logger.warning(f"Notice reading existing vectorstore: {e}")
        indexed_versions = {}

    existing_sources = set(indexed_versions.keys())
    incoming_sources = set(
        doc.metadata.get("source") for doc in documents if doc.metadata and doc.metadata.get("source")
    )

    if documents:
        # 1. Remove any documents currently in vectorstore that are no longer in incoming documents
        orphans = existing_sources - incoming_sources
        for orphan in orphans:
            try:
                logger.info(f"Removing obsolete vector embeddings for deleted file: {orphan}")
                vectorstore.delete(where={"source": orphan})
            except Exception as e:
                logger.warning(f"Could not remove orphan chunks for {orphan}: {e}")

        # 2. Check for documents that need schema upgrade to INGESTION_VERSION ("2.0.0")
        for src, ver in list(indexed_versions.items()):
            if src in incoming_sources and ver != "2.0.0":
                logger.info(f"Upgrading vector index schema for '{src}' (version {ver} -> 2.0.0)...")
                try:
                    vectorstore.delete(where={"source": src})
                    existing_sources.discard(src)
                except Exception as e:
                    logger.warning(f"Could not purge old schema chunks for {src}: {e}")

        # 3. Index any chunks belonging to documents not yet present in existing_sources
        chunks_to_add = [doc for doc in documents if doc.metadata.get("source") not in existing_sources]
        if chunks_to_add:
            logger.info(
                f"Indexing {len(chunks_to_add)} document chunks into persistent Chroma collection "
                f"'{CHROMA_COLLECTION_NAME}' at '{persist_dir}'..."
            )
            batch_size = 32
            for i in range(0, len(chunks_to_add), batch_size):
                batch = chunks_to_add[i:i + batch_size]
                vectorstore.add_documents(batch)
                gc.collect()
        else:
            logger.info(
                f"All {len(incoming_sources)} document(s) are already persistently indexed in "
                f"Chroma collection '{CHROMA_COLLECTION_NAME}'."
            )

        return vectorstore

    # If no incoming documents were passed, check if collection already contains data
    if existing_sources:
        logger.info(f"Loaded persistent vectorstore with {len(existing_sources)} document(s) from '{persist_dir}'.")
        return vectorstore

    logger.info("No documents provided and vectorstore is empty.")
    return None
