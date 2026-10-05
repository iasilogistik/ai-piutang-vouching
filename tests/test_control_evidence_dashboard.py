from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import BillingReconciliation, Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
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
        assert dashboard["rows"][0]["document_url"] == f"/documents/{doc.id}/view"
        assert dashboard["rows"][0]["document_content_url"] == f"/documents/{doc.id}/content"
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



def test_dashboard_overall_uses_reconciliation_not_control_only():
    with Session(_db()) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="2138024",
            customer_account_name="BERKAH AL AQSO, TB",
            billing_document="8501681202",
            doc_date=__import__("datetime").date(2026, 9, 10),
            nominal=Decimal("5415882.00"),
        )
        billing_doc = Document(
            file_name="Berkah Al aqso 8501681202.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="combined-hash",
            storage_path="billing.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="Berkah Al aqso 8501681202.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="combined-hash",
            storage_path="spj.pdf",
            branch="KEDIRI",
        )
        db.add_all([sap, billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8501681202",
            no_spj="2501731412",
            nominal=Decimal("881589.00"),
        )
        spj = SPJ(document_id=spj_doc.id, no_spj="2501731412")
        control = DocumentControlEvidence(
            document_id=spj_doc.id,
            receiver_signature_status="PRESENT",
            driver_signature_status="PRESENT",
            security_signature_status="PRESENT",
            bm_signature_status="PRESENT",
            checker_signature_status="PRESENT",
            receiver_stamp_status="PRESENT",
            stamp_customer_match_status="NOT_EVALUATED",
            review_required=False,
        )
        db.add_all([billing, spj, control])
        db.flush()
        rec = BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=billing.id,
            billing_match=True,
            date_match=False,
            nominal_match=False,
            nominal_difference=Decimal("4534293.00"),
            status="EXCEPTION",
        )
        vouch = VouchingResult(
            billing_id=billing.id,
            spj_id=spj.id,
            no_spj_billing="2501731412",
            no_spj_document="2501731412",
            spj_match=True,
            status="PASS",
            automated_status="PASS",
            control_evidence_id=control.id,
        )
        db.add_all([rec, vouch])
        db.commit()

        dashboard = build_control_evidence_dashboard(db, branch="KEDIRI")

        row = dashboard["rows"][0]
        assert row["control_evidence_status"] == "PASS"
        assert row["reconciliation_status"] == "EXCEPTION"
        assert row["overall_control_status"] == "EXCEPTION"
        assert dashboard["summary"]["exception_documents"] == 1
        assert dashboard["summary"]["pass_documents"] == 0
