from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DocumentControlEvidence
from app.services.control_evidence_store import evidence_payload

VALID_REVIEW_STATUSES = {"PASS", "REVIEW", "EXCEPTION"}


def _system_status(row: DocumentControlEvidence) -> str:
    return "REVIEW" if row.review_required else "PASS"


def review_control_evidence(
    db: Session,
    evidence_id: int,
    *,
    status: str,
    reviewer_id: str,
    remarks: str | None = None,
) -> dict[str, Any]:
    """Apply an auditor manual review decision to SPJ control evidence.

    The reviewer decision does not judge authenticity. It records the auditor's
    conclusion after checking the image/manual evidence and drives whether the
    item stays in the manual review queue.
    """

    row = db.get(DocumentControlEvidence, evidence_id)
    if row is None:
        raise ValueError("Control evidence result not found")

    normalized_status = status.upper().strip()
    if normalized_status not in VALID_REVIEW_STATUSES:
        raise ValueError("status must be PASS, REVIEW, or EXCEPTION")

    row.review_status = normalized_status
    row.reviewer_id = reviewer_id
    row.reviewer_remarks = remarks
    row.reviewed_at = func.now()
    row.review_required = normalized_status != "PASS"
    db.flush()

    payload = evidence_payload(row) or {}
    payload["previous_review_status"] = _system_status(row)
    return payload
