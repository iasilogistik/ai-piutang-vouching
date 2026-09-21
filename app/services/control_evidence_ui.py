from __future__ import annotations


def control_evidence_dashboard_html() -> str:
    """Return a lightweight auditor-facing Control Evidence dashboard shell.

    The page does not embed data. Users paste a bearer token locally; all data
    and review actions are still served by protected API endpoints.
    """

    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dashboard Control Evidence SPJ</title>
  <style>
    :root { color-scheme: light; --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#62748a; --blue:#1f6feb; --green:#188038; --yellow:#b26a00; --red:#b3261e; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }
    header { background: #0f172a; color: white; padding: 18px 24px; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 6px 0 0; color: #cbd5e1; }
    main { padding: 20px 24px 40px; }
    .toolbar, .filterbar, .card, .table-wrap { background: var(--card); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 1px 3px rgba(15, 23, 42, .06); }
    .toolbar { padding: 16px; display: grid; gap: 12px; grid-template-columns: 1.5fr .7fr .5fr auto auto; align-items: end; }
    .filterbar { margin-top: 12px; padding: 16px; display: grid; gap: 12px; grid-template-columns: 1.3fr .7fr .7fr .7fr auto; align-items: end; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }
    input, select, textarea { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px; font: inherit; background: white; }
    button, .button-link { border: 0; border-radius: 8px; padding: 10px 13px; background: var(--blue); color: white; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }
    button.secondary, .button-link.secondary { background: #475569; }
    button.warning { background: var(--yellow); }
    button.danger { background: var(--red); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .cards { margin: 18px 0; display: grid; gap: 12px; grid-template-columns: repeat(5, minmax(140px, 1fr)); }
    .card { padding: 16px; }
    .card .value { font-size: 28px; font-weight: 800; margin-top: 5px; }
    .card .label { color: var(--muted); font-size: 13px; }
    .table-wrap { overflow: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 1380px; }
    th, td { text-align: left; padding: 10px 11px; border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: top; }
    th { background: #f8fafc; color: #334155; position: sticky; top: 0; z-index: 1; }
    tr:hover td { background: #f8fbff; }
    .badge { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #e2e8f0; color: #334155; }
    .PASS, .PRESENT, .MATCH { background: #e6f4ea; color: var(--green); }
    .REVIEW, .UNKNOWN, .NOT_EVALUATED { background: #fff7e6; color: var(--yellow); }
    .EXCEPTION, .MISSING, .NOT_MATCH { background: #fce8e6; color: var(--red); }
    .reasons { max-width: 260px; color: #475569; }
    .actions { display: flex; gap: 6px; flex-wrap: wrap; }
    .notice { margin: 14px 0; color: var(--muted); font-size: 13px; }
    dialog { border: 0; border-radius: 12px; padding: 0; max-width: 520px; width: calc(100% - 32px); box-shadow: 0 12px 36px rgba(15, 23, 42, .25); }
    dialog::backdrop { background: rgba(15,23,42,.45); }
    .modal { padding: 18px; }
    .modal h2 { margin: 0 0 12px; font-size: 18px; }
    .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
    @media (max-width: 1000px) { .toolbar, .filterbar { grid-template-columns: 1fr; } .cards { grid-template-columns: repeat(2, 1fr); } }
  </style>
</head>
<body>
<header>
  <h1>Dashboard Control Evidence SPJ</h1>
  <p>Monitoring TTD penerima, driver, satpam, BM, checker, stempel, dan manual review.</p>
</header>
<main>
  <section class="toolbar" aria-label="Filter dashboard">
    <div>
      <label for="token">Bearer Token</label>
      <input id="token" type="password" placeholder="Paste access token Supabase/production" autocomplete="off" />
    </div>
    <div>
      <label for="reviewOnly">Filter API</label>
      <select id="reviewOnly"><option value="false">Semua evidence</option><option value="true">Manual review saja</option></select>
    </div>
    <div>
      <label for="limit">Limit</label>
      <input id="limit" type="number" min="1" max="500" value="200" />
    </div>
    <button id="loadBtn" type="button">Muat Dashboard</button>
    <button id="exportBtn" class="secondary" type="button">Export Excel</button>
  </section>

  <section class="filterbar" aria-label="Pencarian dan filter tampilan">
    <div>
      <label for="searchText">Search</label>
      <input id="searchText" type="search" placeholder="Cari file, customer, No SPJ, stempel, alasan review" />
    </div>
    <div>
      <label for="statusFilter">Overall</label>
      <select id="statusFilter"><option value="ALL">Semua</option><option>PASS</option><option>REVIEW</option><option>EXCEPTION</option></select>
    </div>
    <div>
      <label for="signatureFilter">TTD Checker</label>
      <select id="signatureFilter"><option value="ALL">Semua</option><option>PRESENT</option><option>MISSING</option><option>UNKNOWN</option></select>
    </div>
    <div>
      <label for="stampFilter">Stempel</label>
      <select id="stampFilter"><option value="ALL">Semua</option><option>PRESENT</option><option>MISSING</option><option>UNKNOWN</option></select>
    </div>
    <button id="clearFiltersBtn" class="secondary" type="button">Reset Filter</button>
  </section>

  <p class="notice" id="message">Data tidak dimuat otomatis. Masukkan token, lalu klik Muat Dashboard.</p>

  <section class="cards" aria-label="Ringkasan">
    <div class="card"><div class="label">Total Dokumen</div><div class="value" id="totalDocuments">-</div></div>
    <div class="card"><div class="label">PASS</div><div class="value" id="passDocuments">-</div></div>
    <div class="card"><div class="label">Perlu Review</div><div class="value" id="reviewDocuments">-</div></div>
    <div class="card"><div class="label">Rows API</div><div class="value" id="returnedRows">-</div></div>
    <div class="card"><div class="label">Rows Setelah Filter</div><div class="value" id="visibleRows">-</div></div>
  </section>

  <section class="table-wrap" aria-label="Tabel control evidence">
    <table>
      <thead>
        <tr>
          <th>Document</th><th>No SPJ</th><th>Overall</th><th>Review</th><th>TTD Penerima</th><th>TTD Driver</th><th>TTD Satpam</th><th>TTD BM</th><th>TTD Checker</th><th>Stempel</th><th>Nama Stempel</th><th>Match</th><th>Alasan Review</th><th>Aksi</th>
        </tr>
      </thead>
      <tbody id="rows"><tr><td colspan="14">Belum ada data.</td></tr></tbody>
    </table>
  </section>
</main>

<dialog id="reviewDialog">
  <form class="modal" method="dialog" id="reviewForm">
    <h2>Manual Review Evidence</h2>
    <input type="hidden" id="evidenceId" />
    <div><label>Status Review</label><select id="reviewStatus"><option>PASS</option><option>REVIEW</option><option>EXCEPTION</option></select></div>
    <div style="margin-top:10px"><label>Catatan Auditor</label><textarea id="reviewRemarks" rows="4" placeholder="Contoh: TTD checker terlihat setelah cek manual dokumen fisik."></textarea></div>
    <div class="modal-actions"><button class="secondary" value="cancel" type="button" id="cancelReview">Batal</button><button value="default" type="submit">Simpan Review</button></div>
  </form>
</dialog>

<script>
const tokenInput = document.getElementById('token');
const reviewOnly = document.getElementById('reviewOnly');
const limitInput = document.getElementById('limit');
const searchText = document.getElementById('searchText');
const statusFilter = document.getElementById('statusFilter');
const signatureFilter = document.getElementById('signatureFilter');
const stampFilter = document.getElementById('stampFilter');
const message = document.getElementById('message');
const rows = document.getElementById('rows');
const dialog = document.getElementById('reviewDialog');
let dashboardData = null;

tokenInput.value = localStorage.getItem('auditToken') || '';
reviewOnly.value = localStorage.getItem('reviewOnly') || 'false';
limitInput.value = localStorage.getItem('dashboardLimit') || '200';
searchText.value = localStorage.getItem('controlEvidenceSearch') || '';
statusFilter.value = localStorage.getItem('controlEvidenceStatus') || 'ALL';
signatureFilter.value = localStorage.getItem('controlEvidenceChecker') || 'ALL';
stampFilter.value = localStorage.getItem('controlEvidenceStamp') || 'ALL';

function authHeaders() {
  const token = tokenInput.value.trim();
  if (!token) throw new Error('Bearer token wajib diisi.');
  localStorage.setItem('auditToken', token);
  return { 'Authorization': `Bearer ${token}` };
}

function badge(value) {
  const text = value || '-';
  const cls = String(text).replace(/[^A-Z_]/g, '');
  return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[s]));
}

function rowSearchBlob(row) {
  return [
    row.file_name, row.document_id, row.no_spj, row.no_spj_raw, row.billing_id,
    row.stamp_text_raw, row.stamp_text_normalized, row.stamp_customer_match_status,
    row.overall_control_status, row.review_status, row.reviewer_remarks,
    ...(row.review_reasons || [])
  ].map(v => String(v || '').toLowerCase()).join(' ');
}

function filteredRows(data) {
  const q = searchText.value.trim().toLowerCase();
  const overall = statusFilter.value;
  const checker = signatureFilter.value;
  const stamp = stampFilter.value;
  localStorage.setItem('controlEvidenceSearch', searchText.value);
  localStorage.setItem('controlEvidenceStatus', overall);
  localStorage.setItem('controlEvidenceChecker', checker);
  localStorage.setItem('controlEvidenceStamp', stamp);
  return (data.rows || []).filter(row => {
    const matchSearch = !q || rowSearchBlob(row).includes(q);
    const matchOverall = overall === 'ALL' || row.overall_control_status === overall;
    const matchChecker = checker === 'ALL' || row.checker_signature_status === checker;
    const matchStamp = stamp === 'ALL' || row.receiver_stamp_status === stamp;
    return matchSearch && matchOverall && matchChecker && matchStamp;
  });
}

function renderSummary(data, visibleCount) {
  const summary = data.summary || {};
  document.getElementById('totalDocuments').textContent = summary.total_documents ?? '-';
  document.getElementById('passDocuments').textContent = summary.pass_documents ?? '-';
  document.getElementById('reviewDocuments').textContent = summary.review_required_documents ?? '-';
  document.getElementById('returnedRows').textContent = data.returned_rows ?? '-';
  document.getElementById('visibleRows').textContent = visibleCount ?? '-';
}

function renderRows() {
  if (!dashboardData) return;
  const list = filteredRows(dashboardData);
  renderSummary(dashboardData, list.length);
  if (!list.length) {
    rows.innerHTML = '<tr><td colspan="14">Tidak ada data sesuai filter/search.</td></tr>';
    return;
  }
  rows.innerHTML = list.map(row => {
    const reasons = (row.review_reasons || []).map(escapeHtml).join('<br>');
    const evidenceId = Number(row.control_evidence_id || 0);
    return `<tr>
      <td><strong>${escapeHtml(row.file_name || row.document_id)}</strong><br><a href="${escapeHtml(row.document_url)}" target="_blank" rel="noopener">Buka dokumen</a></td>
      <td>${escapeHtml(row.no_spj || row.no_spj_raw || '-')}</td>
      <td>${badge(row.overall_control_status)}</td>
      <td>${badge(row.review_status || (row.review_required ? 'REVIEW' : 'PASS'))}<br><small>${escapeHtml(row.reviewer_remarks || '')}</small></td>
      <td>${badge(row.receiver_signature_status)}</td>
      <td>${badge(row.driver_signature_status)}</td>
      <td>${badge(row.security_signature_status)}</td>
      <td>${badge(row.bm_signature_status)}</td>
      <td>${badge(row.checker_signature_status)}</td>
      <td>${badge(row.receiver_stamp_status)}</td>
      <td>${escapeHtml(row.stamp_text_raw || row.stamp_text_normalized || '-')}</td>
      <td>${badge(row.stamp_customer_match_status)}</td>
      <td class="reasons">${reasons || '-'}</td>
      <td class="actions"><button type="button" onclick="openReview(${evidenceId}, 'PASS')">PASS</button><button class="warning" type="button" onclick="openReview(${evidenceId}, 'REVIEW')">REVIEW</button><button class="danger" type="button" onclick="openReview(${evidenceId}, 'EXCEPTION')">EXCEPTION</button></td>
    </tr>`;
  }).join('');
}

async function loadDashboard() {
  try {
    message.textContent = 'Memuat dashboard...';
    localStorage.setItem('reviewOnly', reviewOnly.value);
    localStorage.setItem('dashboardLimit', limitInput.value);
    const url = `/dashboard/control-evidence?review_only=${reviewOnly.value}&limit=${limitInput.value || 200}`;
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) throw new Error(`Gagal memuat dashboard (${response.status})`);
    dashboardData = await response.json();
    renderRows();
    message.textContent = `Dashboard berhasil dimuat. Total rows API: ${dashboardData.total_rows}. Gunakan search/filter untuk mempersempit tampilan.`;
  } catch (error) {
    message.textContent = error.message;
  }
}

function openReview(evidenceId, defaultStatus) {
  document.getElementById('evidenceId').value = evidenceId;
  document.getElementById('reviewStatus').value = defaultStatus;
  document.getElementById('reviewRemarks').value = '';
  dialog.showModal();
}

async function submitReview(event) {
  event.preventDefault();
  try {
    const id = document.getElementById('evidenceId').value;
    const status = document.getElementById('reviewStatus').value;
    const remarks = document.getElementById('reviewRemarks').value.trim();
    const params = new URLSearchParams({ status, remarks });
    const response = await fetch(`/reviews/control-evidence/${id}?${params}`, { method: 'POST', headers: authHeaders() });
    if (!response.ok) throw new Error(`Gagal menyimpan review (${response.status})`);
    dialog.close();
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
  }
}

async function exportExcel() {
  try {
    const url = `/dashboard/control-evidence/export?review_only=${reviewOnly.value}&limit=${limitInput.value || 500}`;
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) throw new Error(`Gagal export (${response.status})`);
    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `control_evidence_${new Date().toISOString().slice(0,10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    message.textContent = error.message;
  }
}

function clearFilters() {
  searchText.value = '';
  statusFilter.value = 'ALL';
  signatureFilter.value = 'ALL';
  stampFilter.value = 'ALL';
  renderRows();
}

document.getElementById('loadBtn').addEventListener('click', loadDashboard);
document.getElementById('exportBtn').addEventListener('click', exportExcel);
document.getElementById('reviewForm').addEventListener('submit', submitReview);
document.getElementById('cancelReview').addEventListener('click', () => dialog.close());
document.getElementById('clearFiltersBtn').addEventListener('click', clearFilters);
[searchText, statusFilter, signatureFilter, stampFilter].forEach(el => el.addEventListener('input', renderRows));
window.openReview = openReview;
</script>
</body>
</html>
"""
