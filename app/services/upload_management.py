from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, scoped_branch, write_branch
from app.database import SessionLocal
from app.models import (
    BillingReconciliation,
    ControlEvidenceDetection,
    Document,
    EvidenceResourceLink,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
    SPJ,
    VouchingResult,
)
from app.services.branch_master import ensure_branch_catalog

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _batch_for_user(db: Session, batch_id: int, user: CurrentUser) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="SAP import batch not found")
    ensure_branch_access(user, batch.branch)
    return batch


def _document_for_user(db: Session, document_id: int, user: CurrentUser) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Evidence document not found")
    ensure_branch_access(user, document.branch)
    return document


def _sap_downstream_count(db: Session, batch_id: int) -> int:
    value = db.scalar(
        select(func.count(BillingReconciliation.id))
        .select_from(BillingReconciliation)
        .join(SAPBilling, BillingReconciliation.sap_billing_id == SAPBilling.id)
        .where(SAPBilling.import_batch_id == batch_id)
    )
    return int(value or 0)


def _document_downstream_count(db: Session, document_id: int) -> int:
    physical_id = db.scalar(select(PhysicalBilling.id).where(PhysicalBilling.document_id == document_id))
    spj_id = db.scalar(select(SPJ.id).where(SPJ.document_id == document_id))

    count = 0
    if physical_id is not None:
        count += int(
            db.scalar(
                select(func.count(BillingReconciliation.id)).where(
                    BillingReconciliation.physical_billing_id == physical_id
                )
            )
            or 0
        )
        count += int(
            db.scalar(select(func.count(VouchingResult.id)).where(VouchingResult.billing_id == physical_id))
            or 0
        )
    if spj_id is not None:
        count += int(
            db.scalar(select(func.count(VouchingResult.id)).where(VouchingResult.spj_id == spj_id))
            or 0
        )

    count += int(
        db.scalar(
            select(func.count(EvidenceResourceLink.id)).where(EvidenceResourceLink.document_id == document_id)
        )
        or 0
    )
    count += int(
        db.scalar(select(func.count(Document.id)).where(Document.supersedes_document_id == document_id))
        or 0
    )
    return count


def _recent_items(db: Session, user: CurrentUser, limit: int) -> list[dict[str, object]]:
    branch = scoped_branch(user)
    batch_stmt = select(ImportBatch).order_by(ImportBatch.uploaded_at.desc()).limit(limit)
    document_stmt = select(Document).order_by(Document.uploaded_at.desc()).limit(limit)
    if branch:
        batch_stmt = batch_stmt.where(ImportBatch.branch == branch)
        document_stmt = document_stmt.where(Document.branch == branch)

    items: list[dict[str, object]] = []
    for batch in db.scalars(batch_stmt):
        items.append(
            {
                "kind": "SAP",
                "id": batch.id,
                "file_name": batch.file_name,
                "branch": batch.branch,
                "uploaded_at": batch.uploaded_at,
                "period": batch.period,
                "status": batch.status,
                "total_records": batch.total_records,
                "document_type": None,
                "description": None,
            }
        )
    for document in db.scalars(document_stmt):
        items.append(
            {
                "kind": "EVIDENCE",
                "id": document.id,
                "file_name": document.file_name,
                "branch": document.branch,
                "uploaded_at": document.uploaded_at,
                "period": None,
                "status": "UPLOADED",
                "total_records": None,
                "document_type": document.document_type,
                "description": document.description,
            }
        )
    items.sort(key=lambda row: row["uploaded_at"], reverse=True)
    return items[:limit]


@router.get("/uploads/recent")
def recent_uploads(
    limit: int = 50,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    safe_limit = min(max(limit, 1), 100)
    return {"items": _recent_items(db, user, safe_limit)}


@router.patch("/uploads/sap/{batch_id}")
def edit_sap_upload(
    batch_id: int,
    branch: str | None = None,
    period: date | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    batch = _batch_for_user(db, batch_id, user)
    old_branch = batch.branch
    old_period = batch.period

    target_branch = old_branch
    if branch is not None:
        target_branch = ensure_branch_catalog(db, write_branch(user, branch))

    changed = target_branch != old_branch or (period is not None and period != old_period)
    if changed and _sap_downstream_count(db, batch.id):
        raise HTTPException(
            status_code=409,
            detail="SAP upload sudah dipakai dalam rekonsiliasi dan tidak dapat diedit. Gunakan correction workflow.",
        )

    batch.branch = target_branch
    if period is not None:
        batch.period = period
    record_audit(
        db,
        entity_type="IMPORT_BATCH",
        entity_id=batch.id,
        action="SAP_IMPORT_EDIT",
        actor=user.user_id,
        status_to=batch.status,
        branch=batch.branch,
        metadata={
            "old_branch": old_branch,
            "new_branch": batch.branch,
            "old_period": old_period.isoformat() if old_period else None,
            "new_period": batch.period.isoformat() if batch.period else None,
        },
    )
    db.commit()
    return {
        "id": batch.id,
        "branch": batch.branch,
        "period": batch.period,
        "status": batch.status,
        "message": "SAP upload berhasil diperbarui.",
    }


@router.delete("/uploads/sap/{batch_id}")
def delete_sap_upload(
    batch_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    batch = _batch_for_user(db, batch_id, user)
    if _sap_downstream_count(db, batch.id):
        raise HTTPException(
            status_code=409,
            detail="SAP upload sudah dipakai dalam rekonsiliasi dan tidak dapat dihapus.",
        )

    row_count = int(
        db.scalar(select(func.count(SAPBilling.id)).where(SAPBilling.import_batch_id == batch.id)) or 0
    )
    metadata = {"file_name": batch.file_name, "sap_rows_deleted": row_count}
    try:
        db.execute(delete(SAPBilling).where(SAPBilling.import_batch_id == batch.id))
        db.execute(delete(ImportBatch).where(ImportBatch.id == batch.id))
        record_audit(
            db,
            entity_type="IMPORT_BATCH",
            entity_id=batch.id,
            action="SAP_IMPORT_DELETE",
            actor=user.user_id,
            branch=batch.branch,
            metadata=metadata,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="SAP upload masih terhubung ke proses audit lain dan tidak dapat dihapus.",
        ) from exc
    return {"deleted": True, "id": batch_id, **metadata}


@router.patch("/uploads/evidence/{document_id}")
def edit_evidence_upload(
    document_id: int,
    branch: str | None = None,
    description: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    document = _document_for_user(db, document_id, user)
    old_branch = document.branch
    old_description = document.description

    target_branch = old_branch
    if branch is not None:
        target_branch = ensure_branch_catalog(db, write_branch(user, branch))

    if target_branch != old_branch and _document_downstream_count(db, document.id):
        raise HTTPException(
            status_code=409,
            detail="Evidence sudah dipakai dalam rekonsiliasi/vouching/audit dan cabangnya tidak dapat diubah.",
        )

    document.branch = target_branch
    if description is not None:
        document.description = description.strip() or None

    if target_branch != old_branch:
        db.execute(
            update(ControlEvidenceDetection)
            .where(ControlEvidenceDetection.document_id == document.id)
            .values(branch=target_branch)
        )

    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=document.id,
        action="DOCUMENT_EDIT",
        actor=user.user_id,
        branch=document.branch,
        metadata={
            "document_type": document.document_type,
            "file_name": document.file_name,
            "old_branch": old_branch,
            "new_branch": document.branch,
            "old_description": old_description,
            "new_description": document.description,
        },
    )
    db.commit()
    return {
        "id": document.id,
        "branch": document.branch,
        "description": document.description,
        "document_type": document.document_type,
        "message": "Evidence berhasil diperbarui.",
    }


@router.delete("/uploads/evidence/{document_id}")
def delete_evidence_upload(
    document_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    document = _document_for_user(db, document_id, user)
    if _document_downstream_count(db, document.id):
        raise HTTPException(
            status_code=409,
            detail="Evidence sudah dipakai dalam rekonsiliasi/vouching/audit dan tidak dapat dihapus.",
        )

    metadata = {
        "file_name": document.file_name,
        "document_type": document.document_type,
        "storage_path_retained_for_audit_recovery": document.storage_path,
    }
    try:
        db.execute(delete(Document).where(Document.id == document.id))
        record_audit(
            db,
            entity_type="DOCUMENT",
            entity_id=document.id,
            action="DOCUMENT_DELETE",
            actor=user.user_id,
            branch=document.branch,
            metadata=metadata,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Evidence masih terhubung ke working paper/finding/action plan dan tidak dapat dihapus.",
        ) from exc
    return {
        "deleted": True,
        "id": document_id,
        "message": "Evidence dihapus dari proses aplikasi. Raw storage dipertahankan untuk audit recovery.",
    }


def register_upload_management_routes(app) -> None:
    global _REGISTERED
    if any(getattr(route, "path", None) == "/uploads/recent" for route in app.routes):
        _REGISTERED = True
        return
    app.include_router(router)
    _REGISTERED = True
