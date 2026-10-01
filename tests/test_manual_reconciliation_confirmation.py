from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    BillingReconciliation,
    Document,
    DocumentControlEvidence,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
    SPJ,
    VouchingResult,
)
from app.services.vouching import confirm_reconciliation_manual, reconcile_batch


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_manual_confirmation_promotes_review_to_match_and_pass_and_survives_rerun():
    with Session(_engine()) as db:
        batch = ImportBatch(
            file_name="sample.xlsx",
            branch="KEDIRI",
            total_records=1,
            status="IMPORTED",
        )
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="C-1",
            customer_account_name="TB JOYO ARJUNO PRIGEN",
            billing_document="8540088421",
            doc_date=date(2026, 8, 3),
            nominal=Decimal("1144600.00"),
        )
        db.add(sap)
        db.flush()

        billing_doc = Document(
            file_name="TB JOYO ARJUNO PRIGEN 8540088421.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-hash",
            storage_path="BILLING/same.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="TB JOYO ARJUNO PRIGEN 8540088421.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-hash",
            storage_path="SPJ/same.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()

        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8540088421",
            billing_document_raw="8540088421",
            doc_date=None,
            nominal=None,
            no_spj=None,
            ocr_confidence=Decimal("0.0000"),
        )
        spj = SPJ(
            document_id=spj_doc.id,
            no_spj=None,
            ocr_confidence=Decimal("0.0000"),
        )
        db.add_all([billing, spj])
        db.flush()

        evidence = DocumentControlEvidence(
            document_id=spj_doc.id,
            receiver_signature_status="UNKNOWN",
            driver_signature_status="UNKNOWN",
            security_signature_status="UNKNOWN",
            bm_signature_status="UNKNOWN",
            checker_signature_status="UNKNOWN",
            receiver_stamp_status="UNKNOWN",
            stamp_customer_match_status="NOT_EVALUATED",
            review_required=True,
        )
        db.add(evidence)
        db.flush()

        rec = BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=billing.id,
            billing_match=True,
            date_match=False,
            nominal_match=False,
            nominal_difference=sap.nominal,
            status="REVIEW",
            remarks="OCR belum lengkap; manual review required.",
        )
        db.add(rec)
        db.commit()

        payload = confirm_reconciliation_manual(
            db,
            rec.id,
            reviewer_id="auditor-1",
            remarks="Cek visual selesai: Billing, SPJ, TTD dan stempel sesuai.",
            branch="KEDIRI",
        )
        db.commit()
        db.refresh(rec)
        db.refresh(evidence)

        vouch = db.scalar(
            __import__("sqlalchemy").select(VouchingResult).where(VouchingResult.billing_id == billing.id)
        )

        assert payload["manual_confirmed"] is True
        assert rec.status == "MATCH"
        assert rec.billing_match is True
        assert rec.date_match is True
        assert rec.nominal_match is True
        assert rec.nominal_difference == Decimal("0.00")
        assert "[MANUAL_CONFIRMED]" in (rec.remarks or "")
        assert evidence.review_status == "PASS"
        assert evidence.review_required is False
        assert vouch is not None
        assert vouch.status == "PASS"
        assert vouch.manual_review_status == "PASS"
        assert vouch.review_reason_code == "EVIDENCE_CONFIRMED"
        assert vouch.spj_id == spj.id
        assert vouch.spj_match is True

        rerun = reconcile_batch(db, batch.id, branch="KEDIRI")
        rerun_row = next(row for row in rerun if row.sap_billing_id == sap.id)
        assert rerun_row.id == rec.id
        assert rerun_row.status == "MATCH"
        assert "[MANUAL_CONFIRMED]" in (rerun_row.remarks or "")


def test_manual_confirmation_requires_linked_spj_evidence():
    with Session(_engine()) as db:
        batch = ImportBatch(file_name="sample.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            billing_document="8500000001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("100.00"),
        )
        db.add(sap)
        db.flush()
        billing_doc = Document(
            file_name="8500000001.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="billing-only",
            storage_path="BILLING/only.pdf",
            branch="KEDIRI",
        )
        db.add(billing_doc)
        db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id, billing_document="8500000001")
        db.add(billing)
        db.flush()
        rec = BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=billing.id,
            billing_match=True,
            date_match=False,
            nominal_match=False,
            nominal_difference=Decimal("100.00"),
            status="REVIEW",
        )
        db.add(rec)
        db.commit()

        try:
            confirm_reconciliation_manual(
                db,
                rec.id,
                reviewer_id="auditor-1",
                branch="KEDIRI",
            )
        except ValueError as exc:
            assert "linked SPJ evidence" in str(exc)
        else:
            raise AssertionError("Expected missing SPJ evidence to block manual confirmation")
