from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditException,
    AuditSample,
    AuditWorkingPaper,
    AuditWorkingPaperEvidence,
    AuditWorkingPaperException,
    AuditWorkingPaperVersion,
    Document,
    DocumentControlEvidence,
)

router = APIRouter()
_REGISTERED = False

TRANSITIONS = {
    "DRAFT": {"PREPARED"},
    "PREPARED": {"IN_REVIEW"},
    "IN_REVIEW": {"REVIEWED"},
    "REVIEWED": set(),
}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _is_assigned(db: Session, engagement_id: int, user: CurrentUser, assignment_role: str) -> bool:
    if user.role == "ADMIN":
        return True
    if user.role != assignment_role:
        return False
    return db.scalar(
        select(AuditEngagementAssignment.id).where(
            AuditEngagementAssignment.engagement_id == engagement_id,
            AuditEngagementAssignment.user_id == user.user_id,
            AuditEngagementAssignment.assignment_role == assignment_role,
        )
    ) is not None


def _require_assignment(db: Session, engagement_id: int, user: CurrentUser, role: str) -> None:
    if not _is_assigned(db, engagement_id, user, role):
        raise HTTPException(status_code=403, detail=f"Assigned {role} role required")


def _snapshot(
    db: Session,
    row: AuditWorkingPaper,
    *,
    user: CurrentUser,
    status: str,
    reason: str | None = None,
    increment: bool = True,
) -> AuditWorkingPaperVersion:
    if increment:
        row.version_number += 1
    version = AuditWorkingPaperVersion(
        working_paper_id=row.id,
        version_number=row.version_number,
        title=row.title,
        audit_objective=row.audit_objective,
        procedure_performed=row.procedure_performed,
        result_observation=row.result_observation,
        conclusion=row.conclusion,
        status=status,
        changed_by=user.user_id,
        change_reason=reason,
    )
    db.add(version)
    db.flush()
    return version


def working_paper_payload(db: Session, row: AuditWorkingPaper) -> dict[str, object]:
    versions = list(
        db.scalars(
            select(AuditWorkingPaperVersion)
            .where(AuditWorkingPaperVersion.working_paper_id == row.id)
            .order_by(AuditWorkingPaperVersion.version_number)
        ).all()
    )
    evidence = list(
        db.scalars(
            select(AuditWorkingPaperEvidence)
            .where(AuditWorkingPaperEvidence.working_paper_id == row.id)
            .order_by(AuditWorkingPaperEvidence.id)
        ).all()
    )
    exceptions = list(
        db.scalars(
            select(AuditWorkingPaperException)
            .where(AuditWorkingPaperException.working_paper_id == row.id)
            .order_by(AuditWorkingPaperException.id)
        ).all()
    )
    return {
        "id": row.id,
        "engagement_id": row.engagement_id,
        "branch": row.branch,
        "reference": row.reference,
        "title": row.title,
        "audit_objective": row.audit_objective,
        "procedure_performed": row.procedure_performed,
        "result_observation": row.result_observation,
        "conclusion": row.conclusion,
        "preparer_id": row.preparer_id,
        "prepared_at": row.prepared_at.isoformat() if row.prepared_at else None,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "status": row.status,
        "version_number": row.version_number,
        "sample_id": row.sample_id,
        "allowed_transitions": sorted(TRANSITIONS.get(row.status, set())),
        "evidence": [
            {"id": x.id, "document_id": x.document_id, "control_evidence_id": x.control_evidence_id}
            for x in evidence
        ],
        "exception_ids": [x.audit_exception_id for x in exceptions],
        "versions": [
            {
                "version_number": x.version_number,
                "status": x.status,
                "changed_by": x.changed_by,
                "change_reason": x.change_reason,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in versions
        ],
    }


def create_working_paper(
    db: Session,
    *,
    engagement: AuditEngagement,
    reference: str,
    title: str,
    audit_objective: str,
    procedure_performed: str,
    sample_id: int | None,
    user: CurrentUser,
) -> AuditWorkingPaper:
    ensure_branch_access(user, engagement.branch)
    _require_assignment(db, engagement.id, user, "AUDITOR")
    if engagement.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed engagement cannot receive working papers")

    reference = reference.strip().upper()
    title = title.strip()
    objective = audit_objective.strip()
    procedure = procedure_performed.strip()
    if not all((reference, title, objective, procedure)):
        raise HTTPException(status_code=400, detail="reference, title, audit_objective and procedure_performed are required")
    if db.scalar(
        select(AuditWorkingPaper.id).where(
            AuditWorkingPaper.engagement_id == engagement.id,
            AuditWorkingPaper.reference == reference,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="Working paper reference already exists in this engagement")

    if sample_id is not None:
        sample = db.get(AuditSample, sample_id)
        if sample is None or sample.engagement_id != engagement.id or normalize_branch(sample.branch) != normalize_branch(engagement.branch):
            raise HTTPException(status_code=404, detail="Audit sample not found")

    row = AuditWorkingPaper(
        engagement_id=engagement.id,
        branch=engagement.branch,
        reference=reference,
        title=title,
        audit_objective=objective,
        procedure_performed=procedure,
        status="DRAFT",
        version_number=1,
        sample_id=sample_id,
        preparer_id=user.user_id,
    )
    db.add(row)
    db.flush()
    _snapshot(db, row, user=user, status="DRAFT", increment=False)
    record_audit(
        db,
        entity_type="AUDIT_WORKING_PAPER",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="DRAFT",
        branch=row.branch,
        metadata={"engagement_id": row.engagement_id, "reference": row.reference, "sample_id": row.sample_id},
    )
    db.flush()
    return row


def update_working_paper(
    db: Session,
    row: AuditWorkingPaper,
    *,
    title: str | None,
    audit_objective: str | None,
    procedure_performed: str | None,
    result_observation: str | None,
    conclusion: str | None,
    user: CurrentUser,
) -> AuditWorkingPaper:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "AUDITOR")
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT working papers can be edited")

    updates = {
        "title": title,
        "audit_objective": audit_objective,
        "procedure_performed": procedure_performed,
        "result_observation": result_observation,
        "conclusion": conclusion,
    }
    changed = {}
    for field, value in updates.items():
        if value is None:
            continue
        clean = value.strip()
        if field in {"title", "audit_objective", "procedure_performed"} and not clean:
            raise HTTPException(status_code=400, detail=f"{field} cannot be blank")
        if getattr(row, field) != (clean or None):
            changed[field] = True
            setattr(row, field, clean or None)
    if changed:
        record_audit(
            db,
            entity_type="AUDIT_WORKING_PAPER",
            entity_id=row.id,
            action="UPDATE",
            actor=user.user_id,
            branch=row.branch,
            metadata={"fields": sorted(changed)},
        )
    db.flush()
    return row


def transition_working_paper(
    db: Session,
    row: AuditWorkingPaper,
    *,
    target_status: str,
    user: CurrentUser,
) -> AuditWorkingPaper:
    ensure_branch_access(user, row.branch)
    target = target_status.strip().upper()
    if target not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid working paper transition: {row.status} -> {target}")

    if target in {"PREPARED", "IN_REVIEW"}:
        _require_assignment(db, row.engagement_id, user, "AUDITOR")
    else:
        _require_assignment(db, row.engagement_id, user, "REVIEWER")

    if target == "PREPARED" and (not row.result_observation or not row.conclusion):
        raise HTTPException(status_code=400, detail="result_observation and conclusion are required before PREPARED")

    previous = row.status
    row.status = target
    now = datetime.now(timezone.utc)
    if target == "PREPARED":
        row.preparer_id = user.user_id
        row.prepared_at = now
        _snapshot(db, row, user=user, status=target)
    elif target == "REVIEWED":
        row.reviewer_id = user.user_id
        row.reviewed_at = now
        _snapshot(db, row, user=user, status=target)

    record_audit(
        db,
        entity_type="AUDIT_WORKING_PAPER",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=previous,
        status_to=target,
        branch=row.branch,
        metadata={"version_number": row.version_number},
    )
    db.flush()
    return row


def reopen_working_paper(
    db: Session,
    row: AuditWorkingPaper,
    *,
    reason: str,
    user: CurrentUser,
) -> AuditWorkingPaper:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "REVIEWER")
    if row.status != "REVIEWED":
        raise HTTPException(status_code=400, detail="Only REVIEWED working papers can be reopened")
    clean_reason = reason.strip()
    if not clean_reason:
        raise HTTPException(status_code=400, detail="Reopen reason is required")

    previous = row.status
    row.status = "DRAFT"
    row.reviewed_at = None
    _snapshot(db, row, user=user, status="DRAFT", reason=clean_reason)
    record_audit(
        db,
        entity_type="AUDIT_WORKING_PAPER",
        entity_id=row.id,
        action="REOPEN",
        actor=user.user_id,
        status_from=previous,
        status_to="DRAFT",
        remarks=clean_reason,
        branch=row.branch,
        metadata={"version_number": row.version_number},
    )
    db.flush()
    return row


def link_evidence(
    db: Session,
    row: AuditWorkingPaper,
    *,
    document_id: int | None,
    control_evidence_id: int | None,
    user: CurrentUser,
) -> AuditWorkingPaperEvidence:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "AUDITOR")
    if (document_id is None) == (control_evidence_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one evidence source")

    document = None
    if document_id is not None:
        document = db.get(Document, document_id)
    else:
        evidence = db.get(DocumentControlEvidence, control_evidence_id)
        document = evidence.document if evidence else None
    if document is None or normalize_branch(document.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Evidence not found")

    existing = db.scalar(
        select(AuditWorkingPaperEvidence.id).where(
            AuditWorkingPaperEvidence.working_paper_id == row.id,
            AuditWorkingPaperEvidence.document_id == document_id,
            AuditWorkingPaperEvidence.control_evidence_id == control_evidence_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Evidence already linked")
    link = AuditWorkingPaperEvidence(
        working_paper_id=row.id,
        document_id=document_id,
        control_evidence_id=control_evidence_id,
        linked_by=user.user_id,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_WORKING_PAPER",
        entity_id=row.id,
        action="LINK_EVIDENCE",
        actor=user.user_id,
        branch=row.branch,
        metadata={"document_id": document_id, "control_evidence_id": control_evidence_id},
    )
    db.flush()
    return link


def link_exception(
    db: Session,
    row: AuditWorkingPaper,
    *,
    audit_exception_id: int,
    user: CurrentUser,
) -> AuditWorkingPaperException:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "AUDITOR")
    exception = db.get(AuditException, audit_exception_id)
    if exception is None or normalize_branch(exception.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit exception not found")
    existing = db.scalar(
        select(AuditWorkingPaperException.id).where(
            AuditWorkingPaperException.working_paper_id == row.id,
            AuditWorkingPaperException.audit_exception_id == exception.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Audit exception already linked")
    link = AuditWorkingPaperException(
        working_paper_id=row.id,
        audit_exception_id=exception.id,
        linked_by=user.user_id,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_WORKING_PAPER",
        entity_id=row.id,
        action="LINK_EXCEPTION",
        actor=user.user_id,
        branch=row.branch,
        metadata={"audit_exception_id": exception.id},
    )
    db.flush()
    return link


def _html() -> str:
    stages = " → ".join(TRANSITIONS)
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Working Papers - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:white;padding:18px 24px}}
main{{max-width:1200px;margin:auto;padding:20px}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}input,select,textarea,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}
textarea{{min-height:70px}}button{{background:#1f6feb;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}
pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Electronic Working Papers</h1><p>{escape(stages)}; reviewed paper hanya dapat diubah setelah explicit reopen.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="engagementFilter" type="number" placeholder="Engagement ID"><button id="load">Muat Working Papers</button></div></section>
<section class="panel"><h2>Buat Working Paper</h2><div class="grid"><input id="engagementId" type="number" placeholder="Engagement ID"><input id="reference" placeholder="Reference"><input id="title" placeholder="Title"><textarea id="objective" placeholder="Audit objective"></textarea><textarea id="procedure" placeholder="Procedure performed"></textarea><input id="sampleId" type="number" placeholder="Sample ID (opsional)"><button id="create">Buat Draft</button></div></section>
<section class="panel"><h2>Update Draft / Transition</h2><div class="grid"><input id="paperId" type="number" placeholder="Working Paper ID"><textarea id="result" placeholder="Result / observation"></textarea><textarea id="conclusion" placeholder="Conclusion"></textarea><button id="save">Simpan Draft</button><select id="target"><option>PREPARED</option><option>IN_REVIEW</option><option>REVIEWED</option></select><button id="transition">Transition</button><input id="reopenReason" placeholder="Reopen reason"><button id="reopen">Reopen Reviewed</button></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>Ref</th><th>Title</th><th>Branch</th><th>Status</th><th>Version</th><th>Sample</th></tr></thead><tbody id="rows"><tr><td colspan="7">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';const log=document.getElementById('log');const rows=document.getElementById('rows');
function headers(){{const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {{Authorization:'Bearer '+v}}}}
async function req(url,opt={{}}){{opt.headers=Object.assign({{}},opt.headers||{{}},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}}
async function loadData(){{const p=new URLSearchParams();const id=document.getElementById('engagementFilter').value;if(id)p.set('engagement_id',id);const x=await req('/audit-working-papers?'+p);rows.innerHTML=(x.working_papers||[]).map(w=>'<tr><td>'+w.id+'</td><td>'+w.reference+'</td><td>'+w.title+'</td><td>'+w.branch+'</td><td>'+w.status+'</td><td>'+w.version_number+'</td><td>'+(w.sample_id||'-')+'</td></tr>').join('')||'<tr><td colspan="7">Tidak ada working paper.</td></tr>'}}
async function post(url,data,method='POST'){{const fd=new FormData();Object.entries(data).forEach(([k,v])=>{{if(v!==''&&v!=null)fd.append(k,v)}});return req(url,{{method,body:fd}})}}
document.getElementById('load').onclick=()=>loadData().catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>post('/audit-working-papers',{{engagement_id:document.getElementById('engagementId').value,reference:document.getElementById('reference').value,title:document.getElementById('title').value,audit_objective:document.getElementById('objective').value,procedure_performed:document.getElementById('procedure').value,sample_id:document.getElementById('sampleId').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('save').onclick=()=>post('/audit-working-papers/'+document.getElementById('paperId').value,{{result_observation:document.getElementById('result').value,conclusion:document.getElementById('conclusion').value}},'PATCH').then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('transition').onclick=()=>post('/audit-working-papers/'+document.getElementById('paperId').value+'/transition',{{status:document.getElementById('target').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('reopen').onclick=()=>post('/audit-working-papers/'+document.getElementById('paperId').value+'/reopen',{{reason:document.getElementById('reopenReason').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


def _paper_for_user(db: Session, paper_id: int, user: CurrentUser) -> AuditWorkingPaper:
    row = db.get(AuditWorkingPaper, paper_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit working paper not found")
    ensure_branch_access(user, row.branch)
    return row


@router.get("/ui/audit-working-papers", response_class=HTMLResponse)
def audit_working_papers_ui():
    return HTMLResponse(_html())


@router.get("/audit-working-papers")
def get_working_papers(
    engagement_id: int | None = None,
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(AuditWorkingPaper).order_by(AuditWorkingPaper.updated_at.desc(), AuditWorkingPaper.id.desc())
    if effective_branch is not None:
        query = query.where(AuditWorkingPaper.branch == effective_branch)
    if engagement_id is not None:
        query = query.where(AuditWorkingPaper.engagement_id == engagement_id)
    if status:
        query = query.where(AuditWorkingPaper.status == status.strip().upper())
    rows = list(db.scalars(query).all())
    return {"total": len(rows), "working_papers": [working_paper_payload(db, row) for row in rows]}


@router.get("/audit-working-papers/{paper_id}")
def get_working_paper(
    paper_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return working_paper_payload(db, _paper_for_user(db, paper_id, user))


@router.post("/audit-working-papers")
def post_working_paper(
    engagement_id: int = Form(...),
    reference: str = Form(...),
    title: str = Form(...),
    audit_objective: str = Form(...),
    procedure_performed: str = Form(...),
    sample_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    engagement = db.get(AuditEngagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    row = create_working_paper(
        db,
        engagement=engagement,
        reference=reference,
        title=title,
        audit_objective=audit_objective,
        procedure_performed=procedure_performed,
        sample_id=sample_id,
        user=user,
    )
    db.commit()
    db.refresh(row)
    return working_paper_payload(db, row)


@router.patch("/audit-working-papers/{paper_id}")
def patch_working_paper(
    paper_id: int,
    title: str | None = Form(None),
    audit_objective: str | None = Form(None),
    procedure_performed: str | None = Form(None),
    result_observation: str | None = Form(None),
    conclusion: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _paper_for_user(db, paper_id, user)
    update_working_paper(
        db,
        row,
        title=title,
        audit_objective=audit_objective,
        procedure_performed=procedure_performed,
        result_observation=result_observation,
        conclusion=conclusion,
        user=user,
    )
    db.commit()
    db.refresh(row)
    return working_paper_payload(db, row)


@router.post("/audit-working-papers/{paper_id}/transition")
def post_working_paper_transition(
    paper_id: int,
    status: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = _paper_for_user(db, paper_id, user)
    transition_working_paper(db, row, target_status=status, user=user)
    db.commit()
    db.refresh(row)
    return working_paper_payload(db, row)


@router.post("/audit-working-papers/{paper_id}/reopen")
def post_working_paper_reopen(
    paper_id: int,
    reason: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    row = _paper_for_user(db, paper_id, user)
    reopen_working_paper(db, row, reason=reason, user=user)
    db.commit()
    db.refresh(row)
    return working_paper_payload(db, row)


@router.post("/audit-working-papers/{paper_id}/evidence")
def post_working_paper_evidence(
    paper_id: int,
    document_id: int | None = Form(None),
    control_evidence_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _paper_for_user(db, paper_id, user)
    link_evidence(
        db, row, document_id=document_id, control_evidence_id=control_evidence_id, user=user
    )
    db.commit()
    return working_paper_payload(db, row)


@router.post("/audit-working-papers/{paper_id}/exceptions")
def post_working_paper_exception(
    paper_id: int,
    audit_exception_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _paper_for_user(db, paper_id, user)
    link_exception(db, row, audit_exception_id=audit_exception_id, user=user)
    db.commit()
    return working_paper_payload(db, row)


def register_audit_working_paper_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
