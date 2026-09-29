from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
_REGISTERED = False


def upload_center_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload Center - AI Piutang Vouching</title>
<style>
:root{--bg:#f4f7fb;--card:#fff;--line:#dbe5f0;--text:#172033;--muted:#64748b;--blue:#2563eb;--green:#059669;--red:#dc2626;--amber:#d97706}
*{box-sizing:border-box}
body{font-family:Inter,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
header{padding:22px 28px;background:linear-gradient(135deg,#fff,#f0f6ff);border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:25px}header p{margin:7px 0 0;color:var(--muted);font-size:13px}
main{width:100%;padding:20px 24px 42px}
.scope{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.upload-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 8px 24px rgba(15,23,42,.055)}
.panel h2{margin:0;font-size:17px}.panel .subtitle{margin:5px 0 16px;color:var(--muted);font-size:12px;line-height:1.5}
label{display:block;font-size:12px;font-weight:750;color:#475569;margin:11px 0 6px}
input,select,textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid #cfd9e6;border-radius:10px;background:#fff;font:inherit}
input:focus,select:focus,textarea:focus{outline:none;border-color:#93c5fd;box-shadow:0 0 0 3px rgba(37,99,235,.09)}
button{border:0;border-radius:10px;padding:10px 14px;background:var(--blue);color:#fff;font-weight:800;cursor:pointer}
button:disabled{opacity:.55;cursor:not-allowed}.danger{background:var(--red)}.secondary{background:#475569}.small-btn{padding:7px 10px;font-size:11px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.note{margin:12px 0 0;padding:10px 12px;border-radius:10px;background:#eff6ff;color:#475569;font-size:11px;line-height:1.55}
.warn{background:#fff7ed;color:#9a3412}
.result{margin-top:16px;background:#0f172a;color:#dbeafe;border-radius:12px;padding:12px;min-height:84px;white-space:pre-wrap;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}
.manage{margin-top:16px}
table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}
th,td{padding:10px 11px;text-align:left;border-bottom:1px solid #edf2f7;font-size:12px;vertical-align:top}
th{background:#f8fafc;color:#475569;font-size:11px}tr:last-child td{border-bottom:0}
.kind{font-weight:850;color:#1d4ed8}.muted{color:var(--muted)}
main .next-step-card{
  margin-top:16px!important;
  display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;
  padding:18px 20px!important;
  background:linear-gradient(135deg,#f8fbff 0%,#f1f5f9 100%)!important;
  border:1px solid #d9e5f2!important;border-radius:18px!important;
  box-shadow:0 8px 22px rgba(15,23,42,.045)!important;
}
.next-step-icon{
  width:46px;height:46px;border-radius:14px;display:grid;place-items:center;
  background:#e8f1ff;color:#1d4ed8;font-size:12px;font-weight:900;letter-spacing:.04em;
  border:1px solid #d6e6ff;
}
.next-step-content{min-width:0}.next-step-kicker{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.next-step-badge{
  display:inline-flex;align-items:center;min-height:24px;padding:4px 8px;border-radius:999px;
  background:#dbeafe;color:#1d4ed8;font-size:9px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;
}
.next-step-hint{color:#64748b;font-size:10px;font-weight:700}
.next-step-card h2{margin:0!important;font-size:16px!important;letter-spacing:-.2px;color:#172033!important}
.next-step-card p{margin:6px 0 0!important;max-width:760px;color:#64748b!important;font-size:11px!important;line-height:1.55!important}
.next-step-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.next-step-tag{
  display:inline-flex;align-items:center;min-height:26px;padding:4px 8px;border-radius:8px;
  background:#fff;color:#475569;font-size:9px;font-weight:750;border:1px solid #e2e8f0;
}
main .next-step-action{
  min-height:42px;padding:10px 16px!important;border-radius:11px!important;
  display:inline-flex;align-items:center;justify-content:center;gap:9px;white-space:nowrap;
  background:linear-gradient(135deg,#2563eb,#1d4ed8)!important;
  color:#fff!important;text-decoration:none!important;font-size:11px!important;font-weight:850!important;
  border:1px solid #1d4ed8!important;box-shadow:0 7px 16px rgba(37,99,235,.16)!important;
  transition:transform .16s ease,box-shadow .16s ease,filter .16s ease;
}
main .next-step-action:hover{
  color:#fff!important;text-decoration:none!important;transform:translateY(-1px);
  box-shadow:0 9px 20px rgba(37,99,235,.20)!important;filter:brightness(1.02);
}
.next-step-arrow{font-size:15px;line-height:1}
@media(max-width:900px){
  .scope,.upload-grid{grid-template-columns:1fr}main{padding:16px}.manage{overflow-x:auto}table{min-width:900px}
  main .next-step-card{grid-template-columns:auto 1fr;padding:16px!important}
  main .next-step-action{grid-column:1/-1;width:100%;margin-top:2px}
}
@media(max-width:560px){
  main .next-step-card{grid-template-columns:1fr;gap:12px}
  .next-step-icon{width:42px;height:42px}
}
</style>
</head>
<body>
<header>
  <h1>Upload Center</h1>
  <p>Dua tahap upload: data SAP lebih dulu, kemudian evidence Billing dan SPJ.</p>
</header>
<main>
  <section class="panel scope">
    <div><label>Cabang / Scope Upload</label><input id="branch" placeholder="Contoh: KEDIRI"></div>
    <div><label>Status Sesi</label><input id="session" value="Memeriksa sesi login..." disabled></div>
  </section>

  <div class="upload-grid">
    <section class="panel">
      <h2>1. Upload Data SAP</h2>
      <p class="subtitle">Upload population piutang SAP dalam format XLSX/XLS/CSV.</p>
      <label>Periode (opsional)</label>
      <input id="sapPeriod" type="date">
      <label>File SAP</label>
      <input id="sapFile" type="file" accept=".xlsx,.xls,.csv">
      <div class="actions"><button id="sapUploadBtn" type="button">Upload Data SAP</button></div>
      <div class="note">Cabang scoped otomatis dikunci mengikuti akun. Untuk user global, isi cabang sebelum upload.</div>
      <div class="result" id="sapLog">Belum ada upload SAP.</div>
    </section>

    <section class="panel">
      <h2>2. Upload Evidence Billing &amp; SPJ</h2>
      <p class="subtitle">Pilih beberapa file Billing dan SPJ sekaligus. File dikirim satu-per-satu agar tidak terkena batas payload ZIP besar.</p>
      <label>File Billing</label>
      <input id="billingFiles" type="file" multiple accept=".pdf,.png,.jpg,.jpeg">
      <label>File SPJ</label>
      <input id="spjFiles" type="file" multiple accept=".pdf,.png,.jpg,.jpeg">
      <div class="actions"><button id="evidenceUploadBtn" type="button">Upload Evidence</button></div>
      <div class="note warn">ZIP besar tidak dipakai pada form utama. Log production sebelumnya menunjukkan HTTP 413 sebelum request masuk aplikasi. Gunakan file individual; maksimum aman 4 MB per file untuk upload langsung.</div>
      <div class="result" id="evidenceLog">Belum ada upload evidence.</div>
    </section>
  </div>

  <section class="next-step-card" aria-labelledby="nextStepTitle">
    <div class="next-step-icon">03</div>
    <div class="next-step-content">
      <div class="next-step-kicker">
        <span class="next-step-badge">Tahap 3</span>
        <span class="next-step-hint">Proses Berikutnya · setelah upload selesai</span>
      </div>
      <h2 id="nextStepTitle">Reconciliation &amp; Vouching</h2>
      <p>Pastikan data SAP, Billing, dan SPJ sudah lengkap. Lanjutkan ke proses matching otomatis untuk melihat hasil match, review, exception, dan not found.</p>
      <div class="next-step-tags">
        <span class="next-step-tag">Validasi SAP</span>
        <span class="next-step-tag">SAP ↔ Billing</span>
        <span class="next-step-tag">Billing ↔ SPJ</span>
        <span class="next-step-tag">Review Exception</span>
      </div>
    </div>
    <a class="next-step-action" href="/ui/reconciliation-vouching">
      <span>Lanjut ke Reconciliation &amp; Vouching</span>
      <span class="next-step-arrow" aria-hidden="true">→</span>
    </a>
  </section>

  <section class="panel manage">
    <h2>Riwayat Upload &amp; Koreksi</h2>
    <p class="subtitle">Edit metadata/cabang atau delete upload yang salah. Delete akan ditolak bila data sudah dipakai dalam rekonsiliasi, vouching, working paper, finding, atau action plan.</p>
    <div class="actions"><button id="refreshBtn" class="secondary small-btn" type="button">Refresh Riwayat</button></div>
    <table>
      <thead><tr><th>Jenis</th><th>File</th><th>Cabang</th><th>Periode / Tipe</th><th>Status</th><th>Waktu</th><th>Aksi</th></tr></thead>
      <tbody id="historyRows"><tr><td colspan="7">Memuat riwayat...</td></tr></tbody>
    </table>
    <div class="result" id="manageLog">Belum ada aktivitas koreksi.</div>
  </section>
</main>
<script>
const MAX_DIRECT_FILE_BYTES=4*1024*1024;
const branchEl=document.getElementById('branch');
const sessionEl=document.getElementById('session');
const sapLog=document.getElementById('sapLog');
const evidenceLog=document.getElementById('evidenceLog');
const manageLog=document.getElementById('manageLog');
const historyRows=document.getElementById('historyRows');

function token(){return (localStorage.getItem('auditToken')||'').trim();}
function authHeaders(){const value=token();if(!value)throw new Error('Sesi login tidak ditemukan. Silakan login ulang.');return {Authorization:'Bearer '+value};}
function esc(value){return String(value??'-').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function endpointWithQuery(endpoint,params){
  const query=new URLSearchParams();
  Object.entries(params||{}).forEach(([key,value])=>{if(value!==undefined&&value!==null&&String(value).trim()!=='')query.set(key,String(value).trim());});
  const suffix=query.toString();return suffix?endpoint+'?'+suffix:endpoint;
}
async function responseBody(response){
  const text=await response.text();
  if(response.status===413)throw new Error('File terlalu besar untuk upload langsung (HTTP 413). Gunakan file individual maksimal 4 MB atau kompres/pecah file.');
  let body=null;
  try{body=text?JSON.parse(text):{};}catch(_){}
  if(!response.ok)throw new Error((body&&body.detail)||('Upload gagal. HTTP '+response.status+(text?' - '+text.slice(0,180):'')));
  if(body===null)throw new Error('Server mengembalikan response non-JSON. Coba file lebih kecil atau refresh halaman.');
  return body;
}
function log(el,title,payload){el.textContent=title+(payload?'\\n\\n'+JSON.stringify(payload,null,2):'');}
async function loadSession(){
  const response=await fetch('/auth/me',{headers:authHeaders()});
  const profile=await responseBody(response);
  const role=String(profile.role||'-').toUpperCase();
  const scope=profile.branch||profile.access_scope||'ALL';
  sessionEl.value=role+' · '+scope;
  if(profile.branch){branchEl.value=profile.branch;branchEl.disabled=true;branchEl.title='Cabang dikunci mengikuti scope akun.';}
  return profile;
}
function branch(){return branchEl.value.trim();}

async function uploadSap(){
  const file=document.getElementById('sapFile').files[0];
  if(!file)throw new Error('Pilih file SAP terlebih dahulu.');
  if(file.size>MAX_DIRECT_FILE_BYTES)throw new Error('File SAP melebihi 4 MB. Pecah/kompres file sebelum upload.');
  const period=document.getElementById('sapPeriod').value;
  const query={branch:branch()};if(period)query.period=period;
  const fd=new FormData();fd.append('file',file);
  log(sapLog,'Mengupload SAP: '+file.name);
  const response=await fetch(endpointWithQuery('/sap/import',query),{method:'POST',headers:authHeaders(),body:fd});
  const body=await responseBody(response);
  log(sapLog,'UPLOAD SAP BERHASIL',body);
  await loadHistory();
}
async function uploadEvidenceFile(file,type){
  if(file.size>MAX_DIRECT_FILE_BYTES)throw new Error(file.name+' melebihi 4 MB.');
  const fd=new FormData();fd.append('file',file);
  const endpoint=endpointWithQuery('/documents/'+type,{branch:branch()});
  const response=await fetch(endpoint,{method:'POST',headers:authHeaders(),body:fd});
  return responseBody(response);
}
async function uploadEvidence(){
  const billing=[...document.getElementById('billingFiles').files];
  const spj=[...document.getElementById('spjFiles').files];
  if(!billing.length&&!spj.length)throw new Error('Pilih minimal satu file Billing atau SPJ.');
  const jobs=[...billing.map(file=>({file,type:'BILLING'})),...spj.map(file=>({file,type:'SPJ'}))];
  const results=[];
  for(let index=0;index<jobs.length;index++){
    const job=jobs[index];
    log(evidenceLog,'Mengupload '+(index+1)+'/'+jobs.length+': '+job.file.name);
    try{
      const body=await uploadEvidenceFile(job.file,job.type);
      results.push({file:job.file.name,type:job.type,status:'SUCCESS',document_id:body.document_id});
    }catch(error){
      results.push({file:job.file.name,type:job.type,status:'ERROR',error:error.message});
    }
  }
  const success=results.filter(row=>row.status==='SUCCESS').length;
  log(evidenceLog,'UPLOAD EVIDENCE SELESAI - '+success+'/'+results.length+' berhasil',results);
  await loadHistory();
}

async function loadHistory(){
  const response=await fetch('/uploads/recent?limit=60',{headers:authHeaders()});
  const body=await responseBody(response);
  const items=body.items||[];
  if(!items.length){historyRows.innerHTML='<tr><td colspan="7">Belum ada data upload.</td></tr>';return;}
  historyRows.innerHTML=items.map(item=>{
    const detail=item.kind==='SAP'?(item.period||'-'):(item.document_type||'-');
    const time=item.uploaded_at?new Date(item.uploaded_at).toLocaleString('id-ID'):'-';
    return '<tr>'+
      '<td class="kind">'+esc(item.kind)+'</td>'+
      '<td>'+esc(item.file_name)+'</td>'+
      '<td>'+esc(item.branch)+'</td>'+
      '<td>'+esc(detail)+'</td>'+
      '<td>'+esc(item.status)+'</td>'+
      '<td class="muted">'+esc(time)+'</td>'+
      '<td><button class="secondary small-btn" data-edit="'+esc(item.kind)+'" data-id="'+item.id+'">Edit</button> '+
      '<button class="danger small-btn" data-delete="'+esc(item.kind)+'" data-id="'+item.id+'">Delete</button></td>'+
      '</tr>';
  }).join('');
  historyRows.querySelectorAll('[data-edit]').forEach(btn=>btn.addEventListener('click',()=>editItem(btn.dataset.edit,Number(btn.dataset.id),items)));
  historyRows.querySelectorAll('[data-delete]').forEach(btn=>btn.addEventListener('click',()=>deleteItem(btn.dataset.delete,Number(btn.dataset.id),items)));
}
async function editItem(kind,id,items){
  const item=items.find(row=>row.kind===kind&&Number(row.id)===id);
  if(!item)return;
  try{
    let endpoint='',params={};
    if(kind==='SAP'){
      const newBranch=branchEl.disabled?item.branch:prompt('Cabang SAP:',item.branch||'');
      if(newBranch===null)return;
      const newPeriod=prompt('Periode SAP (YYYY-MM-DD, boleh kosong):',item.period||'');
      if(newPeriod===null)return;
      endpoint='/uploads/sap/'+id;params={branch:newBranch};if(newPeriod)params.period=newPeriod;
    }else{
      const newBranch=branchEl.disabled?item.branch:prompt('Cabang evidence:',item.branch||'');
      if(newBranch===null)return;
      const description=prompt('Deskripsi evidence (opsional):',item.description||'');
      if(description===null)return;
      endpoint='/uploads/evidence/'+id;params={branch:newBranch,description};
    }
    const response=await fetch(endpointWithQuery(endpoint,params),{method:'PATCH',headers:authHeaders()});
    const body=await responseBody(response);
    log(manageLog,'EDIT BERHASIL',body);await loadHistory();
  }catch(error){log(manageLog,'EDIT GAGAL: '+error.message);}
}
async function deleteItem(kind,id,items){
  const item=items.find(row=>row.kind===kind&&Number(row.id)===id);
  if(!item)return;
  if(!confirm('Delete '+item.kind+' "'+item.file_name+'"? Aksi akan ditolak jika data sudah dipakai proses audit.'))return;
  try{
    const endpoint=kind==='SAP'?'/uploads/sap/'+id:'/uploads/evidence/'+id;
    const response=await fetch(endpoint,{method:'DELETE',headers:authHeaders()});
    const body=await responseBody(response);
    log(manageLog,'DELETE BERHASIL',body);await loadHistory();
  }catch(error){log(manageLog,'DELETE GAGAL: '+error.message);}
}

document.getElementById('sapUploadBtn').addEventListener('click',async event=>{
  const btn=event.currentTarget;btn.disabled=true;
  try{await uploadSap();}catch(error){log(sapLog,'UPLOAD SAP GAGAL: '+error.message);}finally{btn.disabled=false;}
});
document.getElementById('evidenceUploadBtn').addEventListener('click',async event=>{
  const btn=event.currentTarget;btn.disabled=true;
  try{await uploadEvidence();}catch(error){log(evidenceLog,'UPLOAD EVIDENCE GAGAL: '+error.message);}finally{btn.disabled=false;}
});
document.getElementById('refreshBtn').addEventListener('click',()=>loadHistory().catch(error=>log(manageLog,'REFRESH GAGAL: '+error.message)));

loadSession().then(loadHistory).catch(error=>{sessionEl.value='Sesi tidak valid';log(manageLog,'SESSION ERROR: '+error.message);});
</script>
</body></html>"""


@router.get("/ui/upload", response_class=HTMLResponse)
def upload_center_ui():
    return HTMLResponse(upload_center_html())


def register_upload_center_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
