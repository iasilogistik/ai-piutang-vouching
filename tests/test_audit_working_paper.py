from datetime import date

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
    AuditEngagementAssignment,
    AuditSample,
    AuditPopulation,
    AuditWorkingPaperVersion,
)
from app.services.audit_working_paper import (
    create_working_paper,
    reopen_working_paper,
    transition_working_paper,
    update_working_paper,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role, user_id, branch="PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def _setup(db):
    engagement = AuditEngagement(
        code="AUD-WP-1",
        title="Audit Piutang",
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
    population = AuditPopulation(
        engagement_id=engagement.id,
        branch="PASURUAN",
        name="AR",
        population_type="RECEIVABLE",
        source_type="SYSTEM",
        total_records=10,
    )
    db.add(population)
    db.flush()
    sample = AuditSample(
        engagement_id=engagement.id,
        population_id=population.id,
        branch="PASURUAN",
        source_record_ref="INV-001",
        selection_method="MANUAL",
        status="SELECTED",
        selected_by="auditor-1",
    )
    db.add(sample)
    db.flush()
    return engagement, sample


def test_working_paper_lifecycle_and_version_history():
    with Session(_engine()) as db:
        engagement, sample = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")
        row = create_working_paper(
            db,
            engagement=engagement,
            reference="WP-01",
            title="Vouching Piutang",
            audit_objective="Memastikan keberadaan piutang",
            procedure_performed="Vouch billing ke SPJ",
            sample_id=sample.id,
            user=auditor,
        )
        update_working_paper(
            db,
            row,
            title=None,
            audit_objective=None,
            procedure_performed=None,
            result_observation="Dokumen sesuai",
            conclusion="Saldo dapat diyakini",
            user=auditor,
        )
        transition_working_paper(db, row, target_status="PREPARED", user=auditor)
        transition_working_paper(db, row, target_status="IN_REVIEW", user=auditor)
        transition_working_paper(db, row, target_status="REVIEWED", user=reviewer)
        db.commit()

        assert row.status == "REVIEWED"
        assert row.reviewer_id == "reviewer-1"
        versions = list(
            db.scalars(
                select(AuditWorkingPaperVersion)
                .where(AuditWorkingPaperVersion.working_paper_id == row.id)
                .order_by(AuditWorkingPaperVersion.version_number)
            ).all()
        )
        assert [x.status for x in versions] == ["DRAFT", "PREPARED", "REVIEWED"]


def test_reviewed_paper_is_immutable_until_reopened():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")
        row = create_working_paper(
            db,
            engagement=engagement,
            reference="WP-02",
            title="Test",
            audit_objective="Objective",
            procedure_performed="Procedure",
            sample_id=None,
            user=auditor,
        )
        update_working_paper(
            db, row, title=None, audit_objective=None, procedure_performed=None,
            result_observation="Result", conclusion="Conclusion", user=auditor,
        )
        transition_working_paper(db, row, target_status="PREPARED", user=auditor)
        transition_working_paper(db, row, target_status="IN_REVIEW", user=auditor)
        transition_working_paper(db, row, target_status="REVIEWED", user=reviewer)

        with pytest.raises(HTTPException) as exc:
            update_working_paper(
                db, row, title="Changed", audit_objective=None, procedure_performed=None,
                result_observation=None, conclusion=None, user=auditor,
            )
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            reopen_working_paper(db, row, reason=" ", user=reviewer)
        assert exc.value.status_code == 400

        reopen_working_paper(db, row, reason="Perlu bukti tambahan", user=reviewer)
        update_working_paper(
            db, row, title="Changed", audit_objective=None, procedure_performed=None,
            result_observation=None, conclusion=None, user=auditor,
        )
        assert row.status == "DRAFT"
        assert row.title == "Changed"


def test_unassigned_auditor_cannot_create_working_paper():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        with pytest.raises(HTTPException) as exc:
            create_working_paper(
                db,
                engagement=engagement,
                reference="WP-X",
                title="Test",
                audit_objective="Objective",
                procedure_performed="Procedure",
                sample_id=None,
                user=_user("AUDITOR", "other"),
            )
        assert exc.value.status_code == 403


def test_cross_branch_working_paper_creation_is_hidden():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        with pytest.raises(HTTPException) as exc:
            create_working_paper(
                db,
                engagement=engagement,
                reference="WP-X",
                title="Test",
                audit_objective="Objective",
                procedure_performed="Procedure",
                sample_id=None,
                user=_user("AUDITOR", "auditor-1", branch="SIDOARJO"),
            )
        assert exc.value.status_code == 404


def test_working_paper_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-working-papers")
    assert ui.status_code == 200
    assert "Electronic Working Papers" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/audit-working-papers").status_code == 401
