from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.config import settings
from app.database import Base
from app.main import app
from app.models import AuditClosing
from app.services.audit_closing import closing_payload, list_audit_closings, transition_audit_closing


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _closing(status: str = "OPEN", branch: str = "PASURUAN") -> AuditClosing:
    return AuditClosing(
        audit_report_id=1,
        branch=branch,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_closing_signoff_happy_path():
    with Session(_engine()) as db:
        row = _closing()
        db.add(row)
        db.flush()

        auditor = CurrentUser(user_id="auditor-1", role="AUDITOR", branch="PASURUAN")
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")

        transition_audit_closing(db, row, target_status="AUDITOR_SIGNED", user=auditor)
        assert row.status == "AUDITOR_SIGNED"
        assert row.auditor_signoff_by == "auditor-1"
        assert row.auditor_signed_at is not None

        transition_audit_closing(db, row, target_status="REVIEWER_SIGNED", user=reviewer)
        assert row.status == "REVIEWER_SIGNED"
        assert row.reviewer_signoff_by == "reviewer-1"
        assert row.reviewer_signed_at is not None

        transition_audit_closing(db, row, target_status="CLOSED", user=reviewer)
        assert row.status == "CLOSED"
        assert row.closed_by == "reviewer-1"
        assert row.closed_at is not None
        assert closing_payload(row)["allowed_transitions"] == []


def test_reviewer_cannot_do_auditor_signoff():
    with Session(_engine()) as db:
        row = _closing()
        db.add(row)
        db.flush()
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_audit_closing(db, row, target_status="AUDITOR_SIGNED", user=reviewer)
        assert exc.value.status_code == 403


def test_closing_transition_cannot_skip_stage():
    with Session(_engine()) as db:
        row = _closing()
        db.add(row)
        db.flush()
        reviewer = CurrentUser(user_id="reviewer-1", role="REVIEWER", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_audit_closing(db, row, target_status="REVIEWER_SIGNED", user=reviewer)
        assert exc.value.status_code == 400


def test_cross_branch_closing_is_hidden():
    with Session(_engine()) as db:
        row = _closing(branch="SIDOARJO")
        db.add(row)
        db.flush()
        auditor = CurrentUser(user_id="auditor-pasuruan", role="AUDITOR", branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            transition_audit_closing(db, row, target_status="AUDITOR_SIGNED", user=auditor)
        assert exc.value.status_code == 404


def test_list_audit_closings_filters_branch():
    with Session(_engine()) as db:
        db.add_all(
            [
                _closing(branch="PASURUAN"),
                AuditClosing(
                    audit_report_id=2,
                    branch="SIDOARJO",
                    status="OPEN",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()
        rows = list_audit_closings(db, branch="PASURUAN")
        assert len(rows) == 1
        assert rows[0].branch == "PASURUAN"


def test_audit_closing_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-closing")
    assert ui.status_code == 200
    assert "Audit Closing" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    api = client.get("/audit-closings")
    assert api.status_code == 401
