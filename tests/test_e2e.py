from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.audit_service import list_audit_trail
from app.database import Base
from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
from app.services.vouching import overall_result, reconcile_batch, vouch_spj


def test_end_to_end_pass_flow():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        batch = ImportBatch(file_name="e2e.xlsx", period=date(2026, 9, 1), total_records=1, status="IMPORTED")
        db.add(batch); db.flush()
        sap = SAPBilling(import_batch_id=batch.id, customer="C1", customer_account_name="Customer 1",
                         billing_document="B-100", doc_date=date(2026, 9, 1), nominal=Decimal("1500000.00"))
        db.add(sap); db.flush()
        billing_doc = Document(file_name="billing.pdf", file_type="PDF", document_type="BILLING", file_hash="e2e-billing", storage_path="storage/e2e-billing")
        spj_doc = Document(file_name="spj.pdf", file_type="PDF", document_type="SPJ", file_hash="e2e-spj", storage_path="storage/e2e-spj")
        db.add_all([billing_doc, spj_doc]); db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id, billing_document_raw="B-100", billing_document="B100",
                                  no_spj_raw="SPJ-100", no_spj="SPJ100", doc_date=date(2026, 9, 1), nominal=Decimal("1500000.00"))
        spj = SPJ(document_id=spj_doc.id, no_spj_raw="SPJ-100", no_spj="SPJ100", ocr_confidence=Decimal("0.9000"))
        db.add_all([billing, spj]); db.commit()

        rec = reconcile_batch(db, batch.id)
        assert len(rec) == 1
        assert rec[0].status == "MATCH"
        vouch = vouch_spj(db)
        assert len(vouch) == 1
        assert vouch[0].status == "PASS"
        result = overall_result(db, billing.id)
        assert result["sap_reconciliation_result"] == "MATCH"
        assert result["spj_vouching_result"] == "PASS"
        assert result["overall_result"] == "PASS"
