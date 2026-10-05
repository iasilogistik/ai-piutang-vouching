from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, DocumentControlEvidence, PhysicalBilling, SPJ
from app.services.vouching import vouch_spj


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _control(db, document_id: int, *, stamp_status="PRESENT", stamp_match="MATCH", review_required=False):
    row = DocumentControlEvidence(
        document_id=document_id,
        receiver_signature_status="PRESENT",
        driver_signature_status="PRESENT",
        security_signature_status="PRESENT",
        bm_signature_status="PRESENT",
        checker_signature_status="PRESENT",
        receiver_stamp_status=stamp_status,
        stamp_customer_match_status=stamp_match,
        review_required=review_required,
        review_reasons=("Stempel belum terbaca jelas." if review_required else None),
    )
    db.add(row)
    db.flush()
    return row


def test_santoso_complete_spj_and_control_evidence_passes_automatically(monkeypatch):
    import app.services.vouching as service

    monkeypatch.setattr(service, "vision_available", lambda: False)

    with Session(_engine()) as db:
        billing_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="santoso-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="santoso-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8501735930",
            no_spj="S41C/202608/2501787882",
        )
        spj = SPJ(
            document_id=spj_doc.id,
            no_spj="S41C/202608/2501787882",
        )
        db.add_all([billing, spj])
        db.flush()
        _control(db, spj_doc.id)
        db.commit()

        result = next(row for row in vouch_spj(db, branch="KEDIRI") if row.billing_id == billing.id)

        assert result.status == "PASS"
        assert result.spj_match is True
        assert result.rule_code is None
        assert "control evidence wajib" in (result.remarks or "")


def test_same_spj_with_unclear_stamp_goes_only_to_review(monkeypatch):
    import app.services.vouching as service

    monkeypatch.setattr(service, "vision_available", lambda: False)

    with Session(_engine()) as db:
        billing_doc = Document(
            file_name="sample.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="stamp-review-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="sample.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="stamp-review-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id, billing_document="8500000001", no_spj="2500000001")
        spj = SPJ(document_id=spj_doc.id, no_spj="2500000001")
        db.add_all([billing, spj])
        db.flush()
        _control(db, spj_doc.id, stamp_status="UNKNOWN", stamp_match="REVIEW", review_required=True)
        db.commit()

        result = next(row for row in vouch_spj(db, branch="KEDIRI") if row.billing_id == billing.id)

        assert result.status == "REVIEW"
        assert result.rule_code == "CONTROL_EVIDENCE_REVIEW"
        assert result.spj_match is True


def test_same_file_pair_requires_review_when_number_unreadable_even_if_visual_controls_complete(monkeypatch):
    import app.services.vouching as service

    monkeypatch.setattr(service, "vision_available", lambda: False)

    with Session(_engine()) as db:
        billing_doc = Document(
            file_name="combined.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="paired-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="combined.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="paired-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id, billing_document="8500000002", no_spj=None)
        spj = SPJ(document_id=spj_doc.id, no_spj=None)
        db.add_all([billing, spj])
        db.flush()
        _control(db, spj_doc.id)
        db.commit()

        result = next(row for row in vouch_spj(db, branch="KEDIRI") if row.billing_id == billing.id)

        assert result.status == "REVIEW"
        assert result.rule_code == "SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE"
        assert result.spj_match is False
        assert result.spj_id == spj.id
