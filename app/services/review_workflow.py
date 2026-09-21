from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditException,
    Document,
    DocumentControlEvidence,
    ImportBatch,
    ReviewWorkflow,
    VouchingResult,
)

router = APIRouter()
_REGISTERED = False

SUPPORTED_ENTITIES = {
    "DOCUMENT",
    "IMPORT_BATCH",
    "VOUCHING_RESULT",
    "DOCUMENT_CONTROL_EVIDENCE",
    "AUDIT_EXCEPTION",
}

TRANSITIONS = {
    "NEW": {"PROCESSING"},
    "PROCESSING": {"EXCEPTION", "AUDITOR_REVIEWED"},
    "EXCEPTION": {"AUDITOR_REVIEWED"},
    "AUDITOR_REVIEWED": {"REVIEWER_APPROVED", "REVIEWER_REJECTED"},
    "REVIEWER_REJECTED": {"PROCESSING"},
    "REVIEWER_APPROVED": {"CLOSED"},
    "CLOSED": set(),
}

AUDITOR_TARGETS = {"PROCESSING", "EXCEPTION", "AUDITOR_REVIEWED"}
REVIEWER_TARGETS = {"REVIEWER_APPROVED", "REVIEWER_REJECTED", "CLOSED"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resource_branch(db: Session, entity_type: str, entity_id: int) -> str:
    entity_type = entity_type.upper()
    branch = None
    if entity_type == "DOCUMENT":
        row = db.get(Document, entity_id)
        branch = row.branch if row else None
    elif entity_type == "IMPORT_BATCH":
        row = db.get(ImportBatch, entity_id)
        branch = row.branch if row else None
    elif entity_type == "VOUCHING_RESULT":
        row = db.get(VouchingResult, entity_id)
        branch = row.billing.document.branch if row else None
    elif entity_type == "DOCUMENT_CONTROL_EVIDENCE":
        row = db.get(DocumentControlEvidence, entity_id)
        branch = row.document.branch if row else None
    elif entity_type == "AUDIT_EXCEPTION":
        row = db.get(AuditException, entity_id)
        branch = row.branch if row else None
    else:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")

    if row is None:
        raise HTTPException(status_code=404, detail="Review resource not found")
    branch = normalize_branch(branch)
    if branch is None:
        raise HTTPException(status_code=400, detail="Review resource has no branch ownership")
    return branch


def workflow_payload(row: ReviewWorkflow) -> dict[str, object]:
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "branch": row.branch,
        "status": row.status,
        "auditor_id": row.auditor_id,
        "reviewer_id": row.reviewer_id,
        "auditor_remarks": row.auditor_remarks,
        "reviewer_remarks": row.reviewer_remarks,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "allowed_transitions": sorted(TRANSITIONS.get(row.status, set())),
    }


def list_review_workflows(
    db: Session,
    *,
    branch: str | None = None,
    status: str | None = None,
) -> list[ReviewWorkflow]:
    query = select(ReviewWorkflow).order_by(ReviewWorkflow.updated_at.desc(), ReviewWorkflow.id.desc())
    if branch is not None:
        query = query.where(ReviewWorkflow.branch == normalize_branch(branch))
    if status:
        query = query.where(ReviewWorkflow.status == status.upper())
    return list(db.scalars(query).all())


def _require_transition_role(user: CurrentUser, target_status: str) -> None:
    if user.role == "ADMIN":
        return
    if target_status in AUDITOR_TARGETS and user.role != "AUDITOR":
        raise HTTPException(status_code=403, detail="AUDITOR role required for this transition")
    if target_status in REVIEWER_TARGETS and user.role != "REVIEWER":
        raise HTTPException(status_code=403, detail="REVIEWER role required for this transition")


def transition_workflow(
    db: Session,
    row: ReviewWorkflow,
    *,
    target_status: str,
    user: CurrentUser,
    remarks: str | None = None,
) -> ReviewWorkflow:
    target_status = target_status.strip().upper()
    allowed = TRANSITIONS.get(row.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workflow transition: {row.status} -> {target_status}",
        )
    _require_transition_role(user, target_status)
    ensure_branch_access(user, row.branch)

    old_status = row.status
    row.status = target_status
    clean_remarks = remarks.strip() if remarks and remarks.strip() else None

    if target_status in AUDITOR_TARGETS:
        row.auditor_id = user.user_id
        if clean_remarks is not None:
            row.auditor_remarks = clean_remarks
    elif target_status in REVIEWER_TARGETS:
        row.reviewer_id = user.user_id
        if clean_remarks is not None:
            row.reviewer_remarks = clean_remarks

    row.closed_at = datetime.now(timezone.utc) if target_status == "CLOSED" else None

    record_audit(
        db,
        entity_type="REVIEW_WORKFLOW",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=old_status,
        status_to=target_status,
        remarks=clean_remarks,
        metadata={"resource_type": row.entity_type, "resource_id": row.entity_id},
        branch=row.branch,
    )
    db.flush()
    return row


def _html() -> str:
    entity_options = "".join(f'<option>{value}</option>' for value in sorted(SUPPORTED_ENTITIES))
    status_options = "".join(
        f'<option>{value}</option>'
        for value in ("PROCESSING", "EXCEPTION", "AUDITOR_REVIEWED", "REVIEWER_APPROVED", "REVIEWER_REJECTED", "CLOSED")
    )
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review Queue - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:#fff;padding:18px 24px}}
main{{max-width:1200px;margin:auto;padding:20px}}.panel{{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}label{{display:block;font-size:12px;color:#64748b;margin-bottom:4px}}
input,select,textarea,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}button{{background:#1f6feb;color:#fff;font-weight:700;cursor:pointer}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}
@media(max-width:850px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>Review Queue</h1><p>Workflow audit: NEW → PROCESSING → AUDITOR_REVIEWED → REVIEWER_APPROVED/REJECTED → CLOSED.</p></header>
<main>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div>
<div><label>Cabang</label><input id="branch" placeholder="ADMIN: kosong = semua"></div>
<div><label>Filter Status</label><input id="filterStatus" placeholder="AUDITOR_REVIEWED"></div>
<div><button id="load" style="margin-top:18px">Muat Queue</button></div>
</div></section>

<section class="panel"><h2>Mulai Review</h2><div class="grid">
<div><label>Entity Type</label><select id="entityType">{entity_options}</select></div>
<div><label>Entity ID</label><input id="entityId" type="number" min="1"></div>
<div><label>Cabang (opsional, ADMIN validation)</label><input id="startBranch"></div>
<div><button id="start" style="margin-top:18px">Buat Workflow</button></div>
</div></section>

<section class="panel"><h2>Transisi Workflow</h2><div class="grid">
<div><label>Workflow ID</label><input id="workflowId" type="number" min="1"></div>
<div><label>Status Tujuan</label><select id="targetStatus">{status_options}</select></div>
<div style="grid-column:span 2"><label>Remarks</label><input id="remarks"></div>
</div><button id="transition" style="margin-top:10px">Proses Transisi</button></section>

<section class="panel"><table><thead><tr><th>ID</th><th>Cabang</th><th>Resource</th><th>Status</th><th>Auditor</th><th>Reviewer</th><th>Next</th></tr></thead>
<tbody id="rows"><tr><td colspan="7">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const tokenEl=document.getElementById('token');tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){{const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',t);return {{Authorization:'Bearer '+t}}}}
async function load(){{const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();const s=document.getElementById('filterStatus').value.trim();if(b)p.set('branch',b);if(s)p.set('status',s);const r=await fetch('/review-workflows?'+p.toString(),{{headers:headers()}});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('rows').innerHTML=(x.workflows||[]).map(w=>'<tr><td>'+w.id+'</td><td>'+w.branch+'</td><td>'+w.entity_type+' #'+w.entity_id+'</td><td>'+w.status+'</td><td>'+(w.auditor_id||'-')+'</td><td>'+(w.reviewer_id||'-')+'</td><td>'+w.allowed_transitions.join(', ')+'</td></tr>').join('')||'<tr><td colspan="7">Tidak ada workflow.</td></tr>';document.getElementById('log').textContent=JSON.stringify(x,null,2)}}
async function start(){{const fd=new FormData();fd.append('entity_type',document.getElementById('entityType').value);fd.append('entity_id',document.getElementById('entityId').value);const b=document.getElementById('startBranch').value.trim();if(b)fd.append('branch',b);const r=await fetch('/review-workflows',{{method:'POST',headers:headers(),body:fd}});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}}
async function transition(){{const id=document.getElementById('workflowId').value;const fd=new FormData();fd.append('status',document.getElementById('targetStatus').value);fd.append('remarks',document.getElementById('remarks').value);const r=await fetch('/review-workflows/'+encodeURIComponent(id)+'/transition',{{method:'PATCH',headers:headers(),body:fd}});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('start').onclick=()=>start().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('transition').onclick=()=>transition().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/review-queue", response_class=HTMLResponse)
def review_queue_ui():
    return HTMLResponse(_html())


@router.get("/review-workflows")
def get_review_workflows(
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    rows = list_review_workflows(db, branch=effective_branch, status=status)
    return {"total": len(rows), "branch": effective_branch, "workflows": [workflow_payload(row) for row in rows]}


@router.post("/review-workflows")
def create_review_workflow(
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    branch: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    entity_type = entity_type.strip().upper()
    if entity_type not in SUPPORTED_ENTITIES:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")

    resource_branch = _resource_branch(db, entity_type, entity_id)
    ensure_branch_access(user, resource_branch)
    requested_branch = normalize_branch(branch)
    if requested_branch is not None and requested_branch != resource_branch:
        raise HTTPException(status_code=400, detail="Requested branch does not match resource branch")

    existing = db.scalar(
        select(ReviewWorkflow).where(
            ReviewWorkflow.entity_type == entity_type,
            ReviewWorkflow.entity_id == entity_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Review workflow already exists for resource")

    row = ReviewWorkflow(
        entity_type=entity_type,
        entity_id=entity_id,
        branch=resource_branch,
        status="NEW",
        auditor_id=user.user_id if user.role == "AUDITOR" else None,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="REVIEW_WORKFLOW",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="NEW",
        metadata={"resource_type": entity_type, "resource_id": entity_id},
        branch=resource_branch,
    )
    db.commit()
    db.refresh(row)
    return workflow_payload(row)


@router.patch("/review-workflows/{workflow_id}/transition")
def review_transition(
    workflow_id: int,
    status: str = Form(...),
    remarks: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = db.get(ReviewWorkflow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review workflow not found")
    transition_workflow(db, row, target_status=status, user=user, remarks=remarks)
    db.commit()
    db.refresh(row)
    return workflow_payload(row)


def register_review_workflow_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
