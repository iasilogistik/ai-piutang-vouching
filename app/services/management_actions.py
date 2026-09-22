from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditFinding,
    CorrectiveActionPlan,
    CorrectiveActionPlanHistory,
    ManagementResponse,
    ManagementResponseVersion,
)

router = APIRouter()
_REGISTERED = False

RESPONSE_POSITIONS = {"AGREE", "PARTIAL", "DISAGREE"}
RESPONSE_TRANSITIONS = {
    "DRAFT": {"SUBMITTED"},
    "RETURNED": {"SUBMITTED"},
    "SUBMITTED": {"ACCEPTED", "RETURNED"},
    "ACCEPTED": set(),
}
PLAN_TRANSITIONS = {
    "OPEN": {"IN_PROGRESS"},
    "IN_PROGRESS": {"SUBMITTED_FOR_VERIFICATION"},
    "SUBMITTED_FOR_VERIFICATION": {"VERIFIED", "RETURNED"},
    "RETURNED": {"IN_PROGRESS"},
    "VERIFIED": {"CLOSED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"IN_PROGRESS"},
}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _finding_for_user(db: Session, finding_id: int, user: CurrentUser) -> AuditFinding:
    row = db.get(AuditFinding, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit finding not found")
    ensure_branch_access(user, row.branch)
    return row


def _response_for_user(db: Session, response_id: int, user: CurrentUser) -> ManagementResponse:
    row = db.get(ManagementResponse, response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Management response not found")
    ensure_branch_access(user, row.branch)
    return row


def _plan_for_user(db: Session, plan_id: int, user: CurrentUser) -> CorrectiveActionPlan:
    row = db.get(CorrectiveActionPlan, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Corrective action plan not found")
    ensure_branch_access(user, row.branch)
    return row


def _snapshot_response(
    db: Session, row: ManagementResponse, *, user: CurrentUser, reason: str | None = None, increment: bool = True
) -> None:
    if increment:
        row.version_number += 1
    db.add(
        ManagementResponseVersion(
            response_id=row.id,
            version_number=row.version_number,
            response_text=row.response_text,
            position=row.position,
            status=row.status,
            changed_by=user.user_id,
            change_reason=reason,
        )
    )
    db.flush()


def _snapshot_plan(
    db: Session, row: CorrectiveActionPlan, *, user: CurrentUser, reason: str | None = None
) -> None:
    db.add(
        CorrectiveActionPlanHistory(
            action_plan_id=row.id,
            status=row.status,
            action_description=row.action_description,
            pic_user_id=row.pic_user_id,
            external_pic_name=row.external_pic_name,
            target_date=row.target_date,
            completion_notes=row.completion_notes,
            changed_by=user.user_id,
            change_reason=reason,
        )
    )
    db.flush()


def _overdue(row: CorrectiveActionPlan, today: date | None = None) -> bool:
    day = today or date.today()
    return row.status != "CLOSED" and row.target_date < day


def response_payload(db: Session, row: ManagementResponse) -> dict[str, object]:
    versions = list(
        db.scalars(
            select(ManagementResponseVersion)
            .where(ManagementResponseVersion.response_id == row.id)
            .order_by(ManagementResponseVersion.version_number)
        ).all()
    )
    plans = list(
        db.scalars(
            select(CorrectiveActionPlan)
            .where(CorrectiveActionPlan.response_id == row.id)
            .order_by(CorrectiveActionPlan.target_date, CorrectiveActionPlan.id)
        ).all()
    )
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "branch": row.branch,
        "response_text": row.response_text,
        "position": row.position,
        "status": row.status,
        "submitted_by": row.submitted_by,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_note": row.review_note,
        "version_number": row.version_number,
        "allowed_transitions": sorted(RESPONSE_TRANSITIONS.get(row.status, set())),
        "versions": [
            {
                "version_number": x.version_number,
                "status": x.status,
                "position": x.position,
                "changed_by": x.changed_by,
                "change_reason": x.change_reason,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in versions
        ],
        "action_plans": [plan_payload(db, x, include_history=False) for x in plans],
    }


def plan_payload(db: Session, row: CorrectiveActionPlan, *, include_history: bool = True) -> dict[str, object]:
    result = {
        "id": row.id,
        "finding_id": row.finding_id,
        "response_id": row.response_id,
        "branch": row.branch,
        "action_description": row.action_description,
        "pic_user_id": row.pic_user_id,
        "external_pic_name": row.external_pic_name,
        "target_date": row.target_date.isoformat(),
        "status": row.status,
        "completion_notes": row.completion_notes,
        "overdue": _overdue(row),
        "days_overdue": max((date.today() - row.target_date).days, 0) if _overdue(row) else 0,
        "allowed_transitions": sorted(PLAN_TRANSITIONS.get(row.status, set())),
    }
    if include_history:
        history = list(
            db.scalars(
                select(CorrectiveActionPlanHistory)
                .where(CorrectiveActionPlanHistory.action_plan_id == row.id)
                .order_by(CorrectiveActionPlanHistory.id)
            ).all()
        )
        result["history"] = [
            {
                "status": x.status,
                "pic_user_id": x.pic_user_id,
                "external_pic_name": x.external_pic_name,
                "target_date": x.target_date.isoformat(),
                "changed_by": x.changed_by,
                "change_reason": x.change_reason,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in history
        ]
    return result


def create_response(db: Session, finding: AuditFinding, *, user: CurrentUser) -> ManagementResponse:
    ensure_branch_access(user, finding.branch)
    if finding.status != "ISSUED":
        raise HTTPException(status_code=409, detail="Management response requires an ISSUED finding")
    existing = db.scalar(select(ManagementResponse).where(ManagementResponse.finding_id == finding.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Management response already exists")
    row = ManagementResponse(finding_id=finding.id, branch=finding.branch, status="DRAFT", version_number=1)
    db.add(row)
    db.flush()
    _snapshot_response(db, row, user=user, increment=False)
    record_audit(
        db, entity_type="MANAGEMENT_RESPONSE", entity_id=row.id, action="CREATE",
        actor=user.user_id, status_to="DRAFT", branch=row.branch, metadata={"finding_id": finding.id},
    )
    return row


def update_response(
    db: Session, row: ManagementResponse, *, response_text: str, position: str, user: CurrentUser
) -> ManagementResponse:
    ensure_branch_access(user, row.branch)
    if user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="Management response editor role required")
    if row.status not in {"DRAFT", "RETURNED"}:
        raise HTTPException(status_code=409, detail="Response can only be edited in DRAFT or RETURNED")
    text = response_text.strip()
    pos = position.strip().upper()
    if not text:
        raise HTTPException(status_code=400, detail="response_text is required")
    if pos not in RESPONSE_POSITIONS:
        raise HTTPException(status_code=400, detail="Invalid management position")
    row.response_text = text
    row.position = pos
    _snapshot_response(db, row, user=user, reason="CONTENT_UPDATE")
    record_audit(
        db, entity_type="MANAGEMENT_RESPONSE", entity_id=row.id, action="UPDATE",
        actor=user.user_id, branch=row.branch, metadata={"position": pos, "version_number": row.version_number},
    )
    db.flush()
    return row


def transition_response(
    db: Session, row: ManagementResponse, *, target_status: str, review_note: str | None, user: CurrentUser
) -> ManagementResponse:
    ensure_branch_access(user, row.branch)
    target = target_status.strip().upper()
    if target not in RESPONSE_TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid response transition: {row.status} -> {target}")
    previous = row.status
    now = datetime.now(timezone.utc)

    if target == "SUBMITTED":
        if user.role not in {"ADMIN", "AUDITOR"}:
            raise HTTPException(status_code=403, detail="Management response editor role required")
        if not row.response_text or row.position not in RESPONSE_POSITIONS:
            raise HTTPException(status_code=400, detail="Response text and position are required before submission")
        row.submitted_by = user.user_id
        row.submitted_at = now
        row.reviewed_by = None
        row.reviewed_at = None
        row.review_note = None
    else:
        if user.role not in {"ADMIN", "REVIEWER"}:
            raise HTTPException(status_code=403, detail="Reviewer role required")
        note = (review_note or "").strip()
        if target == "RETURNED" and not note:
            raise HTTPException(status_code=400, detail="Return note is required")
        row.reviewed_by = user.user_id
        row.reviewed_at = now
        row.review_note = note or None

    row.status = target
    _snapshot_response(db, row, user=user, reason=f"TRANSITION:{previous}->{target}")
    record_audit(
        db, entity_type="MANAGEMENT_RESPONSE", entity_id=row.id, action="TRANSITION",
        actor=user.user_id, status_from=previous, status_to=target, remarks=row.review_note,
        branch=row.branch, metadata={"finding_id": row.finding_id, "version_number": row.version_number},
    )
    db.flush()
    return row


def create_action_plan(
    db: Session,
    response: ManagementResponse,
    *,
    action_description: str,
    pic_user_id: str | None,
    external_pic_name: str | None,
    target_date: date,
    user: CurrentUser,
) -> CorrectiveActionPlan:
    ensure_branch_access(user, response.branch)
    if user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="Action plan editor role required")
    if response.status != "ACCEPTED":
        raise HTTPException(status_code=409, detail="Action plan requires an ACCEPTED management response")
    action = action_description.strip()
    internal = (pic_user_id or "").strip() or None
    external = (external_pic_name or "").strip() or None
    if not action:
        raise HTTPException(status_code=400, detail="action_description is required")
    if (internal is None) == (external is None):
        raise HTTPException(status_code=400, detail="Provide exactly one PIC")
    if internal is not None:
        pic = db.execute(
            text("select user_id, branch, is_active from public.user_roles where user_id=:user_id"),
            {"user_id": internal},
        ).mappings().one_or_none()
        if pic is None or not pic["is_active"]:
            raise HTTPException(status_code=400, detail="PIC user must be active")
        if pic["branch"] and pic["branch"].strip().upper() != response.branch.strip().upper() and user.role != "ADMIN":
            raise HTTPException(status_code=404, detail="PIC user not found")
    row = CorrectiveActionPlan(
        finding_id=response.finding_id,
        response_id=response.id,
        branch=response.branch,
        action_description=action,
        pic_user_id=internal,
        external_pic_name=external,
        target_date=target_date,
        status="OPEN",
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(row)
    db.flush()
    _snapshot_plan(db, row, user=user, reason="CREATE")
    record_audit(
        db, entity_type="CORRECTIVE_ACTION_PLAN", entity_id=row.id, action="CREATE",
        actor=user.user_id, status_to="OPEN", branch=row.branch,
        metadata={"finding_id": row.finding_id, "response_id": row.response_id, "target_date": row.target_date.isoformat()},
    )
    return row


def update_action_plan(
    db: Session,
    row: CorrectiveActionPlan,
    *,
    action_description: str | None,
    pic_user_id: str | None,
    external_pic_name: str | None,
    target_date: date | None,
    completion_notes: str | None,
    user: CurrentUser,
) -> CorrectiveActionPlan:
    ensure_branch_access(user, row.branch)
    if user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="Action plan editor role required")
    if row.status in {"VERIFIED", "CLOSED"}:
        raise HTTPException(status_code=409, detail="Verified or closed action plan cannot be edited")

    if action_description is not None:
        clean = action_description.strip()
        if not clean:
            raise HTTPException(status_code=400, detail="action_description cannot be blank")
        row.action_description = clean
    if target_date is not None:
        row.target_date = target_date
    if completion_notes is not None:
        row.completion_notes = completion_notes.strip() or None
    if pic_user_id is not None or external_pic_name is not None:
        internal = (pic_user_id or "").strip() or None
        external = (external_pic_name or "").strip() or None
        if (internal is None) == (external is None):
            raise HTTPException(status_code=400, detail="Provide exactly one PIC")
        if internal:
            pic = db.execute(
                text("select user_id, is_active from public.user_roles where user_id=:user_id"),
                {"user_id": internal},
            ).mappings().one_or_none()
            if pic is None or not pic["is_active"]:
                raise HTTPException(status_code=400, detail="PIC user must be active")
        row.pic_user_id = internal
        row.external_pic_name = external
    row.updated_by = user.user_id
    _snapshot_plan(db, row, user=user, reason="CONTENT_UPDATE")
    record_audit(
        db, entity_type="CORRECTIVE_ACTION_PLAN", entity_id=row.id, action="UPDATE",
        actor=user.user_id, branch=row.branch, metadata={"target_date": row.target_date.isoformat()},
    )
    db.flush()
    return row


def transition_action_plan(
    db: Session, row: CorrectiveActionPlan, *, target_status: str, reason: str | None, user: CurrentUser
) -> CorrectiveActionPlan:
    ensure_branch_access(user, row.branch)
    target = target_status.strip().upper()
    if target not in PLAN_TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid action plan transition: {row.status} -> {target}")
    previous = row.status
    editor_targets = {"IN_PROGRESS", "SUBMITTED_FOR_VERIFICATION"}
    reviewer_targets = {"VERIFIED", "RETURNED", "CLOSED", "REOPENED"}
    if target in editor_targets and user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="Action plan editor role required")
    if target in reviewer_targets and user.role not in {"ADMIN", "REVIEWER"}:
        raise HTTPException(status_code=403, detail="Reviewer role required")
    clean_reason = (reason or "").strip()
    if target in {"RETURNED", "REOPENED"} and not clean_reason:
        raise HTTPException(status_code=400, detail=f"{target} reason is required")
    if target == "SUBMITTED_FOR_VERIFICATION" and not row.completion_notes:
        raise HTTPException(status_code=400, detail="completion_notes are required before verification")
    row.status = target
    row.updated_by = user.user_id
    _snapshot_plan(db, row, user=user, reason=clean_reason or f"TRANSITION:{previous}->{target}")
    record_audit(
        db, entity_type="CORRECTIVE_ACTION_PLAN", entity_id=row.id, action="TRANSITION",
        actor=user.user_id, status_from=previous, status_to=target, remarks=clean_reason or None,
        branch=row.branch, metadata={"finding_id": row.finding_id, "target_date": row.target_date.isoformat()},
    )
    db.flush()
    return row


def _html() -> str:
    return """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Management Actions</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1100px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
input,select,textarea,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}textarea{min-height:70px}button{background:#1f6feb;color:#fff;font-weight:700}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}pre{background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px;white-space:pre-wrap}
@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head><body>
<header><h1>Management Response & Corrective Action Plans</h1><p>Finding issued → response → accepted → action plan → verification → closed.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="finding" type="number" placeholder="Finding ID"><button id="load">Muat Response</button></div></section>
<section class="panel"><h2>Management Response</h2><div class="grid"><button id="createResponse">Buat Response</button><textarea id="responseText" placeholder="Management response"></textarea><select id="position"><option>AGREE</option><option>PARTIAL</option><option>DISAGREE</option></select><input id="responseId" type="number" placeholder="Response ID"><button id="saveResponse">Simpan</button><select id="responseTarget"><option>SUBMITTED</option><option>ACCEPTED</option><option>RETURNED</option></select><input id="reviewNote" placeholder="Review/return note"><button id="transitionResponse">Transition Response</button></div></section>
<section class="panel"><h2>Action Plan</h2><div class="grid"><input id="action" placeholder="Action description"><input id="pic" placeholder="PIC user ID"><input id="externalPic" placeholder="External PIC"><input id="targetDate" type="date"><button id="createPlan">Buat Action Plan</button><input id="planId" type="number" placeholder="Plan ID"><textarea id="completion" placeholder="Completion notes"></textarea><button id="savePlan">Simpan Progress</button><select id="planTarget"><option>IN_PROGRESS</option><option>SUBMITTED_FOR_VERIFICATION</option><option>VERIFIED</option><option>RETURNED</option><option>CLOSED</option><option>REOPENED</option></select><input id="reason" placeholder="Reason"><button id="transitionPlan">Transition Plan</button></div></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';const log=document.getElementById('log');
function headers(){const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {Authorization:'Bearer '+v}}
async function req(url,opt={}){opt.headers=Object.assign({},opt.headers||{},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}
async function post(url,data,method='POST'){const fd=new FormData();Object.entries(data).forEach(([k,v])=>{if(v!==''&&v!=null)fd.append(k,v)});return req(url,{method,body:fd})}
document.getElementById('load').onclick=()=>req('/management-responses?finding_id='+document.getElementById('finding').value).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('createResponse').onclick=()=>post('/management-responses',{finding_id:document.getElementById('finding').value}).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('saveResponse').onclick=()=>post('/management-responses/'+document.getElementById('responseId').value,{response_text:document.getElementById('responseText').value,position:document.getElementById('position').value},'PATCH').catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('transitionResponse').onclick=()=>post('/management-responses/'+document.getElementById('responseId').value+'/transition',{status:document.getElementById('responseTarget').value,review_note:document.getElementById('reviewNote').value}).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('createPlan').onclick=()=>post('/corrective-action-plans',{response_id:document.getElementById('responseId').value,action_description:document.getElementById('action').value,pic_user_id:document.getElementById('pic').value,external_pic_name:document.getElementById('externalPic').value,target_date:document.getElementById('targetDate').value}).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('savePlan').onclick=()=>post('/corrective-action-plans/'+document.getElementById('planId').value,{completion_notes:document.getElementById('completion').value},'PATCH').catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('transitionPlan').onclick=()=>post('/corrective-action-plans/'+document.getElementById('planId').value+'/transition',{status:document.getElementById('planTarget').value,reason:document.getElementById('reason').value}).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/management-actions", response_class=HTMLResponse)
def management_actions_ui():
    return HTMLResponse(_html())


@router.get("/management-responses")
def get_responses(
    finding_id: int | None = None,
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(ManagementResponse).order_by(ManagementResponse.updated_at.desc(), ManagementResponse.id.desc())
    if effective_branch is not None:
        query = query.where(ManagementResponse.branch == effective_branch)
    if finding_id is not None:
        query = query.where(ManagementResponse.finding_id == finding_id)
    if status:
        query = query.where(ManagementResponse.status == status.strip().upper())
    rows = list(db.scalars(query).all())
    return {"total": len(rows), "responses": [response_payload(db, x) for x in rows]}


@router.post("/management-responses")
def post_response(
    finding_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = create_response(db, _finding_for_user(db, finding_id, user), user=user)
    db.commit(); db.refresh(row)
    return response_payload(db, row)


@router.patch("/management-responses/{response_id}")
def patch_response(
    response_id: int,
    response_text: str = Form(...),
    position: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = update_response(db, _response_for_user(db, response_id, user), response_text=response_text, position=position, user=user)
    db.commit(); db.refresh(row)
    return response_payload(db, row)


@router.post("/management-responses/{response_id}/transition")
def post_response_transition(
    response_id: int,
    status: str = Form(...),
    review_note: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = transition_response(db, _response_for_user(db, response_id, user), target_status=status, review_note=review_note, user=user)
    db.commit(); db.refresh(row)
    return response_payload(db, row)


@router.get("/corrective-action-plans")
def get_action_plans(
    finding_id: int | None = None,
    response_id: int | None = None,
    branch: str | None = None,
    status: str | None = None,
    overdue: bool | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(CorrectiveActionPlan).order_by(CorrectiveActionPlan.target_date, CorrectiveActionPlan.id)
    if effective_branch is not None:
        query = query.where(CorrectiveActionPlan.branch == effective_branch)
    if finding_id is not None:
        query = query.where(CorrectiveActionPlan.finding_id == finding_id)
    if response_id is not None:
        query = query.where(CorrectiveActionPlan.response_id == response_id)
    if status:
        query = query.where(CorrectiveActionPlan.status == status.strip().upper())
    rows = list(db.scalars(query).all())
    if overdue is not None:
        rows = [x for x in rows if _overdue(x) is overdue]
    return {"total": len(rows), "action_plans": [plan_payload(db, x) for x in rows]}


@router.post("/corrective-action-plans")
def post_action_plan(
    response_id: int = Form(...),
    action_description: str = Form(...),
    pic_user_id: str | None = Form(None),
    external_pic_name: str | None = Form(None),
    target_date: date = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    response = _response_for_user(db, response_id, user)
    row = create_action_plan(
        db, response, action_description=action_description, pic_user_id=pic_user_id,
        external_pic_name=external_pic_name, target_date=target_date, user=user,
    )
    db.commit(); db.refresh(row)
    return plan_payload(db, row)


@router.patch("/corrective-action-plans/{plan_id}")
def patch_action_plan(
    plan_id: int,
    action_description: str | None = Form(None),
    pic_user_id: str | None = Form(None),
    external_pic_name: str | None = Form(None),
    target_date: date | None = Form(None),
    completion_notes: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = update_action_plan(
        db, _plan_for_user(db, plan_id, user), action_description=action_description,
        pic_user_id=pic_user_id, external_pic_name=external_pic_name, target_date=target_date,
        completion_notes=completion_notes, user=user,
    )
    db.commit(); db.refresh(row)
    return plan_payload(db, row)


@router.post("/corrective-action-plans/{plan_id}/transition")
def post_action_plan_transition(
    plan_id: int,
    status: str = Form(...),
    reason: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = transition_action_plan(db, _plan_for_user(db, plan_id, user), target_status=status, reason=reason, user=user)
    db.commit(); db.refresh(row)
    return plan_payload(db, row)


def register_management_action_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
