from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.branch_access import normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    BillingReconciliation,
    Document,
    DocumentControlEvidence,
    ImportBatch,
    PhysicalBilling,
    ReviewWorkflow,
    SAPBilling,
    VouchingResult,
)

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _workflow_payload(row: ReviewWorkflow) -> dict[str, object]:
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
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def build_reviewer_dashboard(
    db: Session,
    *,
    reviewer_id: str,
    branch: str | None = None,
) -> dict[str, object]:
    """Build the reviewer landing payload with only two database round-trips.

    The original implementation executed one SELECT for every metric, which made
    first paint noticeably slower against a remote PostgreSQL/Supabase database.
    Scalar subqueries keep the six counters in one statement; the queue is fetched
    separately with a small first-page limit.
    """
    branch = normalize_branch(branch)

    pending_q = select(func.count(ReviewWorkflow.id)).where(
        ReviewWorkflow.status == "AUDITOR_REVIEWED"
    )
    approved_q = select(func.count(ReviewWorkflow.id)).where(
        ReviewWorkflow.reviewer_id == reviewer_id,
        ReviewWorkflow.status.in_(["REVIEWER_APPROVED", "CLOSED"]),
    )
    rejected_q = select(func.count(ReviewWorkflow.id)).where(
        ReviewWorkflow.reviewer_id == reviewer_id,
        ReviewWorkflow.status == "REVIEWER_REJECTED",
    )
    reconciliation_q = (
        select(func.count(BillingReconciliation.id))
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.status == "EXCEPTION")
    )
    vouching_q = (
        select(func.count(VouchingResult.id))
        .join(VouchingResult.billing)
        .join(PhysicalBilling.document)
        .outerjoin(
            DocumentControlEvidence,
            DocumentControlEvidence.id == VouchingResult.control_evidence_id,
        )
        .where(
            (VouchingResult.status == "EXCEPTION")
            | (
                (VouchingResult.status == "REVIEW")
                & (DocumentControlEvidence.review_required.is_(True))
            )
        )
    )
    evidence_q = (
        select(func.count(DocumentControlEvidence.id))
        .join(DocumentControlEvidence.document)
        .where(DocumentControlEvidence.review_required.is_(True))
    )

    if branch is not None:
        pending_q = pending_q.where(ReviewWorkflow.branch == branch)
        approved_q = approved_q.where(ReviewWorkflow.branch == branch)
        rejected_q = rejected_q.where(ReviewWorkflow.branch == branch)
        reconciliation_q = reconciliation_q.where(ImportBatch.branch == branch)
        vouching_q = vouching_q.where(Document.branch == branch)
        evidence_q = evidence_q.where(Document.branch == branch)

    metric_row = db.execute(
        select(
            pending_q.scalar_subquery().label("waiting_reviewer"),
            reconciliation_q.scalar_subquery().label("reconciliation_attention"),
            vouching_q.scalar_subquery().label("vouching_attention"),
            evidence_q.scalar_subquery().label("control_evidence_review"),
            approved_q.scalar_subquery().label("approved_by_me"),
            rejected_q.scalar_subquery().label("rejected_by_me"),
        )
    ).mappings().one()

    recent_q = (
        select(ReviewWorkflow)
        .where(ReviewWorkflow.status == "AUDITOR_REVIEWED")
        .order_by(ReviewWorkflow.updated_at.desc(), ReviewWorkflow.id.desc())
        .limit(30)
    )
    if branch is not None:
        recent_q = recent_q.where(ReviewWorkflow.branch == branch)
    pending_rows = list(db.scalars(recent_q).all())

    return {
        "branch": branch,
        "metrics": {key: int(value or 0) for key, value in metric_row.items()},
        "pending_workflows": [_workflow_payload(row) for row in pending_rows],
    }


def reviewer_center_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reviewer Center - AI Piutang Vouching</title>
<style>
:root{--bg:#f4f7fb;--surface:#fff;--line:#dbe5f0;--text:#172033;--muted:#64748b;--blue:#2563eb;--blue2:#1d4ed8;--green:#047857;--amber:#92400e;--red:#b91c1c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
header{padding:22px 26px;background:linear-gradient(135deg,#0f2b5f,#1d4ed8 58%,#0ea5e9);color:white}
header h1{margin:0;font-size:24px}header p{margin:7px 0 0;color:#dbeafe;font-size:12px;line-height:1.5}
main{padding:20px 24px 42px}.toolbar,.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;margin-bottom:14px;box-shadow:0 8px 24px rgba(15,23,42,.05)}
.scope{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:end}label{display:block;margin:0 0 6px;font-size:11px;font-weight:800;color:#475569}
input{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;font:inherit}
button,.btn{min-height:40px;border:0;border-radius:10px;padding:9px 13px;background:var(--blue);color:white;font:inherit;font-size:12px;font-weight:850;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
.btn.secondary,button.secondary{background:#475569}.btn.green,button.green{background:var(--green)}button.danger{background:var(--red)}button:disabled{opacity:.55;cursor:not-allowed}
.metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-bottom:14px}.metric{padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.metric span{display:block;color:var(--muted);font-size:10px}.metric b{display:block;margin-top:7px;font-size:24px}.metric.warn{background:#fffbeb;border-color:#fde68a}.metric.bad{background:#fff7f7;border-color:#fecaca}.metric.ok{background:#f0fdf4;border-color:#bbf7d0}
.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}.section-head h2{margin:0;font-size:17px}.section-head p{margin:4px 0 0;color:var(--muted);font-size:11px}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;min-width:1050px;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #edf2f7;text-align:left;font-size:11px;vertical-align:middle}th{background:#f8fafc;color:#475569;font-weight:850}tr:last-child td{border-bottom:0}
.status{display:inline-flex;padding:5px 8px;border-radius:999px;background:#fef3c7;color:#92400e;font-weight:850;font-size:10px}.remarks{min-width:220px;color:#475569;line-height:1.45}.row-actions{display:grid;grid-template-columns:minmax(190px,1fr) auto auto;gap:7px;align-items:center}.row-actions input{min-height:36px;font-size:11px}
.notice{padding:11px 12px;border-radius:11px;background:#eff6ff;color:#1e3a8a;border:1px solid #bfdbfe;font-size:11px;line-height:1.5}.log{margin-top:12px;padding:11px;border-radius:10px;background:#0f172a;color:#dbeafe;white-space:pre-wrap;font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:170px;overflow:auto}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){main{padding:15px}.scope{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header><h1>Reviewer Center</h1><p>Area khusus REVIEWER. Antrean diprioritaskan untuk stempel yang tidak terbaca jelas/tidak cocok dan exception yang benar-benar memerlukan keputusan reviewer.</p></header>
<main>
<section class="panel scope">
  <div><label>Cabang / Scope</label><input id="branch" placeholder="Semua cabang jika user memiliki scope global"></div>
  <div><label>Status Sesi</label><input id="session" value="Memeriksa sesi..." disabled></div>
  <button id="refresh" type="button">Refresh Reviewer Center</button>
</section>

<section class="metrics" id="metrics">
  <div class="metric"><span>Menunggu Reviewer</span><b>-</b></div>
  <div class="metric"><span>Reconciliation Attention</span><b>-</b></div>
  <div class="metric"><span>Vouching Attention</span><b>-</b></div>
  <div class="metric"><span>Evidence Review</span><b>-</b></div>
  <div class="metric"><span>Approved by Me</span><b>-</b></div>
  <div class="metric"><span>Rejected by Me</span><b>-</b></div>
</section>

<section class="panel">
  <div class="section-head">
    <div><h2>Akses Reviewer</h2><p>Dashboard tetap read-only; keputusan review dilakukan pada item yang sudah selesai direview auditor.</p></div>
    <div class="actions">
      <a class="btn secondary" href="/ui/dashboard">Dashboard Cabang</a>
      <a class="btn secondary" href="/ui/review-queue">Review Queue</a>
      <a class="btn secondary" href="/ui/control-evidence">Control Evidence</a>
      <a class="btn secondary" href="/ui/exceptions">Exceptions</a>
    </div>
  </div>
  <div class="notice"><strong>Prioritas reviewer:</strong> stempel tidak terbaca jelas, nama stempel tidak cukup cocok dengan customer SAP, tanda tangan yang secara eksplisit terindikasi hilang, atau exception yang sudah dinaikkan auditor. OCR yang hanya berstatus UNKNOWN tidak otomatis menambah antrean reviewer.</div>
</section>

<section class="panel">
  <div class="section-head"><div><h2>Menunggu Keputusan Reviewer</h2><p>Hanya workflow berstatus AUDITOR_REVIEWED yang ditampilkan di antrean utama.</p></div></div>
  <div class="table-wrap"><table>
    <thead><tr><th>ID</th><th>Cabang</th><th>Resource</th><th>Status</th><th>Auditor</th><th>Catatan Auditor</th><th>Keputusan Reviewer</th></tr></thead>
    <tbody id="rows"><tr><td colspan="7">Memuat antrean reviewer...</td></tr></tbody>
  </table></div>
  <div class="log" id="log">Siap memuat Reviewer Center.</div>
</section>
</main>
<script>
const branchEl=document.getElementById('branch');
const sessionEl=document.getElementById('session');
const metricsEl=document.getElementById('metrics');
const rowsEl=document.getElementById('rows');
const logEl=document.getElementById('log');
let profile=null;
function token(){return (localStorage.getItem('auditToken')||'').trim();}
function headers(){const t=token();if(!t)throw new Error('Sesi login tidak ditemukan. Silakan login ulang.');return {Authorization:'Bearer '+t};}
function esc(v){return String(v??'-').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
async function body(r){const text=await r.text();let x={};try{x=text?JSON.parse(text):{};}catch(_){throw new Error('Response server tidak dapat dibaca. HTTP '+r.status);}if(!r.ok)throw new Error(x.detail||('HTTP '+r.status));return x;}
function log(message,payload=null){logEl.textContent=message+(payload?'\n\n'+JSON.stringify(payload,null,2):'');}
function applySession(x){
  profile=x;
  const role=String(x?.role||'').toUpperCase();
  if(!['REVIEWER','ADMIN'].includes(role))return false;
  const scope=x.branch||x.access_scope||'ALL';
  sessionEl.value=role+' · '+scope;
  if(x.branch){branchEl.value=x.branch;branchEl.disabled=true;}
  return true;
}
function cachedSession(){
  try{
    const raw=localStorage.getItem('auditUser');
    if(!raw)return null;
    const x=JSON.parse(raw);
    return applySession(x)?x:null;
  }catch(_){return null;}
}
async function loadSession(){
  const x=await body(await fetch('/auth/me',{headers:headers()}));
  if(!applySession(x))throw new Error('Menu Reviewer Center hanya untuk role REVIEWER atau ADMIN.');
  localStorage.setItem('auditUser',JSON.stringify(x));
  return x;
}
function renderMetrics(m){
  const defs=[
    ['Menunggu Reviewer',m.waiting_reviewer,'warn'],
    ['Reconciliation Exception',m.reconciliation_attention,'bad'],
    ['Vouching Reviewer',m.vouching_attention,'warn'],
    ['Stamp / Evidence Review',m.control_evidence_review,'warn'],
    ['Approved by Me',m.approved_by_me,'ok'],
    ['Rejected by Me',m.rejected_by_me,'bad']
  ];
  metricsEl.innerHTML=defs.map(([label,value,cls])=>'<div class="metric '+cls+'"><span>'+esc(label)+'</span><b>'+esc(value||0)+'</b></div>').join('');
}
function renderRows(items){
  if(!items.length){rowsEl.innerHTML='<tr><td colspan="7">Tidak ada item yang menunggu keputusan reviewer.</td></tr>';return;}
  rowsEl.innerHTML=items.map(w=>'<tr>'+
    '<td>#'+esc(w.id)+'</td>'+
    '<td>'+esc(w.branch)+'</td>'+
    '<td><strong>'+esc(w.entity_type)+'</strong> #'+esc(w.entity_id)+'</td>'+
    '<td><span class="status">'+esc(w.status)+'</span></td>'+
    '<td>'+esc(w.auditor_id||'-')+'</td>'+
    '<td class="remarks">'+esc(w.auditor_remarks||'Tidak ada catatan auditor.')+'</td>'+
    '<td><div class="row-actions"><input data-remarks="'+esc(w.id)+'" placeholder="Catatan reviewer (disarankan)">'+
      '<button class="green" data-approve="'+esc(w.id)+'" type="button">Approve</button>'+
      '<button class="danger" data-reject="'+esc(w.id)+'" type="button">Reject</button></div></td>'+
  '</tr>').join('');
  rowsEl.querySelectorAll('[data-approve]').forEach(btn=>btn.addEventListener('click',()=>decide(Number(btn.dataset.approve),'REVIEWER_APPROVED',btn)));
  rowsEl.querySelectorAll('[data-reject]').forEach(btn=>btn.addEventListener('click',()=>decide(Number(btn.dataset.reject),'REVIEWER_REJECTED',btn)));
}
async function loadDashboard(){
  const p=new URLSearchParams();const b=branchEl.value.trim();if(b)p.set('branch',b);
  const x=await body(await fetch('/reviewer/dashboard?'+p.toString(),{headers:headers()}));
  if(x.branch && !branchEl.value.trim()){branchEl.value=x.branch;branchEl.disabled=true;}
  renderMetrics(x.metrics||{});renderRows(x.pending_workflows||[]);
  log('Reviewer Center berhasil dimuat cepat.',{branch:x.branch,total_pending:(x.pending_workflows||[]).length});
  return x;
}
async function decide(id,status,button){
  const input=rowsEl.querySelector('[data-remarks="'+id+'"]');
  const remarks=input?input.value.trim():'';
  button.disabled=true;
  try{
    const fd=new FormData();fd.append('status',status);if(remarks)fd.append('remarks',remarks);
    const x=await body(await fetch('/review-workflows/'+id+'/transition',{method:'PATCH',headers:headers(),body:fd}));
    log('Keputusan reviewer berhasil disimpan.',x);await loadDashboard();
  }catch(error){log('KEPUTUSAN REVIEW GAGAL: '+error.message);}
  finally{button.disabled=false;}
}
async function refresh(){
  try{
    const cached=cachedSession();
    const dashboardPromise=loadDashboard();
    if(!cached)await loadSession();
    await dashboardPromise;
  }catch(error){log('REVIEWER CENTER GAGAL: '+error.message);}
}
document.getElementById('refresh').addEventListener('click',refresh);
branchEl.addEventListener('change',()=>loadDashboard().catch(e=>log('REFRESH GAGAL: '+e.message)));
refresh();
</script>
</body></html>"""


@router.get("/ui/reviewer-center", response_class=HTMLResponse)
def reviewer_center_ui():
    return HTMLResponse(reviewer_center_html())


@router.get("/reviewer/dashboard")
def reviewer_dashboard_api(
    branch: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    payload = build_reviewer_dashboard(
        db,
        reviewer_id=user.user_id,
        branch=effective_branch,
    )
    payload["role"] = user.role
    return payload


def register_reviewer_center_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
