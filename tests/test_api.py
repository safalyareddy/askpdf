import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app, SUPER_USER_KEY

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "DocuMind AI"
    assert "status" in data
    assert "indexed_pdfs" in data
    assert "ollama_online" in data

    # Verify /healthz alias
    res_z = client.get("/healthz")
    assert res_z.status_code == 200
    assert res_z.json()["status"] == "healthy"


def test_html_pages():
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "DocuMind AI" in res_home.text

    res_admin = client.get("/admin")
    assert res_admin.status_code == 200
    assert "DocuMind AI" in res_admin.text
    assert "Admin Portal" in res_admin.text


def test_ask_empty_query():
    response = client.post("/ask", json={"query": ""})
    assert response.status_code in [400, 422]

    response_spaces = client.post("/ask", json={"query": "   "})
    assert response_spaces.status_code == 400


def test_admin_auth_failed_without_header():
    res = client.get("/admin/list-pdfs")
    assert res.status_code == 403
    assert "Unauthorized" in res.json()["detail"]


def test_admin_auth_failed_with_wrong_key():
    res = client.get("/admin/list-pdfs", headers={"X-Admin-Key": "incorrect-secret-key"})
    assert res.status_code == 403


def test_admin_auth_rejects_query_param_key():
    # Enforce security control: query param authentication must be rejected
    res = client.get(f"/admin/list-pdfs?super_user_key={SUPER_USER_KEY}")
    assert res.status_code == 403


def test_admin_list_pdfs_success():
    res = client.get("/admin/list-pdfs", headers={"X-Admin-Key": SUPER_USER_KEY})
    assert res.status_code == 200
    data = res.json()
    assert "pdfs" in data
    assert isinstance(data["pdfs"], list)


def test_upload_invalid_file_extension():
    files = {"file": ("malicious.txt", b"Hello text file", "text/plain")}
    res = client.post(
        "/admin/upload-pdf",
        files=files,
        headers={"X-Admin-Key": SUPER_USER_KEY}
    )
    assert res.status_code == 400
    assert "Only PDF files" in res.json()["detail"]


def test_upload_invalid_magic_bytes():
    # PDF extension but fake non-PDF content
    files = {"file": ("fake.pdf", b"NOT_A_REAL_PDF_HEADER_BYTES", "application/pdf")}
    res = client.post(
        "/admin/upload-pdf",
        files=files,
        headers={"X-Admin-Key": SUPER_USER_KEY}
    )
    assert res.status_code == 400
    assert "PDF signature" in res.json()["detail"]


def test_upload_valid_pdf_and_deletion(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import io

    # Generate small valid in-memory PDF
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "DocuMind Automated Integration Test Document")
    c.drawString(100, 680, "Verifying upload, indexing, and deletion cycles.")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    filename = "test_upload_doc.pdf"
    files = {"file": (filename, pdf_bytes, "application/pdf")}

    # Test Upload
    res_upload = client.post(
        "/admin/upload-pdf",
        files=files,
        headers={"X-Admin-Key": SUPER_USER_KEY}
    )
    assert res_upload.status_code == 200
    upload_data = res_upload.json()
    assert "uploaded and indexed" in upload_data["message"]
    assert upload_data["pages"] == 1

    # Test Deletion
    res_delete = client.delete(
        f"/admin/delete-pdf?filename={filename}",
        headers={"X-Admin-Key": SUPER_USER_KEY}
    )
    assert res_delete.status_code == 200
    assert "deleted" in res_delete.json()["message"]


def test_delete_nonexistent_pdf():
    res = client.delete(
        "/admin/delete-pdf?filename=non_existent_file_12345.pdf",
        headers={"X-Admin-Key": SUPER_USER_KEY}
    )
    assert res.status_code == 404


def test_ask_with_mocked_llm():
    from main import rag_pipeline
    with patch("main.rag_pipeline") as mock_pipeline:
        mock_pipeline.answer_query.return_value = {
            "answer": "DocuMind AI provides grounded document intelligence.",
            "sources": [
                {"source": "documind-handbook.pdf", "page": 1, "snippet": "Technical overview"}
            ]
        }
        res = client.post("/ask", json={"query": "What is DocuMind AI?"})
        assert res.status_code == 200
        data = res.json()
        assert "grounded document intelligence" in data["answer"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["page"] == 1


def test_ask_when_pipeline_unavailable():
    with patch("main.rag_pipeline", None):
        with patch("os.path.exists", return_value=False):
            res = client.post("/ask", json={"query": "Test query"})
            assert res.status_code == 200
            assert "No documents are currently indexed" in res.json()["answer"]
