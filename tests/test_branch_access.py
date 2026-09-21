from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user
from app.database import SessionLocal
from app.main import app
from app.models import (
    BillingReconciliation,
    Document,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
    SPJ,
    VouchingResult,
)
from app.services.vouching import reconcile_batch, vouch_spj


client = TestClient(app)


def _document(*, name: str, document_type: str, branch: str) -> Document:
    return Document(
        file_name=name,
        file_type="PDF",
        document_type=document_type,
        file_hash=f"hash-{name}",
        storage_path=f"/tmp/{name}",
        uploaded_by="branch-test",
        branch=branch,
    )


def test_reconciliation_never_matches_physical_billing_from_other_branch():
    db = SessionLocal()
    batch = None
    docs = []
    try:
        batch = ImportBatch(
            file_name="sap_pasuruan.xlsx",
            branch="PASURUAN",
            total_records=1,
            status="IMPORTED",
        )
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="C001",
            customer_account_name="PT PASURUAN",
            billing_document="8500001001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("1000000.00"),
        )
        pasuruan_doc = _document(name="billing-pasuruan.pdf", document_type="BILLING", branch="PASURUAN")
        gresik_doc = _document(name="billing-gresik.pdf", document_type="BILLING", branch="GRESIK")
        docs = [pasuruan_doc, gresik_doc]
        db.add_all([sap, *docs])
        db.flush()
        pasuruan_billing = PhysicalBilling(
            document_id=pasuruan_doc.id,
            billing_document="8500001001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("1000000.00"),
        )
        gresik_billing = PhysicalBilling(
            document_id=gresik_doc.id,
            billing_document="8500001001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("999999.00"),
        )
        db.add_all([pasuruan_billing, gresik_billing])
        db.commit()

        rows = reconcile_batch(db, batch.id, branch="PASURUAN")

        assert len(rows) == 1
        assert rows[0].status == "MATCH"
        assert rows[0].physical_billing_id == pasuruan_billing.id
    finally:
        if batch is not None:
            sap_ids = [
                row.id
                for row in db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch.id).all()
            ]
            if sap_ids:
                db.query(BillingReconciliation).filter(
                    BillingReconciliation.sap_billing_id.in_(sap_ids)
                ).delete(synchronize_session=False)
                db.query(SAPBilling).filter(SAPBilling.id.in_(sap_ids)).delete(synchronize_session=False)
            db.query(ImportBatch).filter(ImportBatch.id == batch.id).delete(synchronize_session=False)
        for doc in docs:
            if doc.id is not None:
                db.query(PhysicalBilling).filter(PhysicalBilling.document_id == doc.id).delete(synchronize_session=False)
                db.query(Document).filter(Document.id == doc.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_spj_vouching_never_matches_spj_from_other_branch():
    db = SessionLocal()
    docs = []
    billing = None
    try:
        billing_doc = _document(name="vouch-billing-pasuruan.pdf", document_type="BILLING", branch="PASURUAN")
        pasuruan_spj_doc = _document(name="spj-pasuruan.pdf", document_type="SPJ", branch="PASURUAN")
        gresik_spj_doc = _document(name="spj-gresik.pdf", document_type="SPJ", branch="GRESIK")
        docs = [billing_doc, pasuruan_spj_doc, gresik_spj_doc]
        db.add_all(docs)
        db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id, no_spj="25010001")
        pasuruan_spj = SPJ(document_id=pasuruan_spj_doc.id, no_spj="25010001")
        gresik_spj = SPJ(document_id=gresik_spj_doc.id, no_spj="25010001")
        db.add_all([billing, pasuruan_spj, gresik_spj])
        db.commit()

        rows = vouch_spj(db, branch="PASURUAN")

        branch_rows = [row for row in rows if row.billing_id == billing.id]
        assert len(branch_rows) == 1
        assert branch_rows[0].status == "PASS"
        assert branch_rows[0].spj_id == pasuruan_spj.id
    finally:
        if billing is not None and billing.id is not None:
            db.query(VouchingResult).filter(VouchingResult.billing_id == billing.id).delete(synchronize_session=False)
        for doc in docs:
            if doc.id is not None:
                db.query(PhysicalBilling).filter(PhysicalBilling.document_id == doc.id).delete(synchronize_session=False)
                db.query(SPJ).filter(SPJ.document_id == doc.id).delete(synchronize_session=False)
                db.query(Document).filter(Document.id == doc.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_branch_user_cannot_open_other_branch_document_but_admin_can():
    db = SessionLocal()
    doc = _document(name="branch-access-gresik.pdf", document_type="BILLING", branch="GRESIK")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    document_id = doc.id
    db.close()

    try:
        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id="pasuruan-user", role="VIEWER", branch="Pasuruan"
        )
        response = client.get(f"/documents/{document_id}")
        assert response.status_code == 404

        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id="admin-user", role="ADMIN", branch=None
        )
        response = client.get(f"/documents/{document_id}")
        assert response.status_code == 200
        assert response.json()["document_id"] == document_id
    finally:
        app.dependency_overrides.pop(current_user, None)
        db = SessionLocal()
        db.query(Document).filter(Document.id == document_id).delete(synchronize_session=False)
        db.commit()
        db.close()
