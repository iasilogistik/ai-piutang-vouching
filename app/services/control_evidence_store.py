from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlEvidenceDetection, Document, DocumentControlEvidence
from app.services.control_evidence import analyze_spj_control_evidence

DETECTOR_NAME = "spj_control_evidence"
DETECTOR_VERSION = "1.0"
_DETECTION_TYPES = (
    "receiver_signature",
    "driver_signature",
    "security_signature",
    "bm_signature",
    "checker_signature",
    "receiver_stamp",
    "stamp_customer_match",
)


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


def _detection_values(evidence: dict[str, Any], detection_type: str) -> dict[str, Any]:
    if detection_type == "stamp_customer_match":
        return dict(evidence.get("receiver_stamp", {}).get("customer_match", {}) or {})
    return dict(evidence.get(detection_type, {}) or {})


def persist_detection_records(
    db: Session,
    document: Document,
    evidence: dict[str, Any],
    *,
    extraction_engine: str | None = None,
    detector_name: str = DETECTOR_NAME,
    detector_version: str = DETECTOR_VERSION,
) -> list[ControlEvidenceDetection]:
    rows: list[ControlEvidenceDetection] = []
    now = datetime.now(timezone.utc)
    for detection_type in _DETECTION_TYPES:
        value = _detection_values(evidence, detection_type)
        status = str(value.get("status") or "UNKNOWN").upper()
        processing_status = str(value.get("processing_status") or ("FAILED" if status == "ERROR" else "SUCCESS")).upper()
        row = db.scalar(
            select(ControlEvidenceDetection).where(
                ControlEvidenceDetection.document_id == document.id,
                ControlEvidenceDetection.detection_type == detection_type,
                ControlEvidenceDetection.source_file_hash == document.file_hash,
                ControlEvidenceDetection.detector_name == detector_name,
                ControlEvidenceDetection.detector_version == detector_version,
            )
        )
        if row is None:
            row = ControlEvidenceDetection(
                document_id=document.id,
                branch=document.branch,
                detection_type=detection_type,
                source_file_hash=document.file_hash,
                detector_name=detector_name,
                detector_version=detector_version,
            )
            db.add(row)
        row.branch = document.branch
        row.status = status
        row.confidence = _confidence(value.get("confidence"))
        row.remarks = value.get("remarks")
        row.page_number = value.get("page_number")
        row.reference_json = value.get("reference")
        row.extraction_engine = extraction_engine
        row.processing_status = processing_status
        row.error_message = value.get("error_message")
        row.processed_at = now
        rows.append(row)
    db.flush()
    return rows


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
        "detection_records": [
            {
                "id": detection.id,
                "detection_type": detection.detection_type,
                "status": detection.status,
                "confidence": str(detection.confidence) if detection.confidence is not None else None,
                "page_number": detection.page_number,
                "reference": detection.reference_json,
                "source_file_hash": detection.source_file_hash,
                "detector_name": detection.detector_name,
                "detector_version": detection.detector_version,
                "extraction_engine": detection.extraction_engine,
                "processing_status": detection.processing_status,
                "error_message": detection.error_message,
                "processed_at": detection.processed_at,
            }
            for detection in sorted(
                getattr(row.document, "control_evidence_detections", []),
                key=lambda item: (item.detection_type, item.id or 0),
            )
        ],
    }


def persist_control_evidence(db: Session, document_id: int, evidence: dict[str, Any], *, extraction_engine: str | None = None) -> DocumentControlEvidence:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError("Document not found")
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
    persist_detection_records(db, document, evidence, extraction_engine=extraction_engine)
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
    row = persist_control_evidence(db, document_id, evidence, extraction_engine=engine)
    payload = evidence_payload(row) or {}
    payload["engine"] = engine
    return payload
