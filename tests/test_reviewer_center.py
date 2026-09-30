from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser, current_user
from app.database import Base
from app.main import app
from app.models import ReviewWorkflow
from app.services.reviewer_center import build_reviewer_dashboard, reviewer_center_html


client = TestClient(app)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_reviewer_dashboard_is_branch_scoped_and_tracks_decisions():
    with Session(_engine()) as db:
        db.add_all(
            [
                ReviewWorkflow(
                    entity_type="AUDIT_EXCEPTION",
                    entity_id=101,
                    branch="PASURUAN",
                    status="AUDITOR_REVIEWED",
                    auditor_id="auditor-1",
                    auditor_remarks="Siap direview.",
                ),
                ReviewWorkflow(
                    entity_type="AUDIT_EXCEPTION",
                    entity_id=102,
                    branch="SIDOARJO",
                    status="AUDITOR_REVIEWED",
                    auditor_id="auditor-2",
                ),
                ReviewWorkflow(
                    entity_type="AUDIT_EXCEPTION",
                    entity_id=103,
                    branch="PASURUAN",
                    status="REVIEWER_APPROVED",
                    reviewer_id="reviewer-1",
                ),
                ReviewWorkflow(
                    entity_type="AUDIT_EXCEPTION",
                    entity_id=104,
                    branch="PASURUAN",
                    status="REVIEWER_REJECTED",
                    reviewer_id="reviewer-1",
                ),
            ]
        )
        db.commit()

        payload = build_reviewer_dashboard(
            db,
            reviewer_id="reviewer-1",
            branch="PASURUAN",
        )

        assert payload["branch"] == "PASURUAN"
        assert payload["metrics"]["waiting_reviewer"] == 1
        assert payload["metrics"]["approved_by_me"] == 1
        assert payload["metrics"]["rejected_by_me"] == 1
        assert len(payload["pending_workflows"]) == 1
        assert payload["pending_workflows"][0]["entity_id"] == 101


def test_reviewer_center_has_dashboard_links_and_no_manual_bearer_field():
    html = reviewer_center_html()

    assert "Reviewer Center" in html
    assert "/reviewer/dashboard" in html
    assert "/ui/dashboard" in html
    assert "/ui/review-queue" in html
    assert "/ui/control-evidence" in html
    assert "/ui/exceptions" in html
    assert "Approve" in html
    assert "Reject" in html
    assert "Bearer Token" not in html
    assert 'id="token"' not in html


def test_reviewer_center_dashboard_api_rejects_viewer_role():
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id="viewer-1",
        role="VIEWER",
        branch="PASURUAN",
    )
    try:
        response = client.get("/reviewer/dashboard")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_reviewer_center_route_is_registered():
    response = client.get("/ui/reviewer-center")

    assert response.status_code == 200
    assert "Menunggu Keputusan Reviewer" in response.text
