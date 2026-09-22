from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.main import app
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditFinding,
    AuditWorkingPaper,
    CorrectiveActionPlan,
    ManagementResponse,
)
from app.services.audit_management_dashboard import build_audit_management_dashboard


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed(db):
    e1 = AuditEngagement(
        code="AUD-PAS-1",
        title="Audit Pasuruan",
        branch="PASURUAN",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        status="IN_PROGRESS",
    )
    e2 = AuditEngagement(
        code="AUD-SDA-1",
        title="Audit Sidoarjo",
        branch="SIDOARJO",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        status="CLOSED",
    )
    db.add_all([e1, e2])
    db.flush()

    db.add_all([
        AuditEngagementAssignment(
            engagement_id=e1.id, user_id="auditor-1", assignment_role="AUDITOR", assigned_by="admin"
        ),
        AuditEngagementAssignment(
            engagement_id=e1.id, user_id="reviewer-1", assignment_role="REVIEWER", assigned_by="admin"
        ),
        AuditEngagementAssignment(
            engagement_id=e2.id, user_id="auditor-2", assignment_role="AUDITOR", assigned_by="admin"
        ),
    ])

    db.add_all([
        AuditWorkingPaper(
            engagement_id=e1.id,
            branch="PASURUAN",
            reference="WP-PAS-1",
            title="WP PAS",
            audit_objective="Objective",
            procedure_performed="Procedure",
            result_observation="Result",
            conclusion="Conclusion",
            preparer_id="auditor-1",
            reviewer_id="reviewer-1",
            status="REVIEWED",
        ),
        AuditWorkingPaper(
            engagement_id=e2.id,
            branch="SIDOARJO",
            reference="WP-SDA-1",
            title="WP SDA",
            audit_objective="Objective",
            procedure_performed="Procedure",
            preparer_id="auditor-2",
            status="DRAFT",
        ),
    ])

    f1 = AuditFinding(
        engagement_id=e1.id,
        branch="PASURUAN",
        reference="F-PAS-1",
        title="Finding PAS",
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
    f2 = AuditFinding(
        engagement_id=e2.id,
        branch="SIDOARJO",
        reference="F-SDA-1",
        title="Finding SDA",
        condition="Condition",
        criteria="Criteria",
        cause="Cause",
        effect_risk="Risk",
        recommendation="Recommendation",
        severity="LOW",
        status="ISSUED",
        preparer_id="auditor-2",
        reviewer_id="reviewer-2",
    )
    db.add_all([f1, f2])
    db.flush()

    r1 = ManagementResponse(
        finding_id=f1.id, branch="PASURUAN", response_text="Agree", position="AGREE", status="ACCEPTED"
    )
    r2 = ManagementResponse(
        finding_id=f2.id, branch="SIDOARJO", response_text="Agree", position="AGREE", status="ACCEPTED"
    )
    db.add_all([r1, r2])
    db.flush()

    created = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db.add_all([
        CorrectiveActionPlan(
            finding_id=f1.id,
            response_id=r1.id,
            branch="PASURUAN",
            action_description="Action overdue",
            external_pic_name="BM PAS",
            target_date=date(2026, 9, 20),
            status="IN_PROGRESS",
            created_at=created,
        ),
        CorrectiveActionPlan(
            finding_id=f1.id,
            response_id=r1.id,
            branch="PASURUAN",
            action_description="Action verify",
            pic_user_id="pic-2",
            target_date=date(2026, 9, 25),
            status="SUBMITTED_FOR_VERIFICATION",
            created_at=created,
        ),
        CorrectiveActionPlan(
            finding_id=f2.id,
            response_id=r2.id,
            branch="SIDOARJO",
            action_description="Closed action",
            external_pic_name="BM SDA",
            target_date=date(2026, 9, 10),
            status="CLOSED",
            created_at=created,
        ),
    ])
    db.flush()
    return e1, e2


def test_dashboard_metrics_reconcile_and_branch_filter():
    with Session(_engine()) as db:
        _seed(db)
        payload = build_audit_management_dashboard(
            db, branch="PASURUAN", as_of=date(2026, 9, 22)
        )

        metrics = payload["metrics"]
        assert metrics["engagements_total"] == 1
        assert metrics["working_papers_total"] == 1
        assert metrics["working_papers_reviewed"] == 1
        assert metrics["working_paper_review_pct"] == 100.0
        assert metrics["findings_total"] == 1
        assert metrics["open_action_plans"] == 2
        assert metrics["overdue"] == 1
        assert metrics["due_soon"] == 1
        assert metrics["awaiting_verification"] == 1
        assert metrics["closed_follow_ups"] == 0

        assert set(payload["distributions"]["branch"]) == {"PASURUAN"}
        assert payload["distributions"]["finding_severity"] == {"HIGH": 1}
        assert payload["distributions"]["open_action_plan_aging"]["8-30"] == 2


def test_dashboard_filter_combination_auditor_severity_pic():
    with Session(_engine()) as db:
        _seed(db)
        payload = build_audit_management_dashboard(
            db,
            auditor_id="auditor-1",
            severity="HIGH",
            pic_user_id="pic-2",
            as_of=date(2026, 9, 22),
        )

        assert payload["metrics"]["engagements_total"] == 1
        assert payload["metrics"]["findings_total"] == 1
        assert payload["metrics"]["open_action_plans"] == 1
        assert payload["metrics"]["due_soon"] == 1
        assert payload["metrics"]["awaiting_verification"] == 1
        assert payload["distributions"]["pic_workload_open"] == {"pic-2": 1}


def test_dashboard_period_overlap_and_empty_state():
    with Session(_engine()) as db:
        _seed(db)
        payload = build_audit_management_dashboard(
            db,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            as_of=date(2026, 10, 1),
        )
        assert payload["metrics"]["engagements_total"] == 0
        assert payload["metrics"]["working_paper_review_pct"] == 0.0
        assert payload["metrics"]["open_action_plans"] == 0


def test_dashboard_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-management")
    assert ui.status_code == 200
    assert "Audit Management Dashboard" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/dashboard/audit-management").status_code == 401
