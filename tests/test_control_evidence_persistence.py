from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, DocumentControlEvidence
from app.services.control_evidence import analyze_spj_control_evidence
from app.services.control_evidence_store import evidence_payload, persist_control_evidence


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_persists_checker_signature_and_stamp_match():
    text = """
    Nomor SPJ 2501787882
    Checker Signature: Ada
    Driver TTD: Ada
    Security TTD: Ada
    BM TTD: Ada
    Tanda tangan penerima: Ada
    Stempel: Ada
    TOKO SANTOSO
    """
    with Session(_db()) as db:
        doc = Document(file_name="spj.pdf", file_type="PDF", document_type="SPJ", file_hash="h", storage_path="spj.pdf")
        db.add(doc); db.flush()

        evidence = analyze_spj_control_evidence(text, expected_customer="SANTOSO, TOKO")
        row = persist_control_evidence(db, doc.id, evidence)
        db.commit()

        stored = db.get(DocumentControlEvidence, row.id)
        assert stored is not None
        assert stored.checker_signature_status == "PRESENT"
        assert stored.receiver_stamp_status == "PRESENT"
        assert stored.stamp_text_raw == "TOKO SANTOSO"
        assert stored.stamp_customer_match_status == "MATCH"
        assert stored.review_required is False

        payload = evidence_payload(stored)
        assert payload["checker_signature"]["status"] == "PRESENT"
        assert payload["receiver_stamp"]["customer_match"]["status"] == "MATCH"


def test_persists_manual_review_reasons_when_evidence_is_uncertain():
    with Session(_db()) as db:
        doc = Document(file_name="spj.pdf", file_type="PDF", document_type="SPJ", file_hash="h2", storage_path="spj.pdf")
        db.add(doc); db.flush()

        evidence = analyze_spj_control_evidence("Nomor SPJ 2501787882", expected_customer="SANTOSO, TOKO")
        row = persist_control_evidence(db, doc.id, evidence)
        db.commit()

        stored = db.get(DocumentControlEvidence, row.id)
        assert stored is not None
        assert stored.review_required is True
        assert stored.review_reasons
        assert "cek" in stored.review_reasons.lower() or "tidak" in stored.review_reasons.lower()
