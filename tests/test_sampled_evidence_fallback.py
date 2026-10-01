from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ
from app.services.vouching import (
    _customer_match_key,
    _filename_customer_key,
    reconcile_batch,
    vouch_spj,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_customer_filename_fallback_is_conservative_for_gemilang_sample():
    assert _filename_customer_key("gemilang 86.pdf") == "GEMILANG86"
    assert _customer_match_key("GEMILANG 86, TB") == "GEMILANG86"
    assert _customer_match_key("TB JOYO ARJUNO PRIGEN") == "TBJOYOARJUNOPRIGEN"


def test_reconciliation_and_vouching_keep_combined_scanned_evidence_linked():
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
            customer_account_name="GEMILANG 86, TB",
            billing_document="8501692627",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("1637280.00"),
        )
        db.add(sap)
        db.flush()

        billing_doc = Document(
            file_name="gemilang 86.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-combined-hash",
            storage_path="BILLING/same.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="gemilang 86.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-combined-hash",
            storage_path="SPJ/same.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document=None,
            no_spj=None,
            doc_date=None,
            nominal=None,
            ocr_confidence=Decimal("0.0000"),
        )
        spj = SPJ(
            document_id=spj_doc.id,
            no_spj=None,
            ocr_confidence=Decimal("0.0000"),
        )
        db.add_all([billing, spj])
        db.commit()

        [rec] = [row for row in reconcile_batch(db, batch.id, branch="KEDIRI") if row.sap_billing_id == sap.id]
        db.refresh(billing)

        assert billing.billing_document == "8501692627"
        assert rec.physical_billing_id == billing.id
        assert rec.billing_match is True
        assert rec.status == "MATCH"
        assert "Evidence SPJ tersedia" in (rec.remarks or "")

        results = vouch_spj(db, branch="KEDIRI")
        result = next(row for row in results if row.billing_id == billing.id)

        assert result.spj_id == spj.id
        assert result.status == "REVIEW"
        assert result.rule_code == "SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE"
        assert "evidence tidak dianggap hilang" in (result.remarks or "")
