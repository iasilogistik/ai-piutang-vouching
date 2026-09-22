from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO, StringIO
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from openpyxl import Workbook
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.branch_access import normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditFinding,
    AuditReport,
    AuditSample,
    AuditWorkingPaper,
    CorrectiveActionPlan,
    CorrectiveActionProgressUpdate,
    CorrectiveActionVerification,
    Document,
    ImportBatch,
    ManagementResponse,
    SAPBilling,
)

router = APIRouter()
_REGISTERED = False

RESOURCE_TYPES = (
    "ENGAGEMENT",
    "SAMPLE",
    "WORKING_PAPER",
    "FINDING",
    "MANAGEMENT_RESPONSE",
    "ACTION_PLAN",
    "FOLLOW_UP",
    "EVIDENCE",
    "AUDIT_REPORT",
    "SAP_BILLING",
)
MAX_PAGE_SIZE = 100
MAX_CANDIDATES = 5000
MAX_EXPORT_ROWS = 5000
MAX_QUERY_ROWS = MAX_EXPORT_ROWS + 2


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _date_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if date_to
        else None
    )
    return start, end


def _contains(columns, term: str | None):
    if not term:
        return None
    pattern = f"%{term.strip()}%"
    return or_(*[cast(column, String).ilike(pattern) for column in columns])


def _limit(query, limit: int):
    # Fetch one sentinel row beyond the requested candidate boundary so
    # oversized single-resource result sets are detectable, not silently cut.
    return query.limit(min(max(limit + 1, 2), MAX_QUERY_ROWS))


def _result(
    *,
    resource_type: str,
    resource_id: int,
    reference: str,
    title: str,
    summary: str | None,
    branch: str | None,
    status: str | None,
    owner: str | None,
    engagement_id: int | None,
    event_at: datetime | date | None,
    target_url: str,
    subtype: str | None = None,
) -> dict[str, object]:
    if isinstance(event_at, datetime):
        event_value = event_at.isoformat()
        sort_value = event_at.timestamp()
    elif isinstance(event_at, date):
        event_value = event_at.isoformat()
        sort_value = datetime.combine(event_at, time.min, tzinfo=timezone.utc).timestamp()
    else:
        event_value = None
        sort_value = 0.0
    return {
        "resource_type": resource_type,
        "subtype": subtype,
        "id": resource_id,
        "reference": reference,
        "title": title,
        "summary": summary,
        "branch": branch,
        "status": status,
        "owner": owner,
        "engagement_id": engagement_id,
        "event_at": event_value,
        "target_url": target_url,
        "_sort": sort_value,
    }


def _status_matches(filter_status: str | None, value: str | None) -> bool:
    return not filter_status or (value or "").upper() == filter_status.strip().upper()


def search_audit_records(
    db: Session,
    *,
    query_text: str | None = None,
    branch: str | None = None,
    engagement_id: int | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
    candidate_limit: int = MAX_CANDIDATES,
) -> dict[str, object]:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")

    requested_type = resource_type.strip().upper() if resource_type else None
    if requested_type and requested_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported resource_type")

    branch = normalize_branch(branch)
    term = query_text.strip() if query_text and query_text.strip() else None
    owner_value = owner.strip() if owner and owner.strip() else None
    status_value = status.strip().upper() if status and status.strip() else None
    start_dt, end_dt = _date_bounds(date_from, date_to)
    per_type_limit = min(max(candidate_limit, 1), MAX_CANDIDATES)
    results: list[dict[str, object]] = []

    def include(resource: str) -> bool:
        return requested_type in {None, resource}

    if include("ENGAGEMENT"):
        q = select(AuditEngagement).order_by(AuditEngagement.updated_at.desc(), AuditEngagement.id.desc())
        if branch:
            q = q.where(AuditEngagement.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditEngagement.id == engagement_id)
        if status_value:
            q = q.where(AuditEngagement.status == status_value)
        if start_dt:
            q = q.where(AuditEngagement.created_at >= start_dt)
        if end_dt:
            q = q.where(AuditEngagement.created_at < end_dt)
        match = _contains(
            [AuditEngagement.id, AuditEngagement.code, AuditEngagement.title, AuditEngagement.scope],
            term,
        )
        if match is not None:
            q = q.where(match)
        if owner_value:
            q = q.where(
                AuditEngagement.id.in_(
                    select(AuditEngagementAssignment.engagement_id).where(
                        AuditEngagementAssignment.user_id == owner_value
                    )
                )
            )
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="ENGAGEMENT",
                resource_id=row.id,
                reference=row.code,
                title=row.title,
                summary=row.scope,
                branch=row.branch,
                status=row.status,
                owner=row.created_by,
                engagement_id=row.id,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/audit-engagements?engagement_id={row.id}",
            ))

    if include("SAMPLE"):
        q = select(AuditSample).order_by(AuditSample.selected_at.desc(), AuditSample.id.desc())
        if branch:
            q = q.where(AuditSample.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditSample.engagement_id == engagement_id)
        if status_value:
            q = q.where(AuditSample.status == status_value)
        if owner_value:
            q = q.where(AuditSample.selected_by == owner_value)
        if start_dt:
            q = q.where(AuditSample.selected_at >= start_dt)
        if end_dt:
            q = q.where(AuditSample.selected_at < end_dt)
        match = _contains(
            [
                AuditSample.id,
                AuditSample.source_record_ref,
                AuditSample.selection_method,
                AuditSample.selection_reason,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="SAMPLE",
                resource_id=row.id,
                reference=row.source_record_ref,
                title=f"Audit sample {row.source_record_ref}",
                summary=row.selection_reason,
                branch=row.branch,
                status=row.status,
                owner=row.selected_by,
                engagement_id=row.engagement_id,
                event_at=row.selected_at,
                target_url=f"/ui/audit-sampling?engagement_id={row.engagement_id}",
            ))

    if include("WORKING_PAPER"):
        q = select(AuditWorkingPaper).order_by(AuditWorkingPaper.updated_at.desc(), AuditWorkingPaper.id.desc())
        if branch:
            q = q.where(AuditWorkingPaper.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditWorkingPaper.engagement_id == engagement_id)
        if status_value:
            q = q.where(AuditWorkingPaper.status == status_value)
        if owner_value:
            q = q.where(or_(
                AuditWorkingPaper.preparer_id == owner_value,
                AuditWorkingPaper.reviewer_id == owner_value,
            ))
        if start_dt:
            q = q.where(AuditWorkingPaper.created_at >= start_dt)
        if end_dt:
            q = q.where(AuditWorkingPaper.created_at < end_dt)
        match = _contains(
            [
                AuditWorkingPaper.id,
                AuditWorkingPaper.reference,
                AuditWorkingPaper.title,
                AuditWorkingPaper.audit_objective,
                AuditWorkingPaper.procedure_performed,
                AuditWorkingPaper.result_observation,
                AuditWorkingPaper.conclusion,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="WORKING_PAPER",
                resource_id=row.id,
                reference=row.reference,
                title=row.title,
                summary=row.conclusion or row.result_observation,
                branch=row.branch,
                status=row.status,
                owner=row.preparer_id,
                engagement_id=row.engagement_id,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/audit-working-papers?engagement_id={row.engagement_id}",
            ))

    if include("FINDING"):
        q = select(AuditFinding).order_by(AuditFinding.updated_at.desc(), AuditFinding.id.desc())
        if branch:
            q = q.where(AuditFinding.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditFinding.engagement_id == engagement_id)
        if status_value:
            q = q.where(AuditFinding.status == status_value)
        if owner_value:
            q = q.where(or_(AuditFinding.preparer_id == owner_value, AuditFinding.reviewer_id == owner_value))
        if start_dt:
            q = q.where(AuditFinding.created_at >= start_dt)
        if end_dt:
            q = q.where(AuditFinding.created_at < end_dt)
        match = _contains(
            [
                AuditFinding.id,
                AuditFinding.reference,
                AuditFinding.title,
                AuditFinding.condition,
                AuditFinding.criteria,
                AuditFinding.cause,
                AuditFinding.effect_risk,
                AuditFinding.recommendation,
                AuditFinding.severity,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="FINDING",
                resource_id=row.id,
                reference=row.reference,
                title=row.title,
                summary=row.effect_risk or row.recommendation,
                branch=row.branch,
                status=row.status,
                owner=row.preparer_id,
                engagement_id=row.engagement_id,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/audit-findings?engagement_id={row.engagement_id}",
            ))

    if include("MANAGEMENT_RESPONSE"):
        q = (
            select(ManagementResponse, AuditFinding.engagement_id, AuditFinding.reference)
            .join(AuditFinding, AuditFinding.id == ManagementResponse.finding_id)
            .order_by(ManagementResponse.updated_at.desc(), ManagementResponse.id.desc())
        )
        if branch:
            q = q.where(ManagementResponse.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditFinding.engagement_id == engagement_id)
        if status_value:
            q = q.where(ManagementResponse.status == status_value)
        if owner_value:
            q = q.where(or_(
                ManagementResponse.submitted_by == owner_value,
                ManagementResponse.reviewed_by == owner_value,
            ))
        if start_dt:
            q = q.where(ManagementResponse.created_at >= start_dt)
        if end_dt:
            q = q.where(ManagementResponse.created_at < end_dt)
        match = _contains(
            [
                ManagementResponse.id,
                AuditFinding.reference,
                ManagementResponse.response_text,
                ManagementResponse.position,
                ManagementResponse.review_note,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.execute(_limit(q, per_type_limit)).all())
        for row, engagement, finding_ref in rows:
            results.append(_result(
                resource_type="MANAGEMENT_RESPONSE",
                resource_id=row.id,
                reference=f"Response #{row.id} / {finding_ref}",
                title=f"Management response for {finding_ref}",
                summary=row.response_text,
                branch=row.branch,
                status=row.status,
                owner=row.submitted_by or row.reviewed_by,
                engagement_id=engagement,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/management-actions?finding_id={row.finding_id}",
            ))

    if include("ACTION_PLAN"):
        q = (
            select(CorrectiveActionPlan, AuditFinding.engagement_id, AuditFinding.reference)
            .join(AuditFinding, AuditFinding.id == CorrectiveActionPlan.finding_id)
            .order_by(CorrectiveActionPlan.updated_at.desc(), CorrectiveActionPlan.id.desc())
        )
        if branch:
            q = q.where(CorrectiveActionPlan.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditFinding.engagement_id == engagement_id)
        if status_value:
            q = q.where(CorrectiveActionPlan.status == status_value)
        if owner_value:
            q = q.where(or_(
                CorrectiveActionPlan.pic_user_id == owner_value,
                CorrectiveActionPlan.external_pic_name.ilike(f"%{owner_value}%"),
                CorrectiveActionPlan.created_by == owner_value,
                CorrectiveActionPlan.updated_by == owner_value,
            ))
        if start_dt:
            q = q.where(CorrectiveActionPlan.created_at >= start_dt)
        if end_dt:
            q = q.where(CorrectiveActionPlan.created_at < end_dt)
        match = _contains(
            [
                CorrectiveActionPlan.id,
                AuditFinding.reference,
                CorrectiveActionPlan.action_description,
                CorrectiveActionPlan.pic_user_id,
                CorrectiveActionPlan.external_pic_name,
                CorrectiveActionPlan.completion_notes,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.execute(_limit(q, per_type_limit)).all())
        for row, engagement, finding_ref in rows:
            owner_name = row.pic_user_id or row.external_pic_name or row.created_by
            results.append(_result(
                resource_type="ACTION_PLAN",
                resource_id=row.id,
                reference=f"Action #{row.id} / {finding_ref}",
                title=row.action_description[:255],
                summary=row.completion_notes,
                branch=row.branch,
                status=row.status,
                owner=owner_name,
                engagement_id=engagement,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/follow-up?action_plan_id={row.id}",
            ))

    if include("FOLLOW_UP"):
        progress_q = (
            select(CorrectiveActionProgressUpdate, CorrectiveActionPlan.finding_id, AuditFinding.engagement_id)
            .join(CorrectiveActionPlan, CorrectiveActionPlan.id == CorrectiveActionProgressUpdate.action_plan_id)
            .join(AuditFinding, AuditFinding.id == CorrectiveActionPlan.finding_id)
            .order_by(CorrectiveActionProgressUpdate.created_at.desc(), CorrectiveActionProgressUpdate.id.desc())
        )
        if branch:
            progress_q = progress_q.where(CorrectiveActionProgressUpdate.branch == branch)
        if engagement_id is not None:
            progress_q = progress_q.where(AuditFinding.engagement_id == engagement_id)
        if status_value and status_value not in {"PROGRESS", "UPDATED"}:
            progress_q = progress_q.where(False)
        if owner_value:
            progress_q = progress_q.where(CorrectiveActionProgressUpdate.submitted_by == owner_value)
        if start_dt:
            progress_q = progress_q.where(CorrectiveActionProgressUpdate.created_at >= start_dt)
        if end_dt:
            progress_q = progress_q.where(CorrectiveActionProgressUpdate.created_at < end_dt)
        match = _contains(
            [
                CorrectiveActionProgressUpdate.id,
                CorrectiveActionProgressUpdate.action_plan_id,
                CorrectiveActionProgressUpdate.update_text,
                CorrectiveActionProgressUpdate.submitted_by,
                CorrectiveActionProgressUpdate.progress_percent,
            ],
            term,
        )
        if match is not None:
            progress_q = progress_q.where(match)
        progress_rows = list(db.execute(_limit(progress_q, per_type_limit)).all())
        for row, finding_id, engagement in progress_rows:
            results.append(_result(
                resource_type="FOLLOW_UP",
                subtype="PROGRESS",
                resource_id=row.id,
                reference=f"Progress #{row.id} / Action #{row.action_plan_id}",
                title=f"Follow-up progress {row.progress_percent if row.progress_percent is not None else '-'}%",
                summary=row.update_text,
                branch=row.branch,
                status="PROGRESS",
                owner=row.submitted_by,
                engagement_id=engagement,
                event_at=row.created_at,
                target_url=f"/ui/follow-up?action_plan_id={row.action_plan_id}",
            ))

        verification_q = (
            select(CorrectiveActionVerification, CorrectiveActionPlan.finding_id, AuditFinding.engagement_id)
            .join(CorrectiveActionPlan, CorrectiveActionPlan.id == CorrectiveActionVerification.action_plan_id)
            .join(AuditFinding, AuditFinding.id == CorrectiveActionPlan.finding_id)
            .order_by(CorrectiveActionVerification.verified_at.desc(), CorrectiveActionVerification.id.desc())
        )
        if branch:
            verification_q = verification_q.where(CorrectiveActionVerification.branch == branch)
        if engagement_id is not None:
            verification_q = verification_q.where(AuditFinding.engagement_id == engagement_id)
        if status_value:
            verification_q = verification_q.where(CorrectiveActionVerification.result == status_value)
        if owner_value:
            verification_q = verification_q.where(CorrectiveActionVerification.verified_by == owner_value)
        if start_dt:
            verification_q = verification_q.where(CorrectiveActionVerification.verified_at >= start_dt)
        if end_dt:
            verification_q = verification_q.where(CorrectiveActionVerification.verified_at < end_dt)
        match = _contains(
            [
                CorrectiveActionVerification.id,
                CorrectiveActionVerification.action_plan_id,
                CorrectiveActionVerification.result,
                CorrectiveActionVerification.verification_note,
                CorrectiveActionVerification.verified_by,
            ],
            term,
        )
        if match is not None:
            verification_q = verification_q.where(match)
        verification_rows = list(db.execute(_limit(verification_q, per_type_limit)).all())
        for row, finding_id, engagement in verification_rows:
            results.append(_result(
                resource_type="FOLLOW_UP",
                subtype="VERIFICATION",
                resource_id=row.id,
                reference=f"Verification #{row.id} / Action #{row.action_plan_id}",
                title=f"Follow-up verification: {row.result}",
                summary=row.verification_note,
                branch=row.branch,
                status=row.result,
                owner=row.verified_by,
                engagement_id=engagement,
                event_at=row.verified_at,
                target_url=f"/ui/follow-up?action_plan_id={row.action_plan_id}",
            ))

    if include("EVIDENCE"):
        q = select(Document).order_by(Document.uploaded_at.desc(), Document.id.desc())
        if branch:
            q = q.where(Document.branch == branch)
        if engagement_id is not None:
            q = q.where(Document.engagement_id == engagement_id)
        if owner_value:
            q = q.where(Document.uploaded_by == owner_value)
        if status_value == "ARCHIVED":
            q = q.where(Document.archived_at.is_not(None))
        elif status_value == "ACTIVE":
            q = q.where(Document.archived_at.is_(None))
        elif status_value:
            q = q.where(False)
        if start_dt:
            q = q.where(Document.uploaded_at >= start_dt)
        if end_dt:
            q = q.where(Document.uploaded_at < end_dt)
        match = _contains(
            [
                Document.id,
                Document.file_name,
                Document.document_type,
                Document.evidence_classification,
                Document.evidence_source,
                Document.description,
                Document.file_hash,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="EVIDENCE",
                resource_id=row.id,
                reference=row.file_name,
                title=row.description or row.file_name,
                summary=f"{row.evidence_classification or row.document_type} · SHA256 {row.file_hash[:12]}…",
                branch=row.branch,
                status="ARCHIVED" if row.archived_at else "ACTIVE",
                owner=row.uploaded_by,
                engagement_id=row.engagement_id,
                event_at=row.uploaded_at,
                target_url=f"/ui/evidence-repository?engagement_id={row.engagement_id or ''}",
            ))

    if include("AUDIT_REPORT"):
        q = select(AuditReport).order_by(AuditReport.updated_at.desc(), AuditReport.id.desc())
        if branch:
            q = q.where(AuditReport.branch == branch)
        if engagement_id is not None:
            q = q.where(AuditReport.engagement_id == engagement_id)
        if status_value:
            q = q.where(AuditReport.status == status_value)
        if owner_value:
            q = q.where(or_(AuditReport.created_by == owner_value, AuditReport.approved_by == owner_value))
        if start_dt:
            q = q.where(AuditReport.created_at >= start_dt)
        if end_dt:
            q = q.where(AuditReport.created_at < end_dt)
        match = _contains(
            [
                AuditReport.id,
                AuditReport.finding_summary,
                AuditReport.conclusion,
                AuditReport.created_by,
                AuditReport.approved_by,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.scalars(_limit(q, per_type_limit)).all())
        for row in rows:
            results.append(_result(
                resource_type="AUDIT_REPORT",
                resource_id=row.id,
                reference=f"Audit Report #{row.id}",
                title=f"Audit report {row.period_start.isoformat()} – {row.period_end.isoformat()}",
                summary=row.finding_summary or row.conclusion,
                branch=row.branch,
                status=row.status,
                owner=row.created_by or row.approved_by,
                engagement_id=row.engagement_id,
                event_at=row.updated_at or row.created_at,
                target_url=f"/ui/audit-reports?report_id={row.id}",
            ))

    if include("SAP_BILLING"):
        q = (
            select(SAPBilling, ImportBatch.branch)
            .join(ImportBatch, ImportBatch.id == SAPBilling.import_batch_id)
            .order_by(SAPBilling.doc_date.desc(), SAPBilling.id.desc())
        )
        if branch:
            q = q.where(ImportBatch.branch == branch)
        if engagement_id is not None:
            q = q.where(False)
        if status_value or owner_value:
            q = q.where(False)
        if date_from:
            q = q.where(SAPBilling.doc_date >= date_from)
        if date_to:
            q = q.where(SAPBilling.doc_date <= date_to)
        match = _contains(
            [
                SAPBilling.id,
                SAPBilling.billing_document,
                SAPBilling.customer,
                SAPBilling.customer_account_name,
            ],
            term,
        )
        if match is not None:
            q = q.where(match)
        rows = list(db.execute(_limit(q, per_type_limit)).all())
        for row, row_branch in rows:
            results.append(_result(
                resource_type="SAP_BILLING",
                resource_id=row.id,
                reference=row.billing_document,
                title=row.customer_account_name or row.customer or row.billing_document,
                summary=f"Customer: {row.customer or '-'} · Nominal: {row.nominal}",
                branch=row_branch,
                status=None,
                owner=None,
                engagement_id=None,
                event_at=row.doc_date,
                target_url="/ui/uat-pasuruan",
            ))

    results.sort(key=lambda item: (item["_sort"], item["resource_type"], item["id"]), reverse=True)
    truncated = len(results) > candidate_limit
    if truncated:
        results = results[:candidate_limit]

    total = len(results)
    offset = (page - 1) * page_size
    page_rows = results[offset:offset + page_size]
    for item in page_rows:
        item.pop("_sort", None)

    return {
        "query": term,
        "filters": {
            "branch": branch,
            "engagement_id": engagement_id,
            "resource_type": requested_type,
            "status": status_value,
            "owner": owner_value,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "truncated": truncated,
        "results": page_rows,
    }


def _export_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return list(payload["results"])


def build_search_export(rows: list[dict[str, object]], fmt: str) -> tuple[bytes, str, str]:
    fmt = fmt.strip().lower()
    headers = [
        "resource_type", "subtype", "id", "reference", "title", "summary", "branch",
        "status", "owner", "engagement_id", "event_at", "target_url",
    ]
    if fmt == "csv":
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "audit_search.csv"
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Audit Search"
        ws.append(headers)
        for row in rows:
            ws.append([row.get(key) for key in headers])
        ws.freeze_panes = "A2"
        widths = {
            "A": 22, "B": 18, "C": 10, "D": 30, "E": 42, "F": 60,
            "G": 18, "H": 24, "I": 24, "J": 14, "K": 28, "L": 45,
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = cell.alignment.copy(vertical="top", wrap_text=True)
        output = BytesIO()
        wb.save(output)
        return (
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "audit_search.xlsx",
        )
    raise HTTPException(status_code=400, detail="format must be csv or xlsx")


def _html() -> str:
    options = "".join(f"<option>{escape(x)}</option>" for x in RESOURCE_TYPES)
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global Audit Search</title><style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:#fff;padding:18px 24px}}main{{max-width:1250px;margin:auto;padding:20px}}
.panel{{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}
input,select,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}button{{background:#1f6feb;color:#fff;font-weight:700}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}.muted{{color:#64748b}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Global Audit Search</h1><p>Authorized search across audit records, evidence, follow-up and SAP identifiers.</p></header><main>
<section class="panel"><div class="grid">
<input id="token" type="password" placeholder="Bearer token"><input id="q" placeholder="Search reference, text, customer..."><input id="branch" placeholder="Branch (ADMIN: blank = all)">
<input id="engagement" type="number" placeholder="Engagement ID"><select id="type"><option value="">All resource types</option>{options}</select><input id="status" placeholder="Status"><input id="owner" placeholder="Owner / PIC">
<input id="from" type="date"><input id="to" type="date"><button id="load">Search</button><button id="csv">Export CSV</button><button id="xlsx">Export XLSX</button>
</div></section>
<section class="panel"><div id="summary" class="muted"></div><table><thead><tr><th>Type</th><th>Reference</th><th>Title</th><th>Branch</th><th>Status</th><th>Owner</th><th>Date</th><th>Open</th></tr></thead><tbody id="rows"><tr><td colspan="8">Belum dimuat.</td></tr></tbody></table></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';
const initial=new URLSearchParams(window.location.search);if(initial.get('q'))document.getElementById('q').value=initial.get('q');
function headers(){{const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {{Authorization:'Bearer '+v}}}}
function params(){{const p=new URLSearchParams();for(const [id,key] of [['q','q'],['branch','branch'],['engagement','engagement_id'],['type','resource_type'],['status','status'],['owner','owner'],['from','date_from'],['to','date_to']]){{const v=document.getElementById(id).value.trim();if(v)p.set(key,v)}}return p}}
async function load(){{const r=await fetch('/search?'+params(),{{headers:headers()}});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('summary').textContent='Total '+x.total+(x.truncated?' (capped)':'');document.getElementById('rows').innerHTML=(x.results||[]).map(v=>'<tr><td>'+v.resource_type+(v.subtype?' / '+v.subtype:'')+'</td><td>'+v.reference+'</td><td>'+v.title+'</td><td>'+(v.branch||'-')+'</td><td>'+(v.status||'-')+'</td><td>'+(v.owner||'-')+'</td><td>'+(v.event_at||'-')+'</td><td><a href="'+v.target_url+'">Open</a></td></tr>').join('')||'<tr><td colspan="8">Tidak ada hasil.</td></tr>'}}
async function exp(fmt){{const p=params();p.set('format',fmt);const r=await fetch('/search/export?'+p,{{headers:headers()}});if(!r.ok){{const x=await r.json();throw new Error(x.detail||JSON.stringify(x))}}const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='audit_search.'+fmt;a.click();URL.revokeObjectURL(u)}}
document.getElementById('load').onclick=()=>load().catch(e=>alert(e.message));document.getElementById('csv').onclick=()=>exp('csv').catch(e=>alert(e.message));document.getElementById('xlsx').onclick=()=>exp('xlsx').catch(e=>alert(e.message));if(initial.get('q')&&token.value)load().catch(()=>{});
</script></body></html>"""


@router.get("/ui/search", response_class=HTMLResponse)
def search_ui():
    return HTMLResponse(_html())


@router.get("/search")
def global_search(
    q: str | None = None,
    branch: str | None = None,
    engagement_id: int | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return search_audit_records(
        db,
        query_text=q,
        branch=scoped_branch(user, branch),
        engagement_id=engagement_id,
        resource_type=resource_type,
        status=status,
        owner=owner,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/search/export")
def export_global_search(
    format: str = "csv",
    q: str | None = None,
    branch: str | None = None,
    engagement_id: int | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    payload = search_audit_records(
        db,
        query_text=q,
        branch=scoped_branch(user, branch),
        engagement_id=engagement_id,
        resource_type=resource_type,
        status=status,
        owner=owner,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=MAX_PAGE_SIZE,
        candidate_limit=MAX_EXPORT_ROWS + 1,
    )
    # search_audit_records paginates at MAX_PAGE_SIZE, so rebuild all authorized
    # export rows in deterministic chunks to preserve active filters.
    total = int(payload["total"])
    if total > MAX_EXPORT_ROWS or payload["truncated"]:
        raise HTTPException(
            status_code=413,
            detail=f"Export exceeds {MAX_EXPORT_ROWS} rows; narrow the active filters",
        )
    rows: list[dict[str, object]] = []
    pages = (total + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE if total else 0
    for page_number in range(1, pages + 1):
        page_payload = search_audit_records(
            db,
            query_text=q,
            branch=scoped_branch(user, branch),
            engagement_id=engagement_id,
            resource_type=resource_type,
            status=status,
            owner=owner,
            date_from=date_from,
            date_to=date_to,
            page=page_number,
            page_size=MAX_PAGE_SIZE,
            candidate_limit=MAX_EXPORT_ROWS + 1,
        )
        rows.extend(page_payload["results"])

    content, media_type, filename = build_search_export(rows, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def register_global_search_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
