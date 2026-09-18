from io import BytesIO
from decimal import Decimal

import pandas as pd
import pytest

from app.database import SessionLocal
from app.models import ImportBatch, SAPBilling
from app.services.sap_import import import_sap_excel


def excel_bytes(rows: list[dict[str, object]]) -> bytes:
    frame = pd.DataFrame(rows)
    output = BytesIO()
    frame.to_excel(output, index=False, engine="openpyxl")
    return output.getvalue()


def cleanup(db, batch_id: int) -> None:
    db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch_id).delete()
    db.query(ImportBatch).filter(ImportBatch.id == batch_id).delete()
    db.commit()


def test_import_sap_excel_persists_batch_and_rows() -> None:
    content = excel_bytes(
        [
            {
                "Customer": "C001",
                "Customer Account: Name": "PT Contoh",
                "Billing Document": "900001",
                "Doc. Date": "2026-09-01",
                "Nominal": "1500000.50",
            },
            {
                "Customer": "C002",
                "Customer Account: Name": "CV Sample",
                "Billing Document": "900002",
                "Doc. Date": "2026-09-02",
                "Nominal": 2500000,
            },
        ]
    )
    db = SessionLocal()
    batch = None
    try:
        batch = import_sap_excel(db, filename="program_sap.xlsx", content=content, uploaded_by="tester")
        rows = db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch.id).order_by(SAPBilling.id).all()
        assert batch.status == "IMPORTED"
        assert batch.total_records == 2
        assert [row.billing_document for row in rows] == ["900001", "900002"]
        assert rows[0].nominal == Decimal("1500000.50")
    finally:
        if batch is not None:
            cleanup(db, batch.id)
        db.close()


def test_import_sap_excel_rejects_missing_required_column() -> None:
    content = excel_bytes(
        [
            {
                "Customer": "C001",
                "Billing Document": "900001",
                "Doc. Date": "2026-09-01",
            }
        ]
    )
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="Missing required columns"):
            import_sap_excel(db, filename="program_sap.xlsx", content=content)
        assert db.query(ImportBatch).count() == 0
    finally:
        db.close()


def test_import_sap_excel_rejects_duplicate_billing_document() -> None:
    content = excel_bytes(
        [
            {
                "Customer": "C001",
                "Customer Account: Name": "PT Contoh",
                "Billing Document": "900001",
                "Doc. Date": "2026-09-01",
                "Nominal": 100,
            },
            {
                "Customer": "C001",
                "Customer Account: Name": "PT Contoh",
                "Billing Document": "900001",
                "Doc. Date": "2026-09-02",
                "Nominal": 200,
            },
        ]
    )
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="duplicate Billing Document"):
            import_sap_excel(db, filename="program_sap.xlsx", content=content)
        assert db.query(ImportBatch).count() == 0
    finally:
        db.close()


def test_import_sap_ledger_uses_text_when_billing_is_empty_and_drops_blank_keys() -> None:
    content = excel_bytes(
        [
            {
                "Billing Document": None,
                "Text": "TEXT-001",
                "Document Date": "2026-09-01",
                "Company Code Currency Value": 1500000,
                "Customer Account: Name 1": "PT Text Fallback",
            },
            {
                "Billing Document": None,
                "Text": None,
                "Document Date": "2026-09-02",
                "Company Code Currency Value": 999999,
                "Customer Account: Name 1": "DROP ME",
            },
        ]
    )
    db = SessionLocal()
    batch = None
    try:
        batch = import_sap_excel(db, filename="sap_ledger.xlsx", content=content)
        rows = db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch.id).all()
        assert batch.total_records == 1
        assert len(rows) == 1
        assert rows[0].billing_document == "TEXT-001"
        assert rows[0].nominal == Decimal("1500000.00")
    finally:
        if batch is not None:
            cleanup(db, batch.id)
        db.close()


def test_import_sap_ledger_aggregates_duplicate_effective_key() -> None:
    content = excel_bytes(
        [
            {
                "Billing Document": "8500000001",
                "Text": None,
                "Document Date": "2026-09-01",
                "Company Code Currency Value": 2000000,
                "Customer Account: Name 1": "PT Aggregate",
            },
            {
                "Billing Document": "8500000001",
                "Text": None,
                "Document Date": "2026-09-03",
                "Company Code Currency Value": -500000,
                "Customer Account: Name 1": "PT Aggregate",
            },
        ]
    )
    db = SessionLocal()
    batch = None
    try:
        batch = import_sap_excel(db, filename="sap_ledger.xlsx", content=content)
        rows = db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch.id).all()
        assert batch.total_records == 1
        assert rows[0].billing_document == "8500000001"
        assert rows[0].nominal == Decimal("1500000.00")
        assert rows[0].doc_date.isoformat() == "2026-09-03"
    finally:
        if batch is not None:
            cleanup(db, batch.id)
        db.close()
