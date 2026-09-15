from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ
from app.services.vouching import reconcile_batch, vouch_spj


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_duplicate_physical_billing_is_exception():
    with Session(_db()) as db:
        batch = ImportBatch(file_name="dup.xlsx", total_records=1, status="IMPORTED")
        db.add(batch); db.flush()
        db.add(SAPBilling(import_batch_id=batch.id, billing_document="B-200", doc_date=date(2026, 9, 1), nominal=Decimal("10.00")))
        d1 = Document(file_name="1.pdf", file_type="PDF", document_type="BILLING", file_hash="dup-1", storage_path="x1")
        d2 = Document(file_name="2.pdf", file_type="PDF", document_type="BILLING", file_hash="dup-2", storage_path="x2")
        db.add_all([d1, d2]); db.flush()
        db.add_all([PhysicalBilling(document_id=d1.id, billing_document="B200"), PhysicalBilling(document_id=d2.id, billing_document="B200")])
        db.commit()
        result = reconcile_batch(db, batch.id)[0]
        assert result.status == "EXCEPTION"
        assert result.exception_code == "DUPLICATE_PHYSICAL_BILLING"


def test_duplicate_spj_number_requires_review():
    with Session(_db()) as db:
        d1 = Document(file_name="b.pdf", file_type="PDF", document_type="BILLING", file_hash="spj-b", storage_path="b")
        s1 = Document(file_name="s1.pdf", file_type="PDF", document_type="SPJ", file_hash="spj-1", storage_path="s1")
        s2 = Document(file_name="s2.pdf", file_type="PDF", document_type="SPJ", file_hash="spj-2", storage_path="s2")
        db.add_all([d1, s1, s2]); db.flush()
        db.add(PhysicalBilling(document_id=d1.id, billing_document="B300", no_spj="SPJ300"))
        db.add_all([SPJ(document_id=s1.id, no_spj="SPJ300"), SPJ(document_id=s2.id, no_spj="SPJ300")])
        db.commit()
        result = vouch_spj(db)[0]
        assert result.status == "REVIEW"
        assert result.rule_code == "DUPLICATE_SPJ_NUMBER"
