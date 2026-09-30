from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()
_REGISTERED = False


def document_viewer_html(document_id: int) -> str:
    document_id = int(document_id)
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Document Viewer - AI Piutang Vouching</title>
<style>
:root{{--bg:#eef2f7;--surface:#fff;--line:#d7e0ea;--text:#172033;--muted:#64748b;--blue:#2563eb;--red:#b91c1c}}
*{{box-sizing:border-box}}
html,body{{margin:0;width:100%;height:100%;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:var(--bg);color:var(--text)}}
body{{display:grid;grid-template-rows:auto 1fr}}
header{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:var(--surface);border-bottom:1px solid var(--line)}}
.title strong{{display:block;font-size:15px}}.title span{{display:block;margin-top:3px;color:var(--muted);font-size:11px}}
.actions{{display:flex;gap:8px;align-items:center}}
button{{border:0;border-radius:9px;padding:9px 12px;background:var(--blue);color:#fff;font:inherit;font-size:12px;font-weight:800;cursor:pointer}}
button.secondary{{background:#475569}}
main{{min-height:0;padding:12px}}
.viewer{{width:100%;height:100%;min-height:420px;border:1px solid var(--line);border-radius:12px;background:#fff;overflow:hidden;display:flex;align-items:center;justify-content:center}}
.viewer iframe{{width:100%;height:100%;border:0;background:#fff}}
.viewer img{{max-width:100%;max-height:100%;object-fit:contain}}
.state{{max-width:620px;padding:24px;text-align:center;color:var(--muted);line-height:1.5}}
.state strong{{display:block;margin-bottom:7px;color:var(--text);font-size:16px}}
.state.error strong{{color:var(--red)}}
@media(max-width:700px){{header{{align-items:flex-start;flex-direction:column}}main{{padding:8px}}}}
</style>
</head>
<body>
<header>
  <div class="title"><strong id="documentTitle">Membuka dokumen #{document_id}</strong><span id="statusText">Memverifikasi sesi dan mengambil dokumen...</span></div>
  <div class="actions"><button id="refreshBtn" class="secondary" type="button">Muat Ulang</button><button id="downloadBtn" type="button" disabled>Download</button></div>
</header>
<main>
  <div class="viewer" id="viewer"><div class="state"><strong>Memuat dokumen...</strong>Dokumen dibuka menggunakan sesi login aplikasi Anda.</div></div>
</main>
<script>
const DOCUMENT_ID={document_id};
const viewer=document.getElementById('viewer');
const statusText=document.getElementById('statusText');
const titleEl=document.getElementById('documentTitle');
const downloadBtn=document.getElementById('downloadBtn');
let objectUrl=null;
let currentBlob=null;
let currentFileName='document-'+DOCUMENT_ID;

function token(){{return (localStorage.getItem('auditToken')||'').trim();}}
function headers(){{const value=token();if(!value)throw new Error('Sesi login tidak ditemukan. Silakan login kembali.');return {{Authorization:'Bearer '+value}};}}
function esc(value){{return String(value??'').replace(/[&<>"']/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));}}
function showError(message){{
  statusText.textContent='Dokumen gagal dibuka';
  viewer.innerHTML='<div class="state error"><strong>Dokumen tidak dapat ditampilkan</strong>'+esc(message)+'</div>';
  downloadBtn.disabled=true;
}}
function cleanup(){{if(objectUrl){{URL.revokeObjectURL(objectUrl);objectUrl=null;}}}}
function filenameFromDisposition(value){{
  const match=String(value||'').match(/filename\*?=(?:UTF-8''|["'])?([^;"']+)/i);
  return match?decodeURIComponent(match[1].replace(/["']/g,'').trim()):'';
}}
async function loadDocument(){{
  cleanup();currentBlob=null;downloadBtn.disabled=true;
  viewer.innerHTML='<div class="state"><strong>Memuat dokumen...</strong>Mohon tunggu sebentar.</div>';
  statusText.textContent='Mengambil dokumen dengan sesi login...';
  try{{
    const response=await fetch('/documents/'+DOCUMENT_ID+'/content',{{headers:headers(),cache:'no-store'}});
    if(!response.ok){{
      let detail='HTTP '+response.status;
      try{{const body=await response.json();detail=body.detail||detail;}}catch(_ ){{}}
      if(response.status===401)detail='Sesi login sudah tidak valid atau token tidak tersedia. Silakan login ulang.';
      if(response.status===403)detail='Akun Anda tidak memiliki akses ke dokumen ini.';
      throw new Error(detail);
    }}
    currentBlob=await response.blob();
    currentFileName=filenameFromDisposition(response.headers.get('content-disposition'))||currentFileName;
    objectUrl=URL.createObjectURL(currentBlob);
    titleEl.textContent=currentFileName;
    statusText.textContent='Dokumen berhasil dimuat';
    const mime=String(currentBlob.type||'').toLowerCase();
    if(mime.startsWith('image/')){{
      viewer.innerHTML='<img alt="'+esc(currentFileName)+'" src="'+objectUrl+'">';
    }}else{{
      viewer.innerHTML='<iframe title="'+esc(currentFileName)+'" src="'+objectUrl+'"></iframe>';
    }}
    downloadBtn.disabled=false;
  }}catch(error){{showError(error.message||'Gagal membuka dokumen.');}}
}}
downloadBtn.addEventListener('click',()=>{{
  if(!currentBlob||!objectUrl)return;
  const a=document.createElement('a');a.href=objectUrl;a.download=currentFileName;document.body.appendChild(a);a.click();a.remove();
}});
document.getElementById('refreshBtn').addEventListener('click',loadDocument);
window.addEventListener('beforeunload',cleanup);
loadDocument();
</script>
</body>
</html>"""


@router.get("/documents/{document_id}/view", response_class=HTMLResponse)
def document_viewer(document_id: int):
    # This page contains no document bytes. It reads the existing browser session
    # and performs an authenticated fetch against the protected content endpoint.
    return HTMLResponse(document_viewer_html(document_id))


def register_document_viewer_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
