from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.config import settings
from app.database import SessionLocal
from app.models import (
    AuditEngagement,
    AuditFinding,
    AuditReport,
    AuditSample,
    AuditWorkingPaper,
    CorrectiveActionPlan,
    Document,
    EvidenceResourceLink,
)
from app.services.storage import download_bytes

router = APIRouter()
_REGISTERED = False

RESOURCE_TYPES = {"SAMPLE", "WORKING_PAPER", "FINDING", "ACTION_PLAN", "FOLLOW_UP", "AUDIT_REPORT"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _document_for_user(db: Session, document_id: int, user: CurrentUser) -> Document:
    row = db.get(Document, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence document not found")
    ensure_branch_access(user, row.branch)
    return row


def _resource_context(db: Session, resource_type: str, resource_id: int) -> tuple[str, int | None]:
    resource_type = resource_type.strip().upper()
    if resource_type == "SAMPLE":
        row = db.get(AuditSample, resource_id)
        branch = row.branch if row else None
        engagement_id = row.engagement_id if row else None
    elif resource_type == "WORKING_PAPER":
        row = db.get(AuditWorkingPaper, resource_id)
        branch = row.branch if row else None
        engagement_id = row.engagement_id if row else None
    elif resource_type == "FINDING":
        row = db.get(AuditFinding, resource_id)
        branch = row.branch if row else None
        engagement_id = row.engagement_id if row else None
    elif resource_type in {"ACTION_PLAN", "FOLLOW_UP"}:
        row = db.get(CorrectiveActionPlan, resource_id)
        branch = row.branch if row else None
        finding = db.get(AuditFinding, row.finding_id) if row else None
        engagement_id = finding.engagement_id if finding else None
    elif resource_type == "AUDIT_REPORT":
        row = db.get(AuditReport, resource_id)
        branch = row.branch if row else None
        engagement_id = row.engagement_id if row else None
    else:
        raise HTTPException(status_code=400, detail="Unsupported resource_type")

    if row is None or normalize_branch(branch) is None:
        raise HTTPException(status_code=404, detail="Audit resource not found")
    return normalize_branch(branch), engagement_id


def evidence_payload(db: Session, row: Document) -> dict[str, object]:
    links = list(
        db.scalars(
            select(EvidenceResourceLink)
            .where(EvidenceResourceLink.document_id == row.id)
            .order_by(EvidenceResourceLink.linked_at, EvidenceResourceLink.id)
        ).all()
    )
    replacements = list(
        db.scalars(
            select(Document)
            .where(Document.supersedes_document_id == row.id)
            .order_by(Document.evidence_version_number, Document.id)
        ).all()
    )
    return {
        "id": row.id,
        "file_name": row.file_name,
        "file_type": row.file_type,
        "document_type": row.document_type,
        "file_hash": row.file_hash,
        "storage_path": row.storage_path,
        "uploaded_by": row.uploaded_by,
        "branch": row.branch,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "engagement_id": row.engagement_id,
        "evidence_classification": row.evidence_classification,
        "evidence_source": row.evidence_source,
        "description": row.description,
        "file_size_bytes": row.file_size_bytes,
        "mime_type": row.mime_type,
        "evidence_version_number": row.evidence_version_number,
        "supersedes_document_id": row.supersedes_document_id,
        "replacement_document_ids": [x.id for x in replacements],
        "archived": row.archived_at is not None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by": row.archived_by,
        "archive_reason": row.archive_reason,
        "links": [
            {
                "id": x.id,
                "resource_type": x.resource_type,
                "resource_id": x.resource_id,
                "engagement_id": x.engagement_id,
                "linked_by": x.linked_by,
                "linked_at": x.linked_at.isoformat() if x.linked_at else None,
            }
            for x in links
        ],
    }


def update_evidence_metadata(
    db: Session,
    row: Document,
    *,
    engagement_id: int | None,
    evidence_classification: str | None,
    evidence_source: str | None,
    description: str | None,
    user: CurrentUser,
) -> Document:
    ensure_branch_access(user, row.branch)
    if row.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived evidence metadata cannot be changed")

    if engagement_id is not None:
        engagement = db.get(AuditEngagement, engagement_id)
        if engagement is None or normalize_branch(engagement.branch) != normalize_branch(row.branch):
            raise HTTPException(status_code=404, detail="Audit engagement not found")
        row.engagement_id = engagement.id

    if evidence_classification is not None:
        row.evidence_classification = evidence_classification.strip().upper() or None
    if evidence_source is not None:
        row.evidence_source = evidence_source.strip() or None
    if description is not None:
        row.description = description.strip() or None

    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=row.id,
        action="EVIDENCE_METADATA_UPDATE",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "engagement_id": row.engagement_id,
            "classification": row.evidence_classification,
            "source": row.evidence_source,
        },
    )
    db.flush()
    return row


def link_evidence(
    db: Session,
    row: Document,
    *,
    resource_type: str,
    resource_id: int,
    user: CurrentUser,
) -> EvidenceResourceLink:
    ensure_branch_access(user, row.branch)
    if row.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived evidence cannot receive new links")

    resource_type = resource_type.strip().upper()
    if resource_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported resource_type")
    resource_branch, engagement_id = _resource_context(db, resource_type, resource_id)
    if resource_branch != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit resource not found")
    if row.engagement_id is not None and engagement_id is not None and row.engagement_id != engagement_id:
        raise HTTPException(status_code=409, detail="Evidence engagement does not match target resource")
    if row.engagement_id is None and engagement_id is not None:
        row.engagement_id = engagement_id

    existing = db.scalar(
        select(EvidenceResourceLink.id).where(
            EvidenceResourceLink.document_id == row.id,
            EvidenceResourceLink.resource_type == resource_type,
            EvidenceResourceLink.resource_id == resource_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Evidence link already exists")

    link = EvidenceResourceLink(
        document_id=row.id,
        branch=resource_branch,
        resource_type=resource_type,
        resource_id=resource_id,
        engagement_id=engagement_id,
        linked_by=user.user_id,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=row.id,
        action="EVIDENCE_LINK",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "link_id": link.id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "engagement_id": engagement_id,
        },
    )
    return link


def supersede_evidence(
    db: Session,
    row: Document,
    *,
    replacement_document_id: int,
    reason: str,
    user: CurrentUser,
) -> Document:
    ensure_branch_access(user, row.branch)
    if row.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived evidence cannot be superseded again")
    replacement = db.get(Document, replacement_document_id)
    if replacement is None or replacement.id == row.id:
        raise HTTPException(status_code=404, detail="Replacement evidence not found")
    ensure_branch_access(user, replacement.branch)
    if normalize_branch(replacement.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Replacement evidence not found")
    if replacement.archived_at is not None or replacement.supersedes_document_id is not None:
        raise HTTPException(status_code=409, detail="Replacement evidence is not eligible")
    clean_reason = reason.strip()
    if not clean_reason:
        raise HTTPException(status_code=400, detail="Supersede reason is required")
    if row.engagement_id is not None and replacement.engagement_id not in {None, row.engagement_id}:
        raise HTTPException(status_code=409, detail="Replacement engagement does not match prior evidence")

    replacement.supersedes_document_id = row.id
    replacement.evidence_version_number = int(row.evidence_version_number or 1) + 1
    replacement.engagement_id = replacement.engagement_id or row.engagement_id
    replacement.evidence_classification = replacement.evidence_classification or row.evidence_classification
    replacement.evidence_source = replacement.evidence_source or "REPLACEMENT"
    replacement.description = replacement.description or row.description

    row.archived_at = datetime.now(timezone.utc)
    row.archived_by = user.user_id
    row.archive_reason = f"SUPERSEDED: {clean_reason}"

    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=row.id,
        action="EVIDENCE_SUPERSEDED",
        actor=user.user_id,
        branch=row.branch,
        metadata={"replacement_document_id": replacement.id, "reason": clean_reason},
    )
    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=replacement.id,
        action="EVIDENCE_VERSION_CREATED",
        actor=user.user_id,
        branch=replacement.branch,
        metadata={"supersedes_document_id": row.id, "version": replacement.evidence_version_number},
    )
    db.flush()
    return replacement


def archive_evidence(db: Session, row: Document, *, reason: str, user: CurrentUser) -> Document:
    ensure_branch_access(user, row.branch)
    clean_reason = reason.strip()
    if not clean_reason:
        raise HTTPException(status_code=400, detail="Archive reason is required")
    if row.archived_at is None:
        row.archived_at = datetime.now(timezone.utc)
        row.archived_by = user.user_id
        row.archive_reason = clean_reason
        record_audit(
            db,
            entity_type="DOCUMENT",
            entity_id=row.id,
            action="EVIDENCE_ARCHIVE",
            actor=user.user_id,
            branch=row.branch,
            remarks=clean_reason,
        )
        db.flush()
    return row


def verify_integrity(db: Session, row: Document, *, user: CurrentUser) -> dict[str, object]:
    ensure_branch_access(user, row.branch)
    if settings.use_supabase_storage:
        content = download_bytes(row.storage_path)
    else:
        path = Path(row.storage_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Stored evidence file not found")
        content = path.read_bytes()

    actual_hash = hashlib.sha256(content).hexdigest()
    actual_size = len(content)
    hash_match = actual_hash == row.file_hash
    size_match = None if row.file_size_bytes is None else actual_size == row.file_size_bytes

    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=row.id,
        action="EVIDENCE_INTEGRITY_VERIFY",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "hash_match": hash_match,
            "size_match": size_match,
            "actual_size_bytes": actual_size,
        },
    )
    db.flush()
    return {
        "document_id": row.id,
        "expected_hash": row.file_hash,
        "actual_hash": actual_hash,
        "hash_match": hash_match,
        "expected_size_bytes": row.file_size_bytes,
        "actual_size_bytes": actual_size,
        "size_match": size_match,
    }


def _html() -> str:
    return """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence Repository</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1150px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
input,select,textarea,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}button{background:#1f6feb;color:#fff;font-weight:700}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}pre{background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px;white-space:pre-wrap}
@media(max-width:850px){.grid{grid-template-columns:1fr}}</style></head><body>
<header><h1>Audit Evidence Repository</h1><p>Metadata, versioning, explicit linkage, archive, and integrity verification over existing document storage.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="branch" placeholder="Branch"><input id="engagement" type="number" placeholder="Engagement ID"><button id="load">Muat Evidence</button></div></section>
<section class="panel"><h2>Link Evidence</h2><div class="grid"><input id="documentId" type="number" placeholder="Document ID"><select id="resourceType"><option>SAMPLE</option><option>WORKING_PAPER</option><option>FINDING</option><option>ACTION_PLAN</option><option>FOLLOW_UP</option><option>AUDIT_REPORT</option></select><input id="resourceId" type="number" placeholder="Resource ID"><button id="link">Link</button></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>File</th><th>Branch</th><th>Class</th><th>Version</th><th>Engagement</th><th>Archived</th><th>Links</th></tr></thead><tbody id="rows"></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main><script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';const log=document.getElementById('log');
function headers(){const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {Authorization:'Bearer '+v}}
async function req(url,opt={}){opt.headers=Object.assign({},opt.headers||{},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}
async function loadData(){const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();const e=document.getElementById('engagement').value;if(b)p.set('branch',b);if(e)p.set('engagement_id',e);const x=await req('/evidence-repository?'+p);document.getElementById('rows').innerHTML=(x.evidence||[]).map(d=>'<tr><td>'+d.id+'</td><td>'+d.file_name+'</td><td>'+(d.branch||'-')+'</td><td>'+(d.evidence_classification||d.document_type)+'</td><td>'+d.evidence_version_number+'</td><td>'+(d.engagement_id||'-')+'</td><td>'+d.archived+'</td><td>'+d.links.length+'</td></tr>').join('')}
async function post(url,data){const fd=new FormData();Object.entries(data).forEach(([k,v])=>fd.append(k,v));return req(url,{method:'POST',body:fd})}
document.getElementById('load').onclick=()=>loadData().catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('link').onclick=()=>post('/evidence-repository/'+document.getElementById('documentId').value+'/links',{resource_type:document.getElementById('resourceType').value,resource_id:document.getElementById('resourceId').value}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/evidence-repository", response_class=HTMLResponse)
def evidence_repository_ui():
    return HTMLResponse(_html())


@router.get("/evidence-repository")
def get_evidence_repository(
    branch: str | None = None,
    engagement_id: int | None = None,
    archived: bool | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(Document).order_by(Document.uploaded_at.desc(), Document.id.desc())
    if effective_branch is not None:
        query = query.where(Document.branch == effective_branch)
    if engagement_id is not None:
        query = query.where(Document.engagement_id == engagement_id)
    if archived is True:
        query = query.where(Document.archived_at.is_not(None))
    elif archived is False:
        query = query.where(Document.archived_at.is_(None))
    rows = list(db.scalars(query).all())
    return {"total": len(rows), "branch": effective_branch, "evidence": [evidence_payload(db, x) for x in rows]}


@router.get("/evidence-repository/{document_id}")
def get_evidence_detail(
    document_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return evidence_payload(db, _document_for_user(db, document_id, user))


@router.patch("/evidence-repository/{document_id}/metadata")
def patch_evidence_metadata(
    document_id: int,
    engagement_id: int | None = Form(None),
    evidence_classification: str | None = Form(None),
    evidence_source: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = update_evidence_metadata(
        db, _document_for_user(db, document_id, user),
        engagement_id=engagement_id, evidence_classification=evidence_classification,
        evidence_source=evidence_source, description=description, user=user,
    )
    db.commit(); db.refresh(row)
    return evidence_payload(db, row)


@router.post("/evidence-repository/{document_id}/links")
def post_evidence_link(
    document_id: int,
    resource_type: str = Form(...),
    resource_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _document_for_user(db, document_id, user)
    link_evidence(db, row, resource_type=resource_type, resource_id=resource_id, user=user)
    db.commit()
    return evidence_payload(db, row)


@router.post("/evidence-repository/{document_id}/supersede")
def post_evidence_supersede(
    document_id: int,
    replacement_document_id: int = Form(...),
    reason: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = supersede_evidence(
        db, _document_for_user(db, document_id, user),
        replacement_document_id=replacement_document_id, reason=reason, user=user,
    )
    db.commit(); db.refresh(row)
    return evidence_payload(db, row)


@router.post("/evidence-repository/{document_id}/archive")
def post_evidence_archive(
    document_id: int,
    reason: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = archive_evidence(db, _document_for_user(db, document_id, user), reason=reason, user=user)
    db.commit(); db.refresh(row)
    return evidence_payload(db, row)


@router.post("/evidence-repository/{document_id}/verify-integrity")
def post_evidence_integrity(
    document_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    result = verify_integrity(db, _document_for_user(db, document_id, user), user=user)
    db.commit()
    return result


@router.delete("/evidence-repository/{document_id}")
def delete_evidence_disabled(
    document_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    _document_for_user(db, document_id, user)
    raise HTTPException(status_code=409, detail="Hard delete is disabled for audit evidence; archive the evidence instead")


def register_evidence_repository_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
