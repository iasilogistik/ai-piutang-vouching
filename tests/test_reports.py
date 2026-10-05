from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ
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

        # No customer subtotal rows: next row is the next customer.
        assert ws["B5"].value == "ZETA TOKO"
        assert all("Total" not in str(ws.cell(row, 2).value or "") for row in range(3, ws.max_row + 1))



def test_working_paper_repairs_obvious_ocr_scale_loss_without_subtotal(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)

    with Session(engine) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="2119709",
            customer_account_name="SANTOSO, TOKO",
            billing_document="8501735930",
            doc_date=date(2026, 8, 24),
            nominal=Decimal("2350000.00"),
        )
        db.add(sap)
        db.flush()
        doc = Document(
            file_name="SANTOSO 8501735930.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="santoso-hash",
            storage_path="dummy.pdf",
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        physical = PhysicalBilling(
            document_id=doc.id,
            billing_document="8501735930",
            nominal=Decimal("2.35"),
        )
        db.add(physical)
        db.flush()
        db.add(BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=physical.id,
            billing_match=True,
            date_match=False,
            nominal_match=False,
            nominal_difference=Decimal("2349997.65"),
            status="EXCEPTION",
        ))
        db.commit()

        path = build_working_paper_report(db, batch.id, branch="KEDIRI")
        ws = load_workbook(path)["Kertas Kerja"]

        assert ws["A3"].value == "2119709"
        assert ws["H3"].value == 2350000
        assert ws["I3"].value == "-"
        assert ws.max_row == 3



def test_working_paper_preloads_spj_without_n_plus_one_queries(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)

    with Session(engine) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=20, status="IMPORTED")
        db.add(batch)
        db.flush()

        spj_doc = Document(
            file_name="shared-spj.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="shared-spj",
            storage_path="shared-spj.pdf",
            branch="KEDIRI",
        )
        db.add(spj_doc)
        db.flush()
        db.add(SPJ(document_id=spj_doc.id, no_spj="2501000001"))

        for index in range(20):
            sap = SAPBilling(
                import_batch_id=batch.id,
                customer=str(2100000 + index),
                customer_account_name=f"CUSTOMER {index:02d}",
                billing_document=str(8500000000 + index),
                doc_date=date(2026, 9, 1),
                nominal=Decimal("1000000.00"),
            )
            db.add(sap)
            db.flush()

            doc = Document(
                file_name=f"billing-{index}.pdf",
                file_type="PDF",
                document_type="BILLING",
                file_hash=f"billing-{index}",
                storage_path=f"billing-{index}.pdf",
                branch="KEDIRI",
            )
            db.add(doc)
            db.flush()
            physical = PhysicalBilling(
                document_id=doc.id,
                billing_document=str(8500000000 + index),
                no_spj="2501000001",
                doc_date=date(2026, 9, 1),
                nominal=Decimal("1000000.00"),
            )
            db.add(physical)
            db.flush()
            db.add(BillingReconciliation(
                sap_billing_id=sap.id,
                physical_billing_id=physical.id,
                billing_match=True,
                date_match=True,
                nominal_match=True,
                nominal_difference=Decimal("0.00"),
                status="MATCH",
            ))
        db.commit()
        batch_id = batch.id

    statements = {"count": 0}

    def before_cursor_execute(*_args, **_kwargs):
        statements["count"] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        with Session(engine) as db:
            path = build_working_paper_report(db, batch_id, branch="KEDIRI")
            assert path.exists()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    # One batch lookup + one joined row query + one SPJ preload query.
    assert statements["count"] <= 5



def test_working_paper_subtracts_partial_payment_and_keeps_invoice_date(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    Base.metadata.create_all(engine)
    import app.services.reports as reports
    monkeypatch.setattr(reports, "REPORT_ROOT", tmp_path)

    with Session(engine) as db:
        batch = ImportBatch(file_name="sap.xlsx", branch="KEDIRI", total_records=1, status="IMPORTED")
        db.add(batch)
        db.flush()
        sap = SAPBilling(
            import_batch_id=batch.id,
            customer="2138780",
            customer_account_name="GEMILANG 86, TB",
            billing_document="8501692627",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("1637280.00"),
        )
        db.add(sap)
        db.flush()

        bill_doc = Document(
            file_name="gemilang 86.pdf",
            file_type="PDF",
            document_type="BILLING",
            file_hash="gemilang-hash",
            storage_path="gemilang.pdf",
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name="gemilang 86.pdf",
            file_type="PDF",
            document_type="SPJ",
            file_hash="gemilang-hash",
            storage_path="gemilang.pdf",
            branch="KEDIRI",
        )
        db.add_all([bill_doc, spj_doc])
        db.flush()

        physical = PhysicalBilling(
            document_id=bill_doc.id,
            billing_document="8501692627",
            doc_date=date(2026, 9, 10),
            nominal=Decimal("2637230.00"),
            partial_payment=Decimal("999950.00"),
            partial_payment_raw="DERIVED_BILLING_GROSS_MINUS_SAP_OUTSTANDING",
            no_spj="2501800001",
        )
        spj = SPJ(document_id=spj_doc.id, no_spj="2501800001")
        db.add_all([physical, spj])
        db.flush()
        db.add(BillingReconciliation(
            sap_billing_id=sap.id,
            physical_billing_id=physical.id,
            billing_match=True,
            date_match=True,
            nominal_match=True,
            nominal_difference=Decimal("0.00"),
            status="MATCH",
        ))
        db.commit()

        path = build_working_paper_report(db, batch.id, branch="KEDIRI")
        ws = load_workbook(path)["Kertas Kerja"]

        assert ws["G3"].value.date() == date(2026, 9, 10)
        assert ws["H3"].value == 1637280
        assert ws["I3"].value == "-"
        assert "DERIVED_BILLING_GROSS_MINUS_SAP_OUTSTANDING" in (ws["K3"].value or "")
