from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.audit_service import list_audit_trail
from app.auth import CurrentUser, require_roles
from app.branch_access import scoped_branch
from app.database import SessionLocal

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _entry(row) -> dict[str, object]:
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "action": row.action,
        "status_from": row.status_from,
        "status_to": row.status_to,
        "actor": row.actor,
        "branch": row.branch,
        "remarks": row.remarks,
        "metadata": row.metadata_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def audit_trail_html() -> str:
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Trail - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:white;padding:18px 24px}
main{max-width:1280px;margin:auto;padding:20px}.panel{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}label{display:block;font-size:12px;color:#64748b;margin-bottom:4px}
input,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}button{background:#1f6feb;color:#fff;font-weight:700;cursor:pointer}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px;vertical-align:top}
pre{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#dbeafe;padding:10px;border-radius:8px;margin:0}
@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>Audit Trail Viewer</h1><p>Filter aktivitas berdasarkan tanggal, actor, cabang, action, dan resource.</p></header>
<main>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div>
<div><label>Cabang</label><input id="branch" placeholder="ADMIN: kosong = semua"></div>
<div><label>Tanggal Dari</label><input id="dateFrom" type="date"></div>
<div><label>Tanggal Sampai</label><input id="dateTo" type="date"></div>
<div><label>Actor</label><input id="actor"></div>
<div><label>Action</label><input id="action" placeholder="UPLOAD / REVIEW / TRANSITION"></div>
<div><label>Entity Type</label><input id="entityType" placeholder="DOCUMENT"></div>
<div><label>Entity ID</label><input id="entityId" type="number" min="1"></div>
</div><button id="load" style="margin-top:10px">Muat Audit Trail</button></section>
<section class="panel"><table><thead><tr><th>Waktu</th><th>Cabang</th><th>Actor</th><th>Resource</th><th>Action</th><th>Status</th><th>Remarks</th><th>Metadata</th></tr></thead>
<tbody id="rows"><tr><td colspan="8">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const tokenEl=document.getElementById('token');tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',t);return {Authorization:'Bearer '+t}}
function params(){const p=new URLSearchParams();for(const [id,key] of [['branch','branch'],['dateFrom','date_from'],['dateTo','date_to'],['actor','actor'],['action','action'],['entityType','entity_type'],['entityId','entity_id']]){const v=document.getElementById(id).value.trim();if(v)p.set(key,v)}p.set('limit','200');return p}
async function load(){const r=await fetch('/audit-trail/query?'+params().toString(),{headers:headers()});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));const rows=b.entries||[];document.getElementById('rows').innerHTML=rows.length?rows.map(x=>'<tr><td>'+x.created_at+'</td><td>'+(x.branch||'-')+'</td><td>'+(x.actor||'-')+'</td><td>'+x.entity_type+' #'+(x.entity_id??'-')+'</td><td>'+x.action+'</td><td>'+(x.status_from||'-')+' → '+(x.status_to||'-')+'</td><td>'+(x.remarks||'-')+'</td><td><pre>'+JSON.stringify(x.metadata||{},null,2)+'</pre></td></tr>').join(''):'<tr><td colspan="8">Tidak ada data.</td></tr>';document.getElementById('log').textContent=JSON.stringify({total:b.total,branch:b.branch},null,2)}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-trail", response_class=HTMLResponse)
def audit_trail_ui():
    return HTMLResponse(audit_trail_html())


@router.get("/audit-trail/query")
def audit_trail_query(
    entity_type: str | None = None,
    entity_id: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    branch: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")
    effective_branch = scoped_branch(user, branch)
    rows = list_audit_trail(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        branch=effective_branch,
    )
    return {"total": len(rows), "branch": effective_branch, "entries": [_entry(row) for row in rows]}


def register_audit_trail_ui_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
