from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.config import settings
from app.database import Base
from app.main import app
from app.models import AuditEngagement, AuditPopulation
from app.services.audit_sampling import create_population, population_payload, select_sample


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(role="AUDITOR", branch="PASURUAN"):
    return CurrentUser(user_id="auditor-1", role=role, branch=branch)


def _engagement(db, branch="PASURUAN"):
    row = AuditEngagement(
        code="AUD-SAMPLE-1",
        title="Audit Sampling",
        branch=branch,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        status="IN_PROGRESS",
    )
    db.add(row)
    db.flush()
    return row


def test_population_snapshot_and_coverage():
    with Session(_engine()) as db:
        engagement = _engagement(db)
        population = create_population(
            db,
            engagement=engagement,
            name="Piutang September",
            population_type="RECEIVABLE",
            source_type="SAP_IMPORT",
            source_reference="BATCH-202609",
            total_records=100,
            total_value=Decimal("1000000"),
            user=_user(),
        )
        select_sample(
            db,
            population=population,
            source_record_ref="INV-001",
            selection_method="HIGH_VALUE",
            selection_reason="Material",
            method_parameters={"threshold": 50000},
            monetary_value=Decimal("100000"),
            user=_user(),
        )
        select_sample(
            db,
            population=population,
            source_record_ref="INV-002",
            selection_method="RANDOM",
            selection_reason=None,
            method_parameters={"seed": 42},
            monetary_value=Decimal("50000"),
            user=_user(),
        )
        db.commit()
        payload = population_payload(db, population)
        assert payload["sample_count"] == 2
        assert payload["record_coverage_pct"] == 2.0
        assert payload["value_coverage_pct"] == 15.0


def test_duplicate_sample_is_rejected():
    with Session(_engine()) as db:
        population = create_population(
            db, engagement=_engagement(db), name="Pop", population_type="AR",
            source_type="SYSTEM", source_reference=None, total_records=10, total_value=None, user=_user(),
        )
        select_sample(
            db, population=population, source_record_ref="1", selection_method="MANUAL",
            selection_reason=None, method_parameters=None, monetary_value=None, user=_user(),
        )
        with pytest.raises(HTTPException) as exc:
            select_sample(
                db, population=population, source_record_ref="1", selection_method="MANUAL",
                selection_reason=None, method_parameters=None, monetary_value=None, user=_user(),
            )
        assert exc.value.status_code == 409


def test_invalid_sampling_method_is_rejected():
    with Session(_engine()) as db:
        population = create_population(
            db, engagement=_engagement(db), name="Pop", population_type="AR",
            source_type="SYSTEM", source_reference=None, total_records=10, total_value=None, user=_user(),
        )
        with pytest.raises(HTTPException) as exc:
            select_sample(
                db, population=population, source_record_ref="1", selection_method="UNKNOWN",
                selection_reason=None, method_parameters=None, monetary_value=None, user=_user(),
            )
        assert exc.value.status_code == 400


def test_closed_engagement_rejects_new_population():
    with Session(_engine()) as db:
        engagement = _engagement(db)
        engagement.status = "CLOSED"
        with pytest.raises(HTTPException) as exc:
            create_population(
                db, engagement=engagement, name="Pop", population_type="AR",
                source_type="SYSTEM", source_reference=None, total_records=10, total_value=None, user=_user(),
            )
        assert exc.value.status_code == 409


def test_sampling_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/audit-sampling")
    assert ui.status_code == 200
    assert "Audit Population & Sampling" in ui.text
    assert "document.getElementById('load').onclick" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/audit-populations").status_code == 401
