from datetime import date
from decimal import Decimal

import pytest
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
from app.services.vouching import review_vouching_result, vouch_spj


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _matched_case(db: Session):
    batch = ImportBatch(
        file_name="sap.xlsx",
        period=date(2026, 9, 1),
        branch="PASURUAN",
        total_records=1,
        status="IMPORTED",
    )
    db.add(batch)
    db.flush()
    sap = SAPBilling(
        import_batch_id=batch.id,
        customer="C-001",
        customer_account_name="TOKO SANTOSO",
        billing_document="B-100",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("1000.00"),
    )
    billing_doc = Document(
        file_name="billing.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="billing-hash",
        storage_path="billing.pdf",
        branch="PASURUAN",
    )
    spj_doc = Document(
        file_name="spj.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash="spj-hash",
        storage_path="spj.pdf",
        branch="PASURUAN",
    )
    db.add_all([sap, billing_doc, spj_doc])
    db.flush()
    billing = PhysicalBilling(
        document_id=billing_doc.id,
        billing_document="B100",
        no_spj_raw="SPJ-100",
        no_spj="SPJ100",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("1000.00"),
    )
    spj = SPJ(
        document_id=spj_doc.id,
        no_spj_raw="SPJ-100",
        no_spj="SPJ100",
        ocr_confidence=Decimal("0.9000"),
    )
    db.add_all([billing, spj])
    db.flush()
    db.add(
        BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=billing.id,
            billing_match=True,
            date_match=True,
            nominal_match=True,
            nominal_difference=Decimal("0.00"),
            status="MATCH",
        )
    )
    evidence = DocumentControlEvidence(
        document_id=spj_doc.id,
        receiver_signature_status="PRESENT",
        driver_signature_status="PRESENT",
        security_signature_status="PRESENT",
        bm_signature_status="PRESENT",
        checker_signature_status="PRESENT",
        receiver_stamp_status="PRESENT",
        stamp_text_raw="TOKO SANTOSO",
        stamp_text_normalized="SANTOSO",
        stamp_customer_match_status="MATCH",
        review_required=False,
    )
    db.add(evidence)
    db.commit()
    return billing, spj, evidence


def test_vouching_links_customer_and_control_evidence():
    with Session(_db()) as db:
        billing, _, evidence = _matched_case(db)

        [result] = vouch_spj(db, branch="PASURUAN")

        assert result.status == "PASS"
        assert result.automated_status == "PASS"
        assert result.manual_review_status is None
        assert result.expected_customer_name == "TOKO SANTOSO"
        assert result.control_evidence_id == evidence.id


def test_override_requires_reason_and_never_mutates_source_records():
    with Session(_db()) as db:
        billing, spj, _ = _matched_case(db)
        [result] = vouch_spj(db, branch="PASURUAN")
        billing_no_spj = billing.no_spj
        spj_no_spj = spj.no_spj

        with pytest.raises(ValueError, match="reason_code is required"):
            review_vouching_result(
                db,
                result.id,
                status="EXCEPTION",
                reviewer_id="reviewer-1",
                branch="PASURUAN",
            )

        payload = review_vouching_result(
            db,
            result.id,
            status="EXCEPTION",
            reason_code="STAMP_CUSTOMER_MISMATCH",
            remarks="Stempel perlu klarifikasi.",
            reviewer_id="reviewer-1",
            branch="PASURUAN",
        )
        db.commit()

        assert payload["status"] == "EXCEPTION"
        assert payload["automated_result"]["status"] == "PASS"
        assert payload["reviewer_decision"]["status"] == "EXCEPTION"
        assert payload["reviewer_decision"]["reason_code"] == "STAMP_CUSTOMER_MISMATCH"
        assert payload["linked_customer"] == "TOKO SANTOSO"
        assert payload["control_evidence"]["receiver_stamp"]["status"] == "PRESENT"
        assert db.get(PhysicalBilling, billing.id).no_spj == billing_no_spj
        assert db.get(SPJ, spj.id).no_spj == spj_no_spj


def test_manual_override_survives_automated_reprocessing():
    with Session(_db()) as db:
        _, _, _ = _matched_case(db)
        [first] = vouch_spj(db, branch="PASURUAN")
        first_id = first.id
        review_vouching_result(
            db,
            first.id,
            status="REVIEW",
            reason_code="OCR_OR_SCAN_UNCLEAR",
            remarks="Perlu cek scan.",
            reviewer_id="reviewer-1",
            branch="PASURUAN",
        )
        db.commit()

        [rerun] = vouch_spj(db, branch="PASURUAN")

        assert rerun.id == first_id
        assert rerun.automated_status == "PASS"
        assert rerun.manual_review_status == "REVIEW"
        assert rerun.status == "REVIEW"
        assert rerun.review_reason_code == "OCR_OR_SCAN_UNCLEAR"
        assert rerun.reviewer_id == "reviewer-1"


def test_review_is_branch_isolated_and_reason_code_is_validated():
    with Session(_db()) as db:
        _, _, _ = _matched_case(db)
        [result] = vouch_spj(db, branch="PASURUAN")

        with pytest.raises(ValueError, match="not found"):
            review_vouching_result(
                db,
                result.id,
                status="PASS",
                reviewer_id="reviewer-1",
                branch="SIDOARJO",
            )

        with pytest.raises(ValueError, match="reason_code must be one of"):
            review_vouching_result(
                db,
                result.id,
                status="EXCEPTION",
                reason_code="FREE_TEXT_REASON",
                reviewer_id="reviewer-1",
                branch="PASURUAN",
            )
