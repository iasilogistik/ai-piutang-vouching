from fastapi.testclient import TestClient

from app.main import app
from app.services.reconciliation_vouching_ui import reconciliation_vouching_html


client = TestClient(app)


def test_reconciliation_vouching_page_exposes_operational_flow():
    html = reconciliation_vouching_html()

    assert "Reconciliation &amp; Vouching" in html
    assert "/uploads/recent?limit=80" in html
    assert "/sap/validate/" in html
    assert "/reconciliation/" in html
    assert "/spj/vouch?branch=" in html
    assert "Run Reconciliation" in html
    assert "Run SPJ Vouching" in html
    assert "/ui/control-evidence" in html
    assert "/ui/review-queue" in html
    assert "/ui/exceptions" in html


def test_reconciliation_vouching_page_requires_branch_for_spj_action_in_ui():
    html = reconciliation_vouching_html()

    assert "if(!branch)" in html
    assert "pilih cabang terlebih dahulu" in html


def test_reconciliation_vouching_route_is_registered():
    response = client.get("/ui/reconciliation-vouching")

    assert response.status_code == 200
    assert "Batch SAP &amp; Hasil Reconciliation" in response.text



def test_reconciliation_vouching_page_highlights_incomplete_evidence_readably():
    html = reconciliation_vouching_html()

    assert "Keterangan Evidence" in html
    assert "Billing belum lengkap" in html
    assert "SPJ belum lengkap" in html
    assert "Proses tetap dilanjutkan" in html
    assert "detail-panel" in html
    assert "renderReconciliationDetail" in html



def test_reconciliation_detail_supports_manual_confirmation_after_visual_check():
    html = reconciliation_vouching_html()

    assert "Konfirmasi Sesuai" in html
    assert "Konfirmasi Semua REVIEW yang Sudah Dicek" in html
    assert "/confirm-manual?" in html
    assert "/confirm-manual-review?" in html
    assert "Billing, tanggal/nominal, SPJ, tanda tangan, dan stempel" in html
