from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
_REGISTERED = False


def upload_center_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unified Upload Center - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}
header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1100px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
label{display:block;font-size:12px;color:#64748b;margin-bottom:5px}
input,select,button{width:100%;padding:9px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}
button{background:#1f6feb;color:#fff;font-weight:700;cursor:pointer}
pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px;min-height:140px}
.small{font-size:12px;color:#64748b}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><h1>Unified Upload Center</h1><p>Satu halaman untuk SAP, Billing, SPJ, Combined, Bulk ZIP, dan Google Drive import.</p></header>
<main>
<section class="panel">
<div class="grid">
<div><label>Bearer Token</label><input id="token" type="password" placeholder="Token dari login"></div>
<div><label>Cabang / Scope Upload</label><input id="branch" placeholder="Contoh: GRESIK — branch baru boleh langsung diketik"></div>
<div><label>Jenis Upload</label>
<select id="type">
<option value="SAP">SAP</option>
<option value="BILLING">Billing</option>
<option value="SPJ">SPJ</option>
<option value="COMBINED">Combined Billing + SPJ</option>
<option value="BULK">Bulk ZIP</option>
<option value="DRIVE">Google Drive Share Link</option>
<option value="DRIVE_FOLDER">Google Drive Folder</option>
</select></div>
<div><label>Mode Bulk/Drive</label><select id="mode"><option>AUTO</option><option>BILLING</option><option>SPJ</option><option>COMBINED</option></select></div>
<div><label>File</label><input id="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.csv,.zip"></div>
<div><label>Google Drive URL</label><input id="url" placeholder="https://drive.google.com/..."></div>
</div>
<p class="small">Branch bersifat dinamis. SAP dapat mendeteksi branch dari kolom Branch/Cabang/Branch Code/Kode Cabang. Untuk dokumen tanpa metadata branch, isi cabang saat upload; branch baru akan terdaftar otomatis. Validasi server-side tetap menjadi kontrol utama.</p>
<button id="send">Upload / Import</button>
</section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main>
<script>
const allowed=['pdf','png','jpg','jpeg','xlsx','xls','csv','zip'];
const tokenEl=document.getElementById('token'); tokenEl.value=localStorage.getItem('auditToken')||'';
function headers(){const t=tokenEl.value.trim();if(!t)throw new Error('Bearer token wajib diisi.');localStorage.setItem('auditToken',t);return {Authorization:'Bearer '+t};}
function ext(name){const p=(name||'').split('.');return p.length>1?p.pop().toLowerCase():'';}
async function submitUpload(){
 const type=document.getElementById('type').value;
 const branch=document.getElementById('branch').value.trim();
 const mode=document.getElementById('mode').value;
 const url=document.getElementById('url').value.trim();
 const file=document.getElementById('file').files[0];
 let endpoint='', opts={method:'POST',headers:headers()};
 if(type==='DRIVE'||type==='DRIVE_FOLDER'){
   if(!url)throw new Error('Google Drive URL wajib diisi.');
   const fd=new FormData();fd.append('url',url);fd.append('mode',mode);if(branch)fd.append('branch',branch);opts.body=fd;
   endpoint=type==='DRIVE'?'/documents/drive-import':'/documents/drive-folder-import';
 }else{
   if(!file)throw new Error('File wajib dipilih.');
   if(!allowed.includes(ext(file.name)))throw new Error('Ekstensi file tidak didukung.');
   const fd=new FormData();fd.append('file',file);if(branch)fd.append('branch',branch);
   if(type==='SAP') endpoint='/sap/import';
   if(type==='BILLING') endpoint='/documents/BILLING';
   if(type==='SPJ') endpoint='/documents/SPJ';
   if(type==='COMBINED') endpoint='/documents/combined';
   if(type==='BULK'){endpoint='/documents/bulk-zip?mode='+encodeURIComponent(mode); if(ext(file.name)!=='zip')throw new Error('Bulk upload wajib file ZIP.');}
   opts.body=fd;
 }
 const r=await fetch(endpoint,opts); const body=await r.json().catch(()=>({detail:'Response bukan JSON'}));
 document.getElementById('log').textContent=JSON.stringify({status:r.status,endpoint,body},null,2);
 if(!r.ok) throw new Error(body.detail||'Upload gagal.');
}
document.getElementById('send').onclick=()=>submitUpload().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
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
