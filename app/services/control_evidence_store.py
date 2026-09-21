from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentControlEvidence
from app.services.control_evidence import analyze_spj_control_evidence


_SIGNATURE_FIELDS = {
    "receiver_signature": "receiver_signature",
    "driver_signature": "driver_signature",
    "security_signature": "security_signature",
    "bm_signature": "bm_signature",
    "checker_signature": "checker_signature",
}


def _confidence(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except Exception:
        return None


def _join_reasons(reasons: list[str] | None) -> str | None:
    if not reasons:
        return None
    return "; ".join(reason for reason in reasons if reason)


def evidence_payload(row: DocumentControlEvidence | None) -> dict[str, Any] | None:
    if row is None:
        return None

    def signature_payload(prefix: str) -> dict[str, Any]:
        return {
            "status": getattr(row, f"{prefix}_status"),
            "confidence": str(getattr(row, f"{prefix}_confidence")) if getattr(row, f"{prefix}_confidence") is not None else None,
            "remarks": getattr(row, f"{prefix}_remarks"),
        }

    return {
        "control_evidence_id": row.id,
        "document_id": row.document_id,
        "receiver_signature": signature_payload("receiver_signature"),
        "driver_signature": signature_payload("driver_signature"),
        "security_signature": signature_payload("security_signature"),
        "bm_signature": signature_payload("bm_signature"),
        "checker_signature": signature_payload("checker_signature"),
        "receiver_stamp": {
            "status": row.receiver_stamp_status,
            "confidence": str(row.receiver_stamp_confidence) if row.receiver_stamp_confidence is not None else None,
            "remarks": row.receiver_stamp_remarks,
            "stamp_text_raw": row.stamp_text_raw,
            "stamp_text_normalized": row.stamp_text_normalized,
            "customer_match": {
                "status": row.stamp_customer_match_status,
                "confidence": str(row.stamp_customer_match_confidence) if row.stamp_customer_match_confidence is not None else None,
                "remarks": row.stamp_customer_match_remarks,
            },
        },
        "review_required": row.review_required,
        "review_reasons": [reason.strip() for reason in (row.review_reasons or "").split(";") if reason.strip()],
        "review_status": row.review_status,
        "reviewer_id": row.reviewer_id,
        "reviewer_remarks": row.reviewer_remarks,
        "reviewed_at": row.reviewed_at,
    }


def persist_control_evidence(db: Session, document_id: int, evidence: dict[str, Any]) -> DocumentControlEvidence:
    row = db.scalar(select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == document_id))
    if row is None:
        row = DocumentControlEvidence(document_id=document_id)
        db.add(row)

    for evidence_key, prefix in _SIGNATURE_FIELDS.items():
        value = evidence.get(evidence_key, {})
        setattr(row, f"{prefix}_status", value.get("status"))
        setattr(row, f"{prefix}_confidence", _confidence(value.get("confidence")))
        setattr(row, f"{prefix}_remarks", value.get("remarks"))

    stamp = evidence.get("receiver_stamp", {})
    match = stamp.get("customer_match", {})
    row.receiver_stamp_status = stamp.get("status")
    row.receiver_stamp_confidence = _confidence(stamp.get("confidence"))
    row.receiver_stamp_remarks = stamp.get("remarks")
    row.stamp_text_raw = stamp.get("stamp_text_raw")
    row.stamp_text_normalized = stamp.get("stamp_text_normalized")
    row.stamp_customer_match_status = match.get("status")
    row.stamp_customer_match_confidence = _confidence(match.get("confidence"))
    row.stamp_customer_match_remarks = match.get("remarks")
    row.review_required = bool(evidence.get("review_required"))
    row.review_reasons = _join_reasons(evidence.get("review_reasons"))
    db.flush()
    return row


def analyze_and_persist_control_evidence(db: Session, document_id: int, *, expected_customer: str | None = None) -> dict[str, Any]:
    """Run control-evidence analysis and persist the structured result.

    The function is intentionally conservative: it is only valid for SPJ
    documents and stores UNKNOWN/REVIEW states rather than guessing when OCR or
    visual evidence is insufficient.
    """

    document = db.get(Document, document_id)
    if document is None:
        raise ValueError("Document not found")
    if document.document_type != "SPJ":
        raise ValueError("Control evidence analysis is only available for SPJ documents")

    from app.services.vouching import extract_text
    from app.config import settings
    from app.services.storage import materialize
    from pathlib import Path

    ocr_path = document.storage_path
    temporary_path: str | None = None
    if settings.use_supabase_storage:
        temporary_path = materialize(document.storage_path, Path(document.file_name).suffix.lower())
        ocr_path = temporary_path
    try:
        text, engine = extract_text(ocr_path)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)

    evidence = analyze_spj_control_evidence(text, expected_customer=expected_customer)
    row = persist_control_evidence(db, document_id, evidence)
    payload = evidence_payload(row) or {}
    payload["engine"] = engine
    return payload
