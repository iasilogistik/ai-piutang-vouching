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
    assert "Branch bersifat dinamis" in html
    assert "branch baru akan terdaftar otomatis" in html


def test_upload_center_route_is_registered():
    client = TestClient(app)
    response = client.get("/ui/upload")
    assert response.status_code == 200
    assert "Unified Upload Center" in response.text


def test_upload_center_hides_bearer_token_and_uses_login_session_automatically():
    html = upload_center_html()

    assert "Bearer Token" not in html
    assert 'id="token"' not in html
    assert "tokenEl" not in html
    assert "localStorage.getItem('auditToken')" in html
    assert "/auth/me" in html
    assert "Sesi login tidak ditemukan" in html


def test_upload_center_sends_branch_using_endpoint_contract():
    html = upload_center_html()

    assert "function endpointWithQuery" in html
    assert "if(branch)query.branch=branch" in html
    assert "endpoint=endpointWithQuery(endpoint,query)" in html
    assert "endpoint='/sap/import'" in html
    assert "endpoint='/documents/BILLING'" in html
    assert "endpoint='/documents/SPJ'" in html
    assert "endpoint='/documents/combined'" in html
    assert "endpoint='/documents/bulk-zip'" in html
    assert "query.mode=mode" in html
    assert "if(branch)fd.append('branch',branch)" in html


def test_upload_center_shows_friendly_upload_status_instead_of_raw_error_log():
    html = upload_center_html()

    assert "UPLOAD BERHASIL" in html
    assert "UPLOAD GAGAL" in html
    assert "Mengirim data ke server..." in html
    assert "Data berhasil diproses oleh server." in html
