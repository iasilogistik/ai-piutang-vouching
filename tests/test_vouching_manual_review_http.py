from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.audit import AuditTrail
from app.auth import CurrentUser, current_user
from app.database import SessionLocal
from app.main import app
from app.models import Document, PhysicalBilling, VouchingResult


client = TestClient(app)


def _reviewer():
    return CurrentUser(user_id="reviewer-dev15", role="REVIEWER", branch="PASURUAN")


def test_vouching_manual_review_writes_structured_audit_trail():
    db = SessionLocal()
    doc = Document(
        file_name="dev15-billing.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="dev15-route-hash",
        storage_path="/tmp/dev15-billing.pdf",
        branch="PASURUAN",
    )
    db.add(doc)
    db.flush()
    billing = PhysicalBilling(
        document_id=doc.id,
        billing_document="DEV15001",
        no_spj="DEV15SPJ",
        doc_date=date(2026, 9, 22),
        nominal=Decimal("1000.00"),
    )
    db.add(billing)
    db.flush()
    result = VouchingResult(
        billing_id=billing.id,
        spj_id=None,
        no_spj_billing="DEV15SPJ",
        no_spj_document="DEV15SPJ",
        spj_match=True,
        status="PASS",
        automated_status="PASS",
    )
    db.add(result)
    db.commit()
    ids = {"doc": doc.id, "billing": billing.id, "result": result.id}
    db.close()

    app.dependency_overrides[current_user] = _reviewer
    try:
        response = client.post(
            f"/reviews/vouching/{ids['result']}",
            params={
                "status": "EXCEPTION",
                "reason_code": "EVIDENCE_MISSING",
                "remarks": "Dokumen pendukung belum lengkap.",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["automated_result"]["status"] == "PASS"
        assert body["reviewer_decision"]["status"] == "EXCEPTION"
        assert body["reviewer_decision"]["reason_code"] == "EVIDENCE_MISSING"

        check = SessionLocal()
        try:
            stored = check.get(VouchingResult, ids["result"])
            assert stored.automated_status == "PASS"
            assert stored.manual_review_status == "EXCEPTION"
            assert stored.review_reason_code == "EVIDENCE_MISSING"

            audit = (
                check.query(AuditTrail)
                .filter(
                    AuditTrail.entity_type == "VOUCHING_RESULT",
                    AuditTrail.entity_id == ids["result"],
                    AuditTrail.action == "MANUAL_REVIEW",
                )
                .order_by(AuditTrail.id.desc())
                .first()
            )
            assert audit is not None
            assert audit.status_from == "PASS"
            assert audit.status_to == "EXCEPTION"
            assert audit.branch == "PASURUAN"
            assert audit.metadata_json["reason_code"] == "EVIDENCE_MISSING"
            assert audit.metadata_json["automated_status"] == "PASS"
        finally:
            check.close()
    finally:
        app.dependency_overrides.clear()
        cleanup = SessionLocal()
        try:
            cleanup.query(AuditTrail).filter(
                AuditTrail.entity_type == "VOUCHING_RESULT",
                AuditTrail.entity_id == ids["result"],
            ).delete(synchronize_session=False)
            cleanup.query(VouchingResult).filter(VouchingResult.id == ids["result"]).delete(synchronize_session=False)
            cleanup.query(PhysicalBilling).filter(PhysicalBilling.id == ids["billing"]).delete(synchronize_session=False)
            cleanup.query(Document).filter(Document.id == ids["doc"]).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()
