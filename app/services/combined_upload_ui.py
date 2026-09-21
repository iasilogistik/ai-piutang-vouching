from __future__ import annotations


def combined_upload_html() -> str:
    """Return a simple UI for files that contain Billing and SPJ together."""

    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Combined Billing + SPJ Upload</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }
    header { background: #0f172a; color: white; padding: 18px 24px; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 6px 0 0; color: #cbd5e1; }
    main { padding: 20px 24px 40px; max-width: 1100px; margin: 0 auto; }
    .panel { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin: 14px 0; box-shadow: 0 1px 3px rgba(15,23,42,.06); }
    label { display:block; font-size:12px; color:var(--muted); margin: 8px 0 5px; }
    input[type='password'], input[type='file'] { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 8px; font: inherit; background:white; }
    button, .button-link { border: 0; border-radius: 8px; padding: 10px 13px; background: var(--blue); color: white; font-weight: 700; cursor: pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background: #475569; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
    .notice { color: var(--muted); font-size: 13px; line-height: 1.45; }
    .ok { color: var(--green); font-weight:700; }
    .err { color: var(--red); font-weight:700; }
    pre { white-space: pre-wrap; word-break: break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; min-height:180px; max-height:420px; overflow:auto; }
    table { width:100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; font-size:13px; }
    th { background:#f8fafc; }
  </style>
</head>
<body>
<header>
  <h1>Combined Billing + SPJ Upload</h1>
  <p>Untuk file PDF/gambar yang berisi dokumen Billing dan SPJ dalam satu file.</p>
</header>
<main>
  <section class="panel">
    <h2>Upload file gabungan</h2>
    <p class="notice">
      Mode ini membuat dua record dari satu file yang sama: satu sebagai <strong>BILLING</strong> dan satu sebagai <strong>SPJ</strong>.
      OCR dijalankan untuk keduanya, lalu control evidence SPJ ikut dianalisa. Sistem tidak memisahkan halaman secara fisik; bila hasil OCR tidak jelas, item tetap masuk REVIEW.
    </p>
    <label for="token">Bearer Token</label>
    <input id="token" type="password" placeholder="Paste access token production" autocomplete="off" />
    <label for="combinedFiles">Combined Billing + SPJ files</label>
    <input id="combinedFiles" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple />
    <div class="actions">
      <button type="button" id="uploadBtn">Upload Combined</button>
      <a class="button-link secondary" href="/ui/control-evidence" target="_blank" rel="noopener">Buka Control Evidence</a>
      <a class="button-link secondary" href="/ui/uat-pasuruan" target="_blank" rel="noopener">Buka UAT Pasuruan</a>
    </div>
  </section>

  <section class="panel">
    <h2>Hasil upload</h2>
    <table>
      <thead><tr><th>File</th><th>Billing Doc ID</th><th>SPJ Doc ID</th><th>Status</th></tr></thead>
      <tbody id="resultRows"><tr><td colspan="4">Belum ada upload.</td></tr></tbody>
    </table>
    <h3>Log</h3>
    <pre id="log">Belum ada aktivitas.</pre>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
const fileInput = document.getElementById('combinedFiles');
const logEl = document.getElementById('log');
const resultRows = document.getElementById('resultRows');
let rows = [];
tokenInput.value = localStorage.getItem('auditToken') || '';
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
  if (!rows.length) {
    resultRows.innerHTML = '<tr><td colspan="4">Belum ada upload.</td></tr>';
    return;
  }
  resultRows.innerHTML = rows.map(row => `<tr><td>${row.file}</td><td>${row.billing || '-'}</td><td>${row.spj || '-'}</td><td class="${row.ok ? 'ok' : 'err'}">${row.status}</td></tr>`).join('');
}
async function uploadOne(file) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/documents/combined', { method: 'POST', headers: authHeaders(), body: form });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
  return body;
}
async function uploadCombined() {
  const files = Array.from(fileInput.files || []);
  if (!files.length) { appendLog('Upload Combined', 'Pilih minimal satu file.', false); return; }
  for (const file of files) {
    try {
      appendLog('Upload Combined', `Uploading ${file.name}...`);
      const result = await uploadOne(file);
      rows.unshift({ file: file.name, billing: result.billing_document?.document_id, spj: result.spj_document?.document_id, status: 'SUCCESS', ok: true });
      renderRows();
      appendLog('Upload Combined', result);
    } catch (error) {
      rows.unshift({ file: file.name, billing: null, spj: null, status: error.message, ok: false });
      renderRows();
      appendLog('Upload Combined', error.message, false);
    }
  }
}
document.getElementById('uploadBtn').addEventListener('click', uploadCombined);
renderRows();
</script>
</body>
</html>
"""
