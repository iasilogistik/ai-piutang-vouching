from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, require_roles
from app.branch_access import normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    BillingReconciliation,
    Document,
    DocumentControlEvidence,
    ImportBatch,
    PhysicalBilling,
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


def _apply_branch(query, branch: str | None, *, source: str):
    if branch is None:
        return query
    if source == "batch":
        return query.where(ImportBatch.branch == branch)
    if source == "document":
        return query.where(Document.branch == branch)
    raise ValueError("Unsupported branch source")


def _reconciliation_payload(row: BillingReconciliation) -> dict[str, object]:
    sap = row.sap_billing
    batch = sap.import_batch if sap else None
    physical = row.physical_billing
    remarks = row.remarks or ""
    if row.exception_code == "BILLING_DOCUMENT_NOT_FOUND" or row.status == "NOT_FOUND":
        evidence_state = "BILLING_BELUM_LENGKAP"
        issue = "Billing belum lengkap"
    elif "SPJ belum lengkap" in remarks:
        evidence_state = "SPJ_BELUM_LENGKAP"
        issue = "SPJ belum lengkap"
    elif row.status == "EXCEPTION":
        evidence_state = "MISMATCH"
        issue = "Data tidak sesuai / exception"
    elif row.status == "REVIEW":
        evidence_state = "REVIEW"
        issue = "Perlu review"
    else:
        evidence_state = "LENGKAP"
        issue = "Hasil sesuai"
    return {
        "kind": "RECONCILIATION",
        "id": row.id,
        "branch": batch.branch if batch else None,
        "billing_document": sap.billing_document if sap else None,
        "customer": (sap.customer_account_name or sap.customer) if sap else None,
        "spj_number": (physical.no_spj_raw or physical.no_spj) if physical else None,
        "status": row.status,
        "evidence_state": evidence_state,
        "issue": issue,
        "remarks": row.remarks,
        "nominal_difference": str(row.nominal_difference),
    }


def _vouching_payload(row: VouchingResult) -> dict[str, object]:
    billing = row.billing
    doc = billing.document if billing else None
    if row.rule_code in {"BILLING_WITHOUT_SPJ", "SPJ_NOT_FOUND"}:
        evidence_state = "SPJ_BELUM_LENGKAP"
        issue = "SPJ belum lengkap"
    elif row.rule_code == "SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE":
        evidence_state = "SPJ_OCR_REVIEW"
        issue = "SPJ tersedia, nomor belum terbaca OCR"
    elif row.rule_code in {"DUPLICATE_SPJ_NUMBER", "DUPLICATE_PAIRED_SPJ_EVIDENCE"}:
        evidence_state = "SPJ_PERLU_REVIEW"
        issue = "SPJ perlu review"
    elif row.status == "EXCEPTION":
        evidence_state = "EXCEPTION"
        issue = "Vouching exception"
    elif row.status == "REVIEW":
        evidence_state = "REVIEW"
        issue = "Perlu review"
    else:
        evidence_state = "LENGKAP"
        issue = "SPJ sesuai"
    return {
        "kind": "SPJ_VOUCHING",
        "id": row.id,
        "branch": doc.branch if doc else None,
        "billing_document": billing.billing_document_raw or billing.billing_document if billing else None,
        "spj_number": row.no_spj_billing or row.no_spj_document,
        "status": row.status,
        "evidence_state": evidence_state,
        "issue": issue,
        "remarks": row.remarks,
    }


def _reconciliation_rows(
    db: Session,
    *,
    branch: str | None,
    attention_only: bool,
    limit: int,
) -> list[dict[str, object]]:
    query = (
        select(BillingReconciliation)
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .options(
            joinedload(BillingReconciliation.sap_billing).joinedload(SAPBilling.import_batch),
            joinedload(BillingReconciliation.physical_billing),
        )
        .order_by(BillingReconciliation.id.desc())
        .limit(limit)
    )
    if attention_only:
        query = query.where(BillingReconciliation.status.in_(["REVIEW", "EXCEPTION", "NOT_FOUND"]))
    if branch is not None:
        query = query.where(ImportBatch.branch == branch)
    return [_reconciliation_payload(row) for row in db.scalars(query).all()]


def _vouching_attention_rows(
    db: Session,
    *,
    branch: str | None,
    limit: int,
) -> list[dict[str, object]]:
    query = (
        select(VouchingResult)
        .join(VouchingResult.billing)
        .join(PhysicalBilling.document)
        .options(
            joinedload(VouchingResult.billing).joinedload(PhysicalBilling.document),
        )
        .where(VouchingResult.status.in_(["REVIEW", "EXCEPTION"]))
        .order_by(VouchingResult.id.desc())
        .limit(limit)
    )
    if branch is not None:
        query = query.where(Document.branch == branch)
    return [_vouching_payload(row) for row in db.scalars(query).all()]


def build_viewer_dashboard(
    db: Session,
    *,
    branch: str | None = None,
    include_recent: bool = True,
    include_attention: bool = True,
    limit: int = 60,
) -> dict[str, object]:
    """Build the read-only dashboard with a compact number of DB round-trips."""
    branch = normalize_branch(branch)
    limit = max(1, min(int(limit), 100))

    sap_count_q = select(func.count(SAPBilling.id)).join(ImportBatch)
    match_q = (
        select(func.count(BillingReconciliation.id))
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.status == "MATCH")
    )
    review_q = (
        select(func.count(BillingReconciliation.id))
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.status == "REVIEW")
    )
    exception_q = (
        select(func.count(BillingReconciliation.id))
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.status == "EXCEPTION")
    )
    billing_missing_q = (
        select(func.count(BillingReconciliation.id))
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.exception_code == "BILLING_DOCUMENT_NOT_FOUND")
    )
    spj_missing_q = (
        select(func.count(VouchingResult.id))
        .join(VouchingResult.billing)
        .join(PhysicalBilling.document)
        .where(VouchingResult.rule_code.in_(["BILLING_WITHOUT_SPJ", "SPJ_NOT_FOUND"]))
    )
    evidence_review_q = (
        select(func.count(DocumentControlEvidence.id))
        .join(DocumentControlEvidence.document)
        .where(DocumentControlEvidence.review_required.is_(True))
    )

    if branch is not None:
        sap_count_q = sap_count_q.where(ImportBatch.branch == branch)
        match_q = match_q.where(ImportBatch.branch == branch)
        review_q = review_q.where(ImportBatch.branch == branch)
        exception_q = exception_q.where(ImportBatch.branch == branch)
        billing_missing_q = billing_missing_q.where(ImportBatch.branch == branch)
        spj_missing_q = spj_missing_q.where(Document.branch == branch)
        evidence_review_q = evidence_review_q.where(Document.branch == branch)

    metric_row = db.execute(
        select(
            sap_count_q.scalar_subquery().label("sap_population"),
            match_q.scalar_subquery().label("matched"),
            review_q.scalar_subquery().label("review"),
            exception_q.scalar_subquery().label("exception"),
            billing_missing_q.scalar_subquery().label("billing_missing"),
            spj_missing_q.scalar_subquery().label("spj_missing"),
            evidence_review_q.scalar_subquery().label("control_evidence_review"),
        )
    ).mappings().one()

    recent_results: list[dict[str, object]] = []
    attention_items: list[dict[str, object]] = []
    if include_recent:
        recent_results = _reconciliation_rows(
            db,
            branch=branch,
            attention_only=False,
            limit=limit,
        )
    if include_attention:
        rec_limit = max(1, limit // 2)
        attention_items = _reconciliation_rows(
            db,
            branch=branch,
            attention_only=True,
            limit=rec_limit,
        )
        attention_items.extend(
            _vouching_attention_rows(
                db,
                branch=branch,
                limit=max(1, limit - rec_limit),
            )
        )

    return {
        "branch": branch,
        "metrics": {key: int(value or 0) for key, value in metric_row.items()},
        "recent_results": recent_results,
        "attention_items": attention_items[:limit],
    }


def viewer_center_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Viewer Center - AI Piutang Vouching</title>
<style>
:root{--bg:#f4f7fb;--surface:#fff;--line:#dbe5f0;--text:#172033;--muted:#64748b;--blue:#2563eb;--green:#166534;--amber:#854d0e;--red:#991b1b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
header{padding:22px 26px;background:linear-gradient(135deg,#0f2b5f,#1d4ed8 58%,#0ea5e9);color:white}header h1{margin:0;font-size:24px}header p{margin:7px 0 0;color:#dbeafe;font-size:12px;line-height:1.5}
main{padding:20px 24px 42px}.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;margin-bottom:14px;box-shadow:0 8px 24px rgba(15,23,42,.05)}
.scope{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:end}label{display:block;margin:0 0 6px;font-size:11px;font-weight:800;color:#475569}
input{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;font:inherit}button,.btn{min-height:40px;border:0;border-radius:10px;padding:9px 13px;background:var(--blue);color:#fff;font:inherit;font-size:12px;font-weight:850;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}.btn.secondary{background:#475569}
.metrics{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin-bottom:14px}.metric{padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.metric span{display:block;color:var(--muted);font-size:10px}.metric b{display:block;margin-top:7px;font-size:23px}.metric.ok{background:#f0fdf4;border-color:#bbf7d0}.metric.warn{background:#fffbeb;border-color:#fde68a}.metric.bad{background:#fff7f7;border-color:#fecaca}
.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}.section-head h2{margin:0;font-size:17px}.section-head p{margin:4px 0 0;color:var(--muted);font-size:11px}.actions{display:flex;gap:8px;flex-wrap:wrap}
.notice{padding:11px 12px;border-radius:11px;background:#eff6ff;color:#1e3a8a;border:1px solid #bfdbfe;font-size:11px;line-height:1.5;margin-bottom:14px}.notice strong{display:block;margin-bottom:3px}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;min-width:1050px;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #edf2f7;text-align:left;font-size:11px;vertical-align:middle}th{background:#f8fafc;color:#475569;font-weight:850}tr:last-child td{border-bottom:0}
.status{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:10px;font-weight:850}.status.match{background:#dcfce7;color:#166534}.status.review{background:#fef3c7;color:#92400e}.status.exception,.status.not-found{background:#fee2e2;color:#991b1b}
.issue{font-weight:850}.issue.ok{color:#166534}.issue.warn{color:#854d0e}.issue.bad{color:#991b1b}.remarks{min-width:300px;color:#475569;line-height:1.45}.tabs{display:flex;gap:8px;margin-bottom:10px}.tabs button{background:#e2e8f0;color:#334155}.tabs button.active{background:#2563eb;color:#fff}.log{margin-top:12px;padding:11px;border-radius:10px;background:#0f172a;color:#dbeafe;white-space:pre-wrap;font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:150px;overflow:auto}
@media(max-width:1200px){.metrics{grid-template-columns:repeat(4,1fr)}}@media(max-width:760px){main{padding:15px}.scope{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header><h1>Viewer Center</h1><p>Dashboard read-only untuk melihat hasil reconciliation/vouching, evidence yang belum lengkap, dan item yang masih memerlukan perhatian.</p></header>
<main>
<section class="panel scope">
  <div><label>Cabang / Scope</label><input id="branch" placeholder="Semua cabang jika scope global"></div>
  <div><label>Status Sesi</label><input id="session" value="Memeriksa sesi..." disabled></div>
  <button id="refresh" type="button">Refresh Viewer Center</button>
</section>

<section class="metrics" id="metrics"></section>

<section class="panel">
  <div class="section-head">
    <div><h2>Akses VIEWER</h2><p>VIEWER hanya membaca hasil dan dashboard. Tidak ada tombol upload, run reconciliation, approve, reject, edit, atau delete.</p></div>
    <div class="actions">
      <a class="btn secondary" href="/ui/dashboard">Dashboard Cabang</a>
      <a class="btn secondary" href="/ui/control-evidence">Control Evidence</a>
      <a class="btn secondary" href="/ui/evidence-repository">Evidence Repository</a>
      <a class="btn secondary" href="/ui/audit-reports">Reports</a>
    </div>
  </div>
  <div class="notice"><strong>Apa yang masih kurang?</strong>Billing yang belum ditemukan, SPJ yang belum tersedia, hasil REVIEW/EXCEPTION, dan control evidence yang masih membutuhkan review ditampilkan pada tabel perhatian di bawah.</div>
</section>

<section class="panel">
  <div class="section-head"><div><h2>Hasil &amp; Kelengkapan Evidence</h2><p>Pilih tampilan hasil terbaru atau hanya item yang masih kurang/perlu perhatian.</p></div></div>
  <div class="tabs"><button id="attentionTab" class="active" type="button">Yang Kurang / Perlu Perhatian</button><button id="resultsTab" type="button">Semua Hasil Terbaru</button></div>
  <div class="table-wrap"><table>
    <thead><tr><th>Jenis</th><th>Cabang</th><th>Billing</th><th>Customer / SPJ</th><th>Status</th><th>Keterangan</th><th>Detail</th></tr></thead>
    <tbody id="rows"><tr><td colspan="7">Memuat Viewer Center...</td></tr></tbody>
  </table></div>
  <div class="log" id="log">Siap memuat data.</div>
</section>
</main>
<script>
const branchEl=document.getElementById('branch');
const sessionEl=document.getElementById('session');
const metricsEl=document.getElementById('metrics');
const rowsEl=document.getElementById('rows');
const logEl=document.getElementById('log');
const attentionTab=document.getElementById('attentionTab');
const resultsTab=document.getElementById('resultsTab');
let profile=null;
let payload=null;
let mode='attention';
function token(){return (localStorage.getItem('auditToken')||'').trim();}
function headers(){const t=token();if(!t)throw new Error('Sesi login tidak ditemukan. Silakan login ulang.');return {Authorization:'Bearer '+t};}
function esc(v){return String(v??'-').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
async function body(r){const text=await r.text();let x={};try{x=text?JSON.parse(text):{};}catch(_){throw new Error('Response server tidak dapat dibaca. HTTP '+r.status);}if(!r.ok)throw new Error(x.detail||('HTTP '+r.status));return x;}
function log(message,data=null){logEl.textContent=message+(data?'\n\n'+JSON.stringify(data,null,2):'');}
function statusPill(status){const value=String(status||'-').toUpperCase();const cls=value==='MATCH'||value==='PASS'?'match':value==='REVIEW'?'review':value==='NOT_FOUND'?'not-found':'exception';return '<span class="status '+cls+'">'+esc(value)+'</span>';}
function issueClass(state){return state==='LENGKAP'?'ok':(state==='REVIEW'||state==='SPJ_BELUM_LENGKAP'||state==='SPJ_OCR_REVIEW'||state==='SPJ_PERLU_REVIEW'?'warn':'bad');}
function applySession(x){
  profile=x;
  const role=String(x?.role||'').toUpperCase();
  if(!['VIEWER','ADMIN'].includes(role))return false;
  const scope=x.branch||x.access_scope||'ALL';sessionEl.value=role+' · '+scope;
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
  if(!applySession(x))throw new Error('Viewer Center hanya untuk role VIEWER atau ADMIN.');
  localStorage.setItem('auditUser',JSON.stringify(x));
  return x;
}
function renderMetrics(m){
  const defs=[
    ['Population SAP',m.sap_population,''],
    ['Match',m.matched,'ok'],
    ['Review',m.review,'warn'],
    ['Exception',m.exception,'bad'],
    ['Billing belum lengkap',m.billing_missing,'bad'],
    ['SPJ belum lengkap',m.spj_missing,'warn'],
    ['Evidence perlu review',m.control_evidence_review,'warn']
  ];
  metricsEl.innerHTML=defs.map(([label,value,cls])=>'<div class="metric '+cls+'"><span>'+esc(label)+'</span><b>'+esc(value||0)+'</b></div>').join('');
}
function renderRows(){
  const items=mode==='attention'?(payload?.attention_items||[]):(payload?.recent_results||[]);
  if(!items.length){rowsEl.innerHTML='<tr><td colspan="7">Tidak ada data pada tampilan ini.</td></tr>';return;}
  rowsEl.innerHTML=items.map(x=>'<tr>'+
    '<td>'+esc(x.kind==='SPJ_VOUCHING'?'SPJ Vouching':'Reconciliation')+'</td>'+
    '<td>'+esc(x.branch||'-')+'</td>'+
    '<td><strong>'+esc(x.billing_document||'-')+'</strong></td>'+
    '<td>'+esc(x.customer||x.spj_number||'-')+'</td>'+
    '<td>'+statusPill(x.status)+'</td>'+
    '<td><span class="issue '+issueClass(x.evidence_state)+'">'+esc(x.issue||'-')+'</span></td>'+
    '<td class="remarks">'+esc(x.remarks||('Selisih nominal: '+(x.nominal_difference||'0')))+'</td>'+
  '</tr>').join('');
}
async function loadDashboard(){
  const p=new URLSearchParams();const b=branchEl.value.trim();if(b)p.set('branch',b);p.set('limit','50');
  payload=await body(await fetch('/viewer/dashboard?'+p.toString(),{headers:headers()}));
  if(payload.branch && !branchEl.value.trim()){branchEl.value=payload.branch;branchEl.disabled=true;}
  renderMetrics(payload.metrics||{});renderRows();
  log('Viewer Center berhasil dimuat cepat.',{branch:payload.branch,attention:(payload.attention_items||[]).length});
  return payload;
}
async function loadRecentResults(){
  if((payload?.recent_results||[]).length)return;
  rowsEl.innerHTML='<tr><td colspan="7">Memuat hasil terbaru...</td></tr>';
  const p=new URLSearchParams();const b=branchEl.value.trim();if(b)p.set('branch',b);p.set('limit','50');
  const x=await body(await fetch('/viewer/results?'+p.toString(),{headers:headers()}));
  payload=payload||{};payload.recent_results=x.results||[];
}
async function setMode(next){
  mode=next;attentionTab.classList.toggle('active',mode==='attention');resultsTab.classList.toggle('active',mode==='results');
  if(mode==='results')await loadRecentResults();
  renderRows();
}
async function refresh(){
  try{
    const cached=cachedSession();
    const dashboardPromise=loadDashboard();
    if(!cached)await loadSession();
    await dashboardPromise;
  }catch(error){log('VIEWER CENTER GAGAL: '+error.message);}
}
document.getElementById('refresh').addEventListener('click',refresh);
attentionTab.addEventListener('click',()=>setMode('attention').catch(e=>log('TAMPILKAN DATA GAGAL: '+e.message)));
resultsTab.addEventListener('click',()=>setMode('results').catch(e=>log('TAMPILKAN DATA GAGAL: '+e.message)));
branchEl.addEventListener('change',()=>loadDashboard().catch(e=>log('REFRESH GAGAL: '+e.message)));
refresh();
</script>
</body></html>"""


@router.get("/ui/viewer-center", response_class=HTMLResponse)
def viewer_center_ui():
    return HTMLResponse(viewer_center_html())


@router.get("/viewer/dashboard")
def viewer_dashboard_api(
    branch: str | None = None,
    limit: int = 50,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    payload = build_viewer_dashboard(
        db,
        branch=effective_branch,
        include_recent=False,
        include_attention=True,
        limit=limit,
    )
    payload["role"] = user.role
    return payload


@router.get("/viewer/results")
def viewer_results_api(
    branch: str | None = None,
    limit: int = 50,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    rows = _reconciliation_rows(
        db,
        branch=normalize_branch(effective_branch),
        attention_only=False,
        limit=max(1, min(int(limit), 100)),
    )
    return {"branch": effective_branch, "total": len(rows), "results": rows}


def register_viewer_center_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
