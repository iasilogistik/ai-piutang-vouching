from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.auth import CurrentUser
from app.database import Base
from app.models import (
    AuditClosing,
    AuditException,
    AuditReport,
    Document,
    DocumentControlEvidence,
    PhysicalBilling,
    ReviewWorkflow,
    SPJ,
    VouchingResult,
)
from app.services.audit_workflow import create_workflow_case, transition_workflow_case, workflow_case_payload


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role: str, branch: str = "PASURUAN"):
    return CurrentUser(user_id=f"{role.lower()}-dev13", role=role, branch=branch)


def _case_resources(db: Session, *, evidence_review_required: bool = False):
    billing_doc = Document(
        file_name="billing.pdf",
        file_type="PDF",
        document_type="BILLING",
        file_hash="dev13-billing",
        storage_path="billing.pdf",
        branch="PASURUAN",
    )
    spj_doc = Document(
        file_name="spj.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash="dev13-spj",
        storage_path="spj.pdf",
        branch="PASURUAN",
    )
    db.add_all([billing_doc, spj_doc])
    db.flush()
    billing = PhysicalBilling(
        document_id=billing_doc.id,
        billing_document="B100",
        no_spj="SPJ100",
        doc_date=date(2026, 9, 22),
        nominal=Decimal("1000.00"),
    )
    spj = SPJ(
        document_id=spj_doc.id,
        no_spj="SPJ100",
        ocr_confidence=Decimal("0.9000"),
    )
    db.add_all([billing, spj])
    db.flush()
    evidence = DocumentControlEvidence(
        document_id=spj_doc.id,
        receiver_signature_status="PRESENT",
        checker_signature_status="PRESENT",
        receiver_stamp_status="PRESENT",
        stamp_customer_match_status="MATCH",
        review_required=evidence_review_required,
        review_status="REVIEW" if evidence_review_required else None,
    )
    db.add(evidence)
    db.flush()
    vouch = VouchingResult(
        billing_id=billing.id,
        spj_id=spj.id,
        no_spj_billing="SPJ100",
        no_spj_document="SPJ100",
        spj_match=True,
        status="REVIEW" if evidence_review_required else "PASS",
        automated_status="PASS",
        control_evidence_id=evidence.id,
    )
    db.add(vouch)
    db.commit()
    return vouch, evidence


def test_happy_path_links_existing_modules_and_closes():
    with Session(_db()) as db:
        vouch, evidence = _case_resources(db)
        auditor = _user("AUDITOR")
        reviewer = _user("REVIEWER")

        case = create_workflow_case(db, vouching_result_id=vouch.id, user=auditor)
        transition_workflow_case(db, case, target_stage="CONTROL_EVIDENCE", user=auditor)
        assert case.control_evidence_id == evidence.id

        review = ReviewWorkflow(
            entity_type="VOUCHING_RESULT",
            entity_id=vouch.id,
            branch="PASURUAN",
            status="CLOSED",
            auditor_id="auditor-dev13",
            reviewer_id="reviewer-dev13",
        )
        db.add(review)
        db.flush()
        transition_workflow_case(
            db,
            case,
            target_stage="REVIEW",
            user=auditor,
            review_workflow_id=review.id,
        )

        report = AuditReport(
            branch="PASURUAN",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status="DRAFT",
            created_by="auditor-dev13",
        )
        db.add(report)
        db.flush()
        transition_workflow_case(
            db,
            case,
            target_stage="REPORT",
            user=auditor,
            audit_report_id=report.id,
        )

        report.status = "APPROVED"
        closing = AuditClosing(
            audit_report_id=report.id,
            branch="PASURUAN",
            status="OPEN",
        )
        db.add(closing)
        db.flush()
        transition_workflow_case(
            db,
            case,
            target_stage="CLOSING",
            user=auditor,
            audit_closing_id=closing.id,
        )

        closing.status = "CLOSED"
        transition_workflow_case(db, case, target_stage="CLOSED", user=reviewer)
        db.commit()

        payload = workflow_case_payload(db, case)
        assert payload["stage"] == "CLOSED"
        assert payload["resources"]["vouching_result_id"] == vouch.id
        assert payload["resources"]["control_evidence_id"] == evidence.id
        assert payload["resources"]["review_workflow_id"] == review.id
        assert payload["resources"]["audit_report_id"] == report.id
        assert payload["resources"]["audit_closing_id"] == closing.id

        audit_rows = list(
            db.scalars(
                select(AuditTrail).where(
                    AuditTrail.entity_type == "AUDIT_WORKFLOW_CASE",
                    AuditTrail.entity_id == case.id,
                )
            ).all()
        )
        assert len(audit_rows) == 6
        assert audit_rows[-1].status_from == "CLOSING"
        assert audit_rows[-1].status_to == "CLOSED"
        assert all(row.branch == "PASURUAN" for row in audit_rows)


def test_exception_condition_cannot_skip_exception_stage():
    with Session(_db()) as db:
        vouch, _ = _case_resources(db, evidence_review_required=True)
        auditor = _user("AUDITOR")
        case = create_workflow_case(db, vouching_result_id=vouch.id, user=auditor)
        transition_workflow_case(db, case, target_stage="CONTROL_EVIDENCE", user=auditor)

        review = ReviewWorkflow(
            entity_type="VOUCHING_RESULT",
            entity_id=vouch.id,
            branch="PASURUAN",
            status="NEW",
        )
        db.add(review)
        db.flush()
        with pytest.raises(HTTPException) as exc:
            transition_workflow_case(
                db,
                case,
                target_stage="REVIEW",
                user=auditor,
                review_workflow_id=review.id,
            )
        assert exc.value.status_code == 409
        assert "Exception condition" in exc.value.detail

        exception = AuditException(
            type="EVIDENCE_MISSING",
            branch="PASURUAN",
            severity="HIGH",
            status="OPEN",
        )
        db.add(exception)
        db.flush()
        transition_workflow_case(
            db,
            case,
            target_stage="EXCEPTION",
            user=auditor,
            audit_exception_id=exception.id,
        )
        exception_review = ReviewWorkflow(
            entity_type="AUDIT_EXCEPTION",
            entity_id=exception.id,
            branch="PASURUAN",
            status="NEW",
        )
        db.add(exception_review)
        db.flush()
        transition_workflow_case(
            db,
            case,
            target_stage="REVIEW",
            user=auditor,
            review_workflow_id=exception_review.id,
        )
        assert case.audit_exception_id == exception.id
        assert case.review_workflow_id == exception_review.id
        assert case.stage == "REVIEW"


def test_invalid_stage_jump_and_branch_access_are_rejected():
    with Session(_db()) as db:
        vouch, _ = _case_resources(db)
        auditor = _user("AUDITOR")
        case = create_workflow_case(db, vouching_result_id=vouch.id, user=auditor)

        with pytest.raises(HTTPException) as invalid:
            transition_workflow_case(db, case, target_stage="REPORT", user=auditor)
        assert invalid.value.status_code == 400

        with pytest.raises(HTTPException):
            transition_workflow_case(
                db,
                case,
                target_stage="CONTROL_EVIDENCE",
                user=_user("AUDITOR", "SIDOARJO"),
            )

        with pytest.raises(HTTPException) as role_error:
            transition_workflow_case(
                db,
                case,
                target_stage="CONTROL_EVIDENCE",
                user=_user("REVIEWER"),
            )
        assert role_error.value.status_code == 403


def test_duplicate_case_is_rejected():
    with Session(_db()) as db:
        vouch, _ = _case_resources(db)
        auditor = _user("AUDITOR")
        create_workflow_case(db, vouching_result_id=vouch.id, user=auditor)
        with pytest.raises(HTTPException) as exc:
            create_workflow_case(db, vouching_result_id=vouch.id, user=auditor)
        assert exc.value.status_code == 409
