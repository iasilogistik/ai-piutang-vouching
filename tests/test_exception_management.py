from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser, current_user
from app.database import Base, SessionLocal
from app.main import app
from app.models import AuditException
from app.services.exception_management import exception_payload, list_exception_records


client = TestClient(app)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_exception_payload_calculates_aging_days():
    row = AuditException(
        id=1,
        type="SPJ_MISSING",
        branch="PASURUAN",
        severity="HIGH",
        status="OPEN",
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    payload = exception_payload(row, today=date(2026, 9, 21))
    assert payload["aging_days"] == 11


def test_exception_list_is_branch_scoped():
    with Session(_engine()) as db:
        db.add_all(
            [
                AuditException(type="SPJ_MISSING", branch="PASURUAN", severity="HIGH", status="OPEN"),
                AuditException(type="AMOUNT_MISMATCH", branch="SIDOARJO", severity="MEDIUM", status="OPEN"),
            ]
        )
        db.commit()

        pasuruan = list_exception_records(db, branch="PASURUAN")
        sidoarjo = list_exception_records(db, branch="SIDOARJO")

        assert len(pasuruan) == 1
        assert pasuruan[0].branch == "PASURUAN"
        assert len(sidoarjo) == 1
        assert sidoarjo[0].branch == "SIDOARJO"


def test_non_admin_cannot_enumerate_other_branch_exception_records():
    db = SessionLocal()
    created_ids = []
    try:
        rows = [
            AuditException(type="SPJ_MISSING", branch="PASURUAN", severity="HIGH", status="OPEN"),
            AuditException(type="BILLING_MISSING", branch="SIDOARJO", severity="HIGH", status="OPEN"),
        ]
        db.add_all(rows)
        db.commit()
        for row in rows:
            db.refresh(row)
            created_ids.append(row.id)

        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id="auditor-pasuruan", role="AUDITOR", branch="PASURUAN"
        )
        response = client.get("/exception-records?branch=SIDOARJO")
        assert response.status_code == 403

        response = client.get("/exception-records")
        assert response.status_code == 200
        payload = response.json()
        assert payload["branch"] == "PASURUAN"
        assert all(row["branch"] == "PASURUAN" for row in payload["exceptions"])

        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id="admin-user", role="ADMIN", branch=None
        )
        response = client.get("/exception-records?branch=SIDOARJO")
        assert response.status_code == 200
        assert all(row["branch"] == "SIDOARJO" for row in response.json()["exceptions"])
    finally:
        app.dependency_overrides.pop(current_user, None)
        if created_ids:
            db.query(AuditException).filter(AuditException.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_reviewer_cannot_write_auditor_note():
    db = SessionLocal()
    row_id = None
    try:
        row = AuditException(type="EVIDENCE_MISSING", branch="PASURUAN", severity="MEDIUM", status="OPEN")
        db.add(row)
        db.commit()
        db.refresh(row)
        row_id = row.id

        app.dependency_overrides[current_user] = lambda: CurrentUser(
            user_id="reviewer-pasuruan", role="REVIEWER", branch="PASURUAN"
        )
        response = client.patch(
            f"/exception-records/{row_id}",
            data={"auditor_note": "reviewer must not alter auditor note"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)
        if row_id is not None:
            db.query(AuditException).filter(AuditException.id == row_id).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_resolved_exception_has_resolved_at_and_fixed_aging():
    with Session(_engine()) as db:
        row = AuditException(
            type="DATE_MISMATCH",
            branch="PASURUAN",
            severity="LOW",
            status="RESOLVED",
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
            updated_at=datetime.now(timezone.utc),
            resolved_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        payload = exception_payload(row)
        assert payload["resolved_at"] is not None
        assert payload["aging_days"] == 3
