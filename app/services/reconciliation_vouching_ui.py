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
.badge{display:inline-flex;padding:5px 7px;border-radius:999px;background:#eff6ff;color:#1d4ed8;font-size:10px;font-weight:850}.badge.ok{background:#ecfdf5;color:#047857}.badge.warn{background:#fff7ed;color:#9a4b08}.badge.bad{background:#fef2f2;color:#b91c1c}
.evidence-note{min-width:190px;padding:9px 10px;border-radius:10px;border:1px solid #bbf7d0;background:#f0fdf4;color:#166534;font-size:11px;line-height:1.45}.evidence-note strong{display:block;font-size:11px;margin-bottom:2px}.evidence-note.warn{border-color:#fcd34d;background:#fffbeb;color:#854d0e}.evidence-note.bad{border-color:#fecaca;background:#fff7f7;color:#991b1b}
.status-pill{display:inline-flex;align-items:center;border-radius:999px;padding:5px 8px;font-size:10px;font-weight:900;letter-spacing:.1px}.status-pill.match,.status-pill.pass{background:#dcfce7;color:#166534}.status-pill.review{background:#fef3c7;color:#92400e}.status-pill.exception,.status-pill.not-found{background:#fee2e2;color:#991b1b}
.detail-panel{margin-top:14px;border:1px solid #cbd5e1;border-radius:14px;background:#fff;padding:14px;box-shadow:0 6px 18px rgba(15,23,42,.04)}.detail-panel[hidden]{display:none}.detail-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.detail-head h3{margin:0;font-size:15px}.detail-head p{margin:4px 0 0;color:#64748b;font-size:11px}.detail-summary{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.detail-chip{padding:7px 9px;border-radius:9px;background:#f8fafc;border:1px solid #e2e8f0;font-size:11px;font-weight:800;color:#334155}.detail-chip.warn{background:#fffbeb;border-color:#fcd34d;color:#854d0e}.detail-chip.bad{background:#fff1f2;border-color:#fecdd3;color:#9f1239}.detail-table-wrap{max-height:430px;overflow:auto;border:1px solid #e2e8f0;border-radius:10px}.detail-table{min-width:980px;border:0;border-radius:0}.detail-table th{position:sticky;top:0;z-index:1}.detail-table td{font-size:11px;line-height:1.45}.detail-table tr.missing td{background:#fffdf2}.detail-table tr.problem td{background:#fff8f8}.detail-message{max-width:470px;white-space:normal;color:#334155;font-weight:650}.mini-confirm{min-height:34px;padding:7px 9px;border:0;border-radius:8px;background:#047857;color:#fff;font-size:10px;font-weight:900;cursor:pointer;white-space:nowrap}.mini-confirm.bulk{min-height:38px;font-size:11px;padding:9px 12px}.log{margin-top:14px;min-height:82px;max-height:220px;overflow:auto;padding:13px;border-radius:12px;background:#0f172a;color:#e2e8f0;white-space:pre-wrap;font:12px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}
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
        <thead><tr><th>Batch</th><th>File SAP</th><th>Cabang</th><th>Periode</th><th>Rows</th><th>Match</th><th>Review</th><th>Exception</th><th>Not Found</th><th>Keterangan Evidence</th><th>Aksi</th></tr></thead>
        <tbody id="batchRows"><tr><td colspan="11">Memuat batch SAP...</td></tr></tbody>
      </table>
    </div>
    <div class="detail-panel" id="detailPanel" hidden></div>
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
const detailEl=document.getElementById('detailPanel');
let currentUser=null;
let batches=[];
let batchSummaries=new Map();

function token(){return (localStorage.getItem('auditToken')||'').trim();}
function headers(){const value=token();if(!value)throw new Error('Sesi login tidak ditemukan. Silakan login ulang.');return {Authorization:'Bearer '+value};}
function esc(value){return String(value??'-').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function formatMoneyId(value){
  if(value===null||value===undefined||value==='')return '-';
  const number=Number(String(value).replace(/\s/g,'').replace(',','.'));
  if(!Number.isFinite(number))return String(value);
  return new Intl.NumberFormat('id-ID',{minimumFractionDigits:2,maximumFractionDigits:2}).format(number);
}
function log(title,payload=null){logEl.textContent=title;if(payload)logEl.textContent+=String.fromCharCode(10,10)+JSON.stringify(payload,null,2);}
async function body(response){const text=await response.text();let payload={};try{payload=text?JSON.parse(text):{};}catch(_){throw new Error('Response server tidak dapat dibaca. HTTP '+response.status);}if(!response.ok)throw new Error(payload.detail||('HTTP '+response.status));return payload;}
function selectedBranch(){return branchEl.value.trim().toUpperCase();}
function badge(value){const n=Number(value||0);return '<span class="badge '+(n===0?'ok':n<5?'warn':'bad')+'">'+n+'</span>';}
function evidenceLabel(state){
  return ({
    LENGKAP:'Evidence lengkap',
    BILLING_BELUM_LENGKAP:'Billing belum lengkap',
    SPJ_BELUM_LENGKAP:'SPJ belum lengkap',
    SPJ_OCR_INFO:'SPJ tersedia · OCR info',
    SPJ_OCR_REVIEW:'SPJ tersedia · OCR perlu review',
    SPJ_PERLU_REVIEW:'SPJ perlu review'
  })[state]||String(state||'-').replaceAll('_',' ');
}
function statusPill(status){
  const value=String(status||'-').toUpperCase();
  const cls=value==='MATCH'?'match':value==='PASS'?'pass':value==='REVIEW'?'review':value==='NOT_FOUND'?'not-found':'exception';
  return '<span class="status-pill '+cls+'">'+esc(value)+'</span>';
}
function evidenceSummary(summary){
  const rows=(summary&&summary.rows)||[];
  const billingMissing=rows.filter(r=>r.evidence_state==='BILLING_BELUM_LENGKAP').length;
  const spjMissing=rows.filter(r=>r.evidence_state==='SPJ_BELUM_LENGKAP').length;
  const spjOcrInfo=rows.filter(r=>r.evidence_state==='SPJ_OCR_INFO').length;
  const spjOcr=rows.filter(r=>r.evidence_state==='SPJ_OCR_REVIEW').length;
  const spjReview=rows.filter(r=>r.evidence_state==='SPJ_PERLU_REVIEW').length;
  if(summary&&summary._error)return '<div class="evidence-note bad"><strong>Detail belum terbaca</strong><span>'+esc(summary._error)+'</span></div>';
  if(billingMissing||spjMissing||spjOcr||spjReview){
    return '<div class="evidence-note warn"><strong>Proses tetap dilanjutkan</strong><span>Perlu perhatian: Billing belum lengkap: '+billingMissing+' · SPJ belum lengkap: '+spjMissing+(spjOcr?' · SPJ tersedia/OCR review: '+spjOcr:'')+(spjReview?' · SPJ review: '+spjReview:'')+'</span></div>';
  }
  if(spjOcrInfo){
    return '<div class="evidence-note"><strong>Evidence terhubung</strong><span>SPJ tersedia; nomor/field OCR yang belum terbaca hanya informasi, bukan REVIEW: '+spjOcrInfo+'</span></div>';
  }
  if(rows.length)return '<div class="evidence-note"><strong>Evidence terhubung</strong><span>Tidak ada Billing/SPJ yang ditandai belum lengkap.</span></div>';
  return '<div class="evidence-note warn"><strong>Belum direkonsiliasi</strong><span>Jalankan reconciliation untuk melihat kelengkapan evidence.</span></div>';
}
function renderReconciliationDetail(batchId,payload){
  const rows=(payload&&payload.rows)||[];
  const counts=(payload&&payload.counts)||{};
  const billingMissing=rows.filter(r=>r.evidence_state==='BILLING_BELUM_LENGKAP').length;
  const spjMissing=rows.filter(r=>r.evidence_state==='SPJ_BELUM_LENGKAP').length;
  const spjOcrInfo=rows.filter(r=>r.evidence_state==='SPJ_OCR_INFO').length;
  const spjOcr=rows.filter(r=>r.evidence_state==='SPJ_OCR_REVIEW').length;
  const spjReview=rows.filter(r=>r.evidence_state==='SPJ_PERLU_REVIEW').length;
  const body=rows.length?rows.map(r=>{
    const state=r.evidence_state||'LENGKAP';
    const rowClass=state==='LENGKAP'?'':(state==='SPJ_PERLU_REVIEW'?'problem':'missing');
    const canConfirm=String(r.status||'').toUpperCase()==='REVIEW'&&r.physical_billing_id;
    const action=canConfirm
      ? '<button class="mini-confirm" type="button" onclick="confirmManualRow('+Number(batchId)+','+Number(r.id)+')">Konfirmasi Sesuai</button>'
      : '-';
    return '<tr class="'+rowClass+'">'+
      '<td>'+esc(r.billing_document||'-')+'</td>'+
      '<td>'+esc(r.customer||'-')+'</td>'+
      '<td>'+esc(r.spj_number||'-')+'</td>'+
      '<td>'+statusPill(r.status)+'</td>'+
      '<td><strong>'+esc(evidenceLabel(state))+'</strong></td>'+
      '<td class="detail-message">'+esc(r.remarks||'Tidak ada catatan khusus.')+'</td>'+
      '<td>'+esc(formatMoneyId(r.billing_partial_payment))+'</td>'+
      '<td>'+esc(formatMoneyId(r.nominal_difference))+'</td>'+
      '<td>'+action+'</td>'+
    '</tr>';
  }).join(''):'<tr><td colspan="9">Belum ada hasil reconciliation. Klik Run Reconciliation.</td></tr>';
  const bulkAction=Number(counts.REVIEW||0)>0
    ? '<button class="mini-confirm bulk" type="button" onclick="confirmManualBatch('+Number(batchId)+')">Konfirmasi Semua REVIEW yang Sudah Dicek</button>'
    : '';
  detailEl.innerHTML=
    '<div class="detail-head"><div><h3>Detail Reconciliation Batch #'+esc(batchId)+'</h3><p>Reconciliation otomatis menggunakan Billing Document unik sebagai identitas utama. Field scan yang belum terbaca dicatat sebagai informasi dan tidak memaksa REVIEW; REVIEW hanya digunakan bila ada kondisi yang benar-benar perlu keputusan auditor.</p></div>'+bulkAction+'</div>'+
    '<div class="detail-summary">'+
      '<div class="detail-chip">Match: '+esc(counts.MATCH||0)+'</div>'+
      '<div class="detail-chip warn">Review: '+esc(counts.REVIEW||0)+'</div>'+
      '<div class="detail-chip bad">Exception: '+esc(counts.EXCEPTION||0)+'</div>'+
      '<div class="detail-chip bad">Not Found: '+esc(counts.NOT_FOUND||0)+'</div>'+
      '<div class="detail-chip warn">Billing belum lengkap: '+billingMissing+'</div>'+
      '<div class="detail-chip warn">SPJ belum lengkap: '+spjMissing+'</div>'+
      (spjOcrInfo?'<div class="detail-chip">SPJ tersedia · OCR info: '+spjOcrInfo+'</div>':'')+
      (spjOcr?'<div class="detail-chip warn">SPJ tersedia · OCR review: '+spjOcr+'</div>':'')+
      (spjReview?'<div class="detail-chip warn">SPJ perlu review: '+spjReview+'</div>':'')+
    '</div>'+
    '<div class="detail-table-wrap"><table class="detail-table"><thead><tr><th>Billing SAP</th><th>Customer</th><th>No. SPJ</th><th>Status</th><th>Evidence</th><th>Keterangan</th><th>Partial Payment</th><th>Selisih Nominal</th><th>Aksi Manual</th></tr></thead><tbody>'+body+'</tbody></table></div>';
  detailEl.hidden=false;
  detailEl.scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function refreshBatchDetail(batchId){
  const summary=await reconciliationSummary(batchId);
  batchSummaries.set(Number(batchId),summary);
  render();
  renderReconciliationDetail(batchId,summary);
}
async function confirmManualRow(batchId,reconciliationId){
  const statement='Konfirmasi hanya jika Anda sudah memeriksa Billing Document, tanggal/nominal, SPJ, tanda tangan, dan stempel pada dokumen asli/scan dan semuanya sesuai. Lanjutkan?';
  if(!window.confirm(statement))return;
  const defaultNote='Sudah diperiksa manual: Billing, tanggal/nominal, SPJ, tanda tangan dan stempel sesuai.';
  const note=window.prompt('Catatan pemeriksaan manual:',defaultNote);
  if(note===null)return;
  try{
    const p=new URLSearchParams({confirmed:'true',remarks:(note.trim()||defaultNote)});
    const response=await fetch('/reconciliation/results/'+encodeURIComponent(reconciliationId)+'/confirm-manual?'+p.toString(),{method:'POST',headers:headers()});
    const payload=await body(response);
    log('KONFIRMASI MANUAL BERHASIL - RECONCILIATION #'+reconciliationId,payload);
    await refreshBatchDetail(batchId);
  }catch(error){log('KONFIRMASI MANUAL GAGAL: '+error.message);}
}
async function confirmManualBatch(batchId){
  const statement='Konfirmasi SEMUA baris REVIEW pada batch ini hanya jika seluruh sampel sudah diperiksa manual: Billing, tanggal/nominal, SPJ, tanda tangan, dan stempel semuanya sesuai. Proses ini dicatat pada audit trail. Lanjutkan?';
  if(!window.confirm(statement))return;
  const defaultNote='Seluruh sampel REVIEW pada batch telah diperiksa manual dan dinyatakan sesuai.';
  const note=window.prompt('Catatan pemeriksaan batch:',defaultNote);
  if(note===null)return;
  try{
    const p=new URLSearchParams({confirmed:'true',remarks:(note.trim()||defaultNote)});
    const response=await fetch('/reconciliation/'+encodeURIComponent(batchId)+'/confirm-manual-review?'+p.toString(),{method:'POST',headers:headers()});
    const payload=await body(response);
    log('KONFIRMASI MANUAL BATCH #'+batchId+' SELESAI',payload);
    await refreshBatchDetail(batchId);
  }catch(error){log('KONFIRMASI MANUAL BATCH GAGAL: '+error.message);}
}
window.confirmManualRow=confirmManualRow;
window.confirmManualBatch=confirmManualBatch;

function renderSpjDetail(branch,payload){
  const rows=(payload&&payload.results)||[];
  const missing=rows.filter(r=>r.evidence_state==='SPJ_BELUM_LENGKAP').length;
  const ocrReview=rows.filter(r=>r.evidence_state==='SPJ_OCR_REVIEW').length;
  const review=rows.filter(r=>r.evidence_state==='SPJ_PERLU_REVIEW').length;
  const body=rows.length?rows.map(r=>{
    const state=r.evidence_state||'LENGKAP';
    return '<tr class="'+(state==='LENGKAP'?'':'missing')+'">'+
      '<td>'+esc(r.billing_id)+'</td><td>'+esc(r.no_spj_billing||'-')+'</td><td>'+statusPill(r.status)+'</td>'+
      '<td><strong>'+esc(evidenceLabel(state))+'</strong></td><td class="detail-message">'+esc(r.remarks||'SPJ terhubung dan dapat diproses.')+'</td></tr>';
  }).join(''):'<tr><td colspan="5">Belum ada Billing untuk divouching.</td></tr>';
  detailEl.innerHTML='<div class="detail-head"><div><h3>Hasil SPJ Vouching · '+esc(branch)+'</h3><p>SPJ yang belum ada tetap diteruskan ke review, bukan menghentikan seluruh proses.</p></div></div>'+
    '<div class="detail-summary"><div class="detail-chip">Total: '+rows.length+'</div><div class="detail-chip warn">SPJ belum lengkap: '+missing+'</div><div class="detail-chip warn">SPJ tersedia · OCR review: '+ocrReview+'</div><div class="detail-chip warn">Perlu review: '+review+'</div></div>'+
    '<div class="detail-table-wrap"><table class="detail-table"><thead><tr><th>Billing ID</th><th>No. SPJ Billing</th><th>Status</th><th>Evidence</th><th>Keterangan</th></tr></thead><tbody>'+body+'</tbody></table></div>';
  detailEl.hidden=false;
  detailEl.scrollIntoView({behavior:'smooth',block:'nearest'});
}

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
    return await body(response);
  }catch(error){
    return {counts:{MATCH:0,REVIEW:0,EXCEPTION:0,NOT_FOUND:0},rows:[],_error:error.message};
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
    const counts=s.counts||{};
    match+=Number(counts.MATCH||0);review+=Number(counts.REVIEW||0);exception+=Number(counts.EXCEPTION||0);notFound+=Number(counts.NOT_FOUND||0);
  });
  const values=[['Batch SAP',batches.length],['Population SAP',population],['Match',match],['Review',review],['Exception',exception],['Not Found',notFound]];
  metricsEl.innerHTML=values.map(([label,value])=>'<div class="metric"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>').join('');
}
function render(){
  renderMetrics();
  if(!batches.length){rowsEl.innerHTML='<tr><td colspan="11">Belum ada batch SAP pada scope ini.</td></tr>';return;}
  rowsEl.innerHTML=batches.map(item=>{
    const s=batchSummaries.get(item.id)||{};
    const counts=s.counts||{};
    return '<tr>'+
      '<td>#'+item.id+'</td><td>'+esc(item.file_name)+'</td><td>'+esc(item.branch)+'</td><td>'+esc(item.period||'-')+'</td><td>'+esc(item.total_records||0)+'</td>'+
      '<td>'+badge(counts.MATCH)+'</td><td>'+badge(counts.REVIEW)+'</td><td>'+badge(counts.EXCEPTION)+'</td><td>'+badge(counts.NOT_FOUND)+'</td>'+
      '<td>'+evidenceSummary(s)+'</td>'+
      '<td><div class="actions">'+
        '<button class="secondary" data-validate="'+item.id+'" type="button">Validate SAP</button>'+
        '<button data-run="'+item.id+'" type="button">Run Reconciliation</button>'+
        '<button class="secondary" data-detail="'+item.id+'" type="button">Detail</button>'+
        '<button class="secondary" data-working-paper="'+item.id+'" type="button">Download Kertas Kerja</button>'+
      '</div></td></tr>';
  }).join('');
  rowsEl.querySelectorAll('[data-validate]').forEach(btn=>btn.addEventListener('click',()=>validateSap(Number(btn.dataset.validate),btn)));
  rowsEl.querySelectorAll('[data-run]').forEach(btn=>btn.addEventListener('click',()=>runReconciliation(Number(btn.dataset.run),btn)));
  rowsEl.querySelectorAll('[data-detail]').forEach(btn=>btn.addEventListener('click',()=>showDetail(Number(btn.dataset.detail))));
  rowsEl.querySelectorAll('[data-working-paper]').forEach(btn=>btn.addEventListener('click',()=>downloadWorkingPaper(Number(btn.dataset.workingPaper),btn)));
}
async function downloadWorkingPaper(id,button){
  button.disabled=true;
  const originalText=button.textContent;
  try{
    button.textContent='Menyiapkan...';
    log('Menyiapkan Kertas Kerja Batch #'+id+' ...');
    const response=await fetch('/reports/'+id+'/working-paper',{headers:headers()});
    if(!response.ok){
      let message='HTTP '+response.status;
      try{
        const payload=await response.json();
        message=payload.detail||message;
      }catch(_error){}
      throw new Error(message);
    }
    const blob=await response.blob();
    const disposition=response.headers.get('content-disposition')||'';
    const match=/filename="?([^";]+)"?/i.exec(disposition);
    const filename=match&&match[1]?match[1]:'kertas_kerja_batch_'+id+'.xlsx';
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    log('KERTAS KERJA BATCH #'+id+' BERHASIL DIDOWNLOAD.');
  }catch(error){
    log('DOWNLOAD KERTAS KERJA GAGAL: '+error.message);
  }finally{
    button.disabled=false;
    button.textContent=originalText;
  }
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
async function refreshVisualEvidenceForBatch(id){
  const response=await fetch('/reconciliation/'+id+'/visual-refresh-candidates',{headers:headers()});
  const payload=await body(response);
  const items=payload.items||[];
  if(!items.length){
    log('VISUAL EVIDENCE: semua evidence sudah memakai engine visual terbaru.');
    return {total:0,success:0,failed:0};
  }

  log('VISUAL EVIDENCE: memproses '+items.length+' dokumen scan/foto secara terpisah agar reconciliation tidak timeout.');
  let success=0,failed=0;
  // Process two documents at a time. Each document has its own HTTP request so
  // one heavy scan cannot make the entire reconciliation request exceed the
  // serverless timeout.
  for(let start=0;start<items.length;start+=2){
    const chunk=items.slice(start,start+2);
    const results=await Promise.all(chunk.map(async item=>{
      try{
        log('VISUAL '+(start+1)+'/'+items.length+': '+item.file_name);
        const r=await fetch('/control-evidence/'+item.document_id+'/reanalyze-visual',{method:'POST',headers:headers()});
        const p=await body(r);
        return {ok:true,payload:p};
      }catch(error){
        return {ok:false,error:error.message,item:item};
      }
    }));
    results.forEach(result=>{
      if(result.ok){success+=1;}
      else{failed+=1;log('VISUAL EVIDENCE GAGAL: '+result.item.file_name+' · '+result.error);}
    });
  }
  log('VISUAL EVIDENCE SELESAI: '+success+' berhasil, '+failed+' gagal.');
  return {total:items.length,success:success,failed:failed};
}
async function runReconciliation(id,button){
  button.disabled=true;
  const originalText=button.textContent;
  try{
    button.textContent='Recon...';
    log('Menjalankan reconciliation batch #'+id+' ...');
    let response=await fetch('/reconciliation/'+id+'/run',{method:'POST',headers:headers()});
    let payload=await body(response);
    log('RECONCILIATION AWAL SELESAI - BATCH #'+id,payload);

    button.textContent='Baca Evidence...';
    const visual=await refreshVisualEvidenceForBatch(id);

    // Re-run only the lightweight matching step after OCR/visual fields were
    // persisted. The second run no longer executes image analysis server-side.
    if(visual.success>0){
      button.textContent='Finalisasi...';
      response=await fetch('/reconciliation/'+id+'/run',{method:'POST',headers:headers()});
      payload=await body(response);
      log('RECONCILIATION FINAL SELESAI - BATCH #'+id,payload);
    }

    const branch=selectedBranch();
    if(branch){
      try{
        const vouchResponse=await fetch('/spj/vouch?branch='+encodeURIComponent(branch),{method:'POST',headers:headers()});
        const vouchPayload=await body(vouchResponse);
        log('SPJ VOUCHING OTOMATIS SELESAI - '+branch,vouchPayload);
      }catch(error){
        log('SPJ VOUCHING OTOMATIS: '+error.message);
      }
    }

    const summary=await reconciliationSummary(id);
    batchSummaries.set(id,summary);
    render();
    renderReconciliationDetail(id,summary);
  }catch(error){log('RECONCILIATION GAGAL: '+error.message);}
  finally{button.disabled=false;button.textContent=originalText;}
}
async function showDetail(id){
  try{
    const response=await fetch('/reconciliation/'+id,{headers:headers()});
    const payload=await body(response);
    log('DETAIL RECONCILIATION - BATCH #'+id,payload);
    renderReconciliationDetail(id,payload);
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
    renderSpjDetail(branch,payload);
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
