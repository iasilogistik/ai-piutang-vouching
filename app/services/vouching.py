from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import re
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult

STORAGE_ROOT = Path("storage/uploads")
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _norm_key(value: str | None) -> str | None:
    value = _norm(value)
    if not value:
        return None
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def _parse_amount(value: str | None) -> Decimal | None:
    if not value:
        return None
    raw = re.sub(r"[^0-9,.-]", "", value)
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", raw):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    elif "." in raw:
        if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", raw):
            raw = raw.replace(".", "")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except Exception:
        return None


_INDONESIAN_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = _norm(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw, re.IGNORECASE)
    if match:
        month = _INDONESIAN_MONTHS.get(match.group(2).lower())
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


def save_document(db: Session, upload: UploadFile, *, document_type: str, uploaded_by: str | None = None) -> Document:
    filename = Path(upload.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise ValueError("Physical document must be PDF, JPG, JPEG, or PNG")
    content = upload.file.read()
    if not content:
        raise ValueError("Uploaded document is empty")
    digest = hashlib.sha256(content).hexdigest()
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    target = STORAGE_ROOT / f"{digest}{suffix}"
    target.write_bytes(content)
    doc = Document(file_name=filename, file_type=suffix[1:].upper(), document_type=document_type,
                   file_hash=digest, storage_path=str(target), uploaded_by=uploaded_by)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    if document_type == "BILLING":
        db.add(PhysicalBilling(document_id=doc.id))
    else:
        db.add(SPJ(document_id=doc.id))
    db.commit()
    db.refresh(doc)
    return doc


def validate_sap_batch(db: Session, batch_id: int) -> dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise ValueError("SAP import batch not found")
    rows = db.scalars(select(SAPBilling).where(SAPBilling.import_batch_id == batch_id)).all()
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not _norm(row.billing_document):
            problems.append(f"SAP row {row.id}: Billing Document is required")
        key = _norm_key(row.billing_document)
        if key in seen:
            problems.append(f"duplicate Billing Document: {row.billing_document}")
        if key:
            seen.add(key)
        if row.doc_date is None:
            problems.append(f"SAP row {row.id}: Doc. Date is required")
        if row.nominal is None:
            problems.append(f"SAP row {row.id}: Nominal is required")
    return {"batch_id": batch_id, "total_records": len(rows), "valid": not problems, "problems": problems}


def _ocr_pdf_scan(path: str) -> tuple[str, str]:
    try:
        import fitz
        from PIL import Image
        import pytesseract
        import io

        pdf = fitz.open(path)
        pages: list[str] = []
        try:
            for page in pdf:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                pages.append(pytesseract.image_to_string(image, lang="eng"))
        finally:
            pdf.close()
        text = "\n".join(pages).strip()
        return text, "TESSERACT_PDF" if text else "REVIEW_REQUIRED"
    except Exception:
        return "", "REVIEW_REQUIRED"


def extract_text(path: str) -> tuple[str, str]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if text:
                return text, "PDF_TEXT"
        except Exception:
            pass
        return _ocr_pdf_scan(path)
    try:
        from PIL import Image
        import pytesseract
        text = pytesseract.image_to_string(Image.open(path), lang="eng")
        return text, "TESSERACT"
    except Exception:
        return "", "REVIEW_REQUIRED"


def parse_document_fields(text: str) -> dict[str, Any]:
    def grab(patterns: list[str], group: int = 1) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return _norm(match.group(group))
        return None

    billing = grab([
        r"Billing\s*(?:Document|No\.?)\s*[:#-]?\s*([A-Z0-9./-]+)",
        r"No\.?\s*Billing\s*[:#-]?\s*([A-Z0-9./-]+)",
    ])
    no_spj = grab([r"No\.?\s*SPJ\s*[:#-]?\s*([A-Z0-9./-]+)"])
    date_raw = grab([r"(?:Doc\.?\s*Date|Tanggal)\s*[:#-]?\s*([0-9A-Za-z./-]+(?:\s+[A-Za-z]+\s+\d{4})?)"])
    nominal_raw = grab([
        r"(?:Grand\s*Total|Total\s*Bayar|Total|Nominal|Amount)\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9.,-]+)",
    ])
    return {"billing_document_raw": billing, "billing_document": _norm_key(billing),
            "no_spj_raw": no_spj, "no_spj": _norm_key(no_spj),
            "doc_date": _parse_date(date_raw), "nominal": _parse_amount(nominal_raw)}


def ocr_document(db: Session, document_id: int) -> dict[str, Any]:
    doc = db.get(Document, document_id)
    if not doc:
        raise ValueError("Document not found")
    text, engine = extract_text(doc.storage_path)
    fields = parse_document_fields(text)
    confidence = Decimal("0.5000") if engine.startswith("TESSERACT") else (Decimal("0.9000") if text else Decimal("0.0000"))
    if doc.document_type == "BILLING":
        row = db.scalar(select(PhysicalBilling).where(PhysicalBilling.document_id == doc.id))
        if not row:
            raise ValueError("Physical Billing record not found")
        for key in ("billing_document_raw", "no_spj_raw", "doc_date", "nominal"):
            setattr(row, key, fields.get(key))
        row.billing_document = fields.get("billing_document")
        row.no_spj = fields.get("no_spj")
        row.ocr_confidence = confidence
        result = {"document_id": doc.id, "document_type": doc.document_type, "engine": engine, "fields": fields, "confidence": str(confidence)}
    else:
        row = db.scalar(select(SPJ).where(SPJ.document_id == doc.id))
        if not row:
            raise ValueError("SPJ record not found")
        row.no_spj_raw = fields.get("no_spj_raw")
        row.no_spj = fields.get("no_spj")
        row.ocr_confidence = confidence
        result = {"document_id": doc.id, "document_type": doc.document_type, "engine": engine,
                  "fields": {"no_spj_raw": fields.get("no_spj_raw"), "no_spj": fields.get("no_spj")}, "confidence": str(confidence)}
    db.commit()
    return result


def reconcile_batch(db: Session, batch_id: int) -> list[BillingReconciliation]:
    validation = validate_sap_batch(db, batch_id)
    if not validation["valid"]:
        raise ValueError("SAP batch validation failed: " + "; ".join(validation["problems"]))
    sap_rows = db.scalars(select(SAPBilling).where(SAPBilling.import_batch_id == batch_id)).all()
    results: list[BillingReconciliation] = []
    for sap in sap_rows:
        candidates = db.scalars(select(PhysicalBilling).where(PhysicalBilling.billing_document == _norm_key(sap.billing_document))).all()
        existing = db.scalar(select(BillingReconciliation).where(BillingReconciliation.sap_billing_id == sap.id))
        if existing:
            db.delete(existing)
            db.flush()
        if len(candidates) == 0:
            rec = BillingReconciliation(sap_billing_id=sap.id, physical_billing_id=None, billing_match=False,
                date_match=False, nominal_match=False, nominal_difference=sap.nominal, status="EXCEPTION",
                exception_code="BILLING_DOCUMENT_NOT_FOUND", remarks="No physical Billing document found")
        elif len(candidates) > 1:
            rec = BillingReconciliation(sap_billing_id=sap.id, physical_billing_id=None, billing_match=False,
                date_match=False, nominal_match=False, nominal_difference=Decimal("0.00"), status="EXCEPTION",
                exception_code="DUPLICATE_PHYSICAL_BILLING", remarks=f"Found {len(candidates)} physical Billing documents")
        else:
            physical = candidates[0]
            billing_match = _norm_key(physical.billing_document) == _norm_key(sap.billing_document)
            date_match = physical.doc_date == sap.doc_date if physical.doc_date else False
            difference = sap.nominal - physical.nominal if physical.nominal is not None else sap.nominal
            nominal_match = difference == Decimal("0.00") if physical.nominal is not None else False
            missing_ocr = physical.billing_document is None or physical.doc_date is None or physical.nominal is None
            status = "REVIEW" if missing_ocr else ("MATCH" if billing_match and date_match and nominal_match else "EXCEPTION")
            rec = BillingReconciliation(sap_billing_id=sap.id, physical_billing_id=physical.id,
                billing_match=billing_match, date_match=date_match, nominal_match=nominal_match,
                nominal_difference=difference, status=status,
                exception_code=None if status in {"MATCH", "REVIEW"} else "BILLING_FIELD_MISMATCH",
                remarks="OCR field incomplete; human review required" if missing_ocr else None)
        db.add(rec)
        db.flush()
        results.append(rec)
    db.commit()
    return results


def vouch_spj(db: Session) -> list[VouchingResult]:
    billings = db.scalars(select(PhysicalBilling)).all()
    results: list[VouchingResult] = []
    for billing in billings:
        old = db.scalar(select(VouchingResult).where(VouchingResult.billing_id == billing.id))
        if old:
            db.delete(old); db.flush()
        no_spj = _norm_key(billing.no_spj)
        if not no_spj:
            result = VouchingResult(billing_id=billing.id, spj_id=None, no_spj_billing=billing.no_spj,
                no_spj_document=None, spj_match=False, status="EXCEPTION", rule_code="BILLING_WITHOUT_SPJ")
        else:
            matches = db.scalars(select(SPJ).where(SPJ.no_spj == no_spj)).all()
            if not matches:
                result = VouchingResult(billing_id=billing.id, spj_id=None, no_spj_billing=billing.no_spj,
                    no_spj_document=None, spj_match=False, status="EXCEPTION", rule_code="SPJ_NOT_FOUND")
            elif len(matches) > 1:
                result = VouchingResult(billing_id=billing.id, spj_id=matches[0].id, no_spj_billing=billing.no_spj,
                    no_spj_document=matches[0].no_spj, spj_match=False, status="REVIEW", rule_code="DUPLICATE_SPJ_NUMBER")
            else:
                spj = matches[0]
                result = VouchingResult(billing_id=billing.id, spj_id=spj.id, no_spj_billing=billing.no_spj,
                    no_spj_document=spj.no_spj, spj_match=True, status="PASS")
        db.add(result); db.flush(); results.append(result)
    db.commit()
    return results


def overall_result(db: Session, billing_id: int) -> dict[str, Any]:
    billing = db.get(PhysicalBilling, billing_id)
    if not billing:
        raise ValueError("Billing not found")
    rec = db.scalar(select(BillingReconciliation).where(BillingReconciliation.physical_billing_id == billing_id))
    vouch = db.scalar(select(VouchingResult).where(VouchingResult.billing_id == billing_id))
    if rec is None:
        overall = "EXCEPTION"
    elif rec.status == "EXCEPTION":
        overall = "EXCEPTION"
    elif vouch is None or vouch.status == "EXCEPTION":
        overall = "EXCEPTION"
    elif rec.status == "REVIEW" or vouch.status == "REVIEW":
        overall = "REVIEW"
    else:
        overall = "PASS"
    return {"billing_id": billing_id, "sap_reconciliation_result": rec.status if rec else "NOT_FOUND",
            "spj_vouching_result": vouch.status if vouch else "NOT_FOUND", "overall_result": overall,
            "reconciliation_id": rec.id if rec else None, "vouching_id": vouch.id if vouch else None}
