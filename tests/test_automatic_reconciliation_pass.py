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
)
from app.services.vouching import _control_evidence_complete, reconcile_batch


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_unique_billing_identity_matches_when_optional_scan_fields_are_unreadable(monkeypatch):
    import app.services.vouching as service

    # Keep this test focused on reconciliation semantics rather than OCR runtime.
    monkeypatch.setattr(service, "ocr_document", lambda *args, **kwargs: {"vision": None, "ocr_text": ""})

    with Session(_engine()) as db:
        batch = ImportBatch(
            file_name="sap.xlsx",
            branch="KEDIRI",
            total_records=1,
            status="IMPORTED",
        )
        db.add(batch)
        db.flush()

        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="C-1",
            customer_account_name="WONOKOYO JAYA, TK",
            billing_document="8501681154",
            doc_date=date(2026, 8, 1),
            nominal=Decimal("3000000.00"),
        )
        db.add(sap)
        db.flush()

        billing_doc = Document(
            file_name="WONOKOYO JAYA 8501681154.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="WONOKOYO JAYA 8501681154.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()

        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8501681154",
            doc_date=None,
            nominal=None,
            no_spj=None,
            ocr_confidence=Decimal("0.0000"),
        )
        spj = SPJ(document_id=spj_doc.id, no_spj=None, ocr_confidence=Decimal("0.0000"))
        db.add_all([billing, spj])
        db.commit()

        rows = reconcile_batch(db, batch.id, branch="KEDIRI")
        rec = next(row for row in rows if row.sap_billing_id == sap.id)

        assert rec.status == "MATCH"
        assert rec.billing_match is True
        assert rec.exception_code is None
        assert "MATCH berdasarkan Billing Document unik" in (rec.remarks or "")


def test_readable_conflict_still_becomes_exception():
    with Session(_engine()) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            billing_document="8500000001",
            doc_date=date(2026, 8, 1),
            nominal=Decimal("1000.00"),
        )
        db.add(sap)
        db.flush()
        doc = Document(
            file_name="8500000001.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="conflict-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        db.add(
            PhysicalBilling(
                document_id=doc.id,
                billing_document="8500000001",
                doc_date=date(2026, 8, 2),
                nominal=Decimal("1000.00"),
                ocr_confidence=Decimal("0.9000"),
            )
        )
        db.commit()

        rec = reconcile_batch(db, batch.id, branch="KEDIRI")[0]

        assert rec.status == "EXCEPTION"
        assert rec.billing_match is True
        assert rec.date_match is False
        assert rec.exception_code == "BILLING_FIELD_MISMATCH"


def test_unknown_signatures_do_not_block_pass_when_stamp_is_present_and_matches():
    row = DocumentControlEvidence(
        document_id=1,
        receiver_signature_status="UNKNOWN",
        driver_signature_status="UNKNOWN",
        security_signature_status="UNKNOWN",
        bm_signature_status="UNKNOWN",
        checker_signature_status="UNKNOWN",
        receiver_stamp_status="PRESENT",
        stamp_customer_match_status="MATCH",
        review_required=False,
    )

    assert _control_evidence_complete(row) is True


def test_explicit_missing_signature_or_unclear_stamp_still_blocks_pass():
    missing_signature = DocumentControlEvidence(
        document_id=1,
        receiver_signature_status="PRESENT",
        driver_signature_status="MISSING",
        security_signature_status="UNKNOWN",
        bm_signature_status="UNKNOWN",
        checker_signature_status="UNKNOWN",
        receiver_stamp_status="PRESENT",
        stamp_customer_match_status="MATCH",
        review_required=False,
    )
    unclear_stamp = DocumentControlEvidence(
        document_id=2,
        receiver_signature_status="UNKNOWN",
        driver_signature_status="UNKNOWN",
        security_signature_status="UNKNOWN",
        bm_signature_status="UNKNOWN",
        checker_signature_status="UNKNOWN",
        receiver_stamp_status="UNKNOWN",
        stamp_customer_match_status="REVIEW",
        review_required=True,
    )

    assert _control_evidence_complete(missing_signature) is False
    assert _control_evidence_complete(unclear_stamp) is False



def test_reconciliation_rerun_updates_same_unique_row_in_place(monkeypatch):
    import app.services.vouching as service

    monkeypatch.setattr(service, "ocr_document", lambda *args, **kwargs: {"vision": None, "ocr_text": ""})

    with Session(_engine()) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="C-1",
            customer_account_name="SANTOSO",
            billing_document="8501735930",
            doc_date=date(2026, 8, 1),
            nominal=Decimal("3000000.00"),
        )
        db.add(sap)
        db.flush()

        billing_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8501735930",
            ocr_confidence=Decimal("0.0000"),
        )
        db.add_all([billing, SPJ(document_id=spj_doc.id, ocr_confidence=Decimal("0.0000"))])
        db.commit()

        first = reconcile_batch(db, batch.id, branch="KEDIRI")
        first_row = next(row for row in first if row.sap_billing_id == sap.id)
        first_id = first_row.id

        second = reconcile_batch(db, batch.id, branch="KEDIRI")
        second_row = next(row for row in second if row.sap_billing_id == sap.id)

        assert second_row.id == first_id
        assert second_row.status == "MATCH"
        assert db.query(BillingReconciliation).filter(
            BillingReconciliation.sap_billing_id == sap.id
        ).count() == 1



def test_reconciliation_defers_visual_scan_to_per_document_refresh(monkeypatch):
    import app.services.vouching as service

    def _unexpected_ocr(*args, **kwargs):
        raise AssertionError("batch reconciliation must not execute visual OCR inline")

    monkeypatch.setattr(service, "ocr_document", _unexpected_ocr)

    with Session(_engine()) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer_account_name="SANTOSO",
            billing_document="8501735930",
            doc_date=date(2026, 8, 1),
            nominal=Decimal("3000000.00"),
        )
        db.add(sap)
        db.flush()
        billing_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="visual-refresh",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="visual-refresh",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        db.add_all([
            PhysicalBilling(
                document_id=billing_doc.id,
                billing_document="8501735930",
                ocr_confidence=Decimal("0.0000"),
            ),
            SPJ(document_id=spj_doc.id, ocr_confidence=Decimal("0.0000")),
        ])
        db.commit()

        rows = reconcile_batch(db, batch.id, branch="KEDIRI")

        assert rows[0].status == "MATCH"
        assert db.query(DocumentControlEvidence).filter(
            DocumentControlEvidence.document_id == spj_doc.id
        ).count() == 0

def test_reconciliation_does_not_run_expensive_ocr_inline(monkeypatch):
    import app.services.vouching as service

    def _unexpected_ocr(*args, **kwargs):
        raise AssertionError("reconciliation must not run image OCR inline")

    monkeypatch.setattr(service, "ocr_document", _unexpected_ocr)

    with Session(_engine()) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer_account_name="SANTOSO",
            billing_document="8501735930",
            doc_date=date(2026, 8, 1),
            nominal=Decimal("3000000.00"),
        )
        db.add(sap)
        db.flush()
        billing_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="timeout-safe",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="timeout-safe",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        db.add_all([
            PhysicalBilling(
                document_id=billing_doc.id,
                billing_document="8501735930",
                ocr_confidence=Decimal("0.0000"),
            ),
            SPJ(document_id=spj_doc.id, ocr_confidence=Decimal("0.0000")),
        ])
        db.commit()

        rows = reconcile_batch(db, batch.id, branch="KEDIRI")
        rec = next(row for row in rows if row.sap_billing_id == sap.id)

        assert rec.status == "MATCH"
