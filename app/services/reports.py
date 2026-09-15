from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingReconciliation, ImportBatch, PhysicalBilling, SAPBilling, VouchingResult

REPORT_ROOT = Path("storage/reports")


def _rows(db: Session, batch_id: int):
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise ValueError("SAP import batch not found")
    stmt = (
        select(SAPBilling, BillingReconciliation, PhysicalBilling, VouchingResult)
        .join(BillingReconciliation, BillingReconciliation.sap_billing_id == SAPBilling.id, isouter=True)
        .join(PhysicalBilling, PhysicalBilling.id == BillingReconciliation.physical_billing_id, isouter=True)
        .join(VouchingResult, VouchingResult.billing_id == PhysicalBilling.id, isouter=True)
        .where(SAPBilling.import_batch_id == batch_id)
        .order_by(SAPBilling.id)
    )
    return batch, db.execute(stmt).all()


def build_report(db: Session, batch_id: int, fmt: str) -> Path:
    fmt = fmt.lower()
    if fmt not in {"xlsx", "pdf"}:
        raise ValueError("format must be xlsx or pdf")
    batch, rows = _rows(db, batch_id)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    path = REPORT_ROOT / f"vouching_batch_{batch_id}_{stamp}.{fmt}"

    counts = {s: 0 for s in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND")}
    for _, rec, _, _ in rows:
        status = rec.status if rec else "NOT_FOUND"
        counts[status] = counts.get(status, 0) + 1

    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(["Batch ID", batch.id])
        ws.append(["File", batch.file_name])
        ws.append(["Period", batch.period.isoformat() if batch.period else ""])
        ws.append(["Total SAP records", len(rows)])
        for status in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND"):
            ws.append([status, counts[status]])
        detail = wb.create_sheet("Reconciliation")
        detail.append(["Billing Document SAP", "Doc Date SAP", "Nominal SAP", "Billing Document Fisik", "Doc Date Fisik", "Nominal Fisik", "Difference", "Reconciliation", "Exception", "SPJ Result", "SPJ Rule"])
        for sap, rec, physical, vouch in rows:
            detail.append([
                sap.billing_document, sap.doc_date.isoformat(), float(sap.nominal),
                physical.billing_document if physical else "", physical.doc_date.isoformat() if physical and physical.doc_date else "",
                float(physical.nominal) if physical and physical.nominal is not None else "",
                float(rec.nominal_difference) if rec else float(sap.nominal), rec.status if rec else "NOT_FOUND",
                rec.exception_code if rec else "BILLING_DOCUMENT_NOT_FOUND", vouch.status if vouch else "NOT_FOUND", vouch.rule_code if vouch else "",
            ])
        for sheet in wb.worksheets:
            sheet.freeze_panes = "A2"
            for column in sheet.columns:
                width = min(max(len(str(cell.value or "")) for cell in column) + 2, 35)
                sheet.column_dimensions[column[0].column_letter].width = width
        wb.save(path)
    else:
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
        story = [Paragraph(f"AI Piutang Vouching — Batch {batch_id}", styles["Title"]), Spacer(1, 8),
                 Paragraph(f"File: {batch.file_name} | Total SAP records: {len(rows)}", styles["Normal"]), Spacer(1, 10)]
        summary = [["MATCH", counts["MATCH"]], ["REVIEW", counts["REVIEW"]], ["EXCEPTION", counts["EXCEPTION"]], ["NOT_FOUND", counts["NOT_FOUND"]]]
        table = Table([["Status", "Count"]] + summary, colWidths=[120, 80])
        table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.lightgrey)]))
        story += [table, Spacer(1, 14)]
        data = [["Billing SAP", "Nominal SAP", "Nominal Fisik", "Selisih", "Reconcile", "Exception", "SPJ"]]
        for sap, rec, physical, vouch in rows:
            data.append([sap.billing_document, str(sap.nominal), str(physical.nominal if physical and physical.nominal is not None else ""), str(rec.nominal_difference if rec else sap.nominal), rec.status if rec else "NOT_FOUND", rec.exception_code if rec else "BILLING_DOCUMENT_NOT_FOUND", vouch.status if vouch else "NOT_FOUND"])
        detail = Table(data, repeatRows=1)
        detail.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.35, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.lightgrey), ("FONTSIZE", (0,0), (-1,-1), 7)]))
        story.append(detail)
        doc.build(story)
    return path
