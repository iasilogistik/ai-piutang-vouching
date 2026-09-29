from fastapi.testclient import TestClient

from app.main import app
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services.bulk_zip import ALLOWED_ARCHIVE_EXTENSIONS, classify_entry, iter_bulk_zip_entries


client = TestClient(app)


def test_bulk_upload_ui_shell_loads():
    response = client.get("/ui/bulk-upload")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Bulk ZIP Upload" in response.text
    assert "/documents/bulk-zip" in response.text
    assert 'id="branch"' in response.text
    assert "branch baru boleh langsung diketik" in response.text
    assert "form.append('branch', branch)" in response.text
    assert "Buka Control Evidence" in response.text


def test_bulk_zip_endpoint_route_is_registered_before_document_type_route():
    response = client.post("/documents/bulk-zip")

    assert response.status_code == 422
    assert "document_type must be BILLING or SPJ" not in response.text


def test_bulk_zip_auto_classification():
    assert classify_entry("BILLING/SANTOSO 8501735930.pdf", "AUTO") == ["BILLING"]
    assert classify_entry("SPJ/SANTOSO SPJ.pdf", "AUTO") == ["SPJ"]
    assert classify_entry("GABUNGAN/SANTOSO 8501735930.pdf", "AUTO") == ["BILLING", "SPJ"]
    assert classify_entry("LAINNYA/unknown.pdf", "AUTO") is None


def test_bulk_archive_endpoint_is_registered():
    response = client.post("/documents/bulk-archive")
    assert response.status_code == 422
    assert "document_type must be BILLING or SPJ" not in response.text


def test_archive_engine_accepts_rar_extension_and_reports_invalid_rar_cleanly():
    assert ".zip" in ALLOWED_ARCHIVE_EXTENSIONS
    assert ".rar" in ALLOWED_ARCHIVE_EXTENSIONS
    upload = UploadFile(filename="evidence.rar", file=BytesIO(b"not-a-real-rar"))
    with pytest.raises(ValueError, match="RAR"):
        iter_bulk_zip_entries(upload)
