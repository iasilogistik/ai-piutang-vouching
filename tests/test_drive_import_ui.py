from fastapi.testclient import TestClient

from app.main import app
from app.services.drive_link import extract_google_drive_file_id, is_google_drive_folder_link


client = TestClient(app)


def test_drive_import_ui_shell_loads():
    response = client.get("/ui/drive-import")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Google Drive / Share Link Import" in response.text
    assert "/documents/drive-import" in response.text
    assert 'id="branch"' in response.text
    assert "branch baru boleh langsung diketik" in response.text
    assert "form.append('branch', branch)" in response.text
    assert "Bulk ZIP Upload" in response.text


def test_google_drive_file_id_parsing():
    assert extract_google_drive_file_id("https://drive.google.com/file/d/abc123/view?usp=sharing") == "abc123"
    assert extract_google_drive_file_id("https://drive.google.com/open?id=xyz789") == "xyz789"


def test_google_drive_folder_link_detected():
    assert is_google_drive_folder_link("https://drive.google.com/drive/folders/folder123?usp=sharing")


def test_drive_import_endpoint_order_not_caught_by_document_type_route():
    response = client.post("/documents/drive-import")

    assert response.status_code == 422
    assert "document_type must be BILLING or SPJ" not in response.text
