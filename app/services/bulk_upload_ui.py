from __future__ import annotations


def bulk_upload_html() -> str:
    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bulk ZIP Upload</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; --yellow:#b26a00; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }
    header { background:#0f172a; color:white; padding:18px 24px; }
    header h1 { margin:0; font-size:22px; }
    header p { margin:6px 0 0; color:#cbd5e1; }
    main { padding:20px 24px 40px; max-width:1150px; margin:0 auto; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin:14px 0; box-shadow:0 1px 3px rgba(15,23,42,.06); }
    label { display:block; font-size:12px; color:var(--muted); margin:8px 0 5px; }
    input[type='password'], input[type='text'], input[type='file'], select { width:100%; border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; background:white; }
    button, .button-link { border:0; border-radius:8px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background:#475569; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
    .notice { color:var(--muted); font-size:13px; line-height:1.45; }
    .ok { color:var(--green); font-weight:700; }
    .err { color:var(--red); font-weight:700; }
    .skip { color:var(--yellow); font-weight:700; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; min-height:180px; max-height:420px; overflow:auto; }
    table { width:100%; border-collapse:collapse; margin-top:10px; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; font-size:13px; vertical-align:top; }
    th { background:#f8fafc; }
  </style>
</head>
<body>
<header>
  <h1>Bulk ZIP Upload</h1>
  <p>Upload glondongan ZIP untuk Billing, SPJ, atau file gabungan Billing + SPJ.</p>
</header>
<main>
  <section class="panel">
    <h2>Upload ZIP dokumen cabang</h2>
    <p class="notice">
      Siapkan ZIP berisi file PDF/JPG/PNG. Mode AUTO membaca folder/nama file seperti <strong>BILLING/</strong>, <strong>SPJ/</strong>, atau <strong>gabungan</strong>. File yang tidak bisa diklasifikasikan akan di-skip agar tidak salah menjadi evidence audit.
    </p>
    <label for="token">Bearer Token</label>
    <input id="token" type="password" placeholder="Paste access token production" autocomplete="off" />
    <label for="branch">Cabang / Scope Upload</label>
    <input id="branch" type="text" placeholder="Contoh: GRESIK — branch baru boleh langsung diketik" />
    <p class="notice">Branch bersifat dinamis dan akan terdaftar otomatis saat upload.</p>
    <label for="mode">Mode import</label>
    <select id="mode">
      <option value="AUTO">AUTO - klasifikasi dari folder/nama file</option>
      <option value="BILLING">Semua file sebagai BILLING</option>
      <option value="SPJ">Semua file sebagai SPJ</option>
      <option value="COMBINED">Semua file sebagai Billing + SPJ gabungan</option>
    </select>
    <label for="zipFile">ZIP file</label>
    <input id="zipFile" type="file" accept=".zip" />
    <div class="actions">
      <button type="button" id="uploadBtn">Upload ZIP</button>
      <a class="button-link secondary" href="/ui/combined-upload" target="_blank" rel="noopener">Combined Upload</a>
      <a class="button-link secondary" href="/ui/control-evidence" target="_blank" rel="noopener">Buka Control Evidence</a>
    </div>
  </section>

  <section class="panel">
    <h2>Format ZIP yang disarankan</h2>
    <pre>BILLING/SANTOSO 8501735930.pdf
BILLING/RAJAWALI 8540132459.pdf
SPJ/SANTOSO SPJ.pdf
SPJ/RAJAWALI SPJ.pdf

atau untuk dokumen gabungan:
GABUNGAN/SANTOSO 8501735930.pdf
GABUNGAN/RAJAWALI 8540132459.pdf</pre>
  </section>

  <section class="panel">
    <h2>Hasil upload</h2>
    <table>
      <thead><tr><th>File</th><th>Mode</th><th>Billing Doc ID</th><th>SPJ Doc ID</th><th>Status</th></tr></thead>
      <tbody id="resultRows"><tr><td colspan="5">Belum ada upload.</td></tr></tbody>
    </table>
    <h3>Log</h3>
    <pre id="log">Belum ada aktivitas.</pre>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
const modeInput = document.getElementById('mode');
const branchInput = document.getElementById('branch');
const zipInput = document.getElementById('zipFile');
const logEl = document.getElementById('log');
const resultRows = document.getElementById('resultRows');
tokenInput.value = localStorage.getItem('auditToken') || '';
let rows = [];
function authHeaders() {
  const token = tokenInput.value.trim();
  if (!token) throw new Error('Bearer token wajib diisi.');
  localStorage.setItem('auditToken', token);
  return { Authorization: `Bearer ${token}` };
}
function appendLog(label, payload, ok = true) {
  const time = new Date().toISOString();
  const text = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  logEl.textContent = `[${time}] ${ok ? 'OK' : 'ERROR'} - ${label}\n${text}\n\n` + (logEl.textContent === 'Belum ada aktivitas.' ? '' : logEl.textContent);
}
function renderRows() {
  if (!rows.length) { resultRows.innerHTML = '<tr><td colspan="5">Belum ada upload.</td></tr>'; return; }
  resultRows.innerHTML = rows.map(row => `<tr><td>${row.file}</td><td>${row.mode || '-'}</td><td>${row.billing || '-'}</td><td>${row.spj || '-'}</td><td class="${row.cls}">${row.status}</td></tr>`).join('');
}
async function uploadZip() {
  const file = zipInput.files[0];
  if (!file) { appendLog('Upload ZIP', 'Pilih file ZIP terlebih dahulu.', false); return; }
  try {
    appendLog('Upload ZIP', `Uploading ${file.name}...`);
    const form = new FormData();
    form.append('file', file);
    const branch = branchInput.value.trim();
    if (branch) form.append('branch', branch);
    const mode = encodeURIComponent(modeInput.value);
    const response = await fetch(`/documents/bulk-zip?mode=${mode}`, { method:'POST', headers:authHeaders(), body:form });
    const text = await response.text();
    let body;
    try { body = JSON.parse(text); } catch { body = text; }
    if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
    rows = (body.results || []).map(item => ({
      file: item.source_path || item.file_name,
      mode: item.mode,
      billing: item.billing_document_id,
      spj: item.spj_document_id,
      status: item.status,
      cls: item.status === 'SUCCESS' ? 'ok' : (item.status === 'SKIPPED' ? 'skip' : 'err')
    }));
    renderRows();
    appendLog('Upload ZIP', body);
  } catch (error) {
    rows.unshift({ file: file.name, mode: modeInput.value, billing: null, spj: null, status: error.message, cls: 'err' });
    renderRows();
    appendLog('Upload ZIP', error.message, false);
  }
}
document.getElementById('uploadBtn').addEventListener('click', uploadZip);
renderRows();
</script>
</body>
</html>
"""
