from fastapi.testclient import TestClient

from app.main import app
from app.services.reconciliation_vouching_ui import reconciliation_vouching_html


client = TestClient(app)


def test_reconciliation_vouching_page_exposes_operational_flow():
    html = reconciliation_vouching_html()

    assert "Reconciliation &amp; Vouching" in html
    assert "/reconciliation/workspace?" in html
    assert "/uploads/recent?limit=80" not in html
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
    assert "Billing Document unik sebagai identitas utama" in html



def test_reconciliation_ui_distinguishes_ocr_info_from_actual_review():
    html = reconciliation_vouching_html()

    assert "SPJ tersedia · OCR info" in html
    assert "bukan REVIEW" in html



def test_reconciliation_ui_offers_separate_working_paper_download():
    html = reconciliation_vouching_html()

    assert "Download Kertas Kerja" in html
    assert "/working-paper" in html
    assert "downloadWorkingPaper" in html



def test_reconciliation_ui_formats_money_in_indonesian_notation():
    html = reconciliation_vouching_html()

    assert "function formatMoneyId(value)" in html
    assert "new Intl.NumberFormat('id-ID'" in html
    assert "formatMoneyId(r.billing_partial_payment)" in html
    assert "formatMoneyId(r.nominal_difference)" in html





def test_reconciliation_ui_does_not_show_separate_customer_backfill_action():
    html = reconciliation_vouching_html()

    assert "Isi Kode Customer" not in html
    assert "/sap/backfill-customer/" not in html



def test_working_paper_download_is_lightweight_and_does_not_run_ocr():
    html = reconciliation_vouching_html()

    start = html.index("async function downloadWorkingPaper")
    end = html.index("async function validateSap", start)
    block = html[start:end]

    assert "Baca tanggal fisik..." not in block
    assert "refreshVisualEvidenceForBatch(id)" not in block
    assert "hasil reconciliation terakhir" in block



def test_reconciliation_workspace_avoids_n_plus_one_initial_load():
    html = reconciliation_vouching_html()

    load_start = html.index("async function loadBatches")
    load_end = html.index("function renderMetrics", load_start)
    block = html[load_start:load_end]

    assert "/reconciliation/workspace?" in block
    assert "Promise.all(batches.map" not in block
    assert "prepareWorkingPaper" not in block
