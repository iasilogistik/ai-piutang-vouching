from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.audit_service import list_audit_trail
from app.database import Base
from app.main import app
from app.services.audit_trail_ui import audit_trail_html
from app.services.navigation import menu_for_role


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_list_audit_trail_filters_branch_actor_action_and_date():
    with Session(_engine()) as db:
        db.add_all(
            [
                AuditTrail(
                    entity_type="DOCUMENT",
                    entity_id=1,
                    action="UPLOAD",
                    actor="auditor-a",
                    branch="PASURUAN",
                    created_at=datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc),
                ),
                AuditTrail(
                    entity_type="DOCUMENT",
                    entity_id=2,
                    action="OCR",
                    actor="auditor-a",
                    branch="PASURUAN",
                    created_at=datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc),
                ),
                AuditTrail(
                    entity_type="DOCUMENT",
                    entity_id=3,
                    action="UPLOAD",
                    actor="auditor-b",
                    branch="SIDOARJO",
                    created_at=datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()

        rows = list_audit_trail(
            db,
            branch="PASURUAN",
            actor="auditor-a",
            action="UPLOAD",
            date_from=date(2026, 9, 20),
            date_to=date(2026, 9, 20),
        )
        assert len(rows) == 1
        assert rows[0].entity_id == 1
        assert rows[0].branch == "PASURUAN"


def test_list_audit_trail_filters_entity():
    with Session(_engine()) as db:
        db.add_all(
            [
                AuditTrail(entity_type="DOCUMENT", entity_id=10, action="UPLOAD", branch="PASURUAN"),
                AuditTrail(entity_type="REVIEW_WORKFLOW", entity_id=10, action="TRANSITION", branch="PASURUAN"),
            ]
        )
        db.commit()

        rows = list_audit_trail(db, entity_type="review_workflow", entity_id=10, branch="PASURUAN")
        assert len(rows) == 1
        assert rows[0].entity_type == "REVIEW_WORKFLOW"


def test_audit_trail_ui_contains_expected_filters():
    html = audit_trail_html()
    for label in ("Tanggal Dari", "Tanggal Sampai", "Actor", "Action", "Entity Type", "Entity ID", "Cabang"):
        assert label in html
    assert "/audit-trail/query" in html


def test_audit_trail_ui_route_is_registered():
    client = TestClient(app)
    response = client.get("/ui/audit-trail")
    assert response.status_code == 200
    assert "Audit Trail Viewer" in response.text


def test_navigation_uses_audit_trail_viewer():
    admin = {item["label"]: item["href"] for item in menu_for_role("ADMIN")}
    auditor = {item["label"]: item["href"] for item in menu_for_role("AUDITOR")}
    assert admin["Audit Trail"] == "/ui/audit-trail"
    assert auditor["Audit Trail"] == "/ui/audit-trail"
