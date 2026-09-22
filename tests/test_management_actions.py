from datetime import date, timedelta

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
    CorrectiveActionPlanHistory,
    ManagementResponseVersion,
)
from app.services.management_actions import (
    _overdue,
    create_action_plan,
    create_response,
    transition_action_plan,
    transition_response,
    update_action_plan,
    update_response,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role, user_id, branch="PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def _setup(db):
    engagement = AuditEngagement(
        code="AUD-MGT-1",
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
        reference="F-01",
        title="Penagihan tidak didukung dokumen valid",
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
    return finding


def _accepted_response(db, finding):
    auditor = _user("AUDITOR", "auditor-1")
    reviewer = _user("REVIEWER", "reviewer-1")
    response = create_response(db, finding, user=auditor)
    update_response(
        db,
        response,
        response_text="Manajemen menyetujui rekomendasi dan akan memperbaiki kontrol.",
        position="AGREE",
        user=auditor,
    )
    transition_response(db, response, target_status="SUBMITTED", review_note=None, user=auditor)
    transition_response(db, response, target_status="ACCEPTED", review_note="Disetujui", user=reviewer)
    return response


def test_management_response_lifecycle_preserves_finding_and_versions():
    with Session(_engine()) as db:
        finding = _setup(db)
        original = (finding.title, finding.condition, finding.recommendation, finding.status)
        response = _accepted_response(db, finding)
        db.commit()

        assert response.status == "ACCEPTED"
        assert (finding.title, finding.condition, finding.recommendation, finding.status) == original
        versions = list(
            db.scalars(
                select(ManagementResponseVersion)
                .where(ManagementResponseVersion.response_id == response.id)
                .order_by(ManagementResponseVersion.version_number)
            ).all()
        )
        assert [x.status for x in versions] == ["DRAFT", "DRAFT", "SUBMITTED", "ACCEPTED"]


def test_response_requires_issued_finding_and_return_note():
    with Session(_engine()) as db:
        finding = _setup(db)
        finding.status = "APPROVED"
        with pytest.raises(HTTPException) as exc:
            create_response(db, finding, user=_user("AUDITOR", "auditor-1"))
        assert exc.value.status_code == 409

        finding.status = "ISSUED"
        response = create_response(db, finding, user=_user("AUDITOR", "auditor-1"))
        update_response(
            db, response, response_text="Perlu tindak lanjut", position="PARTIAL",
            user=_user("AUDITOR", "auditor-1"),
        )
        transition_response(
            db, response, target_status="SUBMITTED", review_note=None,
            user=_user("AUDITOR", "auditor-1"),
        )
        with pytest.raises(HTTPException) as exc:
            transition_response(
                db, response, target_status="RETURNED", review_note=" ",
                user=_user("REVIEWER", "reviewer-1"),
            )
        assert exc.value.status_code == 400


def test_action_plan_lifecycle_history_and_verification_gate():
    with Session(_engine()) as db:
        finding = _setup(db)
        response = _accepted_response(db, finding)
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")

        plan = create_action_plan(
            db,
            response,
            action_description="Rekonsiliasi TTP dengan penerimaan bank setiap hari.",
            pic_user_id=None,
            external_pic_name="Branch Manager",
            target_date=date.today() + timedelta(days=14),
            user=auditor,
        )
        transition_action_plan(db, plan, target_status="IN_PROGRESS", reason=None, user=auditor)

        with pytest.raises(HTTPException) as exc:
            transition_action_plan(
                db, plan, target_status="SUBMITTED_FOR_VERIFICATION", reason=None, user=auditor
            )
        assert exc.value.status_code == 400

        update_action_plan(
            db,
            plan,
            action_description=None,
            pic_user_id=None,
            external_pic_name=None,
            target_date=None,
            completion_notes="Kontrol harian telah diterapkan dan diuji.",
            user=auditor,
        )
        transition_action_plan(db, plan, target_status="SUBMITTED_FOR_VERIFICATION", reason=None, user=auditor)
        transition_action_plan(db, plan, target_status="VERIFIED", reason=None, user=reviewer)
        transition_action_plan(db, plan, target_status="CLOSED", reason=None, user=reviewer)
        db.commit()

        assert plan.status == "CLOSED"
        history = list(
            db.scalars(
                select(CorrectiveActionPlanHistory)
                .where(CorrectiveActionPlanHistory.action_plan_id == plan.id)
                .order_by(CorrectiveActionPlanHistory.id)
            ).all()
        )
        assert [x.status for x in history] == [
            "OPEN", "IN_PROGRESS", "IN_PROGRESS",
            "SUBMITTED_FOR_VERIFICATION", "VERIFIED", "CLOSED",
        ]


def test_action_plan_overdue_is_derived_not_persisted():
    with Session(_engine()) as db:
        finding = _setup(db)
        response = _accepted_response(db, finding)
        plan = create_action_plan(
            db,
            response,
            action_description="Perbaikan kontrol",
            pic_user_id=None,
            external_pic_name="BAO",
            target_date=date.today() - timedelta(days=2),
            user=_user("AUDITOR", "auditor-1"),
        )
        assert _overdue(plan) is True
        plan.status = "CLOSED"
        assert _overdue(plan) is False
        assert "overdue" not in CorrectiveActionPlanHistory.__table__.columns.keys()


def test_action_plan_requires_exactly_one_pic():
    with Session(_engine()) as db:
        finding = _setup(db)
        response = _accepted_response(db, finding)
        with pytest.raises(HTTPException) as exc:
            create_action_plan(
                db,
                response,
                action_description="Action",
                pic_user_id=None,
                external_pic_name=None,
                target_date=date.today(),
                user=_user("AUDITOR", "auditor-1"),
            )
        assert exc.value.status_code == 400


def test_cross_branch_response_is_hidden():
    with Session(_engine()) as db:
        finding = _setup(db)
        with pytest.raises(HTTPException) as exc:
            create_response(db, finding, user=_user("AUDITOR", "auditor-1", branch="SIDOARJO"))
        assert exc.value.status_code == 404


def test_management_action_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/management-actions")
    assert ui.status_code == 200
    assert "Management Response" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/management-responses").status_code == 401
    assert client.get("/corrective-action-plans").status_code == 401
