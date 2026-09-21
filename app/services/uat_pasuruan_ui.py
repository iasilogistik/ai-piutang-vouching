from __future__ import annotations


PASURUAN_DOCUMENTS = [
    ("SANTOSO", "8501735930"),
    ("Gemilang 86", ""),
    ("Berkah Al Aqso", "8501681202"),
    ("Wonokoyo", "8501681154"),
    ("Sumber Pasir", "8501755230"),
    ("Rajawali", "8540132459"),
    ("Firza Jaya", "8540130655"),
    ("Lancar Keramik", "8540131695"),
    ("Icha Jaya Kencana Sakti", "8501709449"),
    ("TB Joyo Arjuno Prigen", "8540088421"),
]


def uat_pasuruan_html() -> str:
    """Return the browser-side UAT runner page for the Pasuruan pilot batch.

    The page uses protected production APIs from the browser. It stores only
    checklist and form state in localStorage; uploaded documents and audit data
    remain managed by the application APIs and database.
    """

    rows = "\n".join(
        f"""
        <tr>
          <td><input type=\"checkbox\" data-check=\"doc-{index}\" /></td>
          <td>{index}</td>
          <td>{customer}</td>
          <td>{billing or '-'}</td>
          <td><input type=\"text\" placeholder=\"PASS / REVIEW / EXCEPTION\" /></td>
          <td><input type=\"text\" placeholder=\"Catatan hasil cek manual\" /></td>
        </tr>
        """
        for index, (customer, billing) in enumerate(PASURUAN_DOCUMENTS, start=1)
    )

    html = r"""
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UAT Pasuruan Final</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; --yellow:#b26a00; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }
    header { background: #0f172a; color: white; padding: 18px 24px; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 6px 0 0; color: #cbd5e1; }
    main { padding: 20px 24px 40px; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .workbench { display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 14px; }
    .card, .panel { background: var(--card); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 1px 3px rgba(15,23,42,.06); }
    .card { padding: 16px; }
    .card .label { color: var(--muted); font-size: 13px; }
    .card .value { font-size: 26px; font-weight: 800; margin-top: 5px; }
    .panel { padding: 16px; margin: 14px 0; overflow: auto; }
    h2 { margin: 0 0 10px; font-size: 18px; }
    h3 { margin: 0 0 10px; font-size: 16px; }
    ol { margin-top: 8px; }
    li { margin: 7px 0; }
    table { width: 100%; border-collapse: collapse; min-width: 900px; }
    th, td { border-bottom: 1px solid var(--line); text-align: left; padding: 9px 10px; font-size: 13px; vertical-align: top; }
    th { background: #f8fafc; color: #334155; }
    label { display:block; font-size:12px; color:var(--muted); margin: 8px 0 5px; }
    input[type='text'], input[type='password'], input[type='date'], input[type='file'], textarea { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 8px; font: inherit; background:white; }
    button, .button-link { border: 0; border-radius: 8px; padding: 10px 13px; background: var(--blue); color: white; font-weight: 700; cursor: pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background: #475569; }
    button.warning { background: var(--yellow); }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .status { font-weight: 700; }
    .ready { color: var(--green); }
    .not-ready { color: var(--red); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
    .notice { color: var(--muted); font-size: 13px; }
    pre { white-space: pre-wrap; word-break: break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; min-height:160px; max-height:360px; overflow:auto; }
    .ok { color: var(--green); font-weight:700; }
    .warn { color: var(--yellow); font-weight:700; }
    @media (max-width: 1000px) { .grid, .workbench { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<header>
  <h1>UAT Pasuruan Final</h1>
  <p>Checklist dan upload workbench untuk SAP, Billing, SPJ, vouching, control evidence, manual review, export Excel, dan audit trail.</p>
</header>
<main>
  <section class="grid" aria-label="Ringkasan UAT">
    <div class="card"><div class="label">Dokumen UAT</div><div class="value">10</div></div>
    <div class="card"><div class="label">Tahap Wajib</div><div class="value">8</div></div>
    <div class="card"><div class="label">Status Checklist</div><div class="value status not-ready" id="status">BELUM SELESAI</div></div>
  </section>

  <section class="panel">
    <h2>Operational Upload Workbench</h2>
    <p class="notice">Gunakan halaman Vercel ini untuk menjalankan UAT aktual. Masukkan Bearer Token, lalu upload SAP, Billing, dan SPJ secara bertahap.</p>
    <label for="token">Bearer Token</label>
    <input id="token" type="password" placeholder="Paste access token production" autocomplete="off" />

    <div class="workbench">
      <div class="panel">
        <h3>1. Import SAP</h3>
        <label for="period">Periode SAP</label>
        <input id="period" type="date" />
        <label for="sapFile">File SAP Excel</label>
        <input id="sapFile" type="file" accept=".xlsx,.xls,.csv" />
        <div class="actions">
          <button type="button" id="importSapBtn">Import SAP</button>
          <button type="button" class="secondary" id="validateSapBtn">Validate SAP</button>
        </div>
        <p class="notice">Batch ID: <strong id="batchIdText">-</strong></p>
      </div>

      <div class="panel">
        <h3>2. Upload Billing & SPJ</h3>
        <label for="billingFiles">Billing files</label>
        <input id="billingFiles" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple />
        <label for="spjFiles">SPJ files</label>
        <input id="spjFiles" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple />
        <div class="actions">
          <button type="button" id="uploadBillingBtn">Upload Billing</button>
          <button type="button" id="uploadSpjBtn">Upload SPJ</button>
        </div>
      </div>

      <div class="panel">
        <h3>3. Run Vouching</h3>
        <p class="notice">Jalankan setelah SAP dan dokumen fisik selesai di-upload.</p>
        <div class="actions">
          <button type="button" id="runReconciliationBtn">Run SAP vs Billing</button>
          <button type="button" id="runSpjBtn">Run Billing vs SPJ</button>
        </div>
      </div>

      <div class="panel">
        <h3>4. Review & Export</h3>
        <div class="actions">
          <a class="button-link" href="/ui/control-evidence" target="_blank" rel="noopener">Buka Control Evidence</a>
          <a class="button-link secondary" href="/dashboard/control-evidence/export?review_only=false&limit=500" target="_blank" rel="noopener">Export Evidence</a>
          <a class="button-link secondary" href="/audit-trail" target="_blank" rel="noopener">Audit Trail API</a>
        </div>
        <p class="notice">Link export dan audit trail tetap membutuhkan Bearer Token jika dibuka langsung melalui API client.</p>
      </div>
    </div>
    <h3>Log UAT</h3>
    <pre id="log">Belum ada aktivitas.</pre>
  </section>

  <section class="panel">
    <h2>Urutan UAT End-to-End</h2>
    <ol>
      <li><label><input type="checkbox" data-check="step" /> Import SAP Pasuruan dan validasi effective billing key.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Upload 10 dokumen Billing/SPJ Pasuruan.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Pastikan OCR/extraction otomatis berjalan saat upload.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Jalankan SAP vs Billing dan Billing vs SPJ vouching.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Buka dashboard <code>/ui/control-evidence</code> dan cek TTD penerima, TTD driver, TTD satpam, TTD BM, TTD checker, dan stempel.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Lakukan manual review untuk data REVIEW/UNKNOWN/MISSING.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Export Excel control evidence dan simpan sebagai evidence UAT.</label></li>
      <li><label><input type="checkbox" data-check="step" /> Cek audit trail untuk upload, OCR, reconciliation, dan review evidence.</label></li>
    </ol>
    <div class="actions"><button type="button" id="printBtn">Print / Save PDF</button><button type="button" class="secondary" id="resetBtn">Reset Checklist</button></div>
  </section>

  <section class="panel">
    <h2>Daftar Evidence Pasuruan</h2>
    <table>
      <thead><tr><th>Selesai</th><th>No</th><th>Customer / File</th><th>Billing Ref</th><th>Status Auditor</th><th>Catatan</th></tr></thead>
      <tbody>__ROWS__</tbody>
    </table>
  </section>

  <section class="panel">
    <h2>Kriteria Sign-off Pilot</h2>
    <ol>
      <li>Seluruh dokumen berhasil di-upload dan dapat dibuka kembali dari link dokumen.</li>
      <li>Hasil OCR menampilkan Billing/SPJ/nominal/partial payment bila tertulis jelas di dokumen.</li>
      <li>Dashboard menampilkan TTD penerima, driver, satpam, BM, checker, stempel, dan match stempel.</li>
      <li>Data yang tidak jelas masuk REVIEW, bukan dipaksakan PASS.</li>
      <li>Auditor dapat menetapkan PASS/REVIEW/EXCEPTION dengan catatan manual.</li>
      <li>Export Excel dan audit trail tersedia sebagai evidence UAT.</li>
    </ol>
  </section>
</main>
<script>
const KEY = 'uatPasuruanChecklist';
const BATCH_KEY = 'uatPasuruanBatchId';
const tokenInput = document.getElementById('token');
const logEl = document.getElementById('log');
const batchIdText = document.getElementById('batchIdText');

tokenInput.value = localStorage.getItem('auditToken') || '';
batchIdText.textContent = localStorage.getItem(BATCH_KEY) || '-';

function controls() { return Array.from(document.querySelectorAll('input[data-check], table input[type="text"], textarea')); }
function save() {
  const values = controls().map(el => el.type === 'checkbox' ? el.checked : el.value);
  localStorage.setItem(KEY, JSON.stringify(values));
  updateStatus();
}
function load() {
  const raw = localStorage.getItem(KEY);
  if (!raw) return;
  const values = JSON.parse(raw);
  controls().forEach((el, index) => { if (values[index] === undefined) return; if (el.type === 'checkbox') el.checked = values[index]; else el.value = values[index]; });
  updateStatus();
}
function updateStatus() {
  const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  const done = boxes.filter(el => el.checked).length;
  const status = document.getElementById('status');
  if (done === boxes.length) { status.textContent = 'SIAP SIGN-OFF'; status.className = 'value status ready'; }
  else { status.textContent = `${done}/${boxes.length} SELESAI`; status.className = 'value status not-ready'; }
}
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
async function jsonOrText(response) {
  const text = await response.text();
  try { return JSON.parse(text); } catch { return text; }
}
async function requestJson(url, options = {}) {
  const headers = { ...(options.headers || {}), ...authHeaders() };
  const response = await fetch(url, { ...options, headers });
  const body = await jsonOrText(response);
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
  return body;
}
async function uploadOne(endpoint, file) {
  const form = new FormData();
  form.append('file', file);
  return requestJson(endpoint, { method: 'POST', body: form });
}
async function uploadMany(endpoint, inputId, label) {
  const files = Array.from(document.getElementById(inputId).files || []);
  if (!files.length) throw new Error(`${label} belum dipilih.`);
  const results = [];
  for (const file of files) {
    appendLog(label, `Uploading ${file.name}...`);
    results.push(await uploadOne(endpoint, file));
  }
  appendLog(label, results);
}
async function importSap() {
  try {
    const file = document.getElementById('sapFile').files[0];
    if (!file) throw new Error('File SAP belum dipilih.');
    const period = document.getElementById('period').value;
    const endpoint = period ? `/sap/import?period=${encodeURIComponent(period)}` : '/sap/import';
    const result = await uploadOne(endpoint, file);
    if (result.batch_id) { localStorage.setItem(BATCH_KEY, result.batch_id); batchIdText.textContent = result.batch_id; }
    appendLog('Import SAP', result);
  } catch (error) { appendLog('Import SAP', error.message, false); }
}
async function validateSap() {
  try {
    const batchId = localStorage.getItem(BATCH_KEY);
    if (!batchId) throw new Error('Batch ID belum ada. Import SAP terlebih dahulu.');
    appendLog('Validate SAP', await requestJson(`/sap/validate/${batchId}`));
  } catch (error) { appendLog('Validate SAP', error.message, false); }
}
async function runReconciliation() {
  try {
    const batchId = localStorage.getItem(BATCH_KEY);
    if (!batchId) throw new Error('Batch ID belum ada. Import SAP terlebih dahulu.');
    appendLog('Run SAP vs Billing', await requestJson(`/reconciliation/${batchId}/run`, { method: 'POST' }));
  } catch (error) { appendLog('Run SAP vs Billing', error.message, false); }
}
async function runSpj() {
  try { appendLog('Run Billing vs SPJ', await requestJson('/spj/vouch', { method: 'POST' })); }
  catch (error) { appendLog('Run Billing vs SPJ', error.message, false); }
}

document.addEventListener('input', save);
document.getElementById('printBtn').addEventListener('click', () => window.print());
document.getElementById('resetBtn').addEventListener('click', () => { localStorage.removeItem(KEY); location.reload(); });
document.getElementById('importSapBtn').addEventListener('click', importSap);
document.getElementById('validateSapBtn').addEventListener('click', validateSap);
document.getElementById('uploadBillingBtn').addEventListener('click', () => uploadMany('/documents/BILLING', 'billingFiles', 'Upload Billing').catch(error => appendLog('Upload Billing', error.message, false)));
document.getElementById('uploadSpjBtn').addEventListener('click', () => uploadMany('/documents/SPJ', 'spjFiles', 'Upload SPJ').catch(error => appendLog('Upload SPJ', error.message, false)));
document.getElementById('runReconciliationBtn').addEventListener('click', runReconciliation);
document.getElementById('runSpjBtn').addEventListener('click', runSpj);
load(); updateStatus();
</script>
</body>
</html>
"""
    return html.replace("__ROWS__", rows)
