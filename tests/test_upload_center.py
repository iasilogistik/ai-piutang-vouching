from fastapi.testclient import TestClient

from app.main import app
from app.services.upload_center import upload_center_html


def test_upload_center_html_contains_supported_modes():
    html = upload_center_html()
    assert "Unified Upload Center" in html
    assert "SAP" in html
    assert "Billing" in html
    assert "SPJ" in html
    assert "Combined Billing + SPJ" in html
    assert "Bulk ZIP" in html
    assert "Google Drive Share Link" in html
    assert "Google Drive Folder" in html
    assert "/documents/bulk-zip" in html
    assert "/documents/drive-import" in html
    assert "/documents/drive-folder-import" in html


def test_upload_center_route_is_registered():
    client = TestClient(app)
    response = client.get("/ui/upload")
    assert response.status_code == 200
    assert "Unified Upload Center" in response.text
