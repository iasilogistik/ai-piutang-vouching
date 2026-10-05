from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import logging
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
from app.services.vision_evidence import analyze_document_vision, partial_payment_summary, vision_available

STORAGE_ROOT = Path("storage/uploads")
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
VALID_VOUCHING_REVIEW_STATUSES = {"PASS", "REVIEW", "EXCEPTION"}
MANUAL_CONFIRM_MARKER = "[MANUAL_CONFIRMED]"

logger = logging.getLogger(__name__)
_RAPID_OCR_ENGINE = None

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


def _normalize_spj_number(value: str | None) -> str | None:
    """Return only the numeric transaction number from a credible SPJ reference."""
    raw = _norm(value)
    if not raw:
        return None

    compact = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"\d{8,12}", compact):
        return compact

    official = re.search(
        r"\bSPJ\s*[/\\-]\s*[A-Z0-9]{2,10}\s*[/\\-]\s*\d{6}\s*[/\\-]\s*(\d{8,12})\b",
        raw,
        re.IGNORECASE,
    )
    if official:
        return official.group(1)

    match = re.search(r"(?<![A-Za-z0-9])(\d{8,12})(?![A-Za-z0-9])", raw)
    return match.group(1) if match else None

def _billing_document_from_filename(file_name: str | None) -> str | None:
    """Return one unambiguous standalone 10-digit Billing token from filename."""
    if not file_name:
        return None
    stem = Path(file_name).stem
    matches = list(dict.fromkeys(re.findall(r"(?<!\d)(\d{10})(?!\d)", stem)))
    return matches[0] if len(matches) == 1 else None


def _customer_match_key(value: str | None) -> str | None:
    """Normalize a customer label for conservative filename-to-SAP matching."""
    value = _norm(value)
    if not value:
        return None
    tokens = re.findall(r"[A-Za-z0-9]+", value.upper())
    while tokens and tokens[-1] in {"TB", "TK", "TOKO", "CV", "PT", "UD", "PD"}:
        tokens.pop()
    return "".join(tokens) or None


def _filename_customer_key(file_name: str | None) -> str | None:
    """Return customer text from a filename after removing evidence labels and billing tokens."""
    if not file_name:
        return None
    stem = Path(file_name).stem
    stem = re.sub(r"(?<!\d)\d{10}(?!\d)", " ", stem)
    tokens = re.findall(r"[A-Za-z0-9]+", stem.upper())
    tokens = [token for token in tokens if token not in {"BILLING", "INVOICE", "FAKTUR", "SPJ", "EVIDENCE"}]
    while tokens and tokens[-1] in {"TB", "TK", "TOKO", "CV", "PT", "UD", "PD"}:
        tokens.pop()
    return "".join(tokens) or None


def _spj_numbers_match(billing_value: str | None, spj_value: str | None) -> bool:
    left = _normalize_spj_number(billing_value)
    right = _normalize_spj_number(spj_value)
    return bool(left and right and left == right)


def _paired_spj_candidates(db: Session, billing: PhysicalBilling) -> list[SPJ]:
    """Find SPJ evidence registered from the exact same uploaded file package.

    Combined Billing+SPJ uploads create two document rows with the same hash/name/branch.
    This provides a deterministic pairing even when scan OCR cannot read the SPJ number.
    """
    doc = billing.document
    if doc is None:
        return []
    query = (
        select(SPJ)
        .join(SPJ.document)
        .where(
            Document.document_type == "SPJ",
            Document.file_hash == doc.file_hash,
            Document.file_name == doc.file_name,
            Document.archived_at.is_(None),
        )
    )
    branch = normalize_branch(doc.branch)
    query = query.where(Document.branch == branch if branch is not None else Document.branch.is_(None))
    return list(db.scalars(query).all())


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
        r"(?:Payment\s+Received|Amount\s+Paid|Paid\s+Amount|Jumlah\s+Dibayar|Pembayaran\s+(?:Diterima|Sebelumnya|Terdahulu)|Telah\s+Dibayar|Sudah\s+Dibayar)\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
        r"(?:DP|Down\s+Payment|Uang\s+Muka)\s*[:#-]?\s*(?:Rp\.?\s*)?([0-9][0-9.,:\s-]*)",
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


def _normalize_ocr_amount_scale(
    amount: Decimal | int | float | None,
    expected_nominal: Decimal | int | float | None,
    partial_payment: Decimal | int | float | None = None,
) -> Decimal | None:
    """Repair obvious OCR magnitude loss without inventing a new amount.

    Example: OCR may return 2.35 for an invoice whose SAP outstanding is
    2,350,000. Rescale only when x1,000/x1,000,000 lands within 5% of
    SAP outstanding plus an explicit partial payment.
    """
    if amount is None:
        return None
    value = Decimal(str(amount))
    if expected_nominal is None or value <= 0:
        return value.quantize(Decimal("0.01"))

    expected = Decimal(str(expected_nominal))
    partial = Decimal(str(partial_payment or 0))
    target_gross = expected + partial
    if target_gross <= 0:
        return value.quantize(Decimal("0.01"))

    if value >= (target_gross / Decimal("100")):
        return value.quantize(Decimal("0.01"))

    candidates = [value * Decimal("1000"), value * Decimal("1000000")]
    best = min(candidates, key=lambda candidate: abs(candidate - target_gross))
    if abs(best - target_gross) / target_gross <= Decimal("0.05"):
        return best.quantize(Decimal("0.01"))
    return value.quantize(Decimal("0.01"))


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
    content_type = upload.content_type or (
        "application/pdf" if suffix == ".pdf"
        else "image/jpeg" if suffix in {".jpg", ".jpeg"}
        else "image/png"
    )
    if settings.use_supabase_storage:
        storage_path = f"{document_type}/{digest}{suffix}"
        upload_bytes(storage_path, content, content_type)
    else:
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        target = STORAGE_ROOT / f"{digest}{suffix}"
        target.write_bytes(content)
        storage_path = str(target)
    doc = Document(
        file_name=filename,
        file_type=suffix[1:].upper(),
        document_type=document_type,
        file_hash=digest,
        storage_path=storage_path,
        uploaded_by=uploaded_by,
        branch=normalize_branch(branch) or branch_for_actor(db, uploaded_by),
        evidence_classification=document_type,
        evidence_source="UPLOAD",
        file_size_bytes=len(content),
        mime_type=content_type,
        evidence_version_number=1,
    )
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


def _rapidocr_image_to_string(image) -> str:
    """Keyless OCR fallback bundled with the application.

    Vercel production does not currently expose an AI Gateway credential, so
    scanned evidence must not depend on an external token to be readable.
    RapidOCR/ONNX runs locally inside the function and is only used when the
    PDF has no text layer or Tesseract is unavailable/empty.
    """
    global _RAPID_OCR_ENGINE
    try:
        import numpy as np
        from rapidocr import RapidOCR

        if _RAPID_OCR_ENGINE is None:
            _RAPID_OCR_ENGINE = RapidOCR()
        result = _RAPID_OCR_ENGINE(np.asarray(image.convert("RGB")))
        txts = getattr(result, "txts", None) or ()
        return "\n".join(str(value).strip() for value in txts if str(value).strip()).strip()
    except Exception as exc:
        logger.warning("RapidOCR failed: %s", exc)
        return ""


def _ocr_pdf_scan(path: str) -> tuple[str, str]:
    try:
        import fitz
        from PIL import Image
        import io

        pdf = fitz.open(path)
        rendered = []
        try:
            for page in list(pdf)[:3]:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                rendered.append(Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB"))
        finally:
            pdf.close()

        tesseract_pages: list[str] = []
        try:
            import pytesseract

            for image in rendered:
                tesseract_pages.append(pytesseract.image_to_string(image, lang="eng"))
            text = "\n".join(tesseract_pages).strip()
            if text:
                return text, "TESSERACT_PDF"
        except Exception as exc:
            logger.info("Tesseract unavailable/failed; using RapidOCR fallback: %s", exc)

        rapid_pages = [_rapidocr_image_to_string(image) for image in rendered]
        rapid_text = "\n".join(value for value in rapid_pages if value).strip()
        return (rapid_text, "RAPIDOCR_PDF") if rapid_text else ("", "REVIEW_REQUIRED")
    except Exception as exc:
        logger.warning("PDF OCR failed for %s: %s", path, exc)
        return "", "REVIEW_REQUIRED"


def extract_text(path: str) -> tuple[str, str]:
    """Extract embedded text cheaply; delegate scanned images to visual service.

    Production has an internal visual OCR service. Running Python Tesseract /
    RapidOCR before that service duplicated rasterization/OCR work and made the
    reconciliation flow slower. For scans, return REVIEW_REQUIRED immediately so
    ocr_document performs one visual pass only.
    """
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
        if vision_available():
            return "", "VISUAL_REQUIRED"
        return _ocr_pdf_scan(path)

    if vision_available():
        return "", "VISUAL_REQUIRED"

    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        try:
            import pytesseract

            text = pytesseract.image_to_string(image, lang="eng").strip()
            if text:
                return text, "TESSERACT"
        except Exception as exc:
            logger.info("Tesseract image OCR unavailable; using RapidOCR: %s", exc)
        rapid_text = _rapidocr_image_to_string(image)
        return (rapid_text, "RAPIDOCR") if rapid_text else ("", "REVIEW_REQUIRED")
    except Exception as exc:
        logger.warning("Image OCR failed for %s: %s", path, exc)
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

    no_spj_raw = grab([
        r"\b(SPJ\s*/\s*[A-Z0-9]+\s*/\s*\d{6}\s*/\s*\d{8,12})\b",
        r"No\.?\s*SPJ\s*[:#-]?\s*([A-Z0-9./-]+)",
        r"Nomor\s+SPJ\s*[:#-]?\s*([A-Z0-9./-]+)",
    ])
    if not no_spj_raw:
        no_spj_raw = grab([r"\b(SPJ/[A-Z0-9./-]+)"])
    no_spj = _normalize_spj_number(no_spj_raw)

    date_raw = grab([
        r"(?:Invoice\s*Date|Date\s+of\s+Invoice|Tanggal\s+Faktur(?:\s+Pajak)?|Tgl\.?\s+Faktur(?:\s+Pajak)?|Tanggal\s+Invoice|Tgl\.?\s+Invoice)\s*[:#-]?\s*([0-9A-Za-z./-]+(?:\s+[A-Za-z]+\s+\d{4})?)",
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
        "no_spj_raw": no_spj_raw,
        "no_spj": no_spj,
        "doc_date": _parse_date(date_raw),
        "nominal": _parse_amount(nominal_raw),
        "partial_payment_raw": partial_payment_raw,
        "partial_payment": partial_payment,
    }


def ocr_document(
    db: Session,
    document_id: int,
    *,
    expected_customer: str | None = None,
    expected_billing_document: str | None = None,
    expected_nominal: Decimal | None = None,
    expected_doc_date: date | None = None,
    force_vision: bool = False,
) -> dict[str, Any]:
    doc = db.get(Document, document_id)
    if not doc:
        raise ValueError("Document not found")
    ocr_path = doc.storage_path
    temporary_path: str | None = None
    vision: dict[str, Any] | None = None
    if settings.use_supabase_storage:
        temporary_path = materialize(doc.storage_path, Path(doc.file_name).suffix.lower())
        ocr_path = temporary_path
    try:
        text, engine = extract_text(ocr_path)
        fields = parse_document_fields(text)

        # Scanned PDFs on serverless often have no text layer and Tesseract may
        # be unavailable. Use multimodal vision only as a fallback when the
        # classic OCR result is materially incomplete.
        critical_missing = (
            force_vision
            or not text
            or (
                doc.document_type == "BILLING"
                and (
                    not fields.get("billing_document")
                    or fields.get("doc_date") is None
                    or fields.get("nominal") is None
                )
            )
            or (doc.document_type == "SPJ" and not fields.get("no_spj"))
        )
        if critical_missing and vision_available():
            vision = analyze_document_vision(
                ocr_path,
                file_name=doc.file_name,
                expected_customer=expected_customer,
                expected_billing_document=expected_billing_document,
                expected_nominal=expected_nominal,
                expected_doc_date=expected_doc_date,
            )
            if vision:
                vision_engine = str(vision.get("engine") or "AI_VISION")
                engine = (
                    f"{engine}+{vision_engine}"
                    if engine != "REVIEW_REQUIRED"
                    else vision_engine
                )

                local_ocr_text = str(vision.get("ocr_text") or "").strip()
                if local_ocr_text:
                    local_fields = parse_document_fields(local_ocr_text)
                    if not text:
                        text = local_ocr_text
                    for raw_key, norm_key in (
                        ("billing_document_raw", "billing_document"),
                        ("no_spj_raw", "no_spj"),
                    ):
                        if not fields.get(norm_key) and local_fields.get(norm_key):
                            fields[raw_key] = local_fields.get(raw_key)
                            fields[norm_key] = local_fields.get(norm_key)
                    for key in ("doc_date", "nominal", "partial_payment_raw", "partial_payment"):
                        if fields.get(key) is None and local_fields.get(key) is not None:
                            fields[key] = local_fields.get(key)

                if not fields.get("billing_document") and vision.get("billing_document"):
                    fields["billing_document_raw"] = vision["billing_document"]
                    fields["billing_document"] = _norm_key(vision["billing_document"])
                if doc.document_type == "SPJ" and vision.get("official_spj_page"):
                    fields["no_spj_raw"] = vision.get("spj_number")
                    fields["no_spj"] = _normalize_spj_number(vision.get("spj_number"))
                elif vision.get("spj_number"):
                    fields["no_spj_raw"] = vision["spj_number"]
                    fields["no_spj"] = _normalize_spj_number(vision["spj_number"])
                if doc.document_type == "BILLING":
                    # Accuracy-first physical fields: when visual Billing analysis
                    # runs, only explicit fields from the selected Billing/Invoice/
                    # Faktur page are authoritative. Null clears stale generic OCR
                    # values rather than retaining a due/delivery date or unrelated
                    # amount from another page in the combined PDF.
                    fields["doc_date"] = vision.get("invoice_date")
                    fields["nominal"] = vision.get("grand_total")
                else:
                    if fields.get("doc_date") is None and vision.get("invoice_date") is not None:
                        fields["doc_date"] = vision["invoice_date"]
                    if fields.get("nominal") is None and vision.get("grand_total") is not None:
                        fields["nominal"] = vision["grand_total"]
                vision_partial, vision_partial_raw = partial_payment_summary(vision)
                if doc.document_type == "BILLING":
                    # Partial payment is evidence-only. Always replace the old
                    # value, including clearing legacy derived/false positives
                    # when no explicit payment label exists on the Billing page.
                    fields["partial_payment"] = vision_partial
                    fields["partial_payment_raw"] = vision_partial_raw
                elif fields.get("partial_payment") is None and vision_partial is not None:
                    fields["partial_payment"] = vision_partial
                    fields["partial_payment_raw"] = vision_partial_raw
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)

    if fields.get("nominal") is not None:
        fields["nominal"] = _normalize_ocr_amount_scale(
            fields.get("nominal"),
            expected_nominal,
            fields.get("partial_payment"),
        )

    filename_fallback = None
    if doc.document_type == "BILLING" and not fields.get("billing_document"):
        filename_fallback = _billing_document_from_filename(doc.file_name)
        if filename_fallback:
            fields["billing_document_raw"] = filename_fallback
            fields["billing_document"] = _norm_key(filename_fallback)

    confidence = (
        (
            Decimal("0.7600")
            if vision and str(vision.get("engine") or "").startswith("LOCAL_")
            else Decimal("0.8500")
        )
        if vision
        else (
            Decimal("0.5000")
            if engine.startswith("TESSERACT")
            else (Decimal("0.9000") if text else Decimal("0.0000"))
        )
    )

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
        result_fields = {
            "no_spj_raw": fields.get("no_spj_raw"),
            "no_spj": fields.get("no_spj"),
            "partial_payment_raw": fields.get("partial_payment_raw"),
            "partial_payment": fields.get("partial_payment"),
        }

        # Combined evidence creates a BILLING and SPJ document row with the same
        # file hash/name/branch. Vision from the SPJ pass can therefore enrich
        # the paired Billing fields without a second AI request.
        if vision:
            paired_query = (
                select(PhysicalBilling)
                .join(PhysicalBilling.document)
                .where(
                    Document.document_type == "BILLING",
                    Document.file_hash == doc.file_hash,
                    Document.file_name == doc.file_name,
                    Document.archived_at.is_(None),
                )
            )
            branch_key = normalize_branch(doc.branch)
            paired_query = paired_query.where(
                Document.branch == branch_key if branch_key is not None else Document.branch.is_(None)
            )
            paired_billings = list(db.scalars(paired_query).all())
            if len(paired_billings) == 1:
                paired = paired_billings[0]
                if vision.get("billing_document"):
                    paired.billing_document_raw = vision["billing_document"]
                    paired.billing_document = _norm_key(vision["billing_document"])
                if vision.get("official_spj_page"):
                    detected_spj_raw = vision.get("spj_number")
                    detected_spj = _normalize_spj_number(detected_spj_raw)
                    paired.no_spj_raw = detected_spj_raw
                    paired.no_spj = detected_spj
                else:
                    detected_spj_raw = vision.get("spj_number") or fields.get("no_spj_raw")
                    detected_spj = _normalize_spj_number(detected_spj_raw or fields.get("no_spj"))
                    paired.no_spj_raw = detected_spj_raw if detected_spj else None
                    paired.no_spj = detected_spj
                # Replace any legacy/generic date with the strict
                # invoice/faktur issue date. If the label is not readable, clear
                # the stale value rather than showing a due/delivery date.
                paired.doc_date = vision.get("invoice_date")
                strict_grand_total = vision.get("grand_total")
                paired.nominal = (
                    _normalize_ocr_amount_scale(
                        strict_grand_total,
                        expected_nominal,
                        paired.partial_payment,
                    )
                    if strict_grand_total is not None
                    else None
                )

                # Prefer structured partial-payment rows from visual analysis. If the
                # visual service could not structure them but OCR text did, use
                # the parsed text result. Persist once on Billing to prevent
                # double subtraction in reconciliation.
                vision_partial, vision_partial_raw = partial_payment_summary(vision)
                paired.partial_payment = vision_partial
                paired.partial_payment_raw = vision_partial_raw
                # Combined-file payment is stored once on Billing to avoid
                # subtracting the same amount twice.
                row.partial_payment = None
                row.partial_payment_raw = None
                if paired.nominal is not None:
                    paired.nominal = _normalize_ocr_amount_scale(
                        paired.nominal,
                        expected_nominal,
                        paired.partial_payment,
                    )
                paired.ocr_confidence = confidence

    db.commit()
    return {
        "document_id": doc.id,
        "document_type": doc.document_type,
        "engine": engine,
        "fields": result_fields,
        "confidence": str(confidence),
        "filename_fallback_used": bool(filename_fallback),
        "vision": vision,
        "ocr_text": text,
    }


def reconcile_batch(db: Session, batch_id: int, *, branch: str | None = None) -> list[BillingReconciliation]:
    validation = validate_sap_batch(db, batch_id, branch=branch)
    if not validation["valid"]:
        raise ValueError("SAP batch validation failed: " + "; ".join(validation["problems"]))
    # Serialize reconciliation runs for the same batch. This prevents two
    # browser requests (double click / retry / concurrent tab) from deleting and
    # recreating the same unique SAP reconciliation row at the same time.
    batch = db.scalar(
        select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
    )
    batch_branch = normalize_branch(batch.branch if batch else None)

    sap_rows = db.scalars(select(SAPBilling).where(SAPBilling.import_batch_id == batch_id)).all()
    customer_map: dict[str, list[SAPBilling]] = {}
    for sap_row in sap_rows:
        customer_key = _customer_match_key(sap_row.customer_account_name or sap_row.customer)
        if customer_key:
            customer_map.setdefault(customer_key, []).append(sap_row)

    physical_query = select(PhysicalBilling, Document.file_name).join(PhysicalBilling.document).where(Document.archived_at.is_(None))
    physical_query = physical_query.where(
        Document.branch == batch_branch if batch_branch is not None else Document.branch.is_(None)
    )
    for physical, file_name in db.execute(physical_query).all():
        if _norm_key(physical.billing_document):
            continue
        fallback = _billing_document_from_filename(file_name)
        if fallback:
            physical.billing_document_raw = fallback
            physical.billing_document = _norm_key(fallback)
            continue

        # OCR can be unavailable for scanned PDFs in serverless runtime. When the
        # filename contains a unique customer label, link only if exactly one SAP
        # row in the current batch has the same normalized customer name.
        customer_key = _filename_customer_key(file_name)
        customer_matches = customer_map.get(customer_key or "", [])
        if customer_key and len(customer_matches) == 1:
            matched_sap = customer_matches[0]
            physical.billing_document_raw = matched_sap.billing_document
            physical.billing_document = _norm_key(matched_sap.billing_document)
    db.flush()

    results: list[BillingReconciliation] = []
    for sap in sap_rows:
        candidate_query = select(PhysicalBilling).join(PhysicalBilling.document).where(
            PhysicalBilling.billing_document == _norm_key(sap.billing_document),
            Document.archived_at.is_(None),
        )
        candidate_query = candidate_query.where(
            Document.branch == batch_branch if batch_branch is not None else Document.branch.is_(None)
        )
        candidates = db.scalars(candidate_query).all()
        existing = db.scalar(
            select(BillingReconciliation)
            .where(BillingReconciliation.sap_billing_id == sap.id)
            .with_for_update()
        )
        manual_confirmed_same_evidence = bool(
            existing
            and existing.status == "MATCH"
            and MANUAL_CONFIRM_MARKER in (existing.remarks or "")
            and len(candidates) == 1
            and existing.physical_billing_id == candidates[0].id
        )
        if manual_confirmed_same_evidence:
            # A manual confirmation is an explicit auditor/reviewer conclusion.
            # Preserve it across automated re-runs while the exact physical
            # evidence link remains unchanged. Replaced/removed evidence causes
            # the normal automated reconciliation to run again.
            results.append(existing)
            continue

        # Reconciliation is an idempotent upsert. Never delete+insert an
        # existing SAP row: the table has a unique sap_billing_id constraint and
        # concurrent/retried runs previously caused HTTP 500 UniqueViolation.
        rec = existing or BillingReconciliation(sap_billing_id=sap.id)
        if len(candidates) == 0:
            rec.physical_billing_id = None
            rec.billing_match = False
            rec.date_match = False
            rec.nominal_match = False
            rec.nominal_difference = sap.nominal
            rec.status = "NOT_FOUND"
            rec.exception_code = "BILLING_DOCUMENT_NOT_FOUND"
            rec.remarks = (
                "Billing belum lengkap: evidence Billing belum ditemukan untuk Billing Document "
                f"{sap.billing_document}. Proses reconciliation tetap dilanjutkan dan item masuk ke review."
            )
        elif len(candidates) > 1:
            rec.physical_billing_id = None
            rec.billing_match = False
            rec.date_match = False
            rec.nominal_match = False
            rec.nominal_difference = Decimal("0.00")
            rec.status = "EXCEPTION"
            rec.exception_code = "DUPLICATE_PHYSICAL_BILLING"
            rec.remarks = f"Found {len(candidates)} physical Billing documents"
        else:
            physical = candidates[0]

            # Keep reconciliation deterministic and fast. Image/OCR analysis is
            # intentionally executed through the per-document visual refresh
            # endpoint, not inside this batch transaction. Running 10 scanned
            # PDFs synchronously here previously exceeded Vercel's request
            # timeout and surfaced as HTTP 500/timeout to the auditor.
            billing_match = _norm_key(physical.billing_document) == _norm_key(sap.billing_document)
            date_match = physical.doc_date == sap.doc_date if physical.doc_date else False
            spj_partial = Decimal("0.00")
            partial_note: str | None = None
            if physical.no_spj:
                spj_query = select(SPJ).join(SPJ.document).where(
                    SPJ.no_spj == _norm_key(physical.no_spj),
                    Document.archived_at.is_(None),
                )
                spj_query = spj_query.where(
                    Document.branch == batch_branch if batch_branch is not None else Document.branch.is_(None)
                )
                spj_matches = db.scalars(spj_query).all()
                if len(spj_matches) == 1:
                    if spj_matches[0].partial_payment is not None:
                        spj_partial = spj_matches[0].partial_payment
                elif len(spj_matches) == 0:
                    partial_note = (
                        "SPJ belum lengkap: evidence SPJ "
                        f"{physical.no_spj_raw or physical.no_spj} belum ditemukan. "
                        "Proses reconciliation tetap dilanjutkan."
                    )
                else:
                    partial_note = (
                        f"SPJ perlu review: ditemukan {len(spj_matches)} evidence dengan nomor "
                        f"{physical.no_spj_raw or physical.no_spj}. Proses reconciliation tetap dilanjutkan."
                    )
            else:
                paired_spj = _paired_spj_candidates(db, physical)
                if len(paired_spj) == 1:
                    paired = paired_spj[0]
                    if paired.partial_payment is not None:
                        spj_partial = paired.partial_payment
                    partial_note = (
                        "Evidence SPJ tersedia dalam paket/file yang sama, tetapi nomor SPJ belum terbaca oleh OCR. "
                        "Kondisi ini dicatat sebagai OCR info dan tidak mengubah MATCH menjadi REVIEW."
                    )
                elif len(paired_spj) > 1:
                    partial_note = (
                        f"SPJ perlu review: ditemukan {len(paired_spj)} evidence SPJ dari file yang sama "
                        "sementara nomor SPJ belum terbaca OCR."
                    )
                else:
                    partial_note = (
                        "SPJ belum lengkap: nomor SPJ belum tersedia/terbaca pada Billing dan evidence pasangan tidak ditemukan. "
                        "Proses reconciliation tetap dilanjutkan."
                    )
            billing_partial = physical.partial_payment or Decimal("0.00")
            net_nominal = _net_document_amount(physical.nominal, billing_partial, spj_partial)
            difference = sap.nominal - net_nominal if net_nominal is not None else Decimal("0.00")
            nominal_match = difference == Decimal("0.00") if net_nominal is not None else False
            date_evaluated = physical.doc_date is not None
            nominal_evaluated = net_nominal is not None
            date_conflict = date_evaluated and not date_match
            nominal_conflict = nominal_evaluated and not nominal_match
            missing_ocr = physical.doc_date is None or physical.nominal is None

            # Reconciliation's primary identity is the unique Billing Document.
            # Missing scan fields are "not evaluated", not mismatches. A unique
            # exact Billing match therefore remains MATCH unless a field that was
            # actually read contradicts SAP. This avoids sending clean scans to
            # manual review merely because OCR could not read every field.
            status = (
                "MATCH"
                if billing_match and not date_conflict and not nominal_conflict
                else "EXCEPTION"
            )
            remarks_parts = []
            if billing_partial:
                remarks_parts.append(f"Billing partial payment deducted: {billing_partial}")
            if spj_partial:
                remarks_parts.append(f"SPJ partial payment deducted: {spj_partial}")
            if missing_ocr:
                missing_fields = []
                if physical.doc_date is None:
                    missing_fields.append("tanggal")
                if physical.nominal is None:
                    missing_fields.append("nominal")
                remarks_parts.append(
                    "MATCH berdasarkan Billing Document unik; "
                    + "/".join(missing_fields)
                    + " belum terbaca OCR dan dicatat sebagai tidak dievaluasi, bukan mismatch."
                )
            if partial_note:
                remarks_parts.append(partial_note)
            rec.physical_billing_id = physical.id
            rec.billing_match = billing_match
            rec.date_match = date_match
            rec.nominal_match = nominal_match
            rec.nominal_difference = difference
            rec.status = status
            rec.exception_code = None if status == "MATCH" else "BILLING_FIELD_MISMATCH"
            rec.remarks = "; ".join(remarks_parts) or partial_note
        if existing is None:
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


def _sap_for_billing(db: Session, billing_id: int) -> SAPBilling | None:
    rec = db.scalar(
        select(BillingReconciliation)
        .where(BillingReconciliation.physical_billing_id == billing_id)
        .order_by(BillingReconciliation.id.desc())
    )
    return db.get(SAPBilling, rec.sap_billing_id) if rec is not None else None


def _control_evidence_complete(row: DocumentControlEvidence | None) -> bool:
    if row is None or row.review_required:
        return False

    # Reviewer policy: OCR uncertainty on a signature is informational and does
    # not by itself create REVIEW. Only an explicitly detected missing signature
    # blocks PASS. Stamp evidence remains the primary reviewer gate.
    signature_statuses = (
        row.receiver_signature_status,
        row.driver_signature_status,
        row.security_signature_status,
        row.bm_signature_status,
        row.checker_signature_status,
    )
    if any(status == "MISSING" for status in signature_statuses):
        return False
    if row.receiver_stamp_status != "PRESENT":
        return False
    return row.stamp_customer_match_status in {"MATCH", "NOT_EVALUATED"}


def _refresh_visual_pair(
    db: Session,
    billing: PhysicalBilling,
    spj: SPJ,
) -> DocumentControlEvidence | None:
    """Return persisted visual controls without running expensive OCR inline.

    Visual analysis is performed through the per-document refresh endpoint. SPJ
    vouching must remain a fast deterministic calculation so a branch with
    multiple scanned documents cannot exceed the serverless HTTP timeout.
    """
    return _control_evidence_for_spj(db, spj)


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

    result.status = result.manual_review_status or automated_status
    result.remarks = result.reviewer_remarks if result.manual_review_status else automated_remarks
    db.flush()
    return result


def vouch_spj(db: Session, *, branch: str | None = None) -> list[VouchingResult]:
    billing_query = select(PhysicalBilling).join(PhysicalBilling.document).where(Document.archived_at.is_(None))
    if branch is not None:
        billing_query = billing_query.where(Document.branch == normalize_branch(branch))
    billings = db.scalars(billing_query).all()
    results: list[VouchingResult] = []

    for billing in billings:
        paired_spj = _paired_spj_candidates(db, billing)
        if len(paired_spj) == 1:
            _refresh_visual_pair(db, billing, paired_spj[0])

        no_spj = _normalize_spj_number(billing.no_spj)
        if not no_spj:
            paired_spj = _paired_spj_candidates(db, billing)
            if len(paired_spj) == 1:
                spj = paired_spj[0]
                control_evidence = _refresh_visual_pair(db, billing, spj)
                # A same-file/hash pair proves the evidence belongs together,
                # but it does NOT prove the SPJ number is correct. A readable
                # 8-12 digit transaction number is mandatory for automatic PASS.
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=spj,
                    spj_match=False,
                    automated_status="REVIEW",
                    automated_rule_code="SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE",
                    automated_remarks=(
                        "Evidence Billing dan SPJ berasal dari file/hash/cabang yang sama, tetapi nomor SPJ resmi "
                        "belum terbaca sebagai 8-12 digit transaction number. Item tidak boleh auto-PASS dan "
                        "diteruskan ke review."
                    ),
                    control_evidence=control_evidence,
                )
            elif len(paired_spj) > 1:
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=paired_spj[0],
                    spj_match=False,
                    automated_status="REVIEW",
                    automated_rule_code="DUPLICATE_PAIRED_SPJ_EVIDENCE",
                    automated_remarks=(
                        f"Ditemukan {len(paired_spj)} evidence SPJ dengan file/hash pasangan yang sama; "
                        "perlu review auditor."
                    ),
                    control_evidence=_control_evidence_for_spj(db, paired_spj[0]),
                )
            else:
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=None,
                    spj_match=False,
                    automated_status="REVIEW",
                    automated_rule_code="BILLING_WITHOUT_SPJ",
                    automated_remarks=(
                        "SPJ belum lengkap: evidence pasangan tidak ditemukan. "
                        "Vouching tetap dilanjutkan dan item masuk ke review."
                    ),
                )
        else:
            billing_branch = normalize_branch(billing.document.branch)
            match_query = select(SPJ).join(SPJ.document).where(
                SPJ.no_spj == no_spj,
                Document.archived_at.is_(None),
            )
            match_query = match_query.where(
                Document.branch == billing_branch if billing_branch is not None else Document.branch.is_(None)
            )
            matches = db.scalars(match_query).all()

            # Some scans contain punctuation/noise differences in the SPJ number.
            # If the exact normalized number is not found, the deterministic
            # combined-file pair remains the preferred fallback.
            if not matches:
                paired_spj = _paired_spj_candidates(db, billing)
                if len(paired_spj) == 1:
                    spj = paired_spj[0]
                    _refresh_visual_pair(db, billing, spj)
                    if _spj_numbers_match(no_spj, spj.no_spj):
                        matches = [spj]

            if not matches:
                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=None,
                    spj_match=False,
                    automated_status="REVIEW",
                    automated_rule_code="SPJ_NOT_FOUND",
                    automated_remarks=(
                        f"SPJ belum lengkap: evidence SPJ {billing.no_spj_raw or billing.no_spj} "
                        "belum ditemukan. Vouching tetap dilanjutkan ke review."
                    ),
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
                    control_evidence=_control_evidence_for_spj(db, matches[0]),
                )
            else:
                spj = matches[0]
                control_evidence = _refresh_visual_pair(db, billing, spj)
                if control_evidence is None:
                    # Backward-compatible path for legacy/API-created SPJ records
                    # that predate control-evidence analysis. Uploaded production
                    # evidence creates this row automatically.
                    status = "PASS"
                    rule = None
                    remarks = "Nomor SPJ cocok. Control-evidence record belum tersedia (legacy evidence)."
                elif control_evidence.review_required:
                    status = "REVIEW"
                    rule = "CONTROL_EVIDENCE_REVIEW"
                    remarks = (
                        control_evidence.review_reasons
                        or "Nomor SPJ cocok, tetapi stempel/tanda tangan masih memerlukan review."
                    )
                elif _control_evidence_complete(control_evidence):
                    status = "PASS"
                    rule = None
                    remarks = (
                        "Nomor SPJ cocok dan seluruh control evidence wajib terdeteksi lengkap: "
                        "tanda tangan serta stempel sesuai."
                    )
                else:
                    status = "REVIEW"
                    rule = "CONTROL_EVIDENCE_INCOMPLETE"
                    remarks = "Nomor SPJ cocok, tetapi sebagian control evidence belum lengkap."

                result = _upsert_vouching_result(
                    db,
                    billing=billing,
                    spj=spj,
                    spj_match=True,
                    automated_status=status,
                    automated_rule_code=rule,
                    automated_remarks=remarks,
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


def confirm_reconciliation_manual(
    db: Session,
    reconciliation_id: int,
    *,
    reviewer_id: str,
    remarks: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    """Record an explicit manual confirmation for one sampled Billing/SPJ item.

    This is used when scan OCR cannot read the fields but the auditor/reviewer
    has visually checked Billing vs SAP, the paired SPJ, signatures and stamp.
    It does not fabricate OCR output: instead it stores a clearly-marked manual
    conclusion and preserves the automated OCR limitations in the audit trail.
    """

    query = (
        select(BillingReconciliation)
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.id == reconciliation_id)
    )
    if branch is not None:
        query = query.where(ImportBatch.branch == normalize_branch(branch))
    rec = db.scalar(query)
    if rec is None:
        raise ValueError("Reconciliation result not found")
    if rec.physical_billing_id is None:
        raise ValueError("Manual confirmation requires linked Billing evidence")

    billing = db.get(PhysicalBilling, rec.physical_billing_id)
    if billing is None or billing.document is None or billing.document.archived_at is not None:
        raise ValueError("Linked Billing evidence is not active")

    # Prefer a number-based SPJ match. For scanned combined evidence where the
    # number is unreadable, use the deterministic same file/hash/branch pair.
    spj: SPJ | None = None
    if billing.no_spj:
        spj_query = (
            select(SPJ)
            .join(SPJ.document)
            .where(
                SPJ.no_spj == _normalize_spj_number(billing.no_spj),
                Document.archived_at.is_(None),
            )
        )
        branch_key = normalize_branch(billing.document.branch)
        spj_query = spj_query.where(
            Document.branch == branch_key if branch_key is not None else Document.branch.is_(None)
        )
        spj_matches = list(db.scalars(spj_query).all())
        if len(spj_matches) == 1:
            spj = spj_matches[0]
    if spj is None:
        paired = _paired_spj_candidates(db, billing)
        if len(paired) == 1:
            spj = paired[0]
    if spj is None:
        raise ValueError("Manual confirmation requires exactly one linked SPJ evidence")

    note = _norm(remarks) or (
        "Billing, tanggal/nominal, SPJ, tanda tangan, dan stempel telah diperiksa manual dan dinyatakan sesuai."
    )
    now = datetime.now(timezone.utc)

    control_evidence = _control_evidence_for_spj(db, spj)
    if control_evidence is not None:
        control_evidence.review_status = "PASS"
        control_evidence.review_required = False
        control_evidence.reviewer_id = reviewer_id
        control_evidence.reviewer_remarks = note
        control_evidence.reviewed_at = now

    vouch = db.scalar(select(VouchingResult).where(VouchingResult.billing_id == billing.id))
    if vouch is None:
        vouch = _upsert_vouching_result(
            db,
            billing=billing,
            spj=spj,
            spj_match=False,
            automated_status="REVIEW",
            automated_rule_code=(
                None if billing.no_spj and spj.no_spj
                else "SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE"
            ),
            automated_remarks="Automatic OCR result required manual confirmation.",
            control_evidence=control_evidence,
        )
    vouch.spj_id = spj.id
    vouch.spj_match = True
    vouch.manual_review_status = "PASS"
    vouch.review_reason_code = "EVIDENCE_CONFIRMED"
    vouch.reviewer_remarks = note
    vouch.reviewer_id = reviewer_id
    vouch.reviewed_at = now
    vouch.status = "PASS"
    vouch.remarks = note
    vouch.control_evidence_id = control_evidence.id if control_evidence else None

    rec.billing_match = True
    rec.date_match = True
    rec.nominal_match = True
    rec.nominal_difference = Decimal("0.00")
    rec.status = "MATCH"
    rec.exception_code = None
    rec.remarks = (
        f"{MANUAL_CONFIRM_MARKER} {note} "
        f"Confirmed by {reviewer_id}; physical_billing_id={billing.id}; spj_id={spj.id}."
    )
    db.flush()

    return {
        "reconciliation_id": rec.id,
        "sap_billing_id": rec.sap_billing_id,
        "physical_billing_id": rec.physical_billing_id,
        "spj_id": spj.id,
        "control_evidence_id": control_evidence.id if control_evidence else None,
        "vouching_result_id": vouch.id,
        "status": rec.status,
        "vouching_status": vouch.status,
        "manual_confirmed": True,
        "reviewer_id": reviewer_id,
        "remarks": note,
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
    elif rec.status in {"EXCEPTION", "NOT_FOUND"}:
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
