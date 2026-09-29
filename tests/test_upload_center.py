from fastapi.testclient import TestClient

from app.main import app
from app.services.upload_center import upload_center_html
from app.services.upload_management import router as upload_management_router


def test_upload_center_has_two_separate_upload_flows():
    html = upload_center_html()
    assert "1. Upload Data SAP" in html
    assert "2. Upload Evidence Billing &amp; SPJ" in html
    assert 'id="sapFile"' in html
    assert 'id="billingFiles"' in html
    assert 'id="spjFiles"' in html
    assert "multiple" in html
    assert "Bulk ZIP" not in html


def test_upload_center_uses_login_session_and_branch_scope():
    html = upload_center_html()
    assert "Bearer Token" not in html
    assert 'id="token"' not in html
    assert "localStorage.getItem('auditToken')" in html
    assert "/auth/me" in html
    assert "branchEl.disabled=true" in html


def test_upload_center_handles_413_and_uploads_evidence_individually():
    html = upload_center_html()
    assert "response.status===413" in html
    assert "HTTP 413" in html
    assert "MAX_DIRECT_FILE_BYTES=4*1024*1024" in html
    assert "uploadEvidenceFile" in html
    assert "for(let index=0;index<jobs.length;index++)" in html
    assert "ZIP besar tidak dipakai pada form utama" in html


def test_upload_center_has_edit_delete_history_management():
    html = upload_center_html()
    assert "/uploads/recent?limit=60" in html
    assert "data-edit" in html
    assert "data-delete" in html
    assert "EDIT BERHASIL" in html
    assert "DELETE BERHASIL" in html


def test_upload_center_rendered_javascript_keeps_escaped_newlines():
    html = upload_center_html()
    assert r"title+(payload?'\n\n'+JSON.stringify" in html
    assert "title+(payload?'\n\n'+JSON.stringify" not in html


def test_upload_center_route_is_registered():
    client = TestClient(app)
    response = client.get("/ui/upload")
    assert response.status_code == 200
    assert "Upload Center" in response.text


def test_upload_management_router_defines_correction_endpoints():
    paths = {getattr(route, "path", "") for route in upload_management_router.routes}
    assert "/uploads/recent" in paths
    assert "/uploads/sap/{batch_id}" in paths
    assert "/uploads/evidence/{document_id}" in paths
