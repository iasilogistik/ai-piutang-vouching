from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.audit_service import list_audit_trail, record_audit


def test_record_and_list_audit_trail() -> None:
    engine = create_engine("sqlite:///:memory:")
    AuditTrail.metadata.create_all(engine)
    with Session(engine) as db:
        row = record_audit(
            db,
            entity_type="VOUCHING_RESULT",
            entity_id=10,
            action="REVIEW",
            actor="auditor-1",
            status_from="REVIEW",
            status_to="PASS",
            remarks="Reviewed evidence",
            metadata={"source": "manual"},
        )
        db.commit()
        assert row.id is not None
        entries = list_audit_trail(db, entity_type="VOUCHING_RESULT", entity_id=10)
        assert len(entries) == 1
        assert entries[0].actor == "auditor-1"
        assert entries[0].status_from == "REVIEW"
        assert entries[0].status_to == "PASS"
        assert entries[0].metadata_json == {"source": "manual"}


def test_audit_trail_is_append_only_by_service() -> None:
    engine = create_engine("sqlite:///:memory:")
    AuditTrail.metadata.create_all(engine)
    with Session(engine) as db:
        record_audit(db, entity_type="DOCUMENT", entity_id=1, action="UPLOAD", actor="user-1")
        record_audit(db, entity_type="DOCUMENT", entity_id=1, action="OCR", actor="system")
        db.commit()
        entries = list(db.scalars(select(AuditTrail).order_by(AuditTrail.id)).all())
        assert [entry.action for entry in entries] == ["UPLOAD", "OCR"]
