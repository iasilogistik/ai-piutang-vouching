from fastapi.testclient import TestClient

from app.main import app
from app.services.document_viewer import document_viewer_html


client = TestClient(app)


def test_document_viewer_shell_uses_browser_session_for_protected_content():
    html = document_viewer_html(123)

    assert "Document Viewer - AI Piutang Vouching" in html
    assert "localStorage.getItem('auditToken')" in html
    assert "Authorization:'Bearer '+value" in html
    assert "/documents/'+DOCUMENT_ID+'/content" in html
    assert "Bearer access token required" not in html
    assert "Download" in html


def test_document_viewer_route_is_public_shell_but_document_bytes_remain_protected():
    shell = client.get("/documents/123/view")
    content = client.get("/documents/123/content")

    assert shell.status_code == 200
    assert "Membuka dokumen #123" in shell.text
    assert content.status_code == 401
