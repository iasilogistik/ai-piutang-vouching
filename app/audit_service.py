from __future__ import annotations

import logging

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.branch_access import branch_for_actor, normalize_branch

logger = logging.getLogger(__name__)


def record_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    actor: str | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    remarks: str | None = None,
    metadata: dict[str, Any] | None = None,
    branch: str | None = None,
) -> AuditTrail:
    entry = AuditTrail(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        status_from=status_from,
        status_to=status_to,
        actor=actor,
        branch=normalize_branch(branch) or branch_for_actor(db, actor),
        remarks=remarks,
        metadata_json=metadata,
    )
    db.add(entry)
    db.flush()

    # Notifications are supplemental. A notification failure is isolated in a
    # savepoint and must never roll back the audit business transaction.
    try:
        from app.services.notifications import emit_from_audit_event

        with db.begin_nested():
            emit_from_audit_event(db, entry)
    except Exception:
        logger.exception("notification delivery failed for audit trail id=%s", entry.id)

    return entry


def list_audit_trail(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    branch: str | None = None,
) -> list[AuditTrail]:
    query = select(AuditTrail).order_by(AuditTrail.created_at.desc(), AuditTrail.id.desc()).limit(limit)
    if entity_type:
        query = query.where(AuditTrail.entity_type == entity_type.upper())
    if entity_id is not None:
        query = query.where(AuditTrail.entity_id == entity_id)
    if actor:
        query = query.where(AuditTrail.actor == actor.strip())
    if action:
        query = query.where(AuditTrail.action == action.strip().upper())
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        query = query.where(AuditTrail.created_at >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query = query.where(AuditTrail.created_at < end)
    if branch is not None:
        query = query.where(AuditTrail.branch == normalize_branch(branch))
    return list(db.scalars(query).all())
