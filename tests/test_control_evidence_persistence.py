from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import ControlEvidenceDetection, Document, DocumentControlEvidence
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


def test_detection_records_are_idempotent_for_same_document_hash_and_detector_version():
    with Session(_db()) as db:
        doc = Document(
            file_name="spj.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-hash",
            storage_path="spj.pdf",
            branch="PASURUAN",
        )
        db.add(doc); db.flush()
        evidence = analyze_spj_control_evidence("Checker Signature: Ada\nStempel: Ada\nTOKO SANTOSO", expected_customer="TOKO SANTOSO")

        persist_control_evidence(db, doc.id, evidence, extraction_engine="test-ocr")
        db.flush()
        first_ids = [row.id for row in db.query(ControlEvidenceDetection).order_by(ControlEvidenceDetection.id).all()]

        persist_control_evidence(db, doc.id, evidence, extraction_engine="test-ocr")
        db.flush()
        second = db.query(ControlEvidenceDetection).order_by(ControlEvidenceDetection.id).all()

        assert len(second) == 7
        assert [row.id for row in second] == first_ids
        assert {row.detection_type for row in second} == {
            "receiver_signature",
            "driver_signature",
            "security_signature",
            "bm_signature",
            "checker_signature",
            "receiver_stamp",
            "stamp_customer_match",
        }
        assert all(row.source_file_hash == "same-hash" for row in second)
        assert all(row.detector_version == "1.0" for row in second)
        assert all(row.branch == "PASURUAN" for row in second)


def test_detection_unknown_and_failure_are_distinct_from_missing():
    with Session(_db()) as db:
        doc = Document(
            file_name="spj.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="state-hash",
            storage_path="spj.pdf",
            branch="PASURUAN",
        )
        db.add(doc); db.flush()
        evidence = analyze_spj_control_evidence("Checker", expected_customer=None)
        evidence["checker_signature"]["status"] = "ERROR"
        evidence["checker_signature"]["processing_status"] = "FAILED"
        evidence["checker_signature"]["error_message"] = "detector unavailable"
        evidence["driver_signature"]["status"] = "MISSING"

        row = persist_control_evidence(db, doc.id, evidence, extraction_engine="test-ocr")
        db.flush()

        detections = {
            item.detection_type: item
            for item in db.query(ControlEvidenceDetection).filter(ControlEvidenceDetection.document_id == doc.id).all()
        }
        assert detections["receiver_signature"].status == "UNKNOWN"
        assert detections["checker_signature"].status == "ERROR"
        assert detections["checker_signature"].processing_status == "FAILED"
        assert detections["checker_signature"].error_message == "detector unavailable"
        assert detections["driver_signature"].status == "MISSING"

        payload = evidence_payload(row)
        assert len(payload["detection_records"]) == 7
