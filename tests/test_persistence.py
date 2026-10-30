import os
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from qa_engine import (
    build_or_load_vectorstore,
    get_embedding_function,
    RAGPipeline,
    CHROMA_COLLECTION_NAME
)


def test_vectorstore_persistence_preserves_documents(tmp_path):
    """Verifies that Chroma vectorstore preserves indexed documents across restarts."""
    persist_dir = str(tmp_path / "test_db")
    embedding_fn = get_embedding_function("BAAI/bge-small-en-v1.5")

    doc1 = Document(
        page_content="DocuMind AI provides grounded document intelligence.",
        metadata={"source": "test-doc1.pdf", "page": 1}
    )

    # First load: index doc1
    vs1 = build_or_load_vectorstore([doc1], embedding_fn, persist_dir)
    assert vs1 is not None
    results1 = vs1.similarity_search("DocuMind AI", k=1)
    assert len(results1) == 1
    assert results1[0].metadata["source"] == "test-doc1.pdf"

    # Second load: pass same document - should not duplicate chunks
    vs2 = build_or_load_vectorstore([doc1], embedding_fn, persist_dir)
    data = vs2.get(include=["metadatas"])
    assert len(data["ids"]) == 1

    # Third load: empty list passed (e.g. reload on existing directory) - should retain persisted data
    vs3 = build_or_load_vectorstore([], embedding_fn, persist_dir)
    assert vs3 is not None
    data3 = vs3.get(include=["metadatas"])
    assert len(data3["ids"]) == 1
    assert data3["metadatas"][0]["source"] == "test-doc1.pdf"


def test_vectorstore_handles_document_removal(tmp_path):
    """Verifies that removing a document source from incoming list cleans up Chroma collection."""
    persist_dir = str(tmp_path / "test_db_removal")
    embedding_fn = get_embedding_function("BAAI/bge-small-en-v1.5")

    doc_a = Document(page_content="Passage from Document A", metadata={"source": "docA.pdf", "page": 1})
    doc_b = Document(page_content="Passage from Document B", metadata={"source": "docB.pdf", "page": 1})

    # Index both A and B
    vs = build_or_load_vectorstore([doc_a, doc_b], embedding_fn, persist_dir)
    data = vs.get(include=["metadatas"])
    assert len(data["ids"]) == 2

    # Subsequent sync where doc_b was removed
    vs_synced = build_or_load_vectorstore([doc_a], embedding_fn, persist_dir)
    data_synced = vs_synced.get(include=["metadatas"])
    assert len(data_synced["ids"]) == 1
    sources = [m["source"] for m in data_synced["metadatas"]]
    assert "docA.pdf" in sources
    assert "docB.pdf" not in sources
