from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling
from app.services.reports import build_report, build_working_paper_report


def test_build_xlsx_report(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)
    with Session(engine) as db:
        batch = ImportBatch(file_name="sap.xlsx", period=date(2026, 9, 1), total_records=1, status="IMPORTED")
        db.add(batch); db.flush()
        sap = SAPBilling(import_batch_id=batch.id, billing_document="B-001", doc_date=date(2026, 9, 1), nominal=Decimal("100.00"))
        db.add(sap); db.flush()
        db.add(BillingReconciliation(sap_billing_id=sap.id, billing_match=False, date_match=False, nominal_match=False,
                                     nominal_difference=Decimal("100.00"), status="EXCEPTION", exception_code="BILLING_DOCUMENT_NOT_FOUND"))
        db.commit()
        path = build_report(db, batch.id, "xlsx")
        assert path.exists()
        wb = load_workbook(path)
        assert "Summary" in wb.sheetnames
        assert "Reconciliation" in wb.sheetnames
        assert wb["Summary"]["A4"].value == "Total SAP records"


def test_build_pdf_report(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)
    with Session(engine) as db:
        batch = ImportBatch(file_name="sap.xlsx", total_records=0, status="IMPORTED")
        db.add(batch); db.commit()
        path = build_report(db, batch.id, "pdf")
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.stat().st_size > 0



def test_build_working_paper_sorted_grouped_and_blank_when_no_evidence(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)

    with Session(engine) as db:
        batch = ImportBatch(
            file_name="sap.xlsx",
            branch="KEDIRI",
            period=date(2026, 9, 1),
            total_records=3,
            status="IMPORTED",
        )
        db.add(batch)
        db.flush()

        # Insert Z customer first to prove export is alphabetically sorted.
        zeta = SAPBilling(
            import_batch_id=batch.id,
            customer="200",
            customer_account_name="ZETA TOKO",
            billing_document="8500000003",
            doc_date=date(2026, 9, 3),
            nominal=Decimal("3000.00"),
        )
        abadi_1 = SAPBilling(
            import_batch_id=batch.id,
            customer="100",
            customer_account_name="ABADI JAYA, TOKO",
            billing_document="8500000001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("1000.00"),
        )
        abadi_2 = SAPBilling(
            import_batch_id=batch.id,
            customer="100",
            customer_account_name="ABADI JAYA, TOKO",
            billing_document="8500000002",
            doc_date=date(2026, 9, 2),
            nominal=Decimal("2000.00"),
        )
        db.add_all([zeta, abadi_1, abadi_2])
        db.flush()

        doc = Document(
            file_name="ABADI 8500000001.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="hash-abadi",
            storage_path="dummy.pdf",
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        physical = PhysicalBilling(
            document_id=doc.id,
            billing_document="8500000001",
            doc_date=date(2026, 9, 1),
            nominal=Decimal("1000.00"),
        )
        db.add(physical)
        db.flush()

        db.add_all([
            BillingReconciliation(
                sap_billing_id=abadi_1.id,
                physical_billing_id=physical.id,
                billing_match=True,
                date_match=True,
                nominal_match=True,
                nominal_difference=Decimal("0.00"),
                status="MATCH",
            ),
            BillingReconciliation(
                sap_billing_id=abadi_2.id,
                billing_match=False,
                date_match=False,
                nominal_match=False,
                nominal_difference=Decimal("2000.00"),
                status="NOT_FOUND",
                exception_code="BILLING_DOCUMENT_NOT_FOUND",
            ),
            BillingReconciliation(
                sap_billing_id=zeta.id,
                billing_match=False,
                date_match=False,
                nominal_match=False,
                nominal_difference=Decimal("3000.00"),
                status="NOT_FOUND",
                exception_code="BILLING_DOCUMENT_NOT_FOUND",
            ),
        ])
        db.commit()

        path = build_working_paper_report(db, batch.id, branch="KEDIRI")
        wb = load_workbook(path)
        ws = wb["Kertas Kerja"]

        assert ws["A1"].value == "Customer"
        assert ws["C1"].value == "Program SAP"
        assert ws["F1"].value == "Fisik Dokumen"
        assert "C1:E1" in {str(item) for item in ws.merged_cells.ranges}
        assert "F1:H1" in {str(item) for item in ws.merged_cells.ranges}

        # ABADI must appear before ZETA even though ZETA was inserted first.
        assert ws["B3"].value == "ABADI JAYA, TOKO"
        assert ws["C3"].value == "8500000001"
        assert ws["F3"].value == "8500000001"
        assert ws["I3"].value == "-"

        # Second ABADI row has no evidence: all physical/result cells stay blank.
        assert ws["B4"].value == "ABADI JAYA, TOKO"
        assert ws["F4"].value in ("", None)
        assert ws["G4"].value in ("", None)
        assert ws["H4"].value in ("", None)
        assert ws["I4"].value in ("", None)
        assert ws["J4"].value in ("", None)
        assert ws["K4"].value in ("", None)

        # Customer subtotal follows the grouped customer rows.
        assert ws["B5"].value == "ABADI JAYA, TOKO Total"
        assert ws["E5"].value == 3000
        assert ws["B6"].value == "ZETA TOKO"
