from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
_REGISTERED = False


def main_home_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Piutang Vouching - Halaman Utama</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; --slate:#0f172a; --amber:#b45309; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }
    header { background:linear-gradient(135deg,#0f172a,#1e293b); color:white; padding:22px 28px; }
    header h1 { margin:0; font-size:26px; }
    header p { margin:8px 0 0; color:#cbd5e1; max-width:900px; line-height:1.45; }
    main { max-width:1260px; margin:0 auto; padding:22px 24px 44px; }
    .topbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:14px 0; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; margin:14px 0; box-shadow:0 1px 3px rgba(15,23,42,.06); }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
    .module-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    .card { border:1px solid var(--line); border-radius:12px; background:white; padding:14px; min-height:124px; display:flex; flex-direction:column; justify-content:space-between; }
    .card h3 { margin:0 0 8px; font-size:16px; }
    .card p { margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.45; }
    .metric { border:1px solid var(--line); border-radius:12px; padding:14px; background:#f8fafc; }
    .metric span { color:var(--muted); font-size:12px; }
    .metric b { display:block; margin-top:6px; font-size:26px; }
    input, select { border:1px solid var(--line); border-radius:9px; padding:10px; font:inherit; background:white; min-width:190px; }
    button, a.button { border:0; border-radius:9px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    a.secondary, button.secondary { background:#475569; }
    .admin-only { display:none; border-color:#f59e0b; background:#fffbeb; }
    .status { display:inline-block; padding:6px 10px; border-radius:999px; background:#e2e8f0; color:#334155; font-weight:700; font-size:12px; }
    .status.admin { background:#ecfdf5; color:#047857; }
    .status.warn { background:#fef3c7; color:#92400e; }
    .status.err { background:#fee2e2; color:#991b1b; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:12px; padding:12px; min-height:90px; max-height:260px; overflow:auto; }
    @media (max-width:1000px) { .grid,.module-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:700px) { .grid,.module-grid { grid-template-columns:1fr; } input,select { width:100%; } }
  </style>
</head>
<body>
<header>
  <h1>AI Piutang Vouching</h1>
  <p>Halaman utama untuk akses dashboard, upload dokumen, Google Drive import, control evidence, workflow audit, review, laporan, dan administrasi user.</p>
</header>
<main>
  <section class="panel">
    <div class="topbar">
      <input id="token" type="password" placeholder="Bearer token otomatis dari login" autocomplete="off" />
      <input id="branch" placeholder="Cabang (ADMIN dapat kosong = semua)" />
      <button id="loadBtn" type="button">Muat Dashboard</button>
      <a class="button secondary" href="/login">Login</a>
      <span id="roleBadge" class="status warn">Belum login</span>
    </div>
  </section>

  <section class="panel">
    <h2>Dashboard Ringkas</h2>
    <div class="grid" id="metrics">
      <div class="metric"><span>Status</span><b>-</b></div>
    </div>
  </section>

  <section class="panel">
    <h2>Menu Utama</h2>
    <div class="module-grid">
      <div class="card"><div><h3>Dashboard Cabang</h3><p>Ringkasan SAP, billing fisik, rekonsiliasi, vouching, dan control evidence per cabang.</p></div><a class="button" href="/ui/dashboard">Buka Dashboard</a></div>
      <div class="card"><div><h3>Upload Center</h3><p>Upload SAP, Billing, SPJ, ZIP, file gabungan Billing+SPJ, dan share link.</p></div><a class="button" href="/ui/upload">Buka Upload</a></div>
      <div class="card"><div><h3>UAT Pasuruan</h3><p>Workbench UAT untuk menjalankan upload, OCR, vouching, dan checklist uji coba.</p></div><a class="button" href="/ui/uat-pasuruan">Buka UAT</a></div>
      <div class="card"><div><h3>Control Evidence</h3><p>Dashboard evidence TTD, stempel, checker, status review, dan export Excel.</p></div><a class="button" href="/ui/control-evidence">Buka Evidence</a></div>
      <div class="card"><div><h3>Google Drive Import</h3><p>Import dari file, ZIP, atau folder Google Drive sesuai mode AUTO/BILLING/SPJ/COMBINED.</p></div><a class="button" href="/ui/drive-import">Buka Drive Import</a></div>
      <div class="card"><div><h3>Review Queue</h3><p>Antrian manual review atas exception, evidence yang tidak lengkap, dan item perlu keputusan auditor.</p></div><a class="button" href="/ui/review-queue">Buka Review</a></div>
      <div class="card"><div><h3>Exception Management</h3><p>Daftar exception rekonsiliasi, vouching, dan control evidence untuk tindak lanjut.</p></div><a class="button" href="/ui/exceptions">Buka Exception</a></div>
      <div class="card"><div><h3>Evidence Repository</h3><p>Repository dokumen dan evidence pendukung untuk pemeriksaan auditor.</p></div><a class="button" href="/ui/evidence-repository">Buka Repository</a></div>
      <div class="card"><div><h3>Audit Workflow</h3><p>Alur kerja audit, engagement, sampling, working paper, temuan, tindak lanjut, dan closing.</p></div><a class="button" href="/ui/audit-workflow">Buka Workflow</a></div>
      <div class="card"><div><h3>Audit Management</h3><p>Dashboard manajemen audit untuk monitoring progress, PIC, status, dan prioritas.</p></div><a class="button" href="/ui/audit-management">Buka Management</a></div>
      <div class="card"><div><h3>Audit Trail</h3><p>Jejak aktivitas sistem: upload, OCR, review, perubahan status, dan tindakan user.</p></div><a class="button" href="/ui/audit-trail">Buka Audit Trail</a></div>
      <div class="card"><div><h3>Laporan</h3><p>Menu laporan audit, export, dan dokumentasi hasil proses vouching.</p></div><a class="button" href="/ui/audit-reports">Buka Reports</a></div>
      <div class="card admin-only" id="userCard"><div><h3>User Management</h3><p>Khusus ADMIN: kelola role ADMIN, AUDITOR, REVIEWER, VIEWER, cabang, dan status aktif/nonaktif.</p></div><a class="button" href="/ui/users">Kelola User</a></div>
    </div>
  </section>

  <section class="panel">
    <h2>Log</h2>
    <pre id="log">Halaman utama siap digunakan.</pre>
  </section>
</main>
<script>
const tokenInput = document.getElementById('token');
const branchInput = document.getElementById('branch');
const badge = document.getElementById('roleBadge');
const metrics = document.getElementById('metrics');
const logEl = document.getElementById('log');
tokenInput.value = localStorage.getItem('auditToken') || '';
function log(text, data) {
  logEl.textContent = text + (data ? '\n' + JSON.stringify(data, null, 2) : '');
}
function headers() {
  const token = tokenInput.value.trim();
  if (token) localStorage.setItem('auditToken', token);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
function setRole(user) {
  const role = (user && user.role) || null;
  if (!role) {
    badge.textContent = 'Belum login';
    badge.className = 'status warn';
    document.getElementById('userCard').style.display = 'none';
    return;
  }
  badge.textContent = `${role} · ${(user.branch || user.access_scope || 'ALL')}`;
  badge.className = `status ${role === 'ADMIN' ? 'admin' : ''}`;
  document.getElementById('userCard').style.display = role === 'ADMIN' ? 'flex' : 'none';
}
async function loadMe() {
  try {
    const response = await fetch('/auth/me', { headers: headers() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    setRole(body);
    return body;
  } catch (error) {
    setRole(null);
    return null;
  }
}
function renderMetrics(payload) {
  const labels = { sap_billing:'SAP Billing', physical_billing:'Physical Billing', matched:'Matched', unmatched:'Unmatched', control_evidence_total:'Control Evidence', control_evidence_review:'Evidence Review', pending_review:'Pending Review', rejected:'Rejected', approved:'Approved' };
  const rows = Object.entries(payload.metrics || {});
  metrics.innerHTML = rows.length ? rows.map(([k,v]) => `<div class="metric"><span>${labels[k] || k}</span><b>${v}</b></div>`).join('') : '<div class="metric"><span>Status</span><b>-</b></div>';
}
async function loadDashboard() {
  const user = await loadMe();
  if (!user) {
    log('Silakan login terlebih dahulu untuk menampilkan dashboard ringkas.');
    return;
  }
  try {
    const params = new URLSearchParams();
    const branch = branchInput.value.trim();
    if (branch) params.set('branch', branch);
    const response = await fetch('/dashboard/branch?' + params.toString(), { headers: headers() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    renderMetrics(body);
    log('Dashboard ringkas berhasil dimuat.', body);
  } catch (error) {
    log('Gagal memuat dashboard ringkas.', { detail: error.message });
  }
}
document.getElementById('loadBtn').addEventListener('click', loadDashboard);
loadDashboard();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def root_home():
    return HTMLResponse(main_home_html())


@router.get("/ui/main", response_class=HTMLResponse)
def main_home_ui():
    return HTMLResponse(main_home_html())


def register_main_home_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
