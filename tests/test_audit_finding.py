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
    AuditFindingVersion,
    AuditWorkingPaper,
)
from app.services.audit_finding import (
    create_finding,
    link_working_paper,
    reopen_finding,
    transition_finding,
    update_finding,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role, user_id, branch="PASURUAN"):
    return CurrentUser(user_id=user_id, role=role, branch=branch)


def _setup(db):
    engagement = AuditEngagement(
        code="AUD-FIND-1",
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
    wp = AuditWorkingPaper(
        engagement_id=engagement.id,
        branch="PASURUAN",
        reference="WP-01",
        title="Vouching",
        audit_objective="Objective",
        procedure_performed="Procedure",
        result_observation="Exception found",
        conclusion="Formal finding needed",
        preparer_id="auditor-1",
        status="REVIEWED",
    )
    db.add(wp)
    db.flush()
    return engagement, wp


def _complete(db, row, auditor):
    return update_finding(
        db,
        row,
        title=None,
        condition="Kontra bon tidak dapat diverifikasi.",
        criteria="Penagihan wajib didukung dokumen valid.",
        cause="Kontrol dokumen penagihan tidak berjalan.",
        effect_risk="Risiko penyalahgunaan penerimaan pelanggan.",
        recommendation="Perkuat validasi dan rekonsiliasi dokumen penagihan.",
        severity="HIGH",
        user=auditor,
    )


def test_finding_lifecycle_preserves_versions():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")
        row = create_finding(
            db,
            engagement=engagement,
            reference="F-01",
            title="Dokumen penagihan tidak valid",
            severity="MEDIUM",
            user=auditor,
        )
        _complete(db, row, auditor)
        transition_finding(db, row, target_status="IN_REVIEW", user=auditor)
        transition_finding(db, row, target_status="APPROVED", user=reviewer)
        transition_finding(db, row, target_status="ISSUED", user=reviewer)
        db.commit()

        assert row.status == "ISSUED"
        assert row.severity == "HIGH"
        assert row.reviewer_id == "reviewer-1"
        assert row.approved_at is not None
        assert row.issued_at is not None

        versions = list(
            db.scalars(
                select(AuditFindingVersion)
                .where(AuditFindingVersion.finding_id == row.id)
                .order_by(AuditFindingVersion.version_number)
            ).all()
        )
        assert [x.status for x in versions] == ["DRAFT", "APPROVED", "ISSUED"]


def test_finding_requires_complete_5c_before_review():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        row = create_finding(
            db,
            engagement=engagement,
            reference="F-02",
            title="Incomplete finding",
            severity="LOW",
            user=auditor,
        )
        with pytest.raises(HTTPException) as exc:
            transition_finding(db, row, target_status="IN_REVIEW", user=auditor)
        assert exc.value.status_code == 400
        assert "5C" in exc.value.detail


def test_approved_finding_is_immutable_until_reopened():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        reviewer = _user("REVIEWER", "reviewer-1")
        row = create_finding(
            db,
            engagement=engagement,
            reference="F-03",
            title="Finding",
            severity="MEDIUM",
            user=auditor,
        )
        _complete(db, row, auditor)
        transition_finding(db, row, target_status="IN_REVIEW", user=auditor)
        transition_finding(db, row, target_status="APPROVED", user=reviewer)

        with pytest.raises(HTTPException) as exc:
            update_finding(
                db,
                row,
                title="Changed silently",
                condition=None,
                criteria=None,
                cause=None,
                effect_risk=None,
                recommendation=None,
                severity=None,
                user=auditor,
            )
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            reopen_finding(db, row, reason=" ", user=reviewer)
        assert exc.value.status_code == 400

        reopen_finding(db, row, reason="Perlu bukti tambahan", user=reviewer)
        update_finding(
            db,
            row,
            title="Changed after reopen",
            condition=None,
            criteria=None,
            cause=None,
            effect_risk=None,
            recommendation=None,
            severity=None,
            user=auditor,
        )
        assert row.status == "DRAFT"
        assert row.title == "Changed after reopen"


def test_finding_links_working_paper_without_mutating_source():
    with Session(_engine()) as db:
        engagement, wp = _setup(db)
        auditor = _user("AUDITOR", "auditor-1")
        row = create_finding(
            db,
            engagement=engagement,
            reference="F-04",
            title="Finding with evidence",
            severity="HIGH",
            user=auditor,
        )
        original_status = wp.status
        link = link_working_paper(db, row, working_paper_id=wp.id, user=auditor)
        assert link.working_paper_id == wp.id
        assert wp.status == original_status

        with pytest.raises(HTTPException) as exc:
            link_working_paper(db, row, working_paper_id=wp.id, user=auditor)
        assert exc.value.status_code == 409


def test_cross_branch_user_cannot_create_finding():
    with Session(_engine()) as db:
        engagement, _ = _setup(db)
        with pytest.raises(HTTPException) as exc:
            create_finding(
                db,
                engagement=engagement,
                reference="F-X",
                title="Cross branch",
                severity="MEDIUM",
                user=_user("AUDITOR", "auditor-1", branch="SIDOARJO"),
            )
        assert exc.value.status_code == 404


def test_finding_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-findings")
    assert ui.status_code == 200
    assert "Audit Finding Management" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/audit-findings").status_code == 401
