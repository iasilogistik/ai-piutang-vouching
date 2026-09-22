from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
    AuditFinding,
    CorrectiveActionEvidence,
    CorrectiveActionPlan,
    CorrectiveActionPlanHistory,
    CorrectiveActionProgressUpdate,
    CorrectiveActionVerification,
    Document,
    DocumentControlEvidence,
)
from app.services.management_actions import plan_payload, transition_action_plan

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _plan_for_user(db: Session, plan_id: int, user: CurrentUser) -> CorrectiveActionPlan:
    row = db.get(CorrectiveActionPlan, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Corrective action plan not found")
    ensure_branch_access(user, row.branch)
    return row


def _can_submit_progress(row: CorrectiveActionPlan, user: CurrentUser) -> bool:
    if user.role in {"ADMIN", "AUDITOR"}:
        return True
    return bool(row.pic_user_id and row.pic_user_id == user.user_id)


def _aging(row: CorrectiveActionPlan, *, as_of: date | None = None) -> dict[str, int | bool]:
    today = as_of or _utc_today()
    created = row.created_at.date() if row.created_at else today
    days_open = max((today - created).days, 0)
    days_overdue = max((today - row.target_date).days, 0) if row.status != "CLOSED" else 0
    return {
        "days_open": days_open,
        "days_overdue": days_overdue,
        "overdue": row.status != "CLOSED" and row.target_date < today,
    }


def follow_up_payload(db: Session, row: CorrectiveActionPlan) -> dict[str, object]:
    payload = plan_payload(db, row)
    finding = db.get(AuditFinding, row.finding_id)
    progress = list(
        db.scalars(
            select(CorrectiveActionProgressUpdate)
            .where(CorrectiveActionProgressUpdate.action_plan_id == row.id)
            .order_by(CorrectiveActionProgressUpdate.created_at, CorrectiveActionProgressUpdate.id)
        ).all()
    )
    evidence = list(
        db.scalars(
            select(CorrectiveActionEvidence)
            .where(CorrectiveActionEvidence.action_plan_id == row.id)
            .order_by(CorrectiveActionEvidence.id)
        ).all()
    )
    verifications = list(
        db.scalars(
            select(CorrectiveActionVerification)
            .where(CorrectiveActionVerification.action_plan_id == row.id)
            .order_by(CorrectiveActionVerification.verified_at, CorrectiveActionVerification.id)
        ).all()
    )
    payload.update(_aging(row))
    payload.update(
        {
            "engagement_id": finding.engagement_id if finding else None,
            "finding_reference": finding.reference if finding else None,
            "finding_title": finding.title if finding else None,
            "severity": finding.severity if finding else None,
            "progress_updates": [
                {
                    "id": x.id,
                    "update_text": x.update_text,
                    "progress_percent": x.progress_percent,
                    "submitted_by": x.submitted_by,
                    "created_at": x.created_at.isoformat() if x.created_at else None,
                }
                for x in progress
            ],
            "completion_evidence": [
                {
                    "id": x.id,
                    "document_id": x.document_id,
                    "control_evidence_id": x.control_evidence_id,
                    "linked_by": x.linked_by,
                    "linked_at": x.linked_at.isoformat() if x.linked_at else None,
                }
                for x in evidence
            ],
            "verifications": [
                {
                    "id": x.id,
                    "result": x.result,
                    "verification_note": x.verification_note,
                    "verified_by": x.verified_by,
                    "verified_at": x.verified_at.isoformat() if x.verified_at else None,
                }
                for x in verifications
            ],
        }
    )
    return payload


def add_progress_update(
    db: Session,
    row: CorrectiveActionPlan,
    *,
    update_text: str,
    progress_percent: int | None,
    user: CurrentUser,
) -> CorrectiveActionProgressUpdate:
    ensure_branch_access(user, row.branch)
    if not _can_submit_progress(row, user):
        raise HTTPException(status_code=403, detail="Only the assigned PIC, AUDITOR, or ADMIN can submit progress")
    if row.status in {"VERIFIED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="Verified or closed plan cannot receive progress updates")
    text = update_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="update_text is required")
    if progress_percent is not None and not 0 <= progress_percent <= 100:
        raise HTTPException(status_code=400, detail="progress_percent must be between 0 and 100")
    update = CorrectiveActionProgressUpdate(
        action_plan_id=row.id,
        branch=row.branch,
        update_text=text,
        progress_percent=progress_percent,
        submitted_by=user.user_id,
    )
    db.add(update)
    db.flush()
    record_audit(
        db,
        entity_type="CORRECTIVE_ACTION_PLAN",
        entity_id=row.id,
        action="FOLLOW_UP_PROGRESS",
        actor=user.user_id,
        branch=row.branch,
        metadata={"progress_update_id": update.id, "progress_percent": progress_percent},
    )
    return update


def link_completion_evidence(
    db: Session,
    row: CorrectiveActionPlan,
    *,
    document_id: int | None,
    control_evidence_id: int | None,
    user: CurrentUser,
) -> CorrectiveActionEvidence:
    ensure_branch_access(user, row.branch)
    if not _can_submit_progress(row, user):
        raise HTTPException(status_code=403, detail="Only the assigned PIC, AUDITOR, or ADMIN can link completion evidence")
    if row.status in {"VERIFIED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="Verified or closed plan cannot receive new completion evidence")
    if (document_id is None) == (control_evidence_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one evidence source")

    document = db.get(Document, document_id) if document_id is not None else None
    if control_evidence_id is not None:
        control = db.get(DocumentControlEvidence, control_evidence_id)
        document = db.get(Document, control.document_id) if control else None
    if document is None or normalize_branch(document.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Completion evidence not found")

    existing = db.scalar(
        select(CorrectiveActionEvidence.id).where(
            CorrectiveActionEvidence.action_plan_id == row.id,
            CorrectiveActionEvidence.document_id == document_id,
            CorrectiveActionEvidence.control_evidence_id == control_evidence_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Completion evidence already linked")

    link = CorrectiveActionEvidence(
        action_plan_id=row.id,
        branch=row.branch,
        document_id=document_id,
        control_evidence_id=control_evidence_id,
        linked_by=user.user_id,
    )
    db.add(link)
    db.flush()
    record_audit(
        db,
        entity_type="CORRECTIVE_ACTION_PLAN",
        entity_id=row.id,
        action="LINK_COMPLETION_EVIDENCE",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "evidence_link_id": link.id,
            "document_id": document_id,
            "control_evidence_id": control_evidence_id,
        },
    )
    return link


def verify_action_plan(
    db: Session,
    row: CorrectiveActionPlan,
    *,
    result: str,
    note: str | None,
    user: CurrentUser,
) -> CorrectiveActionVerification:
    ensure_branch_access(user, row.branch)
    if user.role not in {"ADMIN", "REVIEWER"}:
        raise HTTPException(status_code=403, detail="Reviewer role required")
    if row.status != "SUBMITTED_FOR_VERIFICATION":
        raise HTTPException(status_code=409, detail="Plan must be SUBMITTED_FOR_VERIFICATION")
    decision = result.strip().upper()
    if decision not in {"VERIFIED", "RETURNED"}:
        raise HTTPException(status_code=400, detail="Verification result must be VERIFIED or RETURNED")
    clean_note = (note or "").strip()
    if decision == "RETURNED" and not clean_note:
        raise HTTPException(status_code=400, detail="Verification return note is required")
    if decision == "VERIFIED":
        evidence_count = len(
            db.scalars(
                select(CorrectiveActionEvidence.id).where(
                    CorrectiveActionEvidence.action_plan_id == row.id
                )
            ).all()
        )
        if evidence_count == 0:
            raise HTTPException(status_code=400, detail="Completion evidence is required before verification")

    verification = CorrectiveActionVerification(
        action_plan_id=row.id,
        branch=row.branch,
        result=decision,
        verification_note=clean_note or None,
        verified_by=user.user_id,
    )
    db.add(verification)
    db.flush()
    transition_action_plan(
        db,
        row,
        target_status=decision,
        reason=clean_note or None,
        user=user,
    )
    record_audit(
        db,
        entity_type="CORRECTIVE_ACTION_PLAN",
        entity_id=row.id,
        action="FOLLOW_UP_VERIFICATION",
        actor=user.user_id,
        branch=row.branch,
        metadata={"verification_id": verification.id, "result": decision},
    )
    return verification


def _html() -> str:
    return """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Follow-up</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1200px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
input,select,textarea,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}textarea{min-height:70px}button{background:#1f6feb;color:#fff;font-weight:700}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpi{padding:12px;border:1px solid #e2e8f0;border-radius:10px}.kpi strong{font-size:22px;display:block}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}pre{background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px;white-space:pre-wrap}
@media(max-width:850px){.grid,.kpis{grid-template-columns:1fr}}</style></head><body>
<header><h1>Audit Follow-up Monitoring</h1><p>Monitor action plan, overdue, evidence, verification, aging, and reopening.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="branch" placeholder="Branch"><input id="pic" placeholder="PIC user"><select id="status"><option value="">All status</option><option>OPEN</option><option>IN_PROGRESS</option><option>SUBMITTED_FOR_VERIFICATION</option><option>VERIFIED</option><option>CLOSED</option><option>RETURNED</option><option>REOPENED</option></select><button id="load">Muat Follow-up</button></div></section>
<section class="panel"><div class="kpis" id="kpis"></div></section>
<section class="panel"><h2>Update Progress</h2><div class="grid"><input id="planId" type="number" placeholder="Action Plan ID"><textarea id="progressText" placeholder="Progress update"></textarea><input id="progressPct" type="number" min="0" max="100" placeholder="Progress %"><button id="progress">Submit Progress</button></div></section>
<section class="panel"><h2>Verification</h2><div class="grid"><input id="verifyPlanId" type="number" placeholder="Action Plan ID"><select id="result"><option>VERIFIED</option><option>RETURNED</option></select><input id="note" placeholder="Verification note"><button id="verify">Verify</button></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>Finding</th><th>Branch</th><th>PIC</th><th>Severity</th><th>Status</th><th>Target</th><th>Aging</th><th>Overdue</th></tr></thead><tbody id="rows"></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';const log=document.getElementById('log');
function headers(){const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {Authorization:'Bearer '+v}}
async function req(url,opt={}){opt.headers=Object.assign({},opt.headers||{},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}
async function post(url,data){const fd=new FormData();Object.entries(data).forEach(([k,v])=>{if(v!==''&&v!=null)fd.append(k,v)});return req(url,{method:'POST',body:fd})}
async function loadData(){const p=new URLSearchParams();for(const [id,key] of [['branch','branch'],['pic','pic_user_id'],['status','status']]){const v=document.getElementById(id).value;if(v)p.set(key,v)}const x=await req('/follow-up?'+p);document.getElementById('kpis').innerHTML=Object.entries(x.summary).map(([k,v])=>'<div class="kpi"><strong>'+v+'</strong>'+k+'</div>').join('');document.getElementById('rows').innerHTML=x.items.map(i=>'<tr><td>'+i.id+'</td><td>'+i.finding_reference+'</td><td>'+i.branch+'</td><td>'+(i.pic_user_id||i.external_pic_name||'')+'</td><td>'+i.severity+'</td><td>'+i.status+'</td><td>'+i.target_date+'</td><td>'+i.days_open+'</td><td>'+i.days_overdue+'</td></tr>').join('')}
document.getElementById('load').onclick=()=>loadData().catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('progress').onclick=()=>post('/corrective-action-plans/'+document.getElementById('planId').value+'/progress',{update_text:document.getElementById('progressText').value,progress_percent:document.getElementById('progressPct').value}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('verify').onclick=()=>post('/corrective-action-plans/'+document.getElementById('verifyPlanId').value+'/verification',{result:document.getElementById('result').value,note:document.getElementById('note').value}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/follow-up", response_class=HTMLResponse)
def follow_up_ui():
    return HTMLResponse(_html())


@router.get("/follow-up")
def get_follow_up(
    branch: str | None = None,
    engagement_id: int | None = None,
    pic_user_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    overdue: bool | None = None,
    due_within_days: int = 7,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = (
        select(CorrectiveActionPlan)
        .join(AuditFinding, AuditFinding.id == CorrectiveActionPlan.finding_id)
        .order_by(CorrectiveActionPlan.target_date, CorrectiveActionPlan.id)
    )
    if effective_branch is not None:
        query = query.where(CorrectiveActionPlan.branch == effective_branch)
    if engagement_id is not None:
        query = query.where(AuditFinding.engagement_id == engagement_id)
    if pic_user_id:
        query = query.where(CorrectiveActionPlan.pic_user_id == pic_user_id.strip())
    if status:
        query = query.where(CorrectiveActionPlan.status == status.strip().upper())
    if severity:
        query = query.where(AuditFinding.severity == severity.strip().upper())

    rows = list(db.scalars(query).all())
    today = _utc_today()
    items = [follow_up_payload(db, x) for x in rows]
    if overdue is not None:
        items = [x for x in items if bool(x["overdue"]) is overdue]

    due_limit = today + timedelta(days=max(due_within_days, 0))
    summary = {
        "open": sum(1 for x in rows if x.status != "CLOSED"),
        "due_soon": sum(
            1 for x in rows
            if x.status != "CLOSED" and today <= x.target_date <= due_limit
        ),
        "overdue": sum(1 for x in rows if x.status != "CLOSED" and x.target_date < today),
        "awaiting_verification": sum(1 for x in rows if x.status == "SUBMITTED_FOR_VERIFICATION"),
        "closed": sum(1 for x in rows if x.status == "CLOSED"),
    }
    return {"summary": summary, "total": len(items), "items": items}


@router.get("/follow-up/{plan_id}")
def get_follow_up_detail(
    plan_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return follow_up_payload(db, _plan_for_user(db, plan_id, user))


@router.post("/corrective-action-plans/{plan_id}/progress")
def post_progress(
    plan_id: int,
    update_text: str = Form(...),
    progress_percent: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = _plan_for_user(db, plan_id, user)
    update = add_progress_update(
        db, row, update_text=update_text, progress_percent=progress_percent, user=user
    )
    db.commit(); db.refresh(update)
    return follow_up_payload(db, row)


@router.post("/corrective-action-plans/{plan_id}/completion-evidence")
def post_completion_evidence(
    plan_id: int,
    document_id: int | None = Form(None),
    control_evidence_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = _plan_for_user(db, plan_id, user)
    link = link_completion_evidence(
        db, row, document_id=document_id, control_evidence_id=control_evidence_id, user=user
    )
    db.commit(); db.refresh(link)
    return follow_up_payload(db, row)


@router.post("/corrective-action-plans/{plan_id}/verification")
def post_verification(
    plan_id: int,
    result: str = Form(...),
    note: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    row = _plan_for_user(db, plan_id, user)
    verification = verify_action_plan(db, row, result=result, note=note, user=user)
    db.commit(); db.refresh(verification)
    return follow_up_payload(db, row)


def register_follow_up_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
