from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, DocumentControlEvidence, SPJ
from app.services.control_evidence_dashboard import build_control_evidence_dashboard


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_control_evidence_dashboard_summarizes_review_queue():
    with Session(_db()) as db:
        doc = Document(
            file_name="spj-review.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="dashboard-spj-review",
            storage_path="storage/spj-review.pdf",
        )
        db.add(doc)
        db.flush()
        db.add(SPJ(document_id=doc.id, no_spj_raw="SPJ-001", no_spj="SPJ001"))
        db.add(
            DocumentControlEvidence(
                document_id=doc.id,
                receiver_signature_status="PRESENT",
                driver_signature_status="PRESENT",
                security_signature_status="UNKNOWN",
                bm_signature_status="PRESENT",
                checker_signature_status="MISSING",
                checker_signature_confidence=Decimal("0.8500"),
                receiver_stamp_status="PRESENT",
                stamp_text_raw="TOKO SANTOSO",
                stamp_text_normalized="SANTOSO",
                stamp_customer_match_status="MATCH",
                review_required=True,
                review_reasons="Label tanda tangan checker tidak ditemukan; Label satpam harus dicek manual",
            )
        )
        db.commit()

        dashboard = build_control_evidence_dashboard(db)

        assert dashboard["summary"]["total_documents"] == 1
        assert dashboard["summary"]["review_required_documents"] == 1
        assert dashboard["summary"]["checker_signature"]["MISSING"] == 1
        assert dashboard["summary"]["stamp_customer_match"]["MATCH"] == 1
        assert dashboard["rows"][0]["overall_control_status"] == "REVIEW"
        assert dashboard["rows"][0]["checker_signature_status"] == "MISSING"
        assert dashboard["rows"][0]["document_url"] == f"/documents/{doc.id}/content"
        assert dashboard["manual_review_queue"][0]["review_reasons"] == [
            "Label tanda tangan checker tidak ditemukan",
            "Label satpam harus dicek manual",
        ]


def test_control_evidence_dashboard_can_filter_review_only():
    with Session(_db()) as db:
        pass_doc = Document(
            file_name="spj-pass.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="dashboard-spj-pass",
            storage_path="storage/spj-pass.pdf",
        )
        review_doc = Document(
            file_name="spj-review.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="dashboard-spj-review-2",
            storage_path="storage/spj-review.pdf",
        )
        db.add_all([pass_doc, review_doc])
        db.flush()
        db.add_all([
            SPJ(document_id=pass_doc.id, no_spj_raw="SPJ-002", no_spj="SPJ002"),
            SPJ(document_id=review_doc.id, no_spj_raw="SPJ-003", no_spj="SPJ003"),
            DocumentControlEvidence(
                document_id=pass_doc.id,
                receiver_signature_status="PRESENT",
                driver_signature_status="PRESENT",
                security_signature_status="PRESENT",
                bm_signature_status="PRESENT",
                checker_signature_status="PRESENT",
                receiver_stamp_status="PRESENT",
                stamp_customer_match_status="MATCH",
                review_required=False,
            ),
            DocumentControlEvidence(
                document_id=review_doc.id,
                receiver_signature_status="PRESENT",
                driver_signature_status="PRESENT",
                security_signature_status="UNKNOWN",
                bm_signature_status="PRESENT",
                checker_signature_status="PRESENT",
                receiver_stamp_status="PRESENT",
                stamp_customer_match_status="REVIEW",
                review_required=True,
                review_reasons="Nama stempel perlu dicek manual",
            ),
        ])
        db.commit()

        dashboard = build_control_evidence_dashboard(db, review_only=True)

        assert dashboard["summary"]["total_documents"] == 2
        assert dashboard["summary"]["pass_documents"] == 1
        assert dashboard["summary"]["review_required_documents"] == 1
        assert dashboard["total_rows"] == 1
        assert dashboard["returned_rows"] == 1
        assert dashboard["rows"][0]["document_id"] == review_doc.id
        assert dashboard["rows"][0]["stamp_customer_match_status"] == "REVIEW"
