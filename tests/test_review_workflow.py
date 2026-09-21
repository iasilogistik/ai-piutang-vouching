from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import Base
from app.models import ReviewWorkflow
from app.services.review_workflow import list_review_workflows, transition_workflow, workflow_payload


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _workflow(status: str = "NEW", branch: str = "PASURUAN") -> ReviewWorkflow:
    return ReviewWorkflow(
        entity_type="AUDIT_EXCEPTION",
        entity_id=1,
        branch=branch,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_auditor_can_move_new_to_processing_and_auditor_reviewed():
    with Session(_engine()) as db:
        row = _workflow()
        db.add(row)
        db.flush()
        auditor = CurrentUser(user_id="auditor-1", role="AUDITOR", branch="PASURUAN")

        transition_workflow(db, row, target_status="PROCESSING", user=auditor, remarks="mulai review")
        assert row.status == "PROCESSING"
        assert row.auditor_id == "auditor-1"

        transition_workflow(db, row, target_status="AUDITOR_REVIEWED", user=auditor, remarks="selesai auditor")
        assert row.status == "AUDITOR_REVIEWED"
        assert row.auditor_remarks == "selesai auditor"


def test_reviewer_approves_then_closes_workflow():
    with Session(_engine()) as db:
        row = _workflow(status="AUDITOR_REVIEWED")
        db.add(row)
        db.flush()
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")

        transition_workflow(db, row, target_status="REVIEWER_APPROVED", user=reviewer, remarks="approved")
        assert row.status == "REVIEWER_APPROVED"
        assert row.reviewer_id == "reviewer-1"

        transition_workflow(db, row, target_status="CLOSED", user=reviewer, remarks="closed")
        assert row.status == "CLOSED"
        assert row.closed_at is not None


def test_reviewer_reject_then_auditor_rework():
    with Session(_engine()) as db:
        row = _workflow(status="AUDITOR_REVIEWED")
        db.add(row)
        db.flush()
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")
        auditor = CurrentUser(user_id="auditor-1", role="AUDITOR", branch="PASURUAN")

        transition_workflow(db, row, target_status="REVIEWER_REJECTED", user=reviewer, remarks="perbaiki evidence")
        assert row.status == "REVIEWER_REJECTED"

        transition_workflow(db, row, target_status="PROCESSING", user=auditor, remarks="rework")
        assert row.status == "PROCESSING"


def test_invalid_transition_is_rejected():
    with Session(_engine()) as db:
        row = _workflow(status="NEW")
        db.add(row)
        db.flush()
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_workflow(db, row, target_status="REVIEWER_APPROVED", user=reviewer)
        assert exc.value.status_code == 400


def test_wrong_role_cannot_perform_reviewer_transition():
    with Session(_engine()) as db:
        row = _workflow(status="AUDITOR_REVIEWED")
        db.add(row)
        db.flush()
        auditor = CurrentUser(user_id="auditor-1", role="AUDITOR", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_workflow(db, row, target_status="REVIEWER_APPROVED", user=auditor)
        assert exc.value.status_code == 403


def test_cross_branch_transition_is_hidden():
    with Session(_engine()) as db:
        row = _workflow(status="NEW", branch="SIDOARJO")
        db.add(row)
        db.flush()
        auditor = CurrentUser(user_id="auditor-pasuruan", role="AUDITOR", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_workflow(db, row, target_status="PROCESSING", user=auditor)
        assert exc.value.status_code == 404


def test_list_review_workflows_filters_branch():
    with Session(_engine()) as db:
        db.add_all([
            _workflow(status="NEW", branch="PASURUAN"),
            ReviewWorkflow(
                entity_type="AUDIT_EXCEPTION",
                entity_id=2,
                branch="SIDOARJO",
                status="NEW",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ])
        db.commit()

        rows = list_review_workflows(db, branch="PASURUAN")
        assert len(rows) == 1
        assert rows[0].branch == "PASURUAN"
        assert "PROCESSING" in workflow_payload(rows[0])["allowed_transitions"]
