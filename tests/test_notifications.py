from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.audit import AuditTrail
from app.audit_service import record_audit
from app.auth import CurrentUser
from app.config import settings
from app.main import app
from app.database import Base
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditFinding,
    AuditNotification,
    CorrectiveActionPlan,
    ManagementResponse,
    NotificationPreference,
)
from app.services import notifications as notification_service
from app.services.notifications import (
    generate_deadline_reminders,
    mark_notification_read,
    unread_count,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(user_id="auditor-1", role="AUDITOR", branch="PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def test_assignment_notification_is_idempotent_when_audit_event_replayed():
    with Session(_engine()) as db:
        entry = AuditTrail(
            entity_type="AUDIT_ENGAGEMENT",
            entity_id=1,
            action="ASSIGN",
            actor="admin",
            branch="PASURUAN",
            metadata_json={"assigned_user_id": "auditor-1", "assignment_role": "AUDITOR"},
        )
        db.add(entry)
        db.flush()

        first = notification_service.emit_from_audit_event(db, entry)
        second = notification_service.emit_from_audit_event(db, entry)
        db.flush()

        rows = list(db.scalars(select(AuditNotification)).all())
        assert len(first) == 1
        assert len(second) == 1
        assert len(rows) == 1
        assert rows[0].user_id == "auditor-1"
        assert rows[0].event_type == "ASSIGNMENT"


def test_due_soon_and_overdue_reminders_are_deterministic_per_day():
    with Session(_engine()) as db:
        engagement = AuditEngagement(
            code="AUD-NOTIF-1",
            title="Audit",
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
            reference="F-01",
            title="Finding",
            condition="C",
            criteria="C",
            cause="C",
            effect_risk="R",
            recommendation="R",
            severity="HIGH",
            status="ISSUED",
            preparer_id="auditor-1",
        )
        db.add(finding)
        db.flush()
        response = ManagementResponse(
            finding_id=finding.id,
            branch="PASURUAN",
            response_text="Agree",
            position="AGREE",
            status="ACCEPTED",
        )
        db.add(response)
        db.flush()
        db.add(NotificationPreference(user_id="pic-1", reminder_days_before=3))
        due = CorrectiveActionPlan(
            finding_id=finding.id,
            response_id=response.id,
            branch="PASURUAN",
            action_description="Due action",
            pic_user_id="pic-1",
            target_date=date(2026, 9, 24),
            status="IN_PROGRESS",
        )
        overdue = CorrectiveActionPlan(
            finding_id=finding.id,
            response_id=response.id,
            branch="PASURUAN",
            action_description="Overdue action",
            pic_user_id="pic-1",
            target_date=date(2026, 9, 20),
            status="IN_PROGRESS",
        )
        db.add_all([due, overdue])
        db.flush()

        first = generate_deadline_reminders(db, as_of=date(2026, 9, 22))
        second = generate_deadline_reminders(db, as_of=date(2026, 9, 22))
        rows = list(db.scalars(select(AuditNotification).order_by(AuditNotification.id)).all())

        assert first == {"due_soon": 1, "overdue": 1}
        assert second == {"due_soon": 0, "overdue": 0}
        assert [x.event_type for x in rows] == ["DUE_SOON_REMINDER", "OVERDUE_REMINDER"]


def test_notification_read_state_is_user_scoped():
    with Session(_engine()) as db:
        row = notification_service.create_notification(
            db,
            user_id="auditor-1",
            branch="PASURUAN",
            event_type="TEST",
            title="Test",
            message="Test notification",
            target_type="AUDIT_ENGAGEMENT",
            target_id=1,
            target_url="/ui/audit-engagements",
            idempotency_key="test:read:1",
        )
        db.flush()
        assert unread_count(db, "auditor-1") == 1

        with pytest.raises(Exception) as exc:
            mark_notification_read(row.id, db=db, user=_user("other-user"))
        assert getattr(exc.value, "status_code", None) == 404

        payload = mark_notification_read(row.id, db=db, user=_user("auditor-1"))
        assert payload["is_read"] is True
        assert unread_count(db, "auditor-1") == 0


def test_notification_failure_does_not_rollback_audit_event(monkeypatch):
    def boom(db, entry):
        raise RuntimeError("notification backend failed")

    monkeypatch.setattr(notification_service, "emit_from_audit_event", boom)

    with Session(_engine()) as db:
        row = record_audit(
            db,
            entity_type="AUDIT_ENGAGEMENT",
            entity_id=1,
            action="ASSIGN",
            actor="admin",
            branch="PASURUAN",
            metadata={"assigned_user_id": "auditor-1"},
        )
        db.commit()
        assert row.id is not None
        stored = db.get(AuditTrail, row.id)
        assert stored is not None
        assert stored.action == "ASSIGN"


def test_finding_issued_notifies_other_engagement_assignees():
    with Session(_engine()) as db:
        engagement = AuditEngagement(
            code="AUD-NOTIF-2",
            title="Audit",
            branch="PASURUAN",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status="IN_PROGRESS",
        )
        db.add(engagement)
        db.flush()
        db.add_all([
            AuditEngagementAssignment(
                engagement_id=engagement.id,
                user_id="auditor-1",
                assignment_role="AUDITOR",
                assigned_by="admin",
            ),
            AuditEngagementAssignment(
                engagement_id=engagement.id,
                user_id="reviewer-1",
                assignment_role="REVIEWER",
                assigned_by="admin",
            ),
        ])
        finding = AuditFinding(
            engagement_id=engagement.id,
            branch="PASURUAN",
            reference="F-02",
            title="Finding",
            condition="C",
            criteria="C",
            cause="C",
            effect_risk="R",
            recommendation="R",
            severity="HIGH",
            status="ISSUED",
            preparer_id="auditor-1",
            reviewer_id="reviewer-1",
        )
        db.add(finding)
        db.flush()
        entry = AuditTrail(
            entity_type="AUDIT_FINDING",
            entity_id=finding.id,
            action="TRANSITION",
            actor="reviewer-1",
            status_from="APPROVED",
            status_to="ISSUED",
            branch="PASURUAN",
        )
        db.add(entry)
        db.flush()

        notification_service.emit_from_audit_event(db, entry)
        rows = list(db.scalars(select(AuditNotification)).all())
        assert [(x.user_id, x.event_type) for x in rows] == [("auditor-1", "FINDING_ISSUED")]


def test_notification_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/notifications")
    assert ui.status_code == 200
    assert "Notification Inbox" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/notifications").status_code == 401
    assert client.get("/notifications/unread-count").status_code == 401
