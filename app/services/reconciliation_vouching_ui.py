from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
_REGISTERED = False


def reconciliation_vouching_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reconciliation & Vouching - AI Piutang Vouching</title>
<style>
:root{--bg:#f4f7fb;--surface:#fff;--line:#dbe5f0;--text:#172033;--muted:#64748b;--blue:#2563eb;--blue2:#1d4ed8;--green:#059669;--amber:#d97706;--red:#dc2626}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
header{padding:22px 28px;background:linear-gradient(135deg,#fff,#eef6ff);border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:25px;letter-spacing:-.4px}header p{margin:7px 0 0;color:var(--muted);font-size:13px}
main{padding:20px 24px 46px;width:100%}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 8px 24px rgba(15,23,42,.055)}
.workflow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:14px}
.step{padding:11px 12px;border:1px solid var(--line);border-radius:12px;background:#fff}
.step.active{border-color:#93c5fd;background:#eff6ff}.step b{display:block;font-size:11px}.step span{display:block;margin-top:4px;color:var(--muted);font-size:9px;line-height:1.4}
.scope{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:end;margin-bottom:14px}
label{display:block;margin:0 0 6px;font-size:11px;font-weight:800;color:#475569}
input,select{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cfd9e6;border-radius:10px;background:#fff;font:inherit}
button,.link-btn{min-height:40px;border:0;border-radius:10px;padding:9px 13px;background:linear-gradient(135deg,var(--blue),var(--blue2));color:#fff;font:inherit;font-size:12px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
button.secondary,.link-btn.secondary{background:#475569}button.success,.link-btn.success{background:var(--green)}button:disabled{opacity:.55;cursor:not-allowed}
.metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-bottom:14px}
.metric{padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.metric span{font-size:10px;color:var(--muted)}.metric b{display:block;margin-top:7px;font-size:23px;letter-spacing:-.4px}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.section-head h2{margin:0;font-size:17px}.section-head p{margin:4px 0 0;color:var(--muted);font-size:11px}
.actions{display:flex;gap:7px;flex-wrap:wrap}
.table-wrap{overflow:auto}table{width:100%;min-width:1020px;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:10px 10px;text-align:left;border-bottom:1px solid #edf2f7;font-size:11px;vertical-align:middle}th{background:#f8fafc;color:#475569;font-weight:850}tr:last-child td{border-bottom:0}
.badge{display:inline-flex;padding:5px 7px;border-radius:999px;background:#eff6ff;color:#1d4ed8;font-size:9px;font-weight:850}.badge.ok{background:#ecfdf5;color:#047857}.badge.warn{background:#fff7ed;color:#b45309}.badge.bad{background:#fef2f2;color:#b91c1c}
.log{margin-top:14px;min-height:110px;max-height:260px;overflow:auto;padding:13px;border-radius:12px;background:#0f172a;color:#dbeafe;white-space:pre-wrap;font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}
.next{margin-top:14px;display:flex;gap:8px;flex-wrap:wrap}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}.workflow{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){main{padding:16px}.scope{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.workflow{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header>
  <h1>Reconciliation &amp; Vouching</h1>
  <p>Proses data setelah Upload Center: validasi SAP → reconciliation SAP vs Billing → vouching Billing vs SPJ → review exception.</p>
</header>
<main>
  <section class="workflow">
    <div class="step"><b>1 · Upload SAP</b><span>Population piutang per cabang.</span></div>
    <div class="step"><b>2 · Upload Evidence</b><span>Billing dan SPJ sebagai bukti.</span></div>
    <div class="step active"><b>3 · Reconciliation &amp; Vouching</b><span>Matching otomatis dan identifikasi mismatch.</span></div>
    <div class="step"><b>4 · Control Evidence</b><span>Review atribut kontrol SPJ.</span></div>
    <div class="step"><b>5 · Review / Exception</b><span>Keputusan auditor dan reviewer.</span></div>
  </section>

  <section class="panel scope">
    <div><label>Cabang / Scope</label><input id="branch" placeholder="Pilih/ketik cabang"></div>
    <div><label>Status Sesi</label><input id="session" value="Memeriksa sesi..." disabled></div>
    <button id="refreshBtn" type="button">Refresh Data</button>
  </section>

  <section class="metrics" id="metrics">
    <div class="metric"><span>Batch SAP</span><b>-</b></div>
    <div class="metric"><span>Population SAP</span><b>-</b></div>
    <div class="metric"><span>Match</span><b>-</b></div>
    <div class="metric"><span>Review</span><b>-</b></div>
    <div class="metric"><span>Exception</span><b>-</b></div>
    <div class="metric"><span>Not Found</span><b>-</b></div>
  </section>

  <section class="panel">
    <div class="section-head">
      <div><h2>Batch SAP &amp; Hasil Reconciliation</h2><p>Pilih batch, validasi struktur, lalu jalankan reconciliation. SPJ vouching dijalankan per cabang.</p></div>
      <div class="actions">
        <button id="spjVouchBtn" class="success" type="button">Run SPJ Vouching</button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Batch</th><th>File SAP</th><th>Cabang</th><th>Periode</th><th>Rows</th><th>Match</th><th>Review</th><th>Exception</th><th>Not Found</th><th>Aksi</th></tr></thead>
        <tbody id="batchRows"><tr><td colspan="10">Memuat batch SAP...</td></tr></tbody>
      </table>
    </div>
    <div class="next">
      <a class="link-btn secondary" href="/ui/control-evidence">Lanjut: Control Evidence</a>
      <a class="link-btn secondary" href="/ui/review-queue">Lanjut: Review Queue</a>
      <a class="link-btn secondary" href="/ui/exceptions">Lihat Exceptions</a>
    </div>
    <div class="log" id="log">Siap memproses reconciliation &amp; vouching.</div>
  </section>
</main>
<script>
const branchEl=document.getElementById('branch');
const sessionEl=document.getElementById('session');
const rowsEl=document.getElementById('batchRows');
const metricsEl=document.getElementById('metrics');
const logEl=document.getElementById('log');
let currentUser=null;
let batches=[];
let batchSummaries=new Map();

function token(){return (localStorage.getItem('auditToken')||'').trim();}
function headers(){const value=token();if(!value)throw new Error('Sesi login tidak ditemukan. Silakan login ulang.');return {Authorization:'Bearer '+value};}
function esc(value){return String(value??'-').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function log(title,payload=null){logEl.textContent=title;if(payload)logEl.textContent+=String.fromCharCode(10,10)+JSON.stringify(payload,null,2);}
async function body(response){const text=await response.text();let payload={};try{payload=text?JSON.parse(text):{};}catch(_){throw new Error('Response server tidak dapat dibaca. HTTP '+response.status);}if(!response.ok)throw new Error(payload.detail||('HTTP '+response.status));return payload;}
function selectedBranch(){return branchEl.value.trim().toUpperCase();}
function badge(value){const n=Number(value||0);return '<span class="badge '+(n===0?'ok':n<5?'warn':'bad')+'">'+n+'</span>';}

async function loadSession(){
  const response=await fetch('/auth/me',{headers:headers()});
  const profile=await body(response);
  currentUser=profile;
  const role=String(profile.role||'-').toUpperCase();
  const scope=profile.branch||profile.access_scope||'ALL';
  sessionEl.value=role+' · '+scope;
  if(profile.branch){branchEl.value=profile.branch;branchEl.disabled=true;}
}
async function reconciliationSummary(batchId){
  try{
    const response=await fetch('/reconciliation/'+batchId,{headers:headers()});
    const payload=await body(response);
    return payload.counts||{MATCH:0,REVIEW:0,EXCEPTION:0,NOT_FOUND:0};
  }catch(error){
    return {MATCH:0,REVIEW:0,EXCEPTION:0,NOT_FOUND:0,_error:error.message};
  }
}
async function loadBatches(){
  const response=await fetch('/uploads/recent?limit=80',{headers:headers()});
  const payload=await body(response);
  const branch=selectedBranch();
  batches=(payload.items||[]).filter(item=>item.kind==='SAP'&&(!branch||String(item.branch||'').toUpperCase()===branch)).slice(0,30);
  batchSummaries=new Map();
  const summaries=await Promise.all(batches.map(async item=>[item.id,await reconciliationSummary(item.id)]));
  summaries.forEach(([id,summary])=>batchSummaries.set(id,summary));
  render();
}
function renderMetrics(){
  let population=0,match=0,review=0,exception=0,notFound=0;
  batches.forEach(item=>{
    population+=Number(item.total_records||0);
    const s=batchSummaries.get(item.id)||{};
    match+=Number(s.MATCH||0);review+=Number(s.REVIEW||0);exception+=Number(s.EXCEPTION||0);notFound+=Number(s.NOT_FOUND||0);
  });
  const values=[['Batch SAP',batches.length],['Population SAP',population],['Match',match],['Review',review],['Exception',exception],['Not Found',notFound]];
  metricsEl.innerHTML=values.map(([label,value])=>'<div class="metric"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>').join('');
}
function render(){
  renderMetrics();
  if(!batches.length){rowsEl.innerHTML='<tr><td colspan="10">Belum ada batch SAP pada scope ini.</td></tr>';return;}
  rowsEl.innerHTML=batches.map(item=>{
    const s=batchSummaries.get(item.id)||{};
    return '<tr>'+
      '<td>#'+item.id+'</td><td>'+esc(item.file_name)+'</td><td>'+esc(item.branch)+'</td><td>'+esc(item.period||'-')+'</td><td>'+esc(item.total_records||0)+'</td>'+
      '<td>'+badge(s.MATCH)+'</td><td>'+badge(s.REVIEW)+'</td><td>'+badge(s.EXCEPTION)+'</td><td>'+badge(s.NOT_FOUND)+'</td>'+
      '<td><div class="actions">'+
        '<button class="secondary" data-validate="'+item.id+'" type="button">Validate SAP</button>'+
        '<button data-run="'+item.id+'" type="button">Run Reconciliation</button>'+
        '<button class="secondary" data-detail="'+item.id+'" type="button">Detail</button>'+
      '</div></td></tr>';
  }).join('');
  rowsEl.querySelectorAll('[data-validate]').forEach(btn=>btn.addEventListener('click',()=>validateSap(Number(btn.dataset.validate),btn)));
  rowsEl.querySelectorAll('[data-run]').forEach(btn=>btn.addEventListener('click',()=>runReconciliation(Number(btn.dataset.run),btn)));
  rowsEl.querySelectorAll('[data-detail]').forEach(btn=>btn.addEventListener('click',()=>showDetail(Number(btn.dataset.detail))));
}
async function validateSap(id,button){
  button.disabled=true;
  try{
    const response=await fetch('/sap/validate/'+id,{headers:headers()});
    const payload=await body(response);
    log('VALIDASI SAP BATCH #'+id,payload);
  }catch(error){log('VALIDASI SAP GAGAL: '+error.message);}
  finally{button.disabled=false;}
}
async function runReconciliation(id,button){
  button.disabled=true;
  try{
    log('Menjalankan reconciliation batch #'+id+' ...');
    const response=await fetch('/reconciliation/'+id+'/run',{method:'POST',headers:headers()});
    const payload=await body(response);
    log('RECONCILIATION SELESAI - BATCH #'+id,payload);
    batchSummaries.set(id,await reconciliationSummary(id));
    render();
  }catch(error){log('RECONCILIATION GAGAL: '+error.message);}
  finally{button.disabled=false;}
}
async function showDetail(id){
  try{
    const response=await fetch('/reconciliation/'+id,{headers:headers()});
    const payload=await body(response);
    log('DETAIL RECONCILIATION - BATCH #'+id,payload);
  }catch(error){log('DETAIL GAGAL: '+error.message);}
}
async function runSpjVouch(){
  const branch=selectedBranch();
  if(!branch){log('SPJ VOUCHING GAGAL: pilih cabang terlebih dahulu.');return;}
  const button=document.getElementById('spjVouchBtn');button.disabled=true;
  try{
    log('Menjalankan SPJ vouching untuk '+branch+' ...');
    const response=await fetch('/spj/vouch?branch='+encodeURIComponent(branch),{method:'POST',headers:headers()});
    const payload=await body(response);
    log('SPJ VOUCHING SELESAI - '+branch,payload);
  }catch(error){log('SPJ VOUCHING GAGAL: '+error.message);}
  finally{button.disabled=false;}
}
async function refresh(){
  try{await loadSession();await loadBatches();log('Data batch SAP berhasil dimuat.');}
  catch(error){log('GAGAL MEMUAT WORKSPACE: '+error.message);}
}
document.getElementById('refreshBtn').addEventListener('click',refresh);
document.getElementById('spjVouchBtn').addEventListener('click',runSpjVouch);
branchEl.addEventListener('change',()=>loadBatches().catch(error=>log('REFRESH GAGAL: '+error.message)));
refresh();
</script>
</body></html>"""


@router.get("/ui/reconciliation-vouching", response_class=HTMLResponse)
def reconciliation_vouching_ui():
    return HTMLResponse(reconciliation_vouching_html())


def register_reconciliation_vouching_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
