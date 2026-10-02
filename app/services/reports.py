from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branch_access import normalize_branch
from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
from app.services.control_evidence_dashboard import build_control_evidence_dashboard
from app.services.vouching import _net_document_amount

REPORT_ROOT = Path("/tmp/ai-piutang-vouching-reports")


def _rows(db: Session, batch_id: int, *, branch: str | None = None):
    batch = db.get(ImportBatch, batch_id)
    if not batch or (branch is not None and normalize_branch(batch.branch) != normalize_branch(branch)):
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


def _spj_partial(db: Session, physical: PhysicalBilling | None):
    if not physical or not physical.no_spj:
        return None
    physical_branch = normalize_branch(physical.document.branch)
    query = select(SPJ).join(SPJ.document).where(SPJ.no_spj == physical.no_spj)
    query = query.where(Document.branch == physical_branch if physical_branch is not None else Document.branch.is_(None))
    matches = db.scalars(query).all()
    if len(matches) == 1:
        return matches[0].partial_payment
    return None


def _detail_values(db: Session, sap: SAPBilling, rec: BillingReconciliation | None, physical: PhysicalBilling | None, vouch: VouchingResult | None):
    billing_partial = physical.partial_payment if physical and physical.partial_payment is not None else 0
    spj_partial = _spj_partial(db, physical) or 0
    net_physical = _net_document_amount(physical.nominal if physical else None, billing_partial, spj_partial)
    return [
        sap.billing_document,
        sap.doc_date.isoformat(),
        float(sap.nominal),
        physical.billing_document if physical else "",
        physical.doc_date.isoformat() if physical and physical.doc_date else "",
        float(physical.nominal) if physical and physical.nominal is not None else "",
        float(billing_partial) if billing_partial else 0,
        float(spj_partial) if spj_partial else 0,
        float(net_physical) if net_physical is not None else "",
        float(rec.nominal_difference) if rec else float(sap.nominal),
        rec.status if rec else "NOT_FOUND",
        rec.exception_code if rec else "BILLING_DOCUMENT_NOT_FOUND",
        vouch.status if vouch else "NOT_FOUND",
        vouch.rule_code if vouch else "",
    ]


def _autosize(wb: Workbook) -> None:
    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 45)
            sheet.column_dimensions[column[0].column_letter].width = width


def build_report(db: Session, batch_id: int, fmt: str, *, branch: str | None = None) -> Path:
    fmt = fmt.lower()
    if fmt not in {"xlsx", "pdf"}:
        raise ValueError("format must be xlsx or pdf")
    batch, rows = _rows(db, batch_id, branch=branch)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    path = REPORT_ROOT / f"vouching_batch_{batch_id}_{stamp}.{fmt}"

    counts = {s: 0 for s in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND")}
    for _, rec, _, _ in rows:
        status = rec.status if rec else "NOT_FOUND"
        counts[status] = counts.get(status, 0) + 1

    headers = [
        "Billing Document SAP", "Doc Date SAP", "Nominal SAP", "Billing Document Fisik", "Doc Date Fisik",
        "Nominal Billing Fisik", "Partial Billing", "Partial SPJ", "Net Physical Nominal", "Difference",
        "Reconciliation", "Exception", "SPJ Result", "SPJ Rule",
    ]

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
        detail.append(headers)
        for sap, rec, physical, vouch in rows:
            detail.append(_detail_values(db, sap, rec, physical, vouch))
        _autosize(wb)
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
        data = [["Billing SAP", "Nominal SAP", "Nominal Billing", "Partial Billing", "Partial SPJ", "Net Physical", "Selisih", "Reconcile", "Exception", "SPJ"]]
        for sap, rec, physical, vouch in rows:
            values = _detail_values(db, sap, rec, physical, vouch)
            data.append([values[0], values[2], values[5], values[6], values[7], values[8], values[9], values[10], values[11], values[12]])
        detail = Table(data, repeatRows=1)
        detail.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.35, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.lightgrey), ("FONTSIZE", (0,0), (-1,-1), 7)]))
        story.append(detail)
        doc.build(story)
    return path



def _working_paper_spj(db: Session, physical: PhysicalBilling | None, vouch: VouchingResult | None) -> SPJ | None:
    if vouch is not None and vouch.spj_id is not None:
        return db.get(SPJ, vouch.spj_id)
    if not physical or not physical.no_spj:
        return None
    physical_branch = normalize_branch(physical.document.branch)
    query = select(SPJ).join(SPJ.document).where(SPJ.no_spj == physical.no_spj)
    query = query.where(
        Document.branch == physical_branch
        if physical_branch is not None
        else Document.branch.is_(None)
    )
    matches = list(db.scalars(query).all())
    return matches[0] if len(matches) == 1 else None


def _working_paper_note(
    physical: PhysicalBilling | None,
    spj: SPJ | None,
    rec: BillingReconciliation | None,
) -> str:
    if physical is None:
        return ""

    notes: list[str] = []
    if physical.partial_payment is not None:
        if physical.partial_payment_raw:
            notes.append(str(physical.partial_payment_raw))
        else:
            notes.append(f"Partial Billing {float(physical.partial_payment):,.2f}")
    if spj is not None and spj.partial_payment is not None:
        if spj.partial_payment_raw:
            notes.append(str(spj.partial_payment_raw))
        else:
            notes.append(f"Partial SPJ {float(spj.partial_payment):,.2f}")
    if rec is not None and rec.status not in {"MATCH", None}:
        notes.append(rec.status)
    return " | ".join(note for note in notes if note)



def _working_paper_net_physical(
    sap_nominal: Decimal,
    physical: PhysicalBilling | None,
    spj: SPJ | None,
) -> Decimal | None:
    """Return a defensible net physical amount for the working paper.

    Corrects obvious OCR scale loss such as 2.35 vs 2,350,000 only when a
    thousand/million rescale lands very close to SAP + explicit partial payment.
    Otherwise suspicious OCR amounts are left blank rather than reported as fact.
    """
    if physical is None or physical.nominal is None:
        return None

    gross = Decimal(str(physical.nominal))
    billing_partial = Decimal(str(physical.partial_payment or 0))
    spj_partial = Decimal(str(spj.partial_payment or 0)) if spj is not None else Decimal("0")
    partial_total = billing_partial + spj_partial
    target_gross = Decimal(str(sap_nominal)) + partial_total

    if gross <= 0:
        return None

    if target_gross > 0 and gross < (target_gross / Decimal("100")):
        candidates = [gross * Decimal("1000"), gross * Decimal("1000000")]
        best = min(candidates, key=lambda value: abs(value - target_gross))
        relative_error = abs(best - target_gross) / target_gross
        if relative_error <= Decimal("0.05"):
            gross = best
        else:
            return None

    net = gross - partial_total
    if net < 0:
        return None

    if sap_nominal and sap_nominal > 0:
        ratio = net / Decimal(str(sap_nominal)) if net > 0 else Decimal("0")
        if ratio > Decimal("20"):
            return None

    return net.quantize(Decimal("0.01"))

def build_working_paper_report(
    db: Session,
    batch_id: int,
    *,
    branch: str | None = None,
) -> Path:
    """Build an audit working-paper workbook without changing the existing report.

    SAP is the population/base table. Rows are sorted alphabetically by customer
    name. If physical evidence is unavailable, the physical-document, difference,
    day and remarks cells remain blank.
    """

    batch, rows = _rows(db, batch_id, branch=branch)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    path = REPORT_ROOT / f"kertas_kerja_batch_{batch_id}_{stamp}.xlsx"

    sorted_rows = sorted(
        rows,
        key=lambda item: (
            (item[0].customer_account_name or item[0].customer or "").casefold(),
            (item[0].customer or "").casefold(),
            item[0].doc_date or date.min,
            item[0].billing_document or "",
            item[0].id,
        ),
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Kertas Kerja"

    # Two-level header matching the auditor working-paper layout.
    ws.merge_cells("A1:A2")
    ws.merge_cells("B1:B2")
    ws.merge_cells("C1:E1")
    ws.merge_cells("F1:H1")
    ws.merge_cells("I1:I2")
    ws.merge_cells("J1:J2")
    ws.merge_cells("K1:K2")

    ws["A1"] = "Customer"
    ws["B1"] = "Customer Account: Name"
    ws["C1"] = "Program SAP"
    ws["F1"] = "Fisik Dokumen"
    ws["I1"] = "Selisih"
    ws["J1"] = "Hari"
    ws["K1"] = "Keterangan"

    ws["C2"] = "Billing Document"
    ws["D2"] = "Doc. Date"
    ws["E2"] = "Nominal"
    ws["F2"] = "Billing Document"
    ws["G2"] = "Doc. Date"
    ws["H2"] = "Nominal"

    header_fill = PatternFill("solid", fgColor="E7E6E6")
    thin = Side(style="thin", color="7F7F7F")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_font = Font(name="Arial", size=10, bold=True)
    body_font = Font(name="Arial", size=10)

    for row in ws.iter_rows(min_row=1, max_row=2, min_col=1, max_col=11):
        for cell in row:
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 22
    ws.freeze_panes = "A3"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    widths = {
        "A": 15,
        "B": 31,
        "C": 22,
        "D": 14,
        "E": 16,
        "F": 22,
        "G": 14,
        "H": 16,
        "I": 16,
        "J": 10,
        "K": 42,
    }
    for column, width in widths.items():
        ws.column_dimensions[column].width = width


    for sap, rec, physical, vouch in sorted_rows:
        customer_code = sap.customer or ""
        customer_name = sap.customer_account_name or sap.customer or ""
        spj = _working_paper_spj(db, physical, vouch)
        net_physical = _working_paper_net_physical(sap.nominal, physical, spj)

        row_number = ws.max_row + 1
        values = [
            customer_code,
            customer_name,
            sap.billing_document,
            sap.doc_date,
            float(sap.nominal),
            physical.billing_document if physical is not None else "",
            physical.doc_date if physical is not None and physical.doc_date else "",
            float(net_physical) if net_physical is not None else "",
            (
                float(sap.nominal - net_physical)
                if net_physical is not None
                else ""
            ),
            (
                abs((physical.doc_date - sap.doc_date).days)
                if physical is not None and physical.doc_date and sap.doc_date
                else ""
            ),
            _working_paper_note(physical, spj, rec),
        ]
        ws.append(values)

        for col in range(1, 12):
            cell = ws.cell(row_number, col)
            cell.font = body_font
            cell.border = border
            cell.alignment = Alignment(vertical="center", wrap_text=(col in {2, 11}))
        ws.cell(row_number, 4).number_format = "dd/mm/yyyy"
        ws.cell(row_number, 7).number_format = "dd/mm/yyyy"
        for col in (5, 8, 9):
            ws.cell(row_number, col).number_format = "#,##0.00"
        if ws.cell(row_number, 9).value == 0:
            ws.cell(row_number, 9).value = "-"

    # Do not add an auto-filter across merged top headers; preserve the classic
    # audit working-paper layout instead.
    wb.save(path)
    return path

def build_control_evidence_report(
    db: Session, *, review_only: bool = False, limit: int = 500, branch: str | None = None
) -> Path:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    path = REPORT_ROOT / f"spj_control_evidence_{stamp}.xlsx"
    dashboard = build_control_evidence_dashboard(db, review_only=review_only, limit=limit, branch=branch)

    wb = Workbook()
    summary_sheet = wb.active
    summary_sheet.title = "Summary"
    summary_sheet.append(["Metric", "Value"])
    summary_sheet.append(["Total SPJ Evidence", dashboard["summary"]["total_documents"]])
    summary_sheet.append(["PASS", dashboard["summary"].get("overall_control_status", {}).get("PASS", 0)])
    summary_sheet.append(["REVIEW", dashboard["summary"].get("overall_control_status", {}).get("REVIEW", 0)])
    summary_sheet.append(["EXCEPTION", dashboard["summary"].get("overall_control_status", {}).get("EXCEPTION", 0)])
    summary_sheet.append(["Review Required", dashboard["summary"]["review_required_documents"]])

    rows_sheet = wb.create_sheet("Control Evidence")
    headers = [
        "Control Evidence ID", "Document ID", "File Name", "No SPJ", "Billing ID", "SPJ Vouching Status",
        "Overall Control Status", "Review Required", "Review Status", "Reviewer", "Reviewer Remarks",
        "TTD Penerima", "TTD Driver", "TTD Satpam", "TTD BM", "TTD Checker", "Stempel", "Nama Stempel",
        "Stempel vs Customer", "Alasan Review", "Document URL",
    ]
    rows_sheet.append(headers)
    for row in dashboard["rows"]:
        rows_sheet.append([
            row.get("control_evidence_id"),
            row.get("document_id"),
            row.get("file_name"),
            row.get("no_spj"),
            row.get("billing_id"),
            row.get("spj_vouching_status"),
            row.get("overall_control_status"),
            row.get("review_required"),
            row.get("review_status"),
            row.get("reviewer_id"),
            row.get("reviewer_remarks"),
            row.get("receiver_signature_status"),
            row.get("driver_signature_status"),
            row.get("security_signature_status"),
            row.get("bm_signature_status"),
            row.get("checker_signature_status"),
            row.get("receiver_stamp_status"),
            row.get("stamp_text_raw"),
            row.get("stamp_customer_match_status"),
            "; ".join(row.get("review_reasons") or []),
            row.get("document_url"),
        ])

    queue_sheet = wb.create_sheet("Manual Review Queue")
    queue_sheet.append(headers)
    for row in dashboard["manual_review_queue"]:
        queue_sheet.append([
            row.get("control_evidence_id"), row.get("document_id"), row.get("file_name"), row.get("no_spj"),
            row.get("billing_id"), row.get("spj_vouching_status"), row.get("overall_control_status"),
            row.get("review_required"), row.get("review_status"), row.get("reviewer_id"), row.get("reviewer_remarks"),
            row.get("receiver_signature_status"), row.get("driver_signature_status"), row.get("security_signature_status"),
            row.get("bm_signature_status"), row.get("checker_signature_status"), row.get("receiver_stamp_status"),
            row.get("stamp_text_raw"), row.get("stamp_customer_match_status"), "; ".join(row.get("review_reasons") or []),
            row.get("document_url"),
        ])

    _autosize(wb)
    wb.save(path)
    return path
