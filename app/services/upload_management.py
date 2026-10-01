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
    AuditFindingEvidence,
    AuditSample,
    AuditWorkflowCase,
    AuditWorkingPaperEvidence,
    BillingReconciliation,
    ControlEvidenceDetection,
    CorrectiveActionEvidence,
    Document,
    DocumentControlEvidence,
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


def _document_delete_policies(
    db: Session,
    documents: list[Document],
) -> dict[int, dict[str, object]]:
    if not documents:
        return {}

    doc_ids = [document.id for document in documents]
    reasons: dict[int, list[str]] = {document.id: [] for document in documents}
    correction_notes: dict[int, list[str]] = {document.id: [] for document in documents}

    def add_reason(document_id: int | None, reason: str) -> None:
        if document_id is None or document_id not in reasons:
            return
        if reason not in reasons[document_id]:
            reasons[document_id].append(reason)

    def add_correction_note(document_id: int | None, note: str) -> None:
        if document_id is None or document_id not in correction_notes:
            return
        if note not in correction_notes[document_id]:
            correction_notes[document_id].append(note)

    for document in documents:
        if document.archived_at is not None:
            add_reason(document.id, "Evidence sudah diarsipkan.")
        if document.supersedes_document_id is not None:
            add_reason(document.id, "Evidence merupakan bagian dari version history.")

    superseded_ids = db.scalars(
        select(Document.supersedes_document_id).where(Document.supersedes_document_id.in_(doc_ids))
    ).all()
    for document_id in superseded_ids:
        add_reason(document_id, "Evidence sudah memiliki versi pengganti.")

    physical_by_doc = {
        document_id: physical_id
        for document_id, physical_id in db.execute(
            select(PhysicalBilling.document_id, PhysicalBilling.id).where(
                PhysicalBilling.document_id.in_(doc_ids)
            )
        ).all()
    }
    spj_by_doc = {
        document_id: spj_id
        for document_id, spj_id in db.execute(
            select(SPJ.document_id, SPJ.id).where(SPJ.document_id.in_(doc_ids))
        ).all()
    }
    control_rows = list(
        db.scalars(
            select(DocumentControlEvidence).where(DocumentControlEvidence.document_id.in_(doc_ids))
        ).all()
    )
    control_by_doc = {row.document_id: row.id for row in control_rows}

    doc_by_physical = {row_id: document_id for document_id, row_id in physical_by_doc.items()}
    doc_by_spj = {row_id: document_id for document_id, row_id in spj_by_doc.items()}
    doc_by_control = {row_id: document_id for document_id, row_id in control_by_doc.items()}

    for control in control_rows:
        if control.review_status is not None or control.reviewer_id is not None or control.reviewed_at is not None:
            add_correction_note(
                control.document_id,
                "Control Evidence sudah direview; keputusan review akan di-reset bila evidence dihapus.",
            )

    for document_id, resource_type in db.execute(
        select(EvidenceResourceLink.document_id, EvidenceResourceLink.resource_type).where(
            EvidenceResourceLink.document_id.in_(doc_ids)
        )
    ).all():
        add_reason(document_id, f"Evidence terhubung ke {resource_type}.")

    control_ids = list(doc_by_control)
    for model, label in (
        (AuditWorkingPaperEvidence, "Working Paper"),
        (AuditFindingEvidence, "Finding"),
        (CorrectiveActionEvidence, "Action Plan"),
    ):
        clauses = [model.document_id.in_(doc_ids)]
        if control_ids:
            clauses.append(model.control_evidence_id.in_(control_ids))
        for document_id, control_evidence_id in db.execute(
            select(model.document_id, model.control_evidence_id).where(or_(*clauses))
        ).all():
            target_document_id = document_id or doc_by_control.get(control_evidence_id)
            add_reason(target_document_id, f"Evidence terhubung ke {label}.")

    vouch_clauses = []
    if physical_by_doc:
        vouch_clauses.append(VouchingResult.billing_id.in_(list(doc_by_physical)))
    if spj_by_doc:
        vouch_clauses.append(VouchingResult.spj_id.in_(list(doc_by_spj)))
    if control_ids:
        vouch_clauses.append(VouchingResult.control_evidence_id.in_(control_ids))

    vouch_rows: list[VouchingResult] = []
    vouch_targets: dict[int, set[int]] = {}
    if vouch_clauses:
        vouch_rows = list(db.scalars(select(VouchingResult).where(or_(*vouch_clauses))).all())
        for row in vouch_rows:
            targets: set[int] = set()
            if row.billing_id in doc_by_physical:
                targets.add(doc_by_physical[row.billing_id])
            if row.spj_id in doc_by_spj:
                targets.add(doc_by_spj[row.spj_id])
            if row.control_evidence_id in doc_by_control:
                targets.add(doc_by_control[row.control_evidence_id])
            vouch_targets[row.id] = targets
            if (
                row.manual_review_status is not None
                or row.reviewer_id is not None
                or row.reviewed_at is not None
            ):
                for document_id in targets:
                    add_correction_note(
                        document_id,
                        "Hasil vouching/reconciliation sudah direview; keputusan MATCH/PASS manual akan di-reset bila evidence dihapus.",
                    )

    vouch_ids = list(vouch_targets)
    workflow_clauses = []
    if vouch_ids:
        workflow_clauses.append(AuditWorkflowCase.vouching_result_id.in_(vouch_ids))
    if control_ids:
        workflow_clauses.append(AuditWorkflowCase.control_evidence_id.in_(control_ids))
    if workflow_clauses:
        for vouching_result_id, control_evidence_id in db.execute(
            select(
                AuditWorkflowCase.vouching_result_id,
                AuditWorkflowCase.control_evidence_id,
            ).where(or_(*workflow_clauses))
        ).all():
            targets = set(vouch_targets.get(vouching_result_id, set()))
            if control_evidence_id in doc_by_control:
                targets.add(doc_by_control[control_evidence_id])
            for document_id in targets:
                add_reason(document_id, "Evidence sudah masuk Audit Workflow.")

    sample_clauses = []
    if vouch_ids:
        sample_clauses.append(AuditSample.vouching_result_id.in_(vouch_ids))
    if control_ids:
        sample_clauses.append(AuditSample.control_evidence_id.in_(control_ids))
    if sample_clauses:
        for vouching_result_id, control_evidence_id in db.execute(
            select(AuditSample.vouching_result_id, AuditSample.control_evidence_id).where(
                or_(*sample_clauses)
            )
        ).all():
            targets = set(vouch_targets.get(vouching_result_id, set()))
            if control_evidence_id in doc_by_control:
                targets.add(doc_by_control[control_evidence_id])
            for document_id in targets:
                add_reason(document_id, "Evidence sudah dipakai pada audit sampling.")

    return {
        document.id: {
            "delete_allowed": not reasons[document.id],
            "delete_reason": " ".join(reasons[document.id][:3]) or None,
            "delete_requires_reset": bool(correction_notes[document.id]),
            "delete_reset_note": " ".join(correction_notes[document.id][:3]) or None,
        }
        for document in documents
    }


def _automatic_document_dependencies(db: Session, document_id: int) -> dict[str, object]:
    physical_id = db.scalar(
        select(PhysicalBilling.id).where(PhysicalBilling.document_id == document_id)
    )
    spj_id = db.scalar(select(SPJ.id).where(SPJ.document_id == document_id))
    control_id = db.scalar(
        select(DocumentControlEvidence.id).where(DocumentControlEvidence.document_id == document_id)
    )

    vouch_clauses = []
    if physical_id is not None:
        vouch_clauses.append(VouchingResult.billing_id == physical_id)
    if spj_id is not None:
        vouch_clauses.append(VouchingResult.spj_id == spj_id)
    if control_id is not None:
        vouch_clauses.append(VouchingResult.control_evidence_id == control_id)

    vouch_rows = (
        list(db.scalars(select(VouchingResult).where(or_(*vouch_clauses))).all())
        if vouch_clauses
        else []
    )
    vouching_ids = [row.id for row in vouch_rows]

    # Deleting an SPJ can invalidate a MATCH reconciliation that was manually
    # confirmed through the linked billing. Reset those reconciliation rows too,
    # otherwise the remaining billing would incorrectly stay MATCH after its SPJ
    # evidence was deleted.
    impacted_billing_ids: set[int] = set()
    if physical_id is not None:
        impacted_billing_ids.add(physical_id)
    impacted_billing_ids.update(
        row.billing_id for row in vouch_rows if row.billing_id is not None
    )

    reconciliation_ids = (
        list(
            db.scalars(
                select(BillingReconciliation.id).where(
                    BillingReconciliation.physical_billing_id.in_(impacted_billing_ids)
                )
            ).all()
        )
        if impacted_billing_ids
        else []
    )

    detection_count = int(
        db.scalar(
            select(func.count(ControlEvidenceDetection.id)).where(
                ControlEvidenceDetection.document_id == document_id
            )
        )
        or 0
    )

    manual_review_reset_count = sum(
        1
        for row in vouch_rows
        if row.manual_review_status is not None
        or row.reviewer_id is not None
        or row.reviewed_at is not None
    )
    control_row = db.get(DocumentControlEvidence, control_id) if control_id is not None else None
    if control_row is not None and (
        control_row.review_status is not None
        or control_row.reviewer_id is not None
        or control_row.reviewed_at is not None
    ):
        manual_review_reset_count += 1

    return {
        "physical_id": physical_id,
        "spj_id": spj_id,
        "control_id": control_id,
        "reconciliation_ids": reconciliation_ids,
        "vouching_ids": vouching_ids,
        "detection_count": detection_count,
        "manual_review_reset_count": manual_review_reset_count,
    }


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
    documents = list(db.scalars(document_stmt).all())
    delete_policies = _document_delete_policies(db, documents)
    for document in documents:
        policy = delete_policies.get(
            document.id,
            {
                "delete_allowed": True,
                "delete_reason": None,
                "delete_requires_reset": False,
                "delete_reset_note": None,
            },
        )
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
                "delete_allowed": policy["delete_allowed"],
                "delete_reason": policy["delete_reason"],
                "delete_requires_reset": policy["delete_requires_reset"],
                "delete_reset_note": policy["delete_reset_note"],
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
    policy = _document_delete_policies(db, [document])[document.id]
    if not policy["delete_allowed"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Evidence dikunci karena sudah dipakai pada proses audit final/terhubung. "
                + str(policy["delete_reason"] or "")
            ).strip(),
        )

    dependencies = _automatic_document_dependencies(db, document.id)
    reconciliation_ids = list(dependencies["reconciliation_ids"])
    vouching_ids = list(dependencies["vouching_ids"])

    metadata = {
        "file_name": document.file_name,
        "document_type": document.document_type,
        "storage_path_retained_for_audit_recovery": document.storage_path,
        "automatic_reconciliation_rows_reset": len(reconciliation_ids),
        "automatic_vouching_rows_reset": len(vouching_ids),
        "control_detections_deleted": dependencies["detection_count"],
        "manual_review_rows_reset": dependencies["manual_review_reset_count"],
    }
    try:
        if vouching_ids:
            db.execute(delete(VouchingResult).where(VouchingResult.id.in_(vouching_ids)))
        if reconciliation_ids:
            db.execute(
                delete(BillingReconciliation).where(
                    BillingReconciliation.id.in_(reconciliation_ids)
                )
            )
        db.execute(
            delete(ControlEvidenceDetection).where(
                ControlEvidenceDetection.document_id == document.id
            )
        )
        if dependencies["control_id"] is not None:
            db.execute(
                delete(DocumentControlEvidence).where(
                    DocumentControlEvidence.id == dependencies["control_id"]
                )
            )
        if dependencies["physical_id"] is not None:
            db.execute(
                delete(PhysicalBilling).where(
                    PhysicalBilling.id == dependencies["physical_id"]
                )
            )
        if dependencies["spj_id"] is not None:
            db.execute(delete(SPJ).where(SPJ.id == dependencies["spj_id"]))

        db.execute(delete(Document).where(Document.id == document.id))
        record_audit(
            db,
            entity_type="DOCUMENT",
            entity_id=document.id,
            action="DOCUMENT_DELETE_CORRECTION",
            actor=user.user_id,
            branch=document.branch,
            metadata=metadata,
            remarks=(
                "Wrong-upload correction. Automated reconciliation/vouching artifacts were reset; "
                "raw storage retained for audit recovery."
            ),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Evidence masih terhubung ke proses audit manual seperti working paper, finding, "
                "sampling, workflow, atau action plan dan tidak dapat dihapus."
            ),
        ) from exc

    return {
        "deleted": True,
        "id": document_id,
        "automatic_reconciliation_rows_reset": len(reconciliation_ids),
        "automatic_vouching_rows_reset": len(vouching_ids),
        "manual_review_rows_reset": dependencies["manual_review_reset_count"],
        "message": (
            "Evidence berhasil dihapus sebagai correction. Status MATCH/PASS, hasil review, "
            "reconciliation/vouching, dan control evidence yang terkait sudah di-reset dan perlu "
            "dijalankan ulang setelah evidence yang benar di-upload. Raw storage dipertahankan "
            "untuk audit recovery."
        ),
    }


def register_upload_management_routes(app) -> None:
    global _REGISTERED
    if any(getattr(route, "path", None) == "/uploads/recent" for route in app.routes):
        _REGISTERED = True
        return
    app.include_router(router)
    _REGISTERED = True
