from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, DocumentControlEvidence
from app.services.control_evidence_review import review_control_evidence


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_review_control_evidence_can_mark_pass_and_clear_queue():
    with Session(_db()) as db:
        doc = Document(
            file_name="spj.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="review-evidence-pass",
            storage_path="storage/spj.pdf",
        )
        db.add(doc)
        db.flush()
        evidence = DocumentControlEvidence(
            document_id=doc.id,
            checker_signature_status="UNKNOWN",
            receiver_stamp_status="PRESENT",
            stamp_customer_match_status="MATCH",
            review_required=True,
            review_reasons="Tanda tangan checker perlu dicek manual",
        )
        db.add(evidence)
        db.commit()

        payload = review_control_evidence(
            db,
            evidence.id,
            status="PASS",
            reviewer_id="auditor-1",
            remarks="Checker sudah terlihat pada dokumen fisik.",
        )
        db.commit()

        assert payload["previous_review_status"] == "REVIEW"
        assert payload["review_status"] == "PASS"
        assert payload["review_required"] is False
        assert payload["reviewer_id"] == "auditor-1"
        assert payload["reviewer_remarks"] == "Checker sudah terlihat pada dokumen fisik."

        refreshed = db.get(DocumentControlEvidence, evidence.id)
        assert refreshed.review_required is False
        assert refreshed.review_status == "PASS"


def test_review_control_evidence_rejects_invalid_status():
    with Session(_db()) as db:
        doc = Document(
            file_name="spj.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="review-evidence-invalid",
            storage_path="storage/spj.pdf",
        )
        db.add(doc)
        db.flush()
        evidence = DocumentControlEvidence(document_id=doc.id, review_required=True)
        db.add(evidence)
        db.commit()

        try:
            review_control_evidence(db, evidence.id, status="DONE", reviewer_id="auditor-1")
        except ValueError as exc:
            assert "status must be PASS" in str(exc)
        else:
            raise AssertionError("Expected invalid review status to raise ValueError")
