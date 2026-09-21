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
    VouchingResult,
)
from app.services.branch_dashboard import build_branch_dashboard


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_branch(db: Session, branch: str, suffix: str, rec_status: str, vouch_status: str):
    batch = ImportBatch(file_name=f"sap-{suffix}.xlsx", branch=branch, total_records=1, status="IMPORTED")
    db.add(batch)
    db.flush()

    sap = SAPBilling(
        import_batch_id=batch.id,
        customer=f"Customer {suffix}",
        billing_document=f"BILL-{suffix}",
        doc_date=__import__("datetime").date(2026, 9, 21),
        nominal=Decimal("100000.00"),
    )
    db.add(sap)

    doc = Document(
        file_name=f"billing-{suffix}.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash=f"hash-{suffix}",
        storage_path=f"storage/{suffix}.pdf",
        branch=branch,
    )
    db.add(doc)
    db.flush()

    physical = PhysicalBilling(
        document_id=doc.id,
        billing_document=f"BILL-{suffix}",
        doc_date=__import__("datetime").date(2026, 9, 21),
        nominal=Decimal("100000.00"),
    )
    db.add(physical)
    db.flush()

    db.add(
        BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=physical.id,
            billing_match=rec_status == "MATCH",
            date_match=True,
            nominal_match=True,
            nominal_difference=Decimal("0"),
            status=rec_status,
        )
    )
    db.add(
        VouchingResult(
            billing_id=physical.id,
            spj_id=None,
            spj_match=vouch_status == "PASS",
            status=vouch_status,
        )
    )

    evidence_doc = Document(
        file_name=f"spj-{suffix}.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash=f"spj-hash-{suffix}",
        storage_path=f"storage/spj-{suffix}.pdf",
        branch=branch,
    )
    db.add(evidence_doc)
    db.flush()
    db.add(
        DocumentControlEvidence(
            document_id=evidence_doc.id,
            review_required=rec_status != "MATCH",
        )
    )


def test_branch_dashboard_isolates_branch_metrics():
    with Session(_engine()) as db:
        _seed_branch(db, "PASURUAN", "P", "MATCH", "PASS")
        _seed_branch(db, "SIDOARJO", "S", "EXCEPTION", "REVIEW")
        db.commit()

        pasuruan = build_branch_dashboard(db, branch="PASURUAN")
        sidoarjo = build_branch_dashboard(db, branch="SIDOARJO")

        assert pasuruan["metrics"]["sap_billing"] == 1
        assert pasuruan["metrics"]["physical_billing"] == 1
        assert pasuruan["metrics"]["matched"] == 1
        assert pasuruan["metrics"]["unmatched"] == 0
        assert pasuruan["metrics"]["approved"] == 2
        assert pasuruan["metrics"]["control_evidence_review"] == 0

        assert sidoarjo["metrics"]["sap_billing"] == 1
        assert sidoarjo["metrics"]["matched"] == 0
        assert sidoarjo["metrics"]["unmatched"] == 1
        assert sidoarjo["metrics"]["pending_review"] == 2
        assert sidoarjo["metrics"]["rejected"] == 1
        assert sidoarjo["metrics"]["control_evidence_review"] == 1


def test_admin_all_branch_dashboard_aggregates_all_branches():
    with Session(_engine()) as db:
        _seed_branch(db, "PASURUAN", "P", "MATCH", "PASS")
        _seed_branch(db, "SIDOARJO", "S", "EXCEPTION", "REVIEW")
        db.commit()

        dashboard = build_branch_dashboard(db)

        assert dashboard["branch"] is None
        assert dashboard["metrics"]["sap_billing"] == 2
        assert dashboard["metrics"]["physical_billing"] == 2
        assert dashboard["metrics"]["matched"] == 1
        assert dashboard["metrics"]["unmatched"] == 1
