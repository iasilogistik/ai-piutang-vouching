from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.main import app
from app.models import (
    AuditException,
    AuditReport,
    BillingReconciliation,
    Document,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
)
from app.services.audit_report import build_audit_snapshot, default_finding_summary, list_audit_reports


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_build_audit_snapshot_is_branch_and_period_scoped():
    with Session(_engine()) as db:
        pas_batch = ImportBatch(file_name="pas.xlsx", branch="PASURUAN", total_records=2)
        sid_batch = ImportBatch(file_name="sid.xlsx", branch="SIDOARJO", total_records=1)
        db.add_all([pas_batch, sid_batch])
        db.flush()

        sap1 = SAPBilling(
            import_batch_id=pas_batch.id,
            billing_document="SAP-1",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("100000"),
        )
        sap2 = SAPBilling(
            import_batch_id=pas_batch.id,
            billing_document="SAP-2",
            doc_date=date(2026, 9, 11),
            nominal=Decimal("200000"),
        )
        sap_other = SAPBilling(
            import_batch_id=sid_batch.id,
            billing_document="SAP-X",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("999999"),
        )
        db.add_all([sap1, sap2, sap_other])
        db.flush()

        doc = Document(
            file_name="billing.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="hash-pas",
            storage_path="/tmp/billing.pdf",
            branch="PASURUAN",
        )
        doc_other = Document(
            file_name="billing-other.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="hash-sid",
            storage_path="/tmp/billing-other.pdf",
            branch="SIDOARJO",
        )
        db.add_all([doc, doc_other])
        db.flush()

        physical = PhysicalBilling(
            document_id=doc.id,
            billing_document="SAP-1",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("100000"),
        )
        physical_other = PhysicalBilling(
            document_id=doc_other.id,
            billing_document="SAP-X",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("999999"),
        )
        db.add_all([physical, physical_other])
        db.flush()

        db.add(
            BillingReconciliation(
                sap_billing_id=sap1.id,
                physical_billing_id=physical.id,
                billing_match=True,
                date_match=True,
                nominal_match=True,
                nominal_difference=Decimal("0"),
                status="MATCH",
            )
        )

        db.add_all(
            [
                AuditException(
                    type="SPJ_MISSING",
                    branch="PASURUAN",
                    severity="HIGH",
                    status="OPEN",
                    created_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
                ),
                AuditException(
                    type="AMOUNT_MISMATCH",
                    branch="PASURUAN",
                    severity="MEDIUM",
                    status="RESOLVED",
                    created_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
                    resolved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
                ),
                AuditException(
                    type="SPJ_MISSING",
                    branch="SIDOARJO",
                    severity="HIGH",
                    status="OPEN",
                    created_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()

        snapshot = build_audit_snapshot(
            db,
            branch="PASURUAN",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )

        assert snapshot == {
            "population_count": 2,
            "sampled_count": 1,
            "matched_count": 1,
            "exception_count": 2,
            "resolved_exception_count": 1,
            "unresolved_exception_count": 1,
        }


def test_default_finding_summary_uses_snapshot_counts():
    summary = default_finding_summary(
        {
            "population_count": 10,
            "sampled_count": 4,
            "matched_count": 3,
            "exception_count": 2,
            "unresolved_exception_count": 1,
            "resolved_exception_count": 1,
        }
    )
    assert "Population 10" in summary
    assert "1 unresolved" in summary
    assert "1 resolved" in summary


def test_list_audit_reports_filters_branch():
    with Session(_engine()) as db:
        db.add_all(
            [
                AuditReport(
                    branch="PASURUAN",
                    period_start=date(2026, 9, 1),
                    period_end=date(2026, 9, 30),
                    status="DRAFT",
                ),
                AuditReport(
                    branch="SIDOARJO",
                    period_start=date(2026, 9, 1),
                    period_end=date(2026, 9, 30),
                    status="APPROVED",
                ),
            ]
        )
        db.commit()

        rows = list_audit_reports(db, branch="PASURUAN")
        assert len(rows) == 1
        assert rows[0].branch == "PASURUAN"


def test_audit_report_ui_route_registered():
    paths = {getattr(route, "path", None) for route in app.routes if getattr(route, "path", None)}
    assert "/ui/audit-reports" in paths
    assert "/audit-reports" in paths
    assert "/audit-reports/{report_id}/approve" in paths
