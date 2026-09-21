from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.audit import AuditTrail
from app.auth import CurrentUser, current_user
from app.database import SessionLocal
from app.main import app
from app.models import Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, VouchingResult

client = TestClient(app)


def _user(role: str, branch: str | None):
    return CurrentUser(user_id=f"{role.lower()}-security-test", role=role, branch=branch)


def _make_scope_fixture():
    db = SessionLocal()
    doc = Document(
        file_name="security-sidoarjo.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="security-sidoarjo-hash",
        storage_path="/tmp/security-sidoarjo.pdf",
        uploaded_by="security-test",
        branch="SIDOARJO",
    )
    db.add(doc)
    db.flush()
    billing = PhysicalBilling(
        document_id=doc.id,
        billing_document="SEC-001",
        doc_date=date(2026, 9, 21),
        nominal=Decimal("1000.00"),
    )
    evidence = DocumentControlEvidence(
        document_id=doc.id,
        review_required=True,
        review_status="PENDING",
        review_reasons="security regression",
    )
    db.add_all([billing, evidence])
    db.flush()
    result = VouchingResult(
        billing_id=billing.id,
        spj_id=None,
        no_spj_billing=None,
        no_spj_document=None,
        spj_match=False,
        status="REVIEW",
        rule_code="SECURITY_TEST",
        remarks="branch security fixture",
    )
    batch = ImportBatch(
        file_name="security-sidoarjo.xlsx",
        branch="SIDOARJO",
        uploaded_by="security-test",
        total_records=0,
        status="IMPORTED",
    )
    audit = AuditTrail(
        entity_type="SECURITY_TEST",
        entity_id=doc.id,
        action="CREATE",
        actor="security-test",
        branch="SIDOARJO",
    )
    db.add_all([result, batch, audit])
    db.commit()
    ids = {
        "doc": doc.id,
        "billing": billing.id,
        "evidence": evidence.id,
        "result": result.id,
        "batch": batch.id,
        "audit": audit.id,
    }
    db.close()
    return ids


def _cleanup(ids):
    db = SessionLocal()
    try:
        db.query(AuditTrail).filter(AuditTrail.id == ids["audit"]).delete(synchronize_session=False)
        db.query(VouchingResult).filter(VouchingResult.id == ids["result"]).delete(synchronize_session=False)
        db.query(DocumentControlEvidence).filter(DocumentControlEvidence.id == ids["evidence"]).delete(synchronize_session=False)
        db.query(PhysicalBilling).filter(PhysicalBilling.id == ids["billing"]).delete(synchronize_session=False)
        db.query(ImportBatch).filter(ImportBatch.id == ids["batch"]).delete(synchronize_session=False)
        db.query(Document).filter(Document.id == ids["doc"]).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_pasuruan_user_cannot_enumerate_or_operate_sidoarjo_resources():
    ids = _make_scope_fixture()
    app.dependency_overrides[current_user] = lambda: _user("AUDITOR", "PASURUAN")
    try:
        assert client.get(f"/documents/{ids['doc']}").status_code == 404
        assert client.get(f"/reconciliation/{ids['batch']}").status_code == 404

        report = client.get(f"/reports/{ids['batch']}")
        assert report.status_code in {400, 404}
        assert "SIDOARJO" not in report.text

        control_review = client.post(
            f"/reviews/control-evidence/{ids['evidence']}",
            params={"status": "PASS", "remarks": "cross branch attempt"},
        )
        assert control_review.status_code in {400, 404}
        assert "SIDOARJO" not in control_review.text

        vouch_review = client.post(
            f"/reviews/vouching/{ids['result']}",
            params={"status": "PASS", "remarks": "cross branch attempt"},
        )
        assert vouch_review.status_code == 404

        assert client.get("/audit-trail", params={"branch": "SIDOARJO"}).status_code == 403
        assert client.get("/exceptions", params={"branch": "SIDOARJO"}).status_code == 403
        assert client.get("/dashboard/control-evidence", params={"branch": "SIDOARJO"}).status_code == 403
        assert client.post("/spj/vouch", params={"branch": "SIDOARJO"}).status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)
        _cleanup(ids)


def test_viewer_cannot_mutate_review_resources():
    ids = _make_scope_fixture()
    app.dependency_overrides[current_user] = lambda: _user("VIEWER", "SIDOARJO")
    try:
        response = client.post(
            f"/reviews/control-evidence/{ids['evidence']}",
            params={"status": "PASS", "remarks": "viewer mutation attempt"},
        )
        assert response.status_code == 403

        response = client.post(
            f"/reviews/vouching/{ids['result']}",
            params={"status": "PASS", "remarks": "viewer mutation attempt"},
        )
        assert response.status_code == 403

        response = client.post("/spj/vouch", params={"branch": "SIDOARJO"})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)
        _cleanup(ids)


def test_admin_can_read_cross_branch_resources_and_filter_audit_trail():
    ids = _make_scope_fixture()
    app.dependency_overrides[current_user] = lambda: _user("ADMIN", None)
    try:
        document = client.get(f"/documents/{ids['doc']}")
        assert document.status_code == 200
        assert document.json()["document_id"] == ids["doc"]

        reconciliation = client.get(f"/reconciliation/{ids['batch']}")
        assert reconciliation.status_code == 200
        assert reconciliation.json()["batch_id"] == ids["batch"]

        audit = client.get("/audit-trail", params={"branch": "SIDOARJO", "limit": 100})
        assert audit.status_code == 200
        matching = [row for row in audit.json()["entries"] if row["id"] == ids["audit"]]
        assert matching
        assert matching[0]["branch"] == "SIDOARJO"
    finally:
        app.dependency_overrides.pop(current_user, None)
        _cleanup(ids)
