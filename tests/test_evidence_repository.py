from datetime import date
import hashlib
from pathlib import Path
from types import SimpleNamespace

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
    AuditWorkingPaper,
    Document,
    EvidenceResourceLink,
)
from app.services import evidence_repository
from app.services.evidence_repository import (
    archive_evidence,
    delete_evidence_disabled,
    link_evidence,
    supersede_evidence,
    verify_integrity,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(branch="PASURUAN"):
    return CurrentUser(user_id="auditor-1", role="AUDITOR", branch=branch)


def _document(db, *, branch="PASURUAN", name="evidence.pdf", content=b"evidence"):
    path = Path("/tmp") / f"{name}-{branch}"
    path.write_bytes(content)
    row = Document(
        file_name=name,
        file_type="PDF",
        document_type="SPJ",
        file_hash=hashlib.sha256(content).hexdigest(),
        storage_path=str(path),
        uploaded_by="auditor-1",
        branch=branch,
        evidence_classification="SPJ",
        evidence_source="UPLOAD",
        file_size_bytes=len(content),
        mime_type="application/pdf",
        evidence_version_number=1,
    )
    db.add(row)
    db.flush()
    return row


def _setup(db):
    engagement = AuditEngagement(
        code="AUD-EV-1",
        title="Audit Evidence",
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
        reference="F-EV-1",
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
    wp = AuditWorkingPaper(
        engagement_id=engagement.id,
        branch="PASURUAN",
        reference="WP-EV-1",
        title="Working Paper",
        audit_objective="Objective",
        procedure_performed="Procedure",
        preparer_id="auditor-1",
        status="DRAFT",
    )
    db.add_all([finding, wp])
    db.flush()
    return engagement, finding, wp


def test_one_evidence_can_link_to_multiple_audit_resources():
    with Session(_engine()) as db:
        engagement, finding, wp = _setup(db)
        doc = _document(db)
        first = link_evidence(db, doc, resource_type="FINDING", resource_id=finding.id, user=_user())
        second = link_evidence(db, doc, resource_type="WORKING_PAPER", resource_id=wp.id, user=_user())
        db.flush()

        links = list(
            db.scalars(
                select(EvidenceResourceLink)
                .where(EvidenceResourceLink.document_id == doc.id)
                .order_by(EvidenceResourceLink.id)
            ).all()
        )
        assert [x.id for x in links] == [first.id, second.id]
        assert {x.resource_type for x in links} == {"FINDING", "WORKING_PAPER"}
        assert doc.engagement_id == engagement.id


def test_supersede_preserves_prior_version_and_archives_old():
    with Session(_engine()) as db:
        _, finding, _ = _setup(db)
        old = _document(db, name="old.pdf", content=b"old evidence")
        replacement = _document(db, name="new.pdf", content=b"new evidence")
        link_evidence(db, old, resource_type="FINDING", resource_id=finding.id, user=_user())

        result = supersede_evidence(
            db,
            old,
            replacement_document_id=replacement.id,
            reason="Updated signed document",
            user=_user(),
        )
        db.flush()

        assert old.archived_at is not None
        assert old.archive_reason.startswith("SUPERSEDED:")
        assert result.supersedes_document_id == old.id
        assert result.evidence_version_number == 2
        assert db.scalar(
            select(EvidenceResourceLink.id).where(EvidenceResourceLink.document_id == old.id)
        ) is not None


def test_integrity_verification_detects_changed_content(monkeypatch):
    monkeypatch.setattr(evidence_repository, "settings", SimpleNamespace(use_supabase_storage=False))
    with Session(_engine()) as db:
        doc = _document(db, name="integrity.pdf", content=b"original")
        ok = verify_integrity(db, doc, user=_user())
        assert ok["hash_match"] is True
        assert ok["size_match"] is True

        Path(doc.storage_path).write_bytes(b"tampered")
        changed = verify_integrity(db, doc, user=_user())
        assert changed["hash_match"] is False
        assert changed["size_match"] is False


def test_archive_blocks_new_links_and_hard_delete():
    with Session(_engine()) as db:
        _, finding, _ = _setup(db)
        doc = _document(db)
        archive_evidence(db, doc, reason="No longer current", user=_user())

        with pytest.raises(HTTPException) as exc:
            link_evidence(db, doc, resource_type="FINDING", resource_id=finding.id, user=_user())
        assert exc.value.status_code == 409

        with pytest.raises(HTTPException) as exc:
            delete_evidence_disabled(doc.id, db=db, user=_user())
        assert exc.value.status_code == 409


def test_cross_branch_resource_link_is_hidden():
    with Session(_engine()) as db:
        engagement = AuditEngagement(
            code="AUD-SDA-EV",
            title="Audit Sidoarjo",
            branch="SIDOARJO",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status="IN_PROGRESS",
        )
        db.add(engagement)
        db.flush()
        finding = AuditFinding(
            engagement_id=engagement.id,
            branch="SIDOARJO",
            reference="F-SDA-EV",
            title="Finding",
            condition="C",
            criteria="C",
            cause="C",
            effect_risk="R",
            recommendation="R",
            severity="MEDIUM",
            status="ISSUED",
            preparer_id="auditor-2",
        )
        db.add(finding)
        db.flush()
        doc = _document(db, branch="PASURUAN")

        with pytest.raises(HTTPException) as exc:
            link_evidence(db, doc, resource_type="FINDING", resource_id=finding.id, user=_user())
        assert exc.value.status_code == 404


def test_evidence_repository_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/evidence-repository")
    assert ui.status_code == 200
    assert "Audit Evidence Repository" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/evidence-repository").status_code == 401
