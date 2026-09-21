from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, scoped_branch, write_branch
from app.database import SessionLocal
from app.models import AuditException

router = APIRouter()
_REGISTERED = False

EXCEPTION_TYPES = {
    "BILLING_MISSING",
    "SPJ_MISSING",
    "AMOUNT_MISMATCH",
    "CUSTOMER_MISMATCH",
    "DATE_MISMATCH",
    "DUPLICATE_DOCUMENT",
    "PHYSICAL_DOCUMENT_MISSING",
    "SAP_DATA_MISSING",
    "EVIDENCE_MISSING",
}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _enum(value: str, allowed: set[str], field: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return normalized


def exception_payload(row: AuditException, *, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    end_date = row.resolved_at.date() if row.resolved_at else today
    created_date = row.created_at.date()
    aging_days = max((end_date - created_date).days, 0)
    return {
        "id": row.id,
        "type": row.type,
        "branch": row.branch,
        "severity": row.severity,
        "status": row.status,
        "owner": row.owner,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "aging_days": aging_days,
        "auditor_note": row.auditor_note,
        "reviewer_note": row.reviewer_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def list_exception_records(
    db: Session,
    *,
    branch: str | None = None,
    status: str | None = None,
    exception_type: str | None = None,
    severity: str | None = None,
    owner: str | None = None,
) -> list[AuditException]:
    query = select(AuditException).order_by(AuditException.created_at.desc(), AuditException.id.desc())
    if branch is not None:
        query = query.where(AuditException.branch == branch)
    if status:
        query = query.where(AuditException.status == status.upper())
    if exception_type:
        query = query.where(AuditException.type == exception_type.upper())
    if severity:
        query = query.where(AuditException.severity == severity.upper())
    if owner:
        query = query.where(AuditException.owner == owner)
    return list(db.scalars(query).all())


def _html() -> str:
    types = "".join(f'<option value="{value}">{value}</option>' for value in sorted(EXCEPTION_TYPES))
    severities = "".join(f'<option value="{value}">{value}</option>' for value in ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exception Management - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:white;padding:18px 24px}}
main{{max-width:1180px;margin:auto;padding:20px}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}label{{display:block;font-size:12px;color:#64748b;margin-bottom:4px}}
input,select,textarea,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}textarea{{min-height:70px}}
button{{background:#1f6feb;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}
pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>Exception Management</h1><p>Kelola exception audit per cabang, severity, owner, due date, status, dan aging.</p></header>
<main>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div>
<div><label>Cabang</label><input id="branch" placeholder="ADMIN: isi cabang; non-ADMIN terkunci"></div>
<div><label>Filter Status</label><select id="filterStatus"><option value="">Semua</option><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option><option>CLOSED</option></select></div>
<div><label>Filter Severity</label><select id="filterSeverity"><option value="">Semua</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></div>
</div><button id="load" style="margin-top:10px">Muat Exception</button></section>

<section class="panel"><h2>Tambah Exception</h2><div class="grid">
<div><label>Type</label><select id="type">{types}</select></div>
<div><label>Severity</label><select id="severity">{severities}</select></div>
<div><label>Owner</label><input id="owner"></div>
<div><label>Due Date</label><input id="dueDate" type="date"></div>
<div style="grid-column:span 2"><label>Auditor Note</label><textarea id="auditorNote"></textarea></div>
</div><button id="create" style="margin-top:10px">Buat Exception</button></section>

<section class="panel"><table><thead><tr><th>ID</th><th>Cabang</th><th>Type</th><th>Severity</th><th>Status</th><th>Owner</th><th>Due</th><th>Aging</th></tr></thead>
<tbody id="rows"><tr><td colspan="8">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const tokenEl=document.getElementById('token');tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){{const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',t);return {{Authorization:'Bearer '+t}}}}
function qs(){{const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();if(b)p.set('branch',b);const s=document.getElementById('filterStatus').value;if(s)p.set('status',s);const sev=document.getElementById('filterSeverity').value;if(sev)p.set('severity',sev);return p}}
async function load(){{const r=await fetch('/exception-records?'+qs().toString(),{{headers:headers()}});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));const rows=b.exceptions||[];document.getElementById('rows').innerHTML=rows.length?rows.map(x=>'<tr><td>'+x.id+'</td><td>'+x.branch+'</td><td>'+x.type+'</td><td>'+x.severity+'</td><td>'+x.status+'</td><td>'+(x.owner||'-')+'</td><td>'+(x.due_date||'-')+'</td><td>'+x.aging_days+' hari</td></tr>').join(''):'<tr><td colspan="8">Tidak ada exception.</td></tr>';document.getElementById('log').textContent=JSON.stringify(b,null,2)}}
async function create(){{const fd=new FormData();for(const [id,key] of [['branch','branch'],['type','type'],['severity','severity'],['owner','owner'],['dueDate','due_date'],['auditorNote','auditor_note']]){{const v=document.getElementById(id).value.trim();if(v)fd.append(key,v)}}const r=await fetch('/exception-records',{{method:'POST',headers:headers(),body:fd}});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));document.getElementById('log').textContent=JSON.stringify(b,null,2);await load()}}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>create().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/exceptions", response_class=HTMLResponse)
def exceptions_ui():
    return HTMLResponse(_html())


@router.get("/exception-records")
def list_exceptions(
    branch: str | None = None,
    status: str | None = None,
    exception_type: str | None = None,
    severity: str | None = None,
    owner: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    if status:
        status = _enum(status, STATUSES, "status")
    if exception_type:
        exception_type = _enum(exception_type, EXCEPTION_TYPES, "exception_type")
    if severity:
        severity = _enum(severity, SEVERITIES, "severity")
    rows = list_exception_records(
        db,
        branch=effective_branch,
        status=status,
        exception_type=exception_type,
        severity=severity,
        owner=_clean(owner),
    )
    return {"total": len(rows), "branch": effective_branch, "exceptions": [exception_payload(row) for row in rows]}


@router.post("/exception-records")
def create_exception(
    type: str = Form(...),
    branch: str | None = Form(None),
    severity: str = Form("MEDIUM"),
    owner: str | None = Form(None),
    due_date: date | None = Form(None),
    auditor_note: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    exception_type = _enum(type, EXCEPTION_TYPES, "type")
    severity = _enum(severity, SEVERITIES, "severity")
    target_branch = write_branch(user, branch)
    row = AuditException(
        type=exception_type,
        branch=target_branch,
        severity=severity,
        status="OPEN",
        owner=_clean(owner),
        due_date=due_date,
        auditor_note=_clean(auditor_note),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_EXCEPTION",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to=row.status,
        remarks=row.auditor_note,
        metadata={"type": row.type, "severity": row.severity, "owner": row.owner, "due_date": row.due_date.isoformat() if row.due_date else None},
        branch=row.branch,
    )
    db.commit()
    db.refresh(row)
    return exception_payload(row)


@router.patch("/exception-records/{exception_id}")
def update_exception(
    exception_id: int,
    status: str | None = Form(None),
    severity: str | None = Form(None),
    owner: str | None = Form(None),
    due_date: date | None = Form(None),
    auditor_note: str | None = Form(None),
    reviewer_note: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = db.get(AuditException, exception_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    ensure_branch_access(user, row.branch)

    if auditor_note is not None and user.role not in {"ADMIN", "AUDITOR"}:
        raise HTTPException(status_code=403, detail="Only ADMIN or AUDITOR may update auditor_note")
    if reviewer_note is not None and user.role not in {"ADMIN", "REVIEWER"}:
        raise HTTPException(status_code=403, detail="Only ADMIN or REVIEWER may update reviewer_note")

    old_status = row.status
    if status is not None:
        row.status = _enum(status, STATUSES, "status")
    if severity is not None:
        row.severity = _enum(severity, SEVERITIES, "severity")
    if owner is not None:
        row.owner = _clean(owner)
    if due_date is not None:
        row.due_date = due_date
    if auditor_note is not None:
        row.auditor_note = _clean(auditor_note)
    if reviewer_note is not None:
        row.reviewer_note = _clean(reviewer_note)

    if row.status in {"RESOLVED", "CLOSED"}:
        if row.resolved_at is None:
            row.resolved_at = datetime.now(timezone.utc)
    elif old_status in {"RESOLVED", "CLOSED"}:
        row.resolved_at = None

    record_audit(
        db,
        entity_type="AUDIT_EXCEPTION",
        entity_id=row.id,
        action="UPDATE",
        actor=user.user_id,
        status_from=old_status,
        status_to=row.status,
        remarks=row.reviewer_note if user.role == "REVIEWER" else row.auditor_note,
        metadata={"severity": row.severity, "owner": row.owner, "due_date": row.due_date.isoformat() if row.due_date else None},
        branch=row.branch,
    )
    db.commit()
    db.refresh(row)
    return exception_payload(row)


def register_exception_management_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
