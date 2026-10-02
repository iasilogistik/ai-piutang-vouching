from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlEvidenceDetection, Document, DocumentControlEvidence, SAPBilling
from app.services.control_evidence import analyze_spj_control_evidence, compare_stamp_to_customer

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

    receiver_signature_detection = next(
        (
            detection
            for detection in getattr(row.document, "control_evidence_detections", [])
            if detection.detection_type == "receiver_signature"
        ),
        None,
    )
    receiver_name = None
    if receiver_signature_detection and isinstance(receiver_signature_detection.reference_json, dict):
        receiver_name = receiver_signature_detection.reference_json.get("receiver_name")

    return {
        "control_evidence_id": row.id,
        "receiver_name": receiver_name,
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


def _customer_from_vision(db: Session, vision: dict[str, Any] | None) -> str | None:
    if not vision or not vision.get("billing_document"):
        return None
    rows = db.scalars(
        select(SAPBilling).where(SAPBilling.billing_document == str(vision["billing_document"]))
    ).all()
    customers = {
        (row.customer_account_name or row.customer or "").strip()
        for row in rows
        if (row.customer_account_name or row.customer or "").strip()
    }
    return next(iter(customers)) if len(customers) == 1 else None


def _vision_evidence(vision: dict[str, Any], *, expected_customer: str | None) -> dict[str, Any]:
    role_map = {
        "receiver": "receiver_signature",
        "driver": "driver_signature",
        "security": "security_signature",
        "bm": "bm_signature",
        "checker": "checker_signature",
    }
    result: dict[str, Any] = {}
    signatures = vision.get("signatures") if isinstance(vision.get("signatures"), dict) else {}
    for source, target in role_map.items():
        value = signatures.get(source) if isinstance(signatures.get(source), dict) else {}
        raw_status = str(value.get("status") or "UNCLEAR").upper()
        status = "UNKNOWN" if raw_status == "UNCLEAR" else raw_status
        if status not in {"PRESENT", "MISSING", "UNKNOWN", "NOT_APPLICABLE"}:
            status = "UNKNOWN"
        if status == "PRESENT":
            remarks = f"Visual mendeteksi coretan/TTD pada area {source}; keaslian tidak dianalisis."
        elif status == "MISSING":
            remarks = f"Tidak terdeteksi coretan/TTD pada area {source}."
        elif status == "NOT_APPLICABLE":
            remarks = f"Role {source} tidak tercetak pada template dokumen."
        else:
            remarks = f"Visual belum dapat memastikan tanda tangan {source}."
        result[target] = {
            "status": status,
            "confidence": value.get("confidence") or 0.0,
            "remarks": remarks,
            "page_number": value.get("page_number"),
            "reference": {"source": "AI_VISION"},
        }

    stamp_value = vision.get("stamp") if isinstance(vision.get("stamp"), dict) else {}
    raw_stamp_status = str(stamp_value.get("status") or "UNCLEAR").upper()
    stamp_status = "UNKNOWN" if raw_stamp_status == "UNCLEAR" else raw_stamp_status
    stamp_text = stamp_value.get("text")
    stamp_match = compare_stamp_to_customer(stamp_text, expected_customer)
    if stamp_status == "PRESENT" and not stamp_text:
        # User policy: for vouching we test presence of a receiver stamp, not
        # authenticity. If the cap is visibly present but its letters are too
        # faint for OCR, do not force a reviewer solely for unreadable stamp text.
        stamp_match = {
            "status": "NOT_EVALUATED",
            "confidence": stamp_value.get("confidence") or 0.0,
            "remarks": "Stempel terlihat secara visual; tulisan stempel tidak dipakai sebagai syarat PASS.",
        }
    result["receiver_stamp"] = {
        "status": stamp_status if stamp_status in {"PRESENT", "MISSING", "UNKNOWN"} else "UNKNOWN",
        "confidence": stamp_value.get("confidence") or 0.0,
        "stamp_text_raw": stamp_text,
        "stamp_text_normalized": stamp_text.upper().strip() if isinstance(stamp_text, str) and stamp_text.strip() else None,
        "customer_match": stamp_match,
        "remarks": (
            None
            if stamp_status == "PRESENT"
            else (
                "AI vision mengindikasikan stempel tidak ada."
                if stamp_status == "MISSING"
                else "AI vision belum dapat memastikan keberadaan stempel."
            )
        ),
        "page_number": stamp_value.get("page_number"),
        "reference": {"source": "AI_VISION"},
    }

    review_reasons: list[str] = []
    informational_reasons: list[str] = []
    stamp = result["receiver_stamp"]
    if stamp["status"] != "PRESENT":
        review_reasons.append(stamp.get("remarks") or "Stempel penerima belum dapat dipastikan.")
    stamp_match = stamp.get("customer_match", {})
    if stamp_match.get("status") == "REVIEW":
        review_reasons.append(stamp_match.get("remarks") or "Nama stempel perlu dicek reviewer.")

    for key in role_map.values():
        value = result[key]
        if value["status"] == "MISSING":
            review_reasons.append(value.get("remarks") or f"{key} terindikasi tidak ada; perlu review.")
        elif value["status"] == "UNKNOWN":
            informational_reasons.append(value.get("remarks") or f"{key} tidak dapat dipastikan.")
        elif value["status"] == "NOT_APPLICABLE":
            informational_reasons.append(value.get("remarks") or f"{key} tidak berlaku pada template.")

    result["review_required"] = bool(review_reasons)
    result["review_reasons"] = review_reasons
    result["informational_reasons"] = informational_reasons
    result["review_focus"] = (
        "STAMP"
        if any("stempel" in reason.lower() for reason in review_reasons)
        else ("SIGNATURE_MISSING" if review_reasons else "NONE")
    )
    return result


def _merge_visual_over_ocr(ocr: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    merged = dict(ocr)
    for key in (
        "receiver_signature",
        "driver_signature",
        "security_signature",
        "bm_signature",
        "checker_signature",
        "receiver_stamp",
    ):
        value = visual.get(key)
        if value:
            merged[key] = value
    merged["review_required"] = visual.get("review_required", ocr.get("review_required", False))
    merged["review_reasons"] = visual.get("review_reasons", ocr.get("review_reasons", []))
    merged["informational_reasons"] = visual.get(
        "informational_reasons", ocr.get("informational_reasons", [])
    )
    merged["review_focus"] = visual.get("review_focus", ocr.get("review_focus", "NONE"))
    return merged


def analyze_and_persist_control_evidence(
    db: Session,
    document_id: int,
    *,
    expected_customer: str | None = None,
    vision_result: dict[str, Any] | None = None,
    ocr_text: str | None = None,
    ocr_engine: str | None = None,
) -> dict[str, Any]:
    """Analyze SPJ visual evidence with OCR first and multimodal vision fallback."""

    document = db.get(Document, document_id)
    if document is None:
        raise ValueError("Document not found")
    if document.document_type != "SPJ":
        raise ValueError("Control evidence analysis is only available for SPJ documents")

    from app.services.vouching import extract_text
    from app.config import settings
    from app.services.storage import materialize
    from app.services.vision_evidence import analyze_document_vision, vision_available
    from pathlib import Path

    if ocr_text is not None:
        text = ocr_text
        engine = ocr_engine or "OCR_REUSED"
    else:
        ocr_path = document.storage_path
        temporary_path: str | None = None
        if settings.use_supabase_storage:
            temporary_path = materialize(document.storage_path, Path(document.file_name).suffix.lower())
            ocr_path = temporary_path
        try:
            text, engine = extract_text(ocr_path)
            if vision_result is None and vision_available() and not text:
                vision_result = analyze_document_vision(
                    ocr_path,
                    file_name=document.file_name,
                    expected_customer=expected_customer,
                )
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    if not expected_customer:
        expected_customer = _customer_from_vision(db, vision_result)

    evidence = analyze_spj_control_evidence(text, expected_customer=expected_customer)
    if vision_result:
        visual = _vision_evidence(vision_result, expected_customer=expected_customer)
        evidence = _merge_visual_over_ocr(evidence, visual)
        engine = f"{engine}+AI_VISION" if engine != "REVIEW_REQUIRED" else "AI_VISION"

    row = persist_control_evidence(db, document_id, evidence, extraction_engine=engine)
    payload = evidence_payload(row) or {}
    payload["engine"] = engine
    payload["vision_used"] = bool(vision_result)
    payload["partial_payments"] = vision_result.get("partial_payments", []) if vision_result else []
    payload["delivery_order_number"] = vision_result.get("delivery_order_number") if vision_result else None
    return payload
