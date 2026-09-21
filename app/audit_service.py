from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.branch_access import branch_for_actor, normalize_branch


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
    return entry


def list_audit_trail(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    limit: int = 100,
    branch: str | None = None,
) -> list[AuditTrail]:
    query = select(AuditTrail).order_by(AuditTrail.created_at.desc(), AuditTrail.id.desc()).limit(limit)
    if entity_type:
        query = query.where(AuditTrail.entity_type == entity_type.upper())
    if entity_id is not None:
        query = query.where(AuditTrail.entity_id == entity_id)
    if branch is not None:
        query = query.where(AuditTrail.branch == normalize_branch(branch))
    return list(db.scalars(query).all())
