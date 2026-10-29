import os
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from qa_engine import (
    extract_pdf_documents,
    load_config,
    check_ollama_status,
    RAGPipeline
)


def test_config_defaults():
    config = load_config("config.yaml")
    assert "llm_model" in config
    assert "pdf_dir" in config
    assert "persist_dir" in config
    assert config["chunk_size"] > 0
    assert config["chunk_overlap"] >= 0
    assert "ollama_timeout_seconds" in config


def test_extract_pdf_documents_from_handbook():
    sample_pdf = os.path.join("data", "documind-handbook.pdf")
    if not os.path.exists(sample_pdf):
        pytest.skip("Synthetic handbook PDF not found in data directory.")

    docs, pages, chars = extract_pdf_documents(sample_pdf, chunk_size=300, chunk_overlap=50)
    assert pages >= 2, "Expected at least 2 pages in handbook"
    assert len(docs) > 0, "Should have extracted document chunks"
    assert chars > 0, "Should have non-zero character count"

    # Verify metadata integrity
    first_doc = docs[0]
    assert "source" in first_doc.metadata
    assert first_doc.metadata["source"] == "documind-handbook.pdf"
    assert "page" in first_doc.metadata
    assert isinstance(first_doc.metadata["page"], int)
    assert first_doc.metadata["page"] >= 1
    assert len(first_doc.page_content.strip()) > 0


def test_extract_invalid_pdf(tmp_path):
    fake_pdf = tmp_path / "corrupt.pdf"
    fake_pdf.write_bytes(b"This is definitely not a real PDF file")
    docs, pages, chars = extract_pdf_documents(str(fake_pdf))
    assert docs == []
    assert pages == 0
    assert chars == 0


def test_rag_pipeline_answer_query_empty_store():
    mock_llm = MagicMock()
    pipeline = RAGPipeline(vectorstore=None, llm=mock_llm)
    res = pipeline.answer_query("What is DocuMind?")
    assert "No documents are currently indexed" in res["answer"]
    assert res["sources"] == []


def test_rag_pipeline_answer_query_with_mock_vectorstore():
    mock_vectorstore = MagicMock()
    mock_doc = Document(
        page_content="DocuMind AI provides enterprise document intelligence.",
        metadata={"source": "documind-handbook.pdf", "page": 1}
    )
    mock_vectorstore.similarity_search.return_value = [mock_doc]

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = "DocuMind AI provides enterprise document intelligence."

    pipeline = RAGPipeline(vectorstore=mock_vectorstore, llm=mock_llm, top_k=2)
    result = pipeline.answer_query("Tell me about DocuMind")

    assert "DocuMind AI" in result["answer"]
    assert len(result["sources"]) == 1
    assert result["sources"][0]["source"] == "documind-handbook.pdf"
    assert result["sources"][0]["page"] == 1


def test_rag_pipeline_handles_llm_connection_error():
    mock_vectorstore = MagicMock()
    mock_doc = Document(page_content="Sample text", metadata={"source": "doc.pdf", "page": 1})
    mock_vectorstore.similarity_search.return_value = [mock_doc]

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("Connection refused at http://localhost:11434")

    pipeline = RAGPipeline(vectorstore=mock_vectorstore, llm=mock_llm)
    result = pipeline.answer_query("Query")

    assert "Unable to connect" in result["answer"]
    assert len(result["sources"]) == 1


def test_check_ollama_status_offline():
    # Test checking a non-existent port returns False safely
    is_online, msg = check_ollama_status("http://127.0.0.1:9999", timeout=0.5)
    assert not is_online
    assert "Could not connect to Ollama" in msg


def test_openai_like_llm_wrapper():
    from qa_engine import OpenAILikeLLM
    from unittest.mock import patch, MagicMock

    llm = OpenAILikeLLM(
        base_url="https://api.groq.com/openai/v1",
        api_key="mock_key",
        model="llama-3.1-8b-instant"
    )
    assert llm._llm_type == "openai_compatible"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "DocuMind AI answer via cloud API"}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = llm.invoke("Test prompt")
        assert "DocuMind AI answer" in res

