from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.config import settings
from app.database import Base
from app.main import app
from app.models import (
    AuditEngagement,
    AuditFinding,
    CorrectiveActionPlan,
    CorrectiveActionProgressUpdate,
    CorrectiveActionVerification,
    Document,
)
from app.services.follow_up import (
    _aging,
    add_progress_update,
    link_completion_evidence,
    verify_action_plan,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role, user_id, branch="PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def _setup(db, *, status="IN_PROGRESS", pic_user_id="pic-1", target_offset=-2):
    engagement = AuditEngagement(
        code="AUD-FU-1",
        title="Audit Piutang",
        branch="PASURUAN",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        status="IN_PROGRESS",
    )
    db.add(engagement)
    db.flush()
    finding = AuditFinding(
        engagement_id=engagement.id,
        branch="PASURUAN",
        reference="F-FU-01",
        title="Follow-up finding",
        condition="Condition",
        criteria="Criteria",
        cause="Cause",
        effect_risk="Risk",
        recommendation="Recommendation",
        severity="HIGH",
        status="ISSUED",
        preparer_id="auditor-1",
        reviewer_id="reviewer-1",
    )
    db.add(finding)
    db.flush()
    plan = CorrectiveActionPlan(
        finding_id=finding.id,
        response_id=1,
        branch="PASURUAN",
        action_description="Perbaiki kontrol penagihan.",
        pic_user_id=pic_user_id,
        external_pic_name=None if pic_user_id else "Branch Manager",
        target_date=date.today() + timedelta(days=target_offset),
        status=status,
        completion_notes="Implementasi selesai" if status == "SUBMITTED_FOR_VERIFICATION" else None,
        created_by="auditor-1",
        updated_by="auditor-1",
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    db.add(plan)
    db.flush()
    return finding, plan


def _document(db, branch="PASURUAN"):
    doc = Document(
        file_name="evidence.pdf",
        file_type="application/pdf",
        document_type="OTHER",
        file_hash="follow-up-evidence-hash",
        storage_path="/tmp/evidence.pdf",
        uploaded_by="pic-1",
        branch=branch,
    )
    db.add(doc)
    db.flush()
    return doc


def test_aging_and_overdue_are_deterministic():
    with Session(_engine()) as db:
        _, plan = _setup(db)
        plan.target_date = date(2026, 9, 18)
        aging = _aging(plan, as_of=date(2026, 9, 22))
        assert aging == {"days_open": 12, "days_overdue": 4, "overdue": True}

        plan.status = "CLOSED"
        aging = _aging(plan, as_of=date(2026, 9, 22))
        assert aging["days_overdue"] == 0
        assert aging["overdue"] is False


def test_assigned_internal_pic_can_submit_progress():
    with Session(_engine()) as db:
        _, plan = _setup(db)
        update = add_progress_update(
            db,
            plan,
            update_text="Rekonsiliasi harian sudah berjalan.",
            progress_percent=60,
            user=_user("VIEWER", "pic-1"),
        )
        db.commit()
        assert update.progress_percent == 60
        assert update.submitted_by == "pic-1"

        rows = list(
            db.scalars(
                select(CorrectiveActionProgressUpdate).where(
                    CorrectiveActionProgressUpdate.action_plan_id == plan.id
                )
            ).all()
        )
        assert len(rows) == 1


def test_unassigned_viewer_cannot_submit_progress():
    with Session(_engine()) as db:
        _, plan = _setup(db)
        with pytest.raises(HTTPException) as exc:
            add_progress_update(
                db,
                plan,
                update_text="Unauthorized update",
                progress_percent=10,
                user=_user("VIEWER", "other-user"),
            )
        assert exc.value.status_code == 403


def test_verification_requires_completion_evidence_and_records_decision():
    with Session(_engine()) as db:
        _, plan = _setup(db, status="SUBMITTED_FOR_VERIFICATION")
        reviewer = _user("REVIEWER", "reviewer-1")

        with pytest.raises(HTTPException) as exc:
            verify_action_plan(db, plan, result="VERIFIED", note="OK", user=reviewer)
        assert exc.value.status_code == 400
        assert "evidence" in exc.value.detail.lower()

        doc = _document(db)
        link_completion_evidence(
            db,
            plan,
            document_id=doc.id,
            control_evidence_id=None,
            user=_user("VIEWER", "pic-1"),
        )
        verification = verify_action_plan(
            db, plan, result="VERIFIED", note="Evidence memadai", user=reviewer
        )
        db.commit()

        assert plan.status == "VERIFIED"
        assert verification.result == "VERIFIED"
        decisions = list(
            db.scalars(
                select(CorrectiveActionVerification).where(
                    CorrectiveActionVerification.action_plan_id == plan.id
                )
            ).all()
        )
        assert len(decisions) == 1
        assert decisions[0].verified_by == "reviewer-1"


def test_returned_verification_requires_note():
    with Session(_engine()) as db:
        _, plan = _setup(db, status="SUBMITTED_FOR_VERIFICATION")
        with pytest.raises(HTTPException) as exc:
            verify_action_plan(
                db, plan, result="RETURNED", note=" ", user=_user("REVIEWER", "reviewer-1")
            )
        assert exc.value.status_code == 400


def test_cross_branch_completion_evidence_is_blocked():
    with Session(_engine()) as db:
        _, plan = _setup(db)
        doc = _document(db, branch="SIDOARJO")
        with pytest.raises(HTTPException) as exc:
            link_completion_evidence(
                db,
                plan,
                document_id=doc.id,
                control_evidence_id=None,
                user=_user("VIEWER", "pic-1"),
            )
        assert exc.value.status_code == 404


def test_follow_up_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/follow-up")
    assert ui.status_code == 200
    assert "Audit Follow-up Monitoring" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/follow-up").status_code == 401
