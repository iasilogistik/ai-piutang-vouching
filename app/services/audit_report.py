from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch, write_branch
from app.database import SessionLocal
from app.models import (
    AuditException,
    AuditReport,
    BillingReconciliation,
    Document,
    ImportBatch,
    PhysicalBilling,
    SAPBilling,
)

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _period_bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end must be on or after period_start")
    start = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start, end


def build_audit_snapshot(db: Session, *, branch: str, period_start: date, period_end: date) -> dict[str, int]:
    branch = normalize_branch(branch)
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")
    start_dt, end_dt = _period_bounds(period_start, period_end)

    population_count = db.scalar(
        select(func.count(SAPBilling.id))
        .join(ImportBatch, ImportBatch.id == SAPBilling.import_batch_id)
        .where(
            ImportBatch.branch == branch,
            SAPBilling.doc_date >= period_start,
            SAPBilling.doc_date <= period_end,
        )
    ) or 0

    sampled_count = db.scalar(
        select(func.count(PhysicalBilling.id))
        .join(Document, Document.id == PhysicalBilling.document_id)
        .where(
            Document.branch == branch,
            PhysicalBilling.doc_date >= period_start,
            PhysicalBilling.doc_date <= period_end,
        )
    ) or 0

    matched_count = db.scalar(
        select(func.count(BillingReconciliation.id))
        .join(SAPBilling, SAPBilling.id == BillingReconciliation.sap_billing_id)
        .join(ImportBatch, ImportBatch.id == SAPBilling.import_batch_id)
        .where(
            ImportBatch.branch == branch,
            SAPBilling.doc_date >= period_start,
            SAPBilling.doc_date <= period_end,
            BillingReconciliation.status == "MATCH",
        )
    ) or 0

    exception_count = db.scalar(
        select(func.count(AuditException.id)).where(
            AuditException.branch == branch,
            AuditException.created_at >= start_dt,
            AuditException.created_at < end_dt,
        )
    ) or 0

    resolved_exception_count = db.scalar(
        select(func.count(AuditException.id)).where(
            AuditException.branch == branch,
            AuditException.created_at >= start_dt,
            AuditException.created_at < end_dt,
            AuditException.status.in_(("RESOLVED", "CLOSED")),
        )
    ) or 0

    unresolved_exception_count = db.scalar(
        select(func.count(AuditException.id)).where(
            AuditException.branch == branch,
            AuditException.created_at >= start_dt,
            AuditException.created_at < end_dt,
            AuditException.status.in_(("OPEN", "IN_PROGRESS")),
        )
    ) or 0

    return {
        "population_count": int(population_count),
        "sampled_count": int(sampled_count),
        "matched_count": int(matched_count),
        "exception_count": int(exception_count),
        "resolved_exception_count": int(resolved_exception_count),
        "unresolved_exception_count": int(unresolved_exception_count),
    }


def default_finding_summary(metrics: dict[str, int]) -> str:
    return (
        f"Population {metrics['population_count']}; sample {metrics['sampled_count']}; "
        f"matched {metrics['matched_count']}; exception {metrics['exception_count']} "
        f"({metrics['unresolved_exception_count']} unresolved, "
        f"{metrics['resolved_exception_count']} resolved)."
    )


def report_payload(row: AuditReport) -> dict[str, object]:
    return {
        "id": row.id,
        "branch": row.branch,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "status": row.status,
        "population_count": row.population_count,
        "sampled_count": row.sampled_count,
        "matched_count": row.matched_count,
        "exception_count": row.exception_count,
        "unresolved_exception_count": row.unresolved_exception_count,
        "resolved_exception_count": row.resolved_exception_count,
        "finding_summary": row.finding_summary,
        "conclusion": row.conclusion,
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


def list_audit_reports(
    db: Session,
    *,
    branch: str | None = None,
    status: str | None = None,
) -> list[AuditReport]:
    query = select(AuditReport).order_by(AuditReport.period_end.desc(), AuditReport.id.desc())
    if branch is not None:
        query = query.where(AuditReport.branch == normalize_branch(branch))
    if status:
        query = query.where(AuditReport.status == status.strip().upper())
    return list(db.scalars(query).all())


def _html() -> str:
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Reports - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}
main{max-width:1200px;margin:auto;padding:20px}.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}label{display:block;font-size:12px;color:#64748b;margin-bottom:4px}
input,select,textarea,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}textarea{min-height:72px}
button{background:#1f6feb;color:white;font-weight:700;cursor:pointer}table{width:100%;border-collapse:collapse}
th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}
@media(max-width:850px){.grid{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>Audit Reports</h1><p>Snapshot population, sample, reconciliation dan exception per cabang/periode.</p></header>
<main>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div>
<div><label>Cabang</label><input id="branch" placeholder="ADMIN: kosong = semua saat melihat"></div>
<div><label>Status</label><select id="filterStatus"><option value="">Semua</option><option>DRAFT</option><option>APPROVED</option></select></div>
<div><button id="load" style="margin-top:18px">Muat Report</button></div>
</div></section>

<section class="panel"><h2>Buat Snapshot Report</h2><div class="grid">
<div><label>Cabang</label><input id="createBranch" placeholder="Wajib untuk ADMIN"></div>
<div><label>Period Start</label><input id="periodStart" type="date"></div>
<div><label>Period End</label><input id="periodEnd" type="date"></div>
<div></div>
<div style="grid-column:span 2"><label>Finding Summary (opsional)</label><textarea id="finding"></textarea></div>
<div style="grid-column:span 2"><label>Conclusion (opsional)</label><textarea id="conclusion"></textarea></div>
</div><button id="create" style="margin-top:10px">Generate Snapshot</button></section>

<section class="panel"><h2>Approval</h2><div class="grid">
<div><label>Report ID</label><input id="approveId" type="number" min="1"></div>
<div><button id="approve" style="margin-top:18px">Approve Report</button></div>
</div></section>

<section class="panel"><table><thead><tr><th>ID</th><th>Cabang</th><th>Periode</th><th>Status</th><th>Population</th><th>Sample</th><th>Match</th><th>Exception</th><th>Unresolved</th></tr></thead>
<tbody id="rows"><tr><td colspan="9">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const tokenEl=document.getElementById('token');tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',t);return {Authorization:'Bearer '+t}}
async function load(){const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();const s=document.getElementById('filterStatus').value;if(b)p.set('branch',b);if(s)p.set('status',s);const r=await fetch('/audit-reports?'+p.toString(),{headers:headers()});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));const rows=x.reports||[];document.getElementById('rows').innerHTML=rows.length?rows.map(v=>'<tr><td>'+v.id+'</td><td>'+v.branch+'</td><td>'+v.period_start+' s/d '+v.period_end+'</td><td>'+v.status+'</td><td>'+v.population_count+'</td><td>'+v.sampled_count+'</td><td>'+v.matched_count+'</td><td>'+v.exception_count+'</td><td>'+v.unresolved_exception_count+'</td></tr>').join(''):'<tr><td colspan="9">Tidak ada report.</td></tr>';document.getElementById('log').textContent=JSON.stringify(x,null,2)}
async function create(){const fd=new FormData();for(const [id,key] of [['createBranch','branch'],['periodStart','period_start'],['periodEnd','period_end'],['finding','finding_summary'],['conclusion','conclusion']]){const v=document.getElementById(id).value.trim();if(v)fd.append(key,v)}const r=await fetch('/audit-reports',{method:'POST',headers:headers(),body:fd});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
async function approve(){const id=document.getElementById('approveId').value;const r=await fetch('/audit-reports/'+encodeURIComponent(id)+'/approve',{method:'POST',headers:headers()});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>create().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('approve').onclick=()=>approve().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-reports", response_class=HTMLResponse)
def audit_reports_ui():
    return HTMLResponse(_html())


@router.get("/audit-reports")
def get_audit_reports(
    branch: str | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    if status and status.strip().upper() not in {"DRAFT", "APPROVED"}:
        raise HTTPException(status_code=400, detail="Invalid report status")
    rows = list_audit_reports(db, branch=effective_branch, status=status)
    return {"total": len(rows), "branch": effective_branch, "reports": [report_payload(row) for row in rows]}


@router.get("/audit-reports/{report_id}")
def get_audit_report(
    report_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = db.get(AuditReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit report not found")
    ensure_branch_access(user, row.branch)
    return report_payload(row)


@router.post("/audit-reports")
def create_audit_report(
    period_start: date = Form(...),
    period_end: date = Form(...),
    branch: str | None = Form(None),
    finding_summary: str | None = Form(None),
    conclusion: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    target_branch = write_branch(user, branch)
    metrics = build_audit_snapshot(db, branch=target_branch, period_start=period_start, period_end=period_end)
    row = AuditReport(
        branch=target_branch,
        period_start=period_start,
        period_end=period_end,
        status="DRAFT",
        created_by=user.user_id,
        finding_summary=(finding_summary or "").strip() or default_finding_summary(metrics),
        conclusion=(conclusion or "").strip() or None,
        **metrics,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_REPORT",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="DRAFT",
        branch=row.branch,
        metadata={"period_start": row.period_start.isoformat(), "period_end": row.period_end.isoformat(), **metrics},
    )
    db.commit()
    db.refresh(row)
    return report_payload(row)


@router.patch("/audit-reports/{report_id}")
def update_audit_report(
    report_id: int,
    finding_summary: str | None = Form(None),
    conclusion: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = db.get(AuditReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit report not found")
    ensure_branch_access(user, row.branch)
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Approved audit report is immutable")
    if finding_summary is not None:
        row.finding_summary = finding_summary.strip() or None
    if conclusion is not None:
        row.conclusion = conclusion.strip() or None
    record_audit(
        db,
        entity_type="AUDIT_REPORT",
        entity_id=row.id,
        action="UPDATE",
        actor=user.user_id,
        status_from="DRAFT",
        status_to="DRAFT",
        branch=row.branch,
    )
    db.commit()
    db.refresh(row)
    return report_payload(row)


@router.post("/audit-reports/{report_id}/approve")
def approve_audit_report(
    report_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    row = db.get(AuditReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit report not found")
    ensure_branch_access(user, row.branch)
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Audit report is already approved")
    row.status = "APPROVED"
    row.approved_by = user.user_id
    row.approved_at = datetime.now(timezone.utc)
    record_audit(
        db,
        entity_type="AUDIT_REPORT",
        entity_id=row.id,
        action="APPROVE",
        actor=user.user_id,
        status_from="DRAFT",
        status_to="APPROVED",
        branch=row.branch,
    )
    db.commit()
    db.refresh(row)
    return report_payload(row)


def register_audit_report_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
