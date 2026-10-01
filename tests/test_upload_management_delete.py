from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import Base
from app.models import (
    BillingReconciliation,
    Document,
    EvidenceResourceLink,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
    SPJ,
    VouchingResult,
)
from app.services.upload_management import (
    _document_delete_policies,
    delete_evidence_upload,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user():
    return CurrentUser(user_id="auditor-1", role="AUDITOR", branch="KEDIRI")


def _automatic_case(db: Session):
    batch = ImportBatch(
        file_name="sap.xlsx",
        period=date(2026, 9, 1),
        branch="KEDIRI",
        total_records=1,
        status="IMPORTED",
    )
    billing_doc = Document(
        file_name="billing.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="billing-delete-hash",
        storage_path="storage/billing.pdf",
        branch="KEDIRI",
    )
    spj_doc = Document(
        file_name="spj.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash="spj-delete-hash",
        storage_path="storage/spj.pdf",
        branch="KEDIRI",
    )
    db.add_all([batch, billing_doc, spj_doc])
    db.flush()

    sap = SAPBilling(
        import_batch_id=batch.id,
        customer="C-001",
        customer_account_name="TOKO KEDIRI",
        billing_document="B-100",
        doc_date=date(2026, 9, 1),
        nominal=Decimal("1000.00"),
    )
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
    db.add_all([sap, billing, spj])
    db.flush()

    reconciliation = BillingReconciliation(
        sap_billing_id=sap.id,
        physical_billing_id=billing.id,
        billing_match=True,
        date_match=True,
        nominal_match=True,
        nominal_difference=Decimal("0.00"),
        status="MATCH",
    )
    vouching = VouchingResult(
        billing_id=billing.id,
        spj_id=spj.id,
        no_spj_billing="SPJ100",
        no_spj_document="SPJ100",
        spj_match=True,
        status="PASS",
        automated_status="PASS",
    )
    db.add_all([reconciliation, vouching])
    db.commit()
    return billing_doc.id, spj_doc.id, reconciliation.id, vouching.id


def test_automatic_reconciliation_and_vouching_do_not_lock_wrong_upload_delete():
    with Session(_engine()) as db:
        billing_doc_id, spj_doc_id, reconciliation_id, vouching_id = _automatic_case(db)

        policy = _document_delete_policies(db, [db.get(Document, billing_doc_id)])[billing_doc_id]
        assert policy["delete_allowed"] is True

        result = delete_evidence_upload(billing_doc_id, db=db, user=_user())

        assert result["deleted"] is True
        assert result["automatic_reconciliation_rows_reset"] == 1
        assert result["automatic_vouching_rows_reset"] == 1
        assert db.get(Document, billing_doc_id) is None
        assert db.get(BillingReconciliation, reconciliation_id) is None
        assert db.get(VouchingResult, vouching_id) is None
        assert db.get(Document, spj_doc_id) is not None


def test_manual_match_or_review_can_be_deleted_as_correction_and_resets_results():
    with Session(_engine()) as db:
        billing_doc_id, spj_doc_id, reconciliation_id, vouching_id = _automatic_case(db)
        vouching = db.get(VouchingResult, vouching_id)
        vouching.status = "PASS"
        vouching.manual_review_status = "PASS"
        vouching.reviewer_id = "reviewer-1"
        db.commit()

        policy = _document_delete_policies(db, [db.get(Document, billing_doc_id)])[billing_doc_id]
        assert policy["delete_allowed"] is True
        assert policy["delete_requires_reset"] is True
        assert "di-reset" in policy["delete_reset_note"]

        result = delete_evidence_upload(billing_doc_id, db=db, user=_user())

        assert result["deleted"] is True
        assert result["automatic_reconciliation_rows_reset"] == 1
        assert result["automatic_vouching_rows_reset"] == 1
        assert result["manual_review_rows_reset"] == 1
        assert db.get(Document, billing_doc_id) is None
        assert db.get(Document, spj_doc_id) is not None
        assert db.get(BillingReconciliation, reconciliation_id) is None
        assert db.get(VouchingResult, vouching_id) is None


def test_delete_spj_after_manual_match_resets_linked_reconciliation_too():
    with Session(_engine()) as db:
        billing_doc_id, spj_doc_id, reconciliation_id, vouching_id = _automatic_case(db)
        reconciliation = db.get(BillingReconciliation, reconciliation_id)
        reconciliation.status = "MATCH"
        reconciliation.remarks = "[MANUAL_CONFIRMED] Billing/SPJ sesuai."
        vouching = db.get(VouchingResult, vouching_id)
        vouching.status = "PASS"
        vouching.manual_review_status = "PASS"
        vouching.reviewer_id = "reviewer-1"
        db.commit()

        policy = _document_delete_policies(db, [db.get(Document, spj_doc_id)])[spj_doc_id]
        assert policy["delete_allowed"] is True
        assert policy["delete_requires_reset"] is True

        result = delete_evidence_upload(spj_doc_id, db=db, user=_user())

        assert result["deleted"] is True
        assert result["automatic_reconciliation_rows_reset"] == 1
        assert result["automatic_vouching_rows_reset"] == 1
        assert db.get(Document, spj_doc_id) is None
        assert db.get(Document, billing_doc_id) is not None
        assert db.get(BillingReconciliation, reconciliation_id) is None
        assert db.get(VouchingResult, vouching_id) is None


def test_working_paper_or_finding_style_resource_link_locks_evidence_delete():
    with Session(_engine()) as db:
        document = Document(
            file_name="linked.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="linked-delete-hash",
            storage_path="storage/linked.pdf",
            branch="KEDIRI",
        )
        db.add(document)
        db.flush()
        db.add(
            EvidenceResourceLink(
                document_id=document.id,
                branch="KEDIRI",
                resource_type="WORKING_PAPER",
                resource_id=99,
                linked_by="auditor-1",
            )
        )
        db.commit()

        policy = _document_delete_policies(db, [document])[document.id]
        assert policy["delete_allowed"] is False
        assert "WORKING_PAPER" in policy["delete_reason"]

        with pytest.raises(HTTPException) as exc:
            delete_evidence_upload(document.id, db=db, user=_user())
        assert exc.value.status_code == 409
        assert db.scalar(select(Document.id).where(Document.id == document.id)) == document.id
