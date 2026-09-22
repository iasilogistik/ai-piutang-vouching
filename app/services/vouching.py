from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import re
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branch_access import branch_for_actor, normalize_branch
from app.config import settings
from app.models import BillingReconciliation, Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
from app.services.storage import materialize, upload_bytes

STORAGE_ROOT = Path("storage/uploads")
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
VALID_VOUCHING_REVIEW_STATUSES = {"PASS", "REVIEW", "EXCEPTION"}
VOUCHING_REVIEW_REASON_CODES = {
    "EVIDENCE_CONFIRMED",
    "EVIDENCE_MISSING",
    "STAMP_CUSTOMER_MISMATCH",
    "SIGNATURE_MISSING",
    "OCR_OR_SCAN_UNCLEAR",
    "DUPLICATE_SPJ",
    "OTHER",
}



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
    """Parse OCR amount text into Decimal.

    Pasuruan scan evidence produced OCR tokens such as ``2:350 000`` and
    ``2.637280``. Those are Indonesian thousand separators corrupted by OCR,
    not decimal values. This parser removes whitespace, treats colon as a
    separator, and only treats the last separator as decimal when it is clearly
    followed by exactly two decimal digits and the whole token is not a standard
    thousand-grouped value.
    """
    if not value:
        return None
    raw = re.sub(r"\s+", "", value)
    raw = raw.replace(":", ".")
    raw = re.sub(r"[^0-9,.-]", "", raw)
    if not raw:
        return None

    negative = raw.startswith("-")
    if negative:
        raw = raw[1:]
    if not raw:
        return None

    if "," in raw or "." in raw:
        separators = [idx for idx, char in enumerate(raw) if char in {",", "."}]
        last_sep = separators[-1]
        fraction = raw[last_sep + 1:]
        integer_part = raw[:last_sep]
        thousand_grouped = re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", raw) is not None
        if len(fraction) == 2 and not thousand_grouped:
            raw = re.sub(r"[,.]", "", integer_part) + "." + fraction
        else:
            raw = re.sub(r"[,.]", "", raw)

    if negative:
        raw = "-" + raw
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


def _extract_partial_payments(text: str) -> tuple[Decimal | None, str | None]:
    patterns = [
        r"(?:Pembayaran\s+(?:Partial|Parsial)|(?:Partial|Parsial)\s+Payment|Bayar\s+(?:Partial|Parsial)|Partial)\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
    ]
    amounts: list[Decimal] = []
    raw_matches: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            amount = _parse_amount(match.group(1))
            if amount is not None:
                amounts.append(amount)
                raw_matches.append(_norm(match.group(0)) or match.group(0))
    if not amounts:
        return None, None
    return sum(amounts, Decimal("0.00")).quantize(Decimal("0.01")), "; ".join(raw_matches)


def _net_document_amount(nominal: Decimal | int | float | None, billing_partial: Decimal | int | float | None = None,
                         spj_partial: Decimal | int | float | None = None) -> Decimal | None:
    if nominal is None:
        return None
    nominal = Decimal(str(nominal))
    return (nominal - Decimal(str(billing_partial or 0)) - Decimal(str(spj_partial or 0))).quantize(Decimal("0.01"))


def save_document(
    db: Session,
    upload: UploadFile,
    *,
    document_type: str,
    uploaded_by: str | None = None,
    branch: str | None = None,
) -> Document:
    filename = Path(upload.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise ValueError("Physical document must be PDF, JPG, JPEG, or PNG")
    content = upload.file.read()
    if not content:
        raise ValueError("Uploaded document is empty")
    digest = hashlib.sha256(content).hexdigest()
    if settings.use_supabase_storage:
        storage_path = f"{document_type}/{digest}{suffix}"
        content_type = upload.content_type or ("application/pdf" if suffix == ".pdf" else "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png")
        upload_bytes(storage_path, content, content_type)
    else:
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        target = STORAGE_ROOT / f"{digest}{suffix}"
        target.write_bytes(content)
        storage_path = str(target)
    doc = Document(file_name=filename, file_type=suffix[1:].upper(), document_type=document_type,
                   file_hash=digest, storage_path=storage_path, uploaded_by=uploaded_by,
                   branch=normalize_branch(branch) or branch_for_actor(db, uploaded_by))
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


def validate_sap_batch(db: Session, batch_id: int, *, branch: str | None = None) -> dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if not batch or (branch is not None and normalize_branch(batch.branch) != normalize_branch(branch)):
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
        r"Nomor\s+Faktur\s*[:#-]?\s*([0-9]+)",
    ])

    no_spj = grab([
        r"No\.?\s*SPJ\s*[:#-]?\s*([A-Z0-9./-]+)",
        r"Nomor\s+SPJ\s*[:#-]?\s*([A-Z0-9./-]+)",
    ])
    if no_spj and no_spj.upper().startswith("SPJ/"):
        no_spj = no_spj.rstrip(".").split("/")[-1]

    if not no_spj:
        spj_header = grab([r"\b(SPJ/[A-Z0-9./-]+)"])
        if spj_header:
            no_spj = spj_header.rstrip(".").split("/")[-1]

    date_raw = grab([
        r"(?:Doc\.?\s*Date|Tanggal\s+Faktur)\s*[:#-]?\s*([0-9A-Za-z./-]+(?:\s+[A-Za-z]+\s+\d{4})?)",
        r"(?:Tanggal)\s*[:#-]?\s*([0-9A-Za-z./-]+(?:\s+[A-Za-z]+\s+\d{4})?)",
    ])

    nominal_raw = grab([
        r"Grand\s*Total\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
        r"Total\s*Bayar\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
        r"(?:^|\n)\s*Total\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
        r"Nominal\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
    ])
    partial_payment, partial_payment_raw = _extract_partial_payments(text)
    return {
        "billing_document_raw": billing,
        "billing_document": _norm_key(billing),
        "no_spj_raw": no_spj,
        "no_spj": _norm_key(no_spj),
        "doc_date": _parse_date(date_raw),
        "nominal": _parse_amount(nominal_raw),
        "partial_payment_raw": partial_payment_raw,
        "partial_payment": partial_payment,
    }


def ocr_document(db: Session, document_id: int) -> dict[str, Any]:
    doc = db.get(Document, document_id)
    if not doc:
        raise ValueError("Document not found")
    ocr_path = doc.storage_path
    temporary_path: str | None = None
    if settings.use_supabase_storage:
        temporary_path = materialize(doc.storage_path, Path(doc.file_name).suffix.lower())
        ocr_path = temporary_path
    try:
        text, engine = extract_text(ocr_path)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    fields = parse_document_fields(text)
    confidence = Decimal("0.5000") if engine.startswith("TESSERACT") else (Decimal("0.9000") if text else Decimal("0.0000"))
    if doc.document_type == "BILLING":
        row = db.scalar(select(PhysicalBilling).where(PhysicalBilling.document_id == doc.id))
        if not row:
            raise ValueError("Physical Billing record not found")
        for key in ("billing_document_raw", "no_spj_raw", "doc_date", "nominal", "partial_payment_raw", "partial_payment"):
            setattr(row, key, fields.get(key))
        row.billing_document = fields.get("billing_document")
        row.no_spj = fields.get("no_spj")
        row.ocr_confidence = confidence
        result_fields = fields
    else:
        row = db.scalar(select(SPJ).where(SPJ.document_id == doc.id))
        if not row:
            raise ValueError("SPJ record not found")
        row.no_spj_raw = fields.get("no_spj_raw")
        row.no_spj = fields.get("no_spj")
        row.partial_payment_raw = fields.get("partial_payment_raw")
        row.partial_payment = fields.get("partial_payment")
        row.ocr_confidence = confidence
        result_fields = {"no_spj_raw": fields.get("no_spj_raw"), "no_spj": fields.get("no_spj"),
                         "partial_payment_raw": fields.get("partial_payment_raw"), "partial_payment": fields.get("partial_payment")}
    db.commit()
    return {"document_id": doc.id, "document_type": doc.document_type, "engine": engine,
            "fields": result_fields, "confidence": str(confidence)}


def reconcile_batch(db: Session, batch_id: int, *, branch: str | None = None) -> list[BillingReconciliation]:
    validation = validate_sap_batch(db, batch_id, branch=branch)
    if not validation["valid"]:
        raise ValueError("SAP batch validation failed: " + "; ".join(validation["problems"]))
    batch = db.get(ImportBatch, batch_id)
    batch_branch = normalize_branch(batch.branch if batch else None)
    sap_rows = db.scalars(select(SAPBilling).where(SAPBilling.import_batch_id == batch_id)).all()
    results: list[BillingReconciliation] = []
    for sap in sap_rows:
        candidate_query = select(PhysicalBilling).join(PhysicalBilling.document).where(
            PhysicalBilling.billing_document == _norm_key(sap.billing_document)
        )
        candidate_query = candidate_query.where(
            Document.branch == batch_branch if batch_branch is not None else Document.branch.is_(None)
        )
        candidates = db.scalars(candidate_query).all()
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
            spj_partial = Decimal("0.00")
            partial_note: str | None = None
            if physical.no_spj:
                spj_query = select(SPJ).join(SPJ.document).where(SPJ.no_spj == _norm_key(physical.no_spj))
                spj_query = spj_query.where(
                    Document.branch == batch_branch if batch_branch is not None else Document.branch.is_(None)
                )
                spj_matches = db.scalars(spj_query).all()
                if len(spj_matches) == 1 and spj_matches[0].partial_payment is not None:
                    spj_partial = spj_matches[0].partial_payment
            billing_partial = physical.partial_payment or Decimal("0.00")
            net_nominal = _net_document_amount(physical.nominal, billing_partial, spj_partial)
            difference = sap.nominal - net_nominal if net_nominal is not None else sap.nominal
            nominal_match = difference == Decimal("0.00") if net_nominal is not None else False
            missing_ocr = physical.billing_document is None or physical.doc_date is None or physical.nominal is None
            status = "REVIEW" if missing_ocr else ("MATCH" if billing_match and date_match and nominal_match else "EXCEPTION")
            remarks_parts = []
            if billing_partial:
                remarks_parts.append(f"Billing partial payment deducted: {billing_partial}")
            if spj_partial:
                remarks_parts.append(f"SPJ partial payment deducted: {spj_partial}")
            if missing_ocr:
                remarks_parts.append("OCR field incomplete; human review required")
            rec = BillingReconciliation(sap_billing_id=sap.id, physical_billing_id=physical.id,
                billing_match=billing_match, date_match=date_match, nominal_match=nominal_match,
                nominal_difference=difference, status=status,
                exception_code=None if status in {"MATCH", "REVIEW"} else "BILLING_FIELD_MISMATCH",
                remarks="; ".join(remarks_parts) or partial_note)
        db.add(rec)
        db.flush()
        results.append(rec)
    db.commit()
    return results


def _expected_customer_for_billing(db: Session, billing_id: int) -> str | None:
    rec = db.scalar(
        select(BillingReconciliation)
        .where(BillingReconciliation.physical_billing_id == billing_id)
        .order_by(BillingReconciliation.id.desc())
    )
    if rec is None:
        return None
    sap = db.get(SAPBilling, rec.sap_billing_id)
    if sap is None:
        return None
    return _norm(sap.customer_account_name) or _norm(sap.customer)


def _control_evidence_for_spj(db: Session, spj: SPJ | None) -> DocumentControlEvidence | None:
    if spj is None:
        return None
    return db.scalar(
        select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == spj.document_id)
    )


def _upsert_vouching_result(
    db: Session,
    *,
    billing: PhysicalBilling,
    spj: SPJ | None,
    spj_match: bool,
    automated_status: str,
    automated_rule_code: str | None,
    automated_remarks: str | None = None,
    control_evidence: DocumentControlEvidence | None = None,
) -> VouchingResult:
    result = db.scalar(select(VouchingResult).where(VouchingResult.billing_id == billing.id))
    if result is None:
        result = VouchingResult(
            billing_id=billing.id,
            spj_id=spj.id if spj else None,
            no_spj_billing=billing.no_spj,
            no_spj_document=spj.no_spj if spj else None,
            spj_match=spj_match,
            status=automated_status,
        )
        db.add(result)

    result.spj_id = spj.id if spj else None
    result.no_spj_billing = billing.no_spj
    result.no_spj_document = spj.no_spj if spj else None
    result.spj_match = spj_match
    result.automated_status = automated_status
    result.automated_rule_code = automated_rule_code
    result.automated_remarks = automated_remarks
    result.rule_code = automated_rule_code
    result.expected_customer_name = _expected_customer_for_billing(db, billing.id)
    result.control_evidence_id = control_evidence.id if control_evidence else None

    # Keep the legacy effective fields stable for existing API consumers while
    # preserving an explicit reviewer override across automated reprocessing.
    result.status = result.manual_review_status or automated_status
    result.remarks = result.reviewer_remarks if result.manual_review_status else automated_remarks
    db.flush()
    return result


def vouch_spj(db: Session, *, branch: str | None = None) -> list[VouchingResult]:
    billing_query = select(PhysicalBilling).join(PhysicalBilling.document)
    if branch is not None:
        billing_query = billing_query.where(Document.branch == normalize_branch(branch))
    billings = db.scalars(billing_query).all()
    results: list[VouchingResult] = []
    for billing in billings:
        no_spj = _norm_key(billing.no_spj)
        if not no_spj:
            result = _upsert_vouching_result(
                db,
                billing=billing,
                spj=None,
                spj_match=False,
                automated_status="EXCEPTION",
                automated_rule_code="BILLING_WITHOUT_SPJ",
            )
        else:
            billing_branch = normalize_branch(billing.document.branch)
            match_query = select(SPJ).join(SPJ.document).where(SPJ.no_spj == no_spj)
            match_query = match_query.where(
                Document.branch == billing_branch if billing_branch is not None else Document.branch.is_(None)
            )
            matches = db.scalars(match_query).all()
            if not matches:
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=None,
                    spj_match=False,
                    automated_status="EXCEPTION",
                    automated_rule_code="SPJ_NOT_FOUND",
                )
            elif len(matches) > 1:
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=matches[0],
                    spj_match=False,
                    automated_status="REVIEW",
                    automated_rule_code="DUPLICATE_SPJ_NUMBER",
                    automated_remarks=f"Found {len(matches)} SPJ documents with the same number",
                )
            else:
                spj = matches[0]
                control_evidence = _control_evidence_for_spj(db, spj)
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=spj,
                    spj_match=True,
                    automated_status="PASS",
                    automated_rule_code=None,
                    control_evidence=control_evidence,
                )
        results.append(result)
    db.commit()
    return results


def vouching_result_payload(row: VouchingResult) -> dict[str, Any]:
    from app.services.control_evidence_store import evidence_payload

    automated_status = row.automated_status or row.status
    automated_rule_code = row.automated_rule_code if row.automated_status is not None else row.rule_code
    automated_remarks = row.automated_remarks if row.automated_status is not None else (
        row.remarks if row.manual_review_status is None else None
    )
    return {
        "id": row.id,
        "billing_id": row.billing_id,
        "spj_id": row.spj_id,
        "no_spj_billing": row.no_spj_billing,
        "no_spj_document": row.no_spj_document,
        "spj_match": row.spj_match,
        "status": row.status,
        "rule_code": row.rule_code,
        "automated_result": {
            "status": automated_status,
            "rule_code": automated_rule_code,
            "remarks": automated_remarks,
        },
        "reviewer_decision": {
            "status": row.manual_review_status,
            "reason_code": row.review_reason_code,
            "remarks": row.reviewer_remarks,
            "reviewer_id": row.reviewer_id,
            "reviewed_at": row.reviewed_at,
        },
        "linked_customer": row.expected_customer_name,
        "control_evidence_id": row.control_evidence_id,
        "control_evidence": evidence_payload(row.control_evidence) if row.control_evidence else None,
    }


def review_vouching_result(
    db: Session,
    result_id: int,
    *,
    status: str,
    reviewer_id: str,
    reason_code: str | None = None,
    remarks: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    query = (
        select(VouchingResult)
        .join(VouchingResult.billing)
        .join(PhysicalBilling.document)
        .where(VouchingResult.id == result_id)
    )
    if branch is not None:
        query = query.where(Document.branch == normalize_branch(branch))
    row = db.scalar(query)
    if row is None:
        raise ValueError("Vouching result not found")

    normalized_status = status.upper().strip()
    if normalized_status not in VALID_VOUCHING_REVIEW_STATUSES:
        raise ValueError("status must be PASS, REVIEW, or EXCEPTION")

    automated_status = row.automated_status or row.status
    normalized_reason = reason_code.upper().strip() if reason_code else None
    if normalized_reason and normalized_reason not in VOUCHING_REVIEW_REASON_CODES:
        raise ValueError(
            "reason_code must be one of: " + ", ".join(sorted(VOUCHING_REVIEW_REASON_CODES))
        )
    requires_reason = normalized_status != automated_status or normalized_status in {"REVIEW", "EXCEPTION"}
    if requires_reason and not normalized_reason:
        raise ValueError("reason_code is required for override or reject/review decisions")

    previous_status = row.status
    row.manual_review_status = normalized_status
    row.review_reason_code = normalized_reason
    row.reviewer_remarks = _norm(remarks)
    row.reviewer_id = reviewer_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.status = normalized_status
    row.remarks = row.reviewer_remarks
    db.flush()

    payload = vouching_result_payload(row)
    payload["previous_status"] = previous_status
    return payload


def overall_result(db: Session, billing_id: int, *, branch: str | None = None) -> dict[str, Any]:
    billing_query = select(PhysicalBilling).join(PhysicalBilling.document).where(PhysicalBilling.id == billing_id)
    if branch is not None:
        billing_query = billing_query.where(Document.branch == normalize_branch(branch))
    billing = db.scalar(billing_query)
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
    return {
        "billing_id": billing_id,
        "sap_reconciliation_result": rec.status if rec else "NOT_FOUND",
        "spj_vouching_result": vouch.status if vouch else "NOT_FOUND",
        "overall_result": overall,
        "reconciliation_id": rec.id if rec else None,
        "vouching_id": vouch.id if vouch else None,
        "vouching": vouching_result_payload(vouch) if vouch else None,
    }
