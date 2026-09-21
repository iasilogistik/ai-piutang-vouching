from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.branch_access import scoped_branch
from app.database import SessionLocal
from app.models import BillingReconciliation, Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, SAPBilling, VouchingResult

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_branch_dashboard(
    db: Session,
    *,
    branch: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
) -> dict[str, object]:
    batch_filters = []
    doc_filters = []
    if branch:
        batch_filters.append(ImportBatch.branch == branch)
        doc_filters.append(Document.branch == branch)
    if date_from:
        batch_filters.append(func.date(ImportBatch.uploaded_at) >= date_from)
        doc_filters.append(func.date(Document.uploaded_at) >= date_from)
    if date_to:
        batch_filters.append(func.date(ImportBatch.uploaded_at) <= date_to)
        doc_filters.append(func.date(Document.uploaded_at) <= date_to)

    sap_q = select(func.count(SAPBilling.id)).join(ImportBatch)
    physical_q = select(func.count(PhysicalBilling.id)).join(Document)
    rec_q = select(BillingReconciliation.status, func.count(BillingReconciliation.id)).join(SAPBilling).join(ImportBatch).group_by(BillingReconciliation.status)
    vouch_q = select(VouchingResult.status, func.count(VouchingResult.id)).join(PhysicalBilling).join(Document).group_by(VouchingResult.status)
    control_q = select(
        func.count(DocumentControlEvidence.id),
        func.sum(func.cast(DocumentControlEvidence.review_required, int)),
    ).join(Document)

    for condition in batch_filters:
        sap_q = sap_q.where(condition)
        rec_q = rec_q.where(condition)
    for condition in doc_filters:
        physical_q = physical_q.where(condition)
        vouch_q = vouch_q.where(condition)
        control_q = control_q.where(condition)

    rec_counts = {row[0]: int(row[1]) for row in db.execute(rec_q).all()}
    vouch_counts = {row[0]: int(row[1]) for row in db.execute(vouch_q).all()}
    control_total, control_review = db.execute(control_q).one()
    control_total = int(control_total or 0)
    control_review = int(control_review or 0)

    exception_statuses = {"EXCEPTION", "REVIEW", "NOT_FOUND"}
    matched = rec_counts.get("MATCH", 0)
    unmatched = sum(rec_counts.get(key, 0) for key in exception_statuses)
    pending_review = rec_counts.get("REVIEW", 0) + vouch_counts.get("REVIEW", 0) + control_review
    rejected = rec_counts.get("EXCEPTION", 0) + vouch_counts.get("EXCEPTION", 0)
    approved = matched + vouch_counts.get("PASS", 0)

    payload = {
        "branch": branch,
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "status": status.upper() if status else None,
        },
        "metrics": {
            "sap_billing": int(db.scalar(sap_q) or 0),
            "physical_billing": int(db.scalar(physical_q) or 0),
            "matched": matched,
            "unmatched": unmatched,
            "control_evidence_total": control_total,
            "control_evidence_review": control_review,
            "pending_review": pending_review,
            "rejected": rejected,
            "approved": approved,
        },
        "reconciliation_status": rec_counts,
        "vouching_status": vouch_counts,
    }
    if status:
        key = status.upper()
        payload["status_total"] = rec_counts.get(key, 0) + vouch_counts.get(key, 0)
    return payload


def _html() -> str:
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Cabang - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:white;padding:18px 24px}
main{max-width:1180px;margin:auto;padding:20px}.panel{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{padding:14px;border:1px solid #d9e0ea;border-radius:10px}
.card b{font-size:24px;display:block;margin-top:6px}input,button{padding:9px;border:1px solid #cbd5e1;border-radius:8px}button{background:#1f6feb;color:white;font-weight:700;cursor:pointer}
.filters{display:flex;gap:8px;flex-wrap:wrap}pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}
@media(max-width:800px){.grid{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><h1>Dashboard Cabang</h1><p>Ringkasan branch-aware untuk SAP, billing fisik, rekonsiliasi, vouching, dan control evidence.</p></header>
<main>
<section class="panel"><div class="filters">
<input id="branch" placeholder="Cabang (ADMIN: kosong = semua)">
<input id="from" type="date"><input id="to" type="date"><input id="status" placeholder="Status opsional">
<button id="load">Muat Dashboard</button></div></section>
<section class="panel"><div class="grid" id="cards"></div></section>
<section class="panel"><pre id="detail">Belum dimuat.</pre></section>
</main><script>
const token=()=>localStorage.getItem('auditToken')||'';
async function load(){const p=new URLSearchParams();for(const [id,key] of [['branch','branch'],['from','date_from'],['to','date_to'],['status','status']]){const v=document.getElementById(id).value.trim();if(v)p.set(key,v)}
const r=await fetch('/dashboard/branch?'+p.toString(),{headers:{Authorization:'Bearer '+token()}});const b=await r.json();if(!r.ok){document.getElementById('detail').textContent=JSON.stringify(b,null,2);return}
const labels={sap_billing:'SAP Billing',physical_billing:'Physical Billing',matched:'Matched',unmatched:'Unmatched',control_evidence_total:'Control Evidence',control_evidence_review:'Evidence Review',pending_review:'Pending Review',rejected:'Rejected',approved:'Approved'};
document.getElementById('cards').innerHTML=Object.entries(b.metrics).map(([k,v])=>'<div class="card"><span>'+(labels[k]||k)+'</span><b>'+v+'</b></div>').join('');
document.getElementById('detail').textContent=JSON.stringify(b,null,2)}
document.getElementById('load').onclick=load;load();
</script></body></html>"""


@router.get("/ui/dashboard", response_class=HTMLResponse)
def dashboard_ui():
    return HTMLResponse(_html())


@router.get("/dashboard/branch")
def dashboard_api(
    branch: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")
    return build_branch_dashboard(
        db,
        branch=scoped_branch(user, branch),
        date_from=date_from,
        date_to=date_to,
        status=status,
    )


def register_branch_dashboard_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
