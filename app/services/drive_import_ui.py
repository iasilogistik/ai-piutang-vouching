def drive_import_html() -> str:
    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Google Drive / Share Link Import</title>
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
    input[type='password'], input[type='url'], select { width:100%; border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; background:white; }
    button, .button-link { border:0; border-radius:8px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background:#475569; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
    .notice { color:var(--muted); font-size:13px; line-height:1.45; }
    .ok { color:var(--green); font-weight:700; }
    .err { color:var(--red); font-weight:700; }
    .skip { color:var(--yellow); font-weight:700; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; min-height:160px; max-height:420px; overflow:auto; }
    table { width:100%; border-collapse:collapse; margin-top:10px; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; font-size:13px; vertical-align:top; }
    th { background:#f8fafc; }
  </style>
</head>
<body>
<header>
  <h1>Google Drive / Share Link Import</h1>
  <p>Import dokumen dari share link file, ZIP, atau folder Google Drive.</p>
</header>
<main>
  <section class="panel">
    <h2>Import dari link</h2>
    <p class="notice">
      Gunakan link file atau folder Google Drive yang permission-nya <strong>Anyone with the link</strong>. Import folder membutuhkan environment variable <strong>GOOGLE_DRIVE_API_KEY</strong> di Vercel. Untuk banyak dokumen tanpa API key, unggah satu file ZIP ke Google Drive lalu gunakan tombol <strong>Import File/ZIP Link</strong>.
    </p>
    <label for="token">Bearer Token</label>
    <input id="token" type="password" placeholder="Paste access token production" autocomplete="off" />
    <label for="url">Share Link</label>
    <input id="url" type="url" placeholder="https://drive.google.com/file/d/... atau https://drive.google.com/drive/folders/..." />
    <label for="mode">Mode import</label>
    <select id="mode">
      <option value="AUTO">AUTO - klasifikasi dari nama file/folder ZIP</option>
      <option value="BILLING">Sebagai BILLING</option>
      <option value="SPJ">Sebagai SPJ</option>
      <option value="COMBINED">Sebagai Billing + SPJ gabungan</option>
    </select>
    <div class="actions">
      <button type="button" id="importFileBtn">Import File/ZIP Link</button>
      <button type="button" id="importFolderBtn">Import Folder Link</button>
      <a class="button-link secondary" href="/ui/bulk-upload" target="_blank" rel="noopener">Bulk ZIP Upload</a>
      <a class="button-link secondary" href="/ui/combined-upload" target="_blank" rel="noopener">Combined Upload</a>
      <a class="button-link secondary" href="/ui/control-evidence" target="_blank" rel="noopener">Control Evidence</a>
    </div>
  </section>

  <section class="panel">
    <h2>Hasil import</h2>
    <table>
      <thead><tr><th>File</th><th>Mode</th><th>Billing Doc ID</th><th>SPJ Doc ID</th><th>Status</th></tr></thead>
      <tbody id="resultRows"><tr><td colspan="5">Belum ada import.</td></tr></tbody>
    </table>
    <h3>Log</h3>
    <pre id="log">Belum ada aktivitas.</pre>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
const urlInput = document.getElementById('url');
const modeInput = document.getElementById('mode');
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
  if (!rows.length) { resultRows.innerHTML = '<tr><td colspan="5">Belum ada import.</td></tr>'; return; }
  resultRows.innerHTML = rows.map(row => `<tr><td>${row.file}</td><td>${row.mode || '-'}</td><td>${row.billing || '-'}</td><td>${row.spj || '-'}</td><td class="${row.cls}">${row.status}</td></tr>`).join('');
}
async function importTo(endpoint, label) {
  try {
    const url = urlInput.value.trim();
    if (!url) { appendLog(label, 'Share link wajib diisi.', false); return; }
    appendLog(label, `Importing ${url}...`);
    const form = new FormData();
    form.append('url', url);
    form.append('mode', modeInput.value);
    const response = await fetch(endpoint, { method:'POST', headers:authHeaders(), body:form });
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
    appendLog(label, body);
  } catch (error) {
    rows.unshift({ file: urlInput.value.trim() || '-', mode: modeInput.value, billing: null, spj: null, status: error.message, cls: 'err' });
    renderRows();
    appendLog(label, error.message, false);
  }
}
document.getElementById('importFileBtn').addEventListener('click', () => importTo('/documents/drive-import', 'Import File/ZIP Link'));
document.getElementById('importFolderBtn').addEventListener('click', () => importTo('/documents/drive-folder-import', 'Import Folder Link'));
renderRows();
</script>
</body>
</html>
"""
