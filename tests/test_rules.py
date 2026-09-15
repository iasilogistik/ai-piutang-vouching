from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
from app.services.vouching import reconcile_batch, vouch_spj


def test_reconciliation_not_found():
    db = SessionLocal()
    batch = ImportBatch(file_name="rules.xlsx", total_records=1, status="IMPORTED")
    db.add(batch); db.flush()
    sap = SAPBilling(import_batch_id=batch.id, billing_document="R-001", doc_date=date(2026, 9, 1), nominal=Decimal("100.00"))
    db.add(sap); db.commit()
    rows = reconcile_batch(db, batch.id)
    assert rows[0].status == "EXCEPTION"
    assert rows[0].exception_code == "BILLING_DOCUMENT_NOT_FOUND"
    db.query(BillingReconciliation).filter(BillingReconciliation.sap_billing_id == sap.id).delete()
    db.delete(sap); db.delete(batch); db.commit(); db.close()


def test_billing_without_spj_is_exception():
    db = SessionLocal()
    doc = Document(file_name="b.pdf", file_type="PDF", document_type="BILLING", file_hash="test-billing-rule", storage_path="storage/test")
    db.add(doc); db.flush()
    billing = PhysicalBilling(document_id=doc.id, billing_document="B-1", billing_document_raw="B-1")
    db.add(billing); db.commit(); db.refresh(billing)
    rows = vouch_spj(db)
    assert rows[-1].status == "EXCEPTION"
    assert rows[-1].rule_code == "BILLING_WITHOUT_SPJ"
    db.query(VouchingResult).filter(VouchingResult.billing_id == billing.id).delete()
    db.delete(billing); db.delete(doc); db.commit(); db.close()
