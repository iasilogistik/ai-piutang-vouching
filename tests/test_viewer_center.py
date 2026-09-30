from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser, current_user
from app.database import Base
from app.main import app
from app.models import (
    BillingReconciliation,
    Document,
    DocumentControlEvidence,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
    VouchingResult,
)
from app.services.viewer_center import build_viewer_dashboard, viewer_center_html


client = TestClient(app)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed(db: Session):
    batch = ImportBatch(
        file_name="viewer.xlsx",
        branch="PASURUAN",
        total_records=2,
        status="IMPORTED",
    )
    db.add(batch)
    db.flush()

    sap_match = SAPBilling(
        import_batch_id=batch.id,
        customer="C-1",
        customer_account_name="TOKO MATCH",
        billing_document="B-100",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("1000.00"),
    )
    sap_missing = SAPBilling(
        import_batch_id=batch.id,
        customer="C-2",
        customer_account_name="TOKO MISSING",
        billing_document="B-404",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("2000.00"),
    )
    db.add_all([sap_match, sap_missing])
    db.flush()

    billing_doc = Document(
        file_name="billing.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="viewer-billing",
        storage_path="billing.pdf",
        branch="PASURUAN",
    )
    spj_doc = Document(
        file_name="spj.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash="viewer-spj",
        storage_path="spj.pdf",
        branch="PASURUAN",
    )
    db.add_all([billing_doc, spj_doc])
    db.flush()

    billing = PhysicalBilling(
        document_id=billing_doc.id,
        billing_document="B100",
        no_spj="SPJ404",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("1000.00"),
    )
    db.add(billing)
    db.flush()

    db.add_all(
        [
            BillingReconciliation(
                sap_billing_id=sap_match.id,
                physical_billing_id=billing.id,
                billing_match=True,
                date_match=True,
                nominal_match=True,
                nominal_difference=Decimal("0.00"),
                status="MATCH",
            ),
            BillingReconciliation(
                sap_billing_id=sap_missing.id,
                physical_billing_id=None,
                billing_match=False,
                date_match=False,
                nominal_match=False,
                nominal_difference=Decimal("2000.00"),
                status="NOT_FOUND",
                exception_code="BILLING_DOCUMENT_NOT_FOUND",
                remarks="Billing belum lengkap: evidence Billing belum ditemukan.",
            ),
            VouchingResult(
                billing_id=billing.id,
                spj_id=None,
                no_spj_billing="SPJ404",
                spj_match=False,
                status="REVIEW",
                rule_code="SPJ_NOT_FOUND",
                remarks="SPJ belum lengkap: evidence belum ditemukan.",
            ),
            DocumentControlEvidence(
                document_id=spj_doc.id,
                review_required=True,
            ),
        ]
    )
    db.commit()


def test_viewer_dashboard_shows_results_and_missing_evidence():
    with Session(_engine()) as db:
        _seed(db)

        payload = build_viewer_dashboard(db, branch="PASURUAN")

        assert payload["metrics"]["sap_population"] == 2
        assert payload["metrics"]["matched"] == 1
        assert payload["metrics"]["billing_missing"] == 1
        assert payload["metrics"]["spj_missing"] == 1
        assert payload["metrics"]["control_evidence_review"] == 1
        assert any(x["issue"] == "Billing belum lengkap" for x in payload["attention_items"])
        assert any(x["issue"] == "SPJ belum lengkap" for x in payload["attention_items"])
        assert any(x["status"] == "MATCH" for x in payload["recent_results"])


def test_viewer_center_is_read_only_and_has_dashboard_links():
    html = viewer_center_html()

    assert "Viewer Center" in html
    assert "Yang Kurang / Perlu Perhatian" in html
    assert "/viewer/dashboard" in html
    assert "/ui/dashboard" in html
    assert "/ui/control-evidence" in html
    assert "Tidak ada tombol upload, run reconciliation, approve, reject, edit, atau delete" in html
    assert "Bearer Token" not in html
    assert 'id="token"' not in html


def test_viewer_dashboard_api_accepts_viewer_and_rejects_auditor():
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id="viewer-1",
        role="VIEWER",
        branch="PASURUAN",
    )
    try:
        response = client.get("/viewer/dashboard")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(current_user, None)

    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id="auditor-1",
        role="AUDITOR",
        branch="PASURUAN",
    )
    try:
        response = client.get("/viewer/dashboard")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_viewer_center_route_is_registered():
    response = client.get("/ui/viewer-center")

    assert response.status_code == 200
    assert "Hasil &amp; Kelengkapan Evidence" in response.text



def test_viewer_center_lazy_loads_recent_results_and_uses_cached_session():
    html = viewer_center_html()

    assert "cachedSession()" in html
    assert "localStorage.getItem('auditUser')" in html
    assert "loadRecentResults" in html
    assert "/viewer/results?" in html
    assert "const dashboardPromise=loadDashboard()" in html
