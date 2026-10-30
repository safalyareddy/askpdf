import pytest
from core.retrieval import QueryIntent, classify_query_intent
from core.doc_registry import DocumentRegistry
from main import verify_admin_key, SUPER_USER_KEY, check_rate_limit, HTTPException


def test_classify_query_intent():
    assert classify_query_intent("What is the abstract of the report?") == QueryIntent.ABSTRACT
    assert classify_query_intent("Give me the executive summary") == QueryIntent.ABSTRACT
    assert classify_query_intent("Summarize 23MIS0125_ListLocal_Safalya.pdf") == QueryIntent.SUMMARIZATION
    assert classify_query_intent("Provide a brief overview of the first document") == QueryIntent.SUMMARIZATION
    assert classify_query_intent("Compare the approaches in both documents") == QueryIntent.COMPARISON
    assert classify_query_intent("What is the difference between doc 1 and doc 2?") == QueryIntent.COMPARISON
    assert classify_query_intent("What are the core components of DocuMind AI?") == QueryIntent.FACTUAL_QA


def test_doc_registry_ordinal_resolution(tmp_path):
    reg = DocumentRegistry(str(tmp_path / "test_reg.json"))
    reg.register("alpha_doc.pdf", pages=10, chunks=20, size_kb=100.0)
    reg.register("beta_doc.pdf", pages=15, chunks=30, size_kb=150.0)

    # First doc resolution
    doc1 = reg.resolve_ordinal("Summarize the first document.")
    assert doc1 is not None
    assert doc1["filename"] == "alpha_doc.pdf"

    # Second doc resolution
    doc2 = reg.resolve_ordinal("Tell me about the 2nd document.")
    assert doc2 is not None
    assert doc2["filename"] == "beta_doc.pdf"

    # Mentioned document resolution
    matched = reg.find_mentioned_document("Explain beta_doc.pdf methodology")
    assert matched is not None
    assert matched["filename"] == "beta_doc.pdf"


def test_admin_auth_constant_time():
    # Correct key passes
    assert verify_admin_key(header_key=SUPER_USER_KEY) is True
    # Wrong key fails
    assert verify_admin_key(header_key="wrong_password_123") is False
    # None fails
    assert verify_admin_key(header_key=None) is False


def test_rate_limiting_enforcement():
    # Distinct test IP
    test_ip = "192.168.100.42"
    # Execute within limit (30 per min)
    for _ in range(30):
        check_rate_limit(test_ip)

    # 31st request triggers HTTP 429
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(test_ip)
    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
