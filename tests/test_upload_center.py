from fastapi.testclient import TestClient

from app.main import app
from app.services.upload_center import upload_center_html
from app.services.upload_management import router as upload_management_router


def test_upload_center_has_flexible_evidence_upload_modes():
    html = upload_center_html()
    assert "1. Upload Data SAP" in html
    assert "2. Upload Evidence Billing &amp; SPJ" in html
    assert 'id="evidenceMode"' in html
    assert "Billing saja" in html
    assert "SPJ saja" in html
    assert "Billing + SPJ terpisah" in html
    assert "Billing + SPJ dalam 1 file" in html
    assert "Arsip ZIP / RAR" in html
    assert "Google Drive / Share Link" in html
    assert 'id="billingFiles"' in html
    assert 'id="spjFiles"' in html
    assert 'id="combinedFiles"' in html
    assert 'id="archiveFile"' in html
    assert 'accept=".zip,.rar"' in html
    assert 'id="driveUrl"' in html


def test_upload_center_uses_login_session_and_branch_scope():
    html = upload_center_html()
    assert "Bearer Token" not in html
    assert 'id="token"' not in html
    assert "localStorage.getItem('auditToken')" in html
    assert "/auth/me" in html
    assert "branchEl.disabled=true" in html


def test_upload_center_handles_individual_combined_archive_and_drive_evidence():
    html = upload_center_html()
    assert "response.status===413" in html
    assert "MAX_DIRECT_FILE_BYTES=4*1024*1024" in html
    assert "uploadEvidenceFile" in html
    assert "uploadCombinedFile" in html
    assert "uploadArchive" in html
    assert "importDrive" in html
    assert "/documents/combined" in html
    assert "/documents/bulk-archive" in html
    assert "/documents/drive-import" in html
    assert "/documents/drive-folder-import" in html
    assert "archiveMode" in html
    assert "driveMode" in html


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


def test_upload_center_points_to_reconciliation_vouching_as_next_process():
    html = upload_center_html()

    assert "Proses Berikutnya" in html
    assert "/ui/reconciliation-vouching" in html
    assert "Lanjut ke Reconciliation &amp; Vouching" in html


def test_upload_center_next_step_card_is_compact_and_eye_friendly():
    html = upload_center_html()

    assert 'class="next-step-card"' in html
    assert 'class="next-step-badge">Tahap 3<' in html
    assert 'class="next-step-icon">03<' in html
    assert "Validasi SAP" in html
    assert "SAP ↔ Billing" in html
    assert "Billing ↔ SPJ" in html
    assert "Review Exception" in html
    assert 'class="next-step-action"' in html
    assert "background:linear-gradient(135deg,#f8fbff 0%,#f1f5f9 100%)!important" in html
    assert "color:#fff!important" in html
    assert "background:linear-gradient(135deg,#2563eb,#1d4ed8)!important" in html


def test_upload_center_keeps_bearer_token_hidden_for_all_new_modes():
    html = upload_center_html()
    assert "Bearer Token" not in html
    assert 'id="token"' not in html
    assert "authHeaders()" in html
    assert "localStorage.getItem('auditToken')" in html


def test_upload_center_explains_public_drive_folder_without_api_key():
    html = upload_center_html()
    assert "Anyone with the link" in html
    assert "tanpa API key" in html


def test_upload_center_explains_multi_fallback_drive_folder_import():
    html = upload_center_html()
    assert "public folder view" in html
    assert "fallback downloader" in html
    assert "API key tidak wajib" in html


def test_upload_center_shows_locked_state_only_for_final_manual_evidence():
    html = upload_center_html()
    assert "item.delete_allowed===false" in html
    assert ">Locked</button>" in html
    assert "item.delete_reason" in html
    assert "hasil reconciliation/vouching akan di-reset" in html
