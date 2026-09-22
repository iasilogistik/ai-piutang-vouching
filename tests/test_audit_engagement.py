from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.auth import CurrentUser
from app.config import settings
from app.database import Base
from app.main import app
from app.models import AuditEngagement, AuditEngagementAssignment
from app.services.audit_engagement import assign_user, create_engagement, transition_engagement


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role: str, user_id: str, branch: str = "PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def test_engagement_lifecycle_with_assignments_and_audit_trail():
    with Session(_engine()) as db:
        admin = _user("ADMIN", "admin-1", "PASURUAN")
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")
        row = create_engagement(
            db,
            code="AUD-2026-001",
            title="Audit Piutang Pasuruan",
            branch="PASURUAN",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            scope="Piutang dan dokumen pendukung",
            user=admin,
        )
        assign_user(db, row, user_id=auditor.user_id, assignment_role="AUDITOR", actor=admin)
        assign_user(db, row, user_id=reviewer.user_id, assignment_role="REVIEWER", actor=admin)

        transition_engagement(db, row, target_status="PLANNED", user=auditor)
        transition_engagement(db, row, target_status="IN_PROGRESS", user=auditor)
        transition_engagement(db, row, target_status="REVIEW", user=auditor)
        transition_engagement(db, row, target_status="COMPLETED", user=reviewer)
        transition_engagement(db, row, target_status="CLOSED", user=reviewer)
        db.commit()

        assert row.status == "CLOSED"
        assignments = list(db.scalars(select(AuditEngagementAssignment)).all())
        assert {(a.user_id, a.assignment_role) for a in assignments} == {
            ("auditor-1", "AUDITOR"),
            ("reviewer-1", "REVIEWER"),
        }
        trail = list(db.scalars(select(AuditTrail).where(AuditTrail.entity_type == "AUDIT_ENGAGEMENT")).all())
        assert trail[0].action == "CREATE"
        assert sum(1 for x in trail if x.action == "ASSIGN") == 2
        assert sum(1 for x in trail if x.action == "TRANSITION") == 5
        assert all(x.branch == "PASURUAN" for x in trail)


def test_unassigned_auditor_cannot_transition():
    with Session(_engine()) as db:
        admin = _user("ADMIN", "admin-1")
        row = create_engagement(
            db, code="AUD-2", title="Audit", branch="PASURUAN",
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            scope=None, user=admin,
        )
        with pytest.raises(HTTPException) as exc:
            transition_engagement(db, row, target_status="PLANNED", user=_user("AUDITOR", "other"))
        assert exc.value.status_code == 403


def test_cross_branch_transition_is_hidden():
    with Session(_engine()) as db:
        admin = _user("ADMIN", "admin-1")
        row = create_engagement(
            db, code="AUD-3", title="Audit", branch="SIDOARJO",
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            scope=None, user=admin,
        )
        with pytest.raises(HTTPException) as exc:
            transition_engagement(db, row, target_status="PLANNED", user=_user("AUDITOR", "auditor-1", "PASURUAN"))
        assert exc.value.status_code == 404


def test_invalid_transition_is_rejected():
    with Session(_engine()) as db:
        admin = _user("ADMIN", "admin-1")
        row = create_engagement(
            db, code="AUD-4", title="Audit", branch="PASURUAN",
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            scope=None, user=admin,
        )
        with pytest.raises(HTTPException) as exc:
            transition_engagement(db, row, target_status="REVIEW", user=admin)
        assert exc.value.status_code == 400


def test_invalid_period_is_rejected():
    with Session(_engine()) as db:
        with pytest.raises(HTTPException) as exc:
            create_engagement(
                db, code="AUD-5", title="Audit", branch="PASURUAN",
                period_start=date(2026, 10, 1), period_end=date(2026, 9, 1),
                scope=None, user=_user("ADMIN", "admin-1"),
            )
        assert exc.value.status_code == 400


def test_audit_engagement_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-engagements")
    assert ui.status_code == 200
    assert "Audit Engagement" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/audit-engagements").status_code == 401
