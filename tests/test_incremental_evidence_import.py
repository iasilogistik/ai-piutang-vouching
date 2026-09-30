from io import BytesIO

from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.main as main
from app.database import Base
from app.models import Document


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


def test_incremental_evidence_replaces_same_name_type_branch_and_adds_new_name(monkeypatch):
    monkeypatch.setattr(main.settings, "use_supabase_storage", False)
    monkeypatch.setattr(
        main,
        "ocr_document",
        lambda db, document_id: {"engine": "TEST", "confidence": "1.0000"},
    )
    monkeypatch.setattr(
        main,
        "analyze_and_persist_control_evidence",
        lambda db, document_id: {"review_required": False},
    )

    with Session(_db()) as db:
        first = main._ingest_physical_document(
            db,
            _upload("SPJ-001.pdf", b"%PDF-first"),
            document_type="SPJ",
            uploaded_by="auditor",
            source_mode="DRIVE_FOLDER",
            branch="KEDIRI",
        )
        db.commit()
        replacement = main._ingest_physical_document(
            db,
            _upload("SPJ-001.pdf", b"%PDF-replacement"),
            document_type="SPJ",
            uploaded_by="auditor",
            source_mode="DRIVE_FOLDER",
            branch="KEDIRI",
        )
        db.commit()
        added = main._ingest_physical_document(
            db,
            _upload("SPJ-002.pdf", b"%PDF-new"),
            document_type="SPJ",
            uploaded_by="auditor",
            source_mode="DRIVE_FOLDER",
            branch="KEDIRI",
        )
        db.commit()

        old = db.get(Document, first["document_id"])
        current = db.get(Document, replacement["document_id"])
        new_doc = db.get(Document, added["document_id"])

        assert first["ingest_action"] == "ADDED"
        assert replacement["ingest_action"] == "REPLACED"
        assert current.supersedes_document_id == old.id
        assert current.evidence_version_number == 2
        assert old.archived_at is not None
        assert added["ingest_action"] == "ADDED"
        assert new_doc.supersedes_document_id is None

        active = list(db.scalars(select(Document).where(Document.archived_at.is_(None))).all())
        assert {row.file_name for row in active} == {"SPJ-001.pdf", "SPJ-002.pdf"}


def test_summary_reports_added_and_replaced_counts():
    summary = main._summary([
        {"status": "SUCCESS", "ingest_action": "ADDED"},
        {"status": "SUCCESS", "ingest_action": "REPLACED"},
        {"status": "SKIPPED"},
        {"status": "ERROR"},
    ])

    assert summary == {"success": 2, "added": 1, "replaced": 1, "skipped": 1, "error": 1}
