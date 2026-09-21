from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, scoped_branch
from app.database import SessionLocal
from app.models import AuditClosing, AuditReport

router = APIRouter()
_REGISTERED = False

TRANSITIONS = {
    "OPEN": {"AUDITOR_SIGNED"},
    "AUDITOR_SIGNED": {"REVIEWER_SIGNED"},
    "REVIEWER_SIGNED": {"CLOSED"},
    "CLOSED": set(),
}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def closing_payload(row: AuditClosing) -> dict[str, object]:
    return {
        "id": row.id,
        "audit_report_id": row.audit_report_id,
        "branch": row.branch,
        "status": row.status,
        "closing_note": row.closing_note,
        "auditor_signoff_by": row.auditor_signoff_by,
        "auditor_signed_at": row.auditor_signed_at.isoformat() if row.auditor_signed_at else None,
        "reviewer_signoff_by": row.reviewer_signoff_by,
        "reviewer_signed_at": row.reviewer_signed_at.isoformat() if row.reviewer_signed_at else None,
        "closed_by": row.closed_by,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "allowed_transitions": sorted(TRANSITIONS.get(row.status, set())),
    }


def list_audit_closings(
    db: Session,
    *,
    branch: str | None = None,
    status: str | None = None,
) -> list[AuditClosing]:
    query = select(AuditClosing).order_by(AuditClosing.updated_at.desc(), AuditClosing.id.desc())
    if branch is not None:
        query = query.where(AuditClosing.branch == branch)
    if status:
        query = query.where(AuditClosing.status == status.strip().upper())
    return list(db.scalars(query).all())


def transition_audit_closing(
    db: Session,
    row: AuditClosing,
    *,
    target_status: str,
    user: CurrentUser,
) -> AuditClosing:
    target_status = target_status.strip().upper()
    if target_status not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid closing transition: {row.status} -> {target_status}")
    ensure_branch_access(user, row.branch)

    if target_status == "AUDITOR_SIGNED" and user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="AUDITOR role required for auditor sign-off")
    if target_status in {"REVIEWER_SIGNED", "CLOSED"} and user.role not in {"ADMIN", "REVIEWER"}:
        raise HTTPException(status_code=403, detail="REVIEWER role required for reviewer sign-off/closing")

    old_status = row.status
    now = datetime.now(timezone.utc)
    row.status = target_status

    if target_status == "AUDITOR_SIGNED":
        row.auditor_signoff_by = user.user_id
        row.auditor_signed_at = now
    elif target_status == "REVIEWER_SIGNED":
        row.reviewer_signoff_by = user.user_id
        row.reviewer_signed_at = now
    elif target_status == "CLOSED":
        row.closed_by = user.user_id
        row.closed_at = now

    record_audit(
        db,
        entity_type="AUDIT_CLOSING",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=old_status,
        status_to=target_status,
        branch=row.branch,
        metadata={"audit_report_id": row.audit_report_id},
    )
    db.flush()
    return row


def _html() -> str:
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Closing - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}
main{max-width:1200px;margin:auto;padding:20px}.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}label{display:block;font-size:12px;color:#64748b;margin-bottom:4px}
input,select,textarea,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}textarea{min-height:72px}
button{background:#1f6feb;color:white;font-weight:700;cursor:pointer}table{width:100%;border-collapse:collapse}
th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}
@media(max-width:850px){.grid{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>Audit Closing & Sign-off</h1><p>Approved Report → Auditor Sign-off → Reviewer Sign-off → Closed.</p></header>
<main>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div>
<div><label>Cabang</label><input id="branch" placeholder="ADMIN: kosong = semua"></div>
<div><label>Status</label><select id="filterStatus"><option value="">Semua</option><option>OPEN</option><option>AUDITOR_SIGNED</option><option>REVIEWER_SIGNED</option><option>CLOSED</option></select></div>
<div><button id="load" style="margin-top:18px">Muat Closing</button></div>
</div></section>

<section class="panel"><h2>Mulai Closing</h2><div class="grid">
<div><label>Approved Audit Report ID</label><input id="reportId" type="number" min="1"></div>
<div style="grid-column:span 3"><label>Closing Note</label><textarea id="closingNote"></textarea></div>
</div><button id="create" style="margin-top:10px">Buat Closing</button></section>

<section class="panel"><h2>Sign-off / Close</h2><div class="grid">
<div><label>Closing ID</label><input id="closingId" type="number" min="1"></div>
<div><label>Aksi</label><select id="targetStatus"><option>AUDITOR_SIGNED</option><option>REVIEWER_SIGNED</option><option>CLOSED</option></select></div>
<div><button id="transition" style="margin-top:18px">Proses</button></div>
</div></section>

<section class="panel"><table><thead><tr><th>ID</th><th>Report</th><th>Cabang</th><th>Status</th><th>Auditor</th><th>Reviewer</th><th>Closed By</th><th>Next</th></tr></thead>
<tbody id="rows"><tr><td colspan="8">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const tokenEl=document.getElementById('token');tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',t);return {Authorization:'Bearer '+t}}
async function load(){const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();const s=document.getElementById('filterStatus').value;if(b)p.set('branch',b);if(s)p.set('status',s);const r=await fetch('/audit-closings?'+p.toString(),{headers:headers()});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));const rows=x.closings||[];document.getElementById('rows').innerHTML=rows.length?rows.map(v=>'<tr><td>'+v.id+'</td><td>'+v.audit_report_id+'</td><td>'+v.branch+'</td><td>'+v.status+'</td><td>'+(v.auditor_signoff_by||'-')+'</td><td>'+(v.reviewer_signoff_by||'-')+'</td><td>'+(v.closed_by||'-')+'</td><td>'+v.allowed_transitions.join(', ')+'</td></tr>').join(''):'<tr><td colspan="8">Tidak ada closing.</td></tr>';document.getElementById('log').textContent=JSON.stringify(x,null,2)}
async function create(){const fd=new FormData();fd.append('audit_report_id',document.getElementById('reportId').value);const n=document.getElementById('closingNote').value.trim();if(n)fd.append('closing_note',n);const r=await fetch('/audit-closings',{method:'POST',headers:headers(),body:fd});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
async function transition(){const id=document.getElementById('closingId').value;const status=document.getElementById('targetStatus').value;const r=await fetch('/audit-closings/'+encodeURIComponent(id)+'/transition',{method:'POST',headers:headers(),body:new URLSearchParams({status})});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>create().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('transition').onclick=()=>transition().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-closing", response_class=HTMLResponse)
def audit_closing_ui():
    return HTMLResponse(_html())


@router.get("/audit-closings")
def get_audit_closings(
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    if status and status.strip().upper() not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="Invalid closing status")
    rows = list_audit_closings(db, branch=effective_branch, status=status)
    return {"total": len(rows), "branch": effective_branch, "closings": [closing_payload(row) for row in rows]}


@router.post("/audit-closings")
def create_audit_closing(
    audit_report_id: int = Form(...),
    closing_note: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    report = db.get(AuditReport, audit_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Audit report not found")
    ensure_branch_access(user, report.branch)
    if report.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Audit report must be APPROVED before closing")

    existing = db.scalar(select(AuditClosing).where(AuditClosing.audit_report_id == report.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Audit closing already exists for report")

    row = AuditClosing(
        audit_report_id=report.id,
        branch=report.branch,
        status="OPEN",
        closing_note=(closing_note or "").strip() or None,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_CLOSING",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="OPEN",
        branch=row.branch,
        metadata={"audit_report_id": report.id},
    )
    db.commit()
    db.refresh(row)
    return closing_payload(row)


@router.post("/audit-closings/{closing_id}/transition")
def audit_closing_transition(
    closing_id: int,
    status: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = db.get(AuditClosing, closing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit closing not found")
    transition_audit_closing(db, row, target_status=status, user=user)
    db.commit()
    db.refresh(row)
    return closing_payload(row)


def register_audit_closing_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
