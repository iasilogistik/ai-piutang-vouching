from __future__ import annotations

from datetime import date
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch, write_branch
from app.database import SessionLocal
from app.models import AuditEngagement, AuditEngagementAssignment, AuditReport, AuditWorkflowCase

router = APIRouter()
_REGISTERED = False

TRANSITIONS = {
    "DRAFT": {"PLANNED"},
    "PLANNED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"REVIEW"},
    "REVIEW": {"COMPLETED"},
    "COMPLETED": {"CLOSED"},
    "CLOSED": set(),
}
_ASSIGNMENT_ROLES = {"AUDITOR", "REVIEWER"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_active_branch(db: Session, branch: str) -> None:
    if db.get_bind().dialect.name == "sqlite":
        return
    exists = db.execute(
        text("select 1 from public.branches where branch_code = :branch and active = true"),
        {"branch": branch},
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=400, detail="branch must reference an active canonical branch")


def _validate_assignee(db: Session, *, user_id: str, assignment_role: str, branch: str) -> None:
    if assignment_role not in _ASSIGNMENT_ROLES:
        raise HTTPException(status_code=400, detail="assignment_role must be AUDITOR or REVIEWER")
    if db.get_bind().dialect.name == "sqlite":
        return
    row = db.execute(
        text(
            """
            select role::text as role, branch, is_active
            from public.user_roles
            where cast(user_id as text) = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()
    if row is None or not row["is_active"]:
        raise HTTPException(status_code=400, detail="assignment must reference an active application user")
    if row["role"] not in {assignment_role, "ADMIN"}:
        raise HTTPException(status_code=400, detail=f"user is not eligible for {assignment_role} assignment")
    user_branch = normalize_branch(row["branch"])
    if row["role"] != "ADMIN" and user_branch != normalize_branch(branch):
        raise HTTPException(status_code=400, detail="assigned user branch must match engagement branch")


def _assignment_rows(db: Session, engagement_id: int) -> list[AuditEngagementAssignment]:
    return list(
        db.scalars(
            select(AuditEngagementAssignment)
            .where(AuditEngagementAssignment.engagement_id == engagement_id)
            .order_by(AuditEngagementAssignment.assignment_role, AuditEngagementAssignment.id)
        ).all()
    )


def _is_assigned(db: Session, engagement_id: int, user_id: str, role: str) -> bool:
    return db.scalar(
        select(AuditEngagementAssignment.id).where(
            AuditEngagementAssignment.engagement_id == engagement_id,
            AuditEngagementAssignment.user_id == user_id,
            AuditEngagementAssignment.assignment_role == role,
        )
    ) is not None


def engagement_payload(db: Session, row: AuditEngagement) -> dict[str, object]:
    assignments = _assignment_rows(db, row.id)
    workflow_ids = list(
        db.scalars(
            select(AuditWorkflowCase.id).where(AuditWorkflowCase.engagement_id == row.id).order_by(AuditWorkflowCase.id)
        ).all()
    )
    report_ids = list(
        db.scalars(select(AuditReport.id).where(AuditReport.engagement_id == row.id).order_by(AuditReport.id)).all()
    )
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "branch": row.branch,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "scope": row.scope,
        "status": row.status,
        "assignments": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "assignment_role": a.assignment_role,
                "assigned_by": a.assigned_by,
            }
            for a in assignments
        ],
        "workflow_case_ids": workflow_ids,
        "audit_report_ids": report_ids,
        "allowed_transitions": sorted(TRANSITIONS.get(row.status, set())),
    }


def list_engagements(
    db: Session, *, branch: str | None = None, status: str | None = None
) -> list[AuditEngagement]:
    query = select(AuditEngagement).order_by(AuditEngagement.period_start.desc(), AuditEngagement.id.desc())
    if branch is not None:
        query = query.where(AuditEngagement.branch == normalize_branch(branch))
    if status:
        query = query.where(AuditEngagement.status == status.strip().upper())
    return list(db.scalars(query).all())


def create_engagement(
    db: Session,
    *,
    code: str,
    title: str,
    branch: str,
    period_start: date,
    period_end: date,
    scope: str | None,
    user: CurrentUser,
) -> AuditEngagement:
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end must be on or after period_start")
    normalized_branch = write_branch(user, branch)
    _ensure_active_branch(db, normalized_branch)
    code = code.strip().upper()
    title = title.strip()
    if not code or not title:
        raise HTTPException(status_code=400, detail="code and title are required")
    if db.scalar(select(AuditEngagement.id).where(AuditEngagement.code == code)) is not None:
        raise HTTPException(status_code=409, detail="Audit engagement code already exists")
    row = AuditEngagement(
        code=code,
        title=title,
        branch=normalized_branch,
        period_start=period_start,
        period_end=period_end,
        scope=(scope or "").strip() or None,
        status="DRAFT",
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_ENGAGEMENT",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="DRAFT",
        branch=row.branch,
        metadata={"code": row.code, "period_start": str(row.period_start), "period_end": str(row.period_end)},
    )
    db.flush()
    return row


def assign_user(
    db: Session,
    row: AuditEngagement,
    *,
    user_id: str,
    assignment_role: str,
    actor: CurrentUser,
) -> AuditEngagementAssignment:
    ensure_branch_access(actor, row.branch)
    assignment_role = assignment_role.strip().upper()
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    _validate_assignee(db, user_id=user_id, assignment_role=assignment_role, branch=row.branch)
    existing = db.scalar(
        select(AuditEngagementAssignment).where(
            AuditEngagementAssignment.engagement_id == row.id,
            AuditEngagementAssignment.user_id == user_id,
            AuditEngagementAssignment.assignment_role == assignment_role,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Assignment already exists")
    assignment = AuditEngagementAssignment(
        engagement_id=row.id,
        user_id=user_id,
        assignment_role=assignment_role,
        assigned_by=actor.user_id,
    )
    db.add(assignment)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_ENGAGEMENT",
        entity_id=row.id,
        action="ASSIGN",
        actor=actor.user_id,
        branch=row.branch,
        metadata={"assigned_user_id": user_id, "assignment_role": assignment_role},
    )
    db.flush()
    return assignment


def transition_engagement(
    db: Session, row: AuditEngagement, *, target_status: str, user: CurrentUser
) -> AuditEngagement:
    ensure_branch_access(user, row.branch)
    target = target_status.strip().upper()
    if target not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid engagement transition: {row.status} -> {target}")

    if user.role != "ADMIN":
        if target in {"PLANNED", "IN_PROGRESS", "REVIEW"}:
            if user.role != "AUDITOR" or not _is_assigned(db, row.id, user.user_id, "AUDITOR"):
                raise HTTPException(status_code=403, detail="Assigned AUDITOR role required")
        elif target in {"COMPLETED", "CLOSED"}:
            if user.role != "REVIEWER" or not _is_assigned(db, row.id, user.user_id, "REVIEWER"):
                raise HTTPException(status_code=403, detail="Assigned REVIEWER role required")
        else:
            raise HTTPException(status_code=403, detail="Role not permitted")

    previous = row.status
    row.status = target
    row.updated_by = user.user_id
    record_audit(
        db,
        entity_type="AUDIT_ENGAGEMENT",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=previous,
        status_to=target,
        branch=row.branch,
    )
    db.flush()
    return row


def link_resource(
    db: Session,
    row: AuditEngagement,
    *,
    resource_type: str,
    resource_id: int,
    user: CurrentUser,
) -> None:
    ensure_branch_access(user, row.branch)
    resource_type = resource_type.strip().upper()
    if resource_type == "WORKFLOW_CASE":
        resource = db.get(AuditWorkflowCase, resource_id)
    elif resource_type == "AUDIT_REPORT":
        resource = db.get(AuditReport, resource_id)
    else:
        raise HTTPException(status_code=400, detail="resource_type must be WORKFLOW_CASE or AUDIT_REPORT")
    if resource is None or normalize_branch(resource.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Resource not found")
    current = resource.engagement_id
    if current is not None and current != row.id:
        raise HTTPException(status_code=409, detail="Resource is already linked to another engagement")
    resource.engagement_id = row.id
    record_audit(
        db,
        entity_type="AUDIT_ENGAGEMENT",
        entity_id=row.id,
        action="LINK_RESOURCE",
        actor=user.user_id,
        branch=row.branch,
        metadata={"resource_type": resource_type, "resource_id": resource_id},
    )
    db.flush()


def _html() -> str:
    stages = " → ".join(TRANSITIONS.keys())
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Engagement - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:white;padding:18px 24px}}
main{{max-width:1180px;margin:auto;padding:20px}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}input,select,textarea,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}
button{{background:#1f6feb;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}
pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Audit Engagement & Assignment</h1><p>{escape(stages)}</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="branch" placeholder="Cabang"><select id="status"><option value="">Semua status</option>{''.join(f'<option>{s}</option>' for s in TRANSITIONS)}</select><button id="load">Muat Engagement</button></div></section>
<section class="panel"><h2>Buat Engagement</h2><div class="grid"><input id="code" placeholder="Kode engagement"><input id="title" placeholder="Judul audit"><input id="createBranch" placeholder="Cabang"><input id="start" type="date"><input id="end" type="date"><textarea id="scope" placeholder="Scope audit"></textarea><button id="create">Buat</button></div></section>
<section class="panel"><h2>Assignment / Transition / Link</h2><div class="grid"><input id="engagementId" type="number" placeholder="Engagement ID"><input id="userId" placeholder="User ID"><select id="assignRole"><option>AUDITOR</option><option>REVIEWER</option></select><button id="assign">Assign</button><select id="target">{''.join(f'<option>{s}</option>' for s in list(TRANSITIONS)[1:])}</select><button id="transition">Transition</button><select id="resourceType"><option>WORKFLOW_CASE</option><option>AUDIT_REPORT</option></select><input id="resourceId" type="number" placeholder="Resource ID"><button id="link">Link Resource</button></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>Kode</th><th>Cabang</th><th>Periode</th><th>Status</th><th>Assignments</th><th>Workflow</th><th>Reports</th></tr></thead><tbody id="rows"><tr><td colspan="8">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';
function headers(){{const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {{Authorization:'Bearer '+v}}}}
async function json(url,opt={{}}){{opt.headers=Object.assign({{}},opt.headers||{{}},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);return x}}
async function load(){{const p=new URLSearchParams();if(branch.value.trim())p.set('branch',branch.value.trim());if(status.value)p.set('status',status.value);const x=await json('/audit-engagements?'+p);rows.innerHTML=(x.engagements||[]).map(e=>'<tr><td>'+e.id+'</td><td>'+e.code+'</td><td>'+e.branch+'</td><td>'+e.period_start+' - '+e.period_end+'</td><td>'+e.status+'</td><td>'+e.assignments.map(a=>a.assignment_role+':'+a.user_id).join('<br>')+'</td><td>'+e.workflow_case_ids.join(', ')+'</td><td>'+e.audit_report_ids.join(', ')+'</td></tr>').join('')||'<tr><td colspan="8">Tidak ada engagement.</td></tr>'}}
async function post(url,data){{const fd=new FormData();Object.entries(data).forEach(([k,v])=>{{if(v!==''&&v!=null)fd.append(k,v)}});return json(url,{{method:'POST',body:fd}})}}
load.onclick=()=>load().catch(e=>log.textContent='ERROR: '+e.message);
create.onclick=()=>post('/audit-engagements',{{code:code.value,title:title.value,branch:createBranch.value,period_start:start.value,period_end:end.value,scope:scope.value}}).then(load).catch(e=>log.textContent='ERROR: '+e.message);
assign.onclick=()=>post('/audit-engagements/'+engagementId.value+'/assign',{{user_id:userId.value,assignment_role:assignRole.value}}).then(load).catch(e=>log.textContent='ERROR: '+e.message);
transition.onclick=()=>post('/audit-engagements/'+engagementId.value+'/transition',{{status:target.value}}).then(load).catch(e=>log.textContent='ERROR: '+e.message);
link.onclick=()=>post('/audit-engagements/'+engagementId.value+'/link',{{resource_type:resourceType.value,resource_id:resourceId.value}}).then(load).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-engagements", response_class=HTMLResponse)
def audit_engagement_ui():
    return HTMLResponse(_html())


@router.get("/audit-engagements")
def get_engagements(
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    if status and status.strip().upper() not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="Invalid engagement status")
    effective_branch = scoped_branch(user, branch)
    rows = list_engagements(db, branch=effective_branch, status=status)
    return {"total": len(rows), "branch": effective_branch, "engagements": [engagement_payload(db, r) for r in rows]}


@router.get("/audit-engagements/{engagement_id}")
def get_engagement(
    engagement_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = db.get(AuditEngagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    ensure_branch_access(user, row.branch)
    return engagement_payload(db, row)


@router.post("/audit-engagements")
def post_engagement(
    code: str = Form(...),
    title: str = Form(...),
    branch: str = Form(...),
    period_start: date = Form(...),
    period_end: date = Form(...),
    scope: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = create_engagement(
        db, code=code, title=title, branch=branch, period_start=period_start,
        period_end=period_end, scope=scope, user=user,
    )
    db.commit()
    db.refresh(row)
    return engagement_payload(db, row)


@router.post("/audit-engagements/{engagement_id}/assign")
def post_assignment(
    engagement_id: int,
    user_id: str = Form(...),
    assignment_role: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    row = db.get(AuditEngagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    assignment = assign_user(db, row, user_id=user_id, assignment_role=assignment_role, actor=user)
    db.commit()
    db.refresh(assignment)
    return engagement_payload(db, row)


@router.post("/audit-engagements/{engagement_id}/transition")
def post_transition(
    engagement_id: int,
    status: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = db.get(AuditEngagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    transition_engagement(db, row, target_status=status, user=user)
    db.commit()
    db.refresh(row)
    return engagement_payload(db, row)


@router.post("/audit-engagements/{engagement_id}/link")
def post_link(
    engagement_id: int,
    resource_type: str = Form(...),
    resource_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = db.get(AuditEngagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    link_resource(db, row, resource_type=resource_type, resource_id=resource_id, user=user)
    db.commit()
    return engagement_payload(db, row)


def register_audit_engagement_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
