from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentControlEvidence, VouchingResult
from app.services.control_evidence_store import evidence_payload


def _split_reasons(value: str | None) -> list[str]:
    return [reason.strip() for reason in (value or "").split(";") if reason.strip()]


def _status_counts(rows: list[DocumentControlEvidence], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = getattr(row, field_name) or "NOT_CAPTURED"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _control_status_counts(rows: list[DocumentControlEvidence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = _control_status(row)
        counts[status] = counts.get(status, 0) + 1
    return counts


def _stamp_match_counts(rows: list[DocumentControlEvidence]) -> dict[str, int]:
    return _status_counts(rows, "stamp_customer_match_status")


def _control_status(row: DocumentControlEvidence) -> str:
    if row.review_status:
        return row.review_status
    return "REVIEW" if row.review_required else "PASS"


def _latest_vouching_for_spj(db: Session, spj_id: int | None) -> VouchingResult | None:
    if spj_id is None:
        return None
    return db.scalar(select(VouchingResult).where(VouchingResult.spj_id == spj_id).order_by(VouchingResult.id.desc()))


def _dashboard_row(db: Session, row: DocumentControlEvidence) -> dict[str, Any]:
    document = row.document
    spj = document.spj if document else None
    vouching = _latest_vouching_for_spj(db, spj.id if spj else None)

    return {
        "control_evidence_id": row.id,
        "document_id": row.document_id,
        "file_name": document.file_name if document else None,
        "document_type": document.document_type if document else None,
        "uploaded_at": document.uploaded_at if document else None,
        "document_url": f"/documents/{row.document_id}/content",
        "no_spj": spj.no_spj if spj else None,
        "no_spj_raw": spj.no_spj_raw if spj else None,
        "spj_id": spj.id if spj else None,
        "billing_id": vouching.billing_id if vouching else None,
        "vouching_result_id": vouching.id if vouching else None,
        "spj_vouching_status": vouching.status if vouching else None,
        "overall_control_status": _control_status(row),
        "review_required": row.review_required,
        "review_reasons": _split_reasons(row.review_reasons),
        "review_status": row.review_status,
        "reviewer_id": row.reviewer_id,
        "reviewer_remarks": row.reviewer_remarks,
        "reviewed_at": row.reviewed_at,
        "receiver_signature_status": row.receiver_signature_status,
        "driver_signature_status": row.driver_signature_status,
        "security_signature_status": row.security_signature_status,
        "bm_signature_status": row.bm_signature_status,
        "checker_signature_status": row.checker_signature_status,
        "receiver_stamp_status": row.receiver_stamp_status,
        "stamp_text_raw": row.stamp_text_raw,
        "stamp_text_normalized": row.stamp_text_normalized,
        "stamp_customer_match_status": row.stamp_customer_match_status,
        "updated_at": row.updated_at,
        "evidence": evidence_payload(row),
    }


def build_control_evidence_dashboard(db: Session, *, review_only: bool = False, limit: int = 200) -> dict[str, Any]:
    """Return auditor-facing SPJ control evidence dashboard data.

    This dashboard is intentionally evidence/status oriented. It does not judge
    signature or stamp authenticity; it summarizes whether required evidence was
    detected, whether the stamp name could be compared to the SAP customer, and
    which documents need manual review.
    """

    all_rows = list(db.scalars(select(DocumentControlEvidence)).all())
    sorted_rows = sorted(all_rows, key=lambda row: ((row.updated_at or row.created_at), row.id), reverse=True)
    filtered_rows = [row for row in sorted_rows if row.review_required] if review_only else sorted_rows
    selected_rows = filtered_rows[:limit]

    review_rows = [row for row in all_rows if row.review_required]
    summary = {
        "total_documents": len(all_rows),
        "pass_documents": sum(1 for row in all_rows if not row.review_required),
        "review_required_documents": len(review_rows),
        "overall_control_status": _control_status_counts(all_rows),
        "receiver_signature": _status_counts(all_rows, "receiver_signature_status"),
        "driver_signature": _status_counts(all_rows, "driver_signature_status"),
        "security_signature": _status_counts(all_rows, "security_signature_status"),
        "bm_signature": _status_counts(all_rows, "bm_signature_status"),
        "checker_signature": _status_counts(all_rows, "checker_signature_status"),
        "receiver_stamp": _status_counts(all_rows, "receiver_stamp_status"),
        "stamp_customer_match": _stamp_match_counts(all_rows),
    }

    dashboard_rows = [_dashboard_row(db, row) for row in selected_rows]
    review_queue = [_dashboard_row(db, row) for row in sorted(review_rows, key=lambda row: ((row.updated_at or row.created_at), row.id), reverse=True)[:limit]]

    return {
        "summary": summary,
        "total_rows": len(filtered_rows),
        "returned_rows": len(dashboard_rows),
        "review_only": review_only,
        "rows": dashboard_rows,
        "manual_review_queue": review_queue,
    }
