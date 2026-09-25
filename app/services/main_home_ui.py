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
  <title>AI Piutang Vouching - Command Center</title>
  <style>
    :root { --bg:#f5f7fb; --card:#fff; --line:#d9e0ea; --text:#172033; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; --slate:#0f172a; --amber:#b45309; --soft:#eef4ff; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }
    header { background:linear-gradient(135deg,#0f172a,#1e3a8a); color:white; padding:28px; }
    header h1 { margin:0; font-size:30px; letter-spacing:-.3px; }
    header p { margin:9px 0 0; color:#dbeafe; max-width:980px; line-height:1.5; }
    main { max-width:1320px; margin:0 auto; padding:22px 24px 46px; }
    .topbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:space-between; }
    .topbar-left, .topbar-right { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; margin:14px 0; box-shadow:0 1px 3px rgba(15,23,42,.06); }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
    .module-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    .two-col { display:grid; grid-template-columns:1.1fr .9fr; gap:14px; }
    .card { border:1px solid var(--line); border-radius:14px; background:white; padding:14px; min-height:132px; display:flex; flex-direction:column; justify-content:space-between; }
    .card.important { background:linear-gradient(180deg,#ffffff,#f8fbff); border-color:#bfdbfe; }
    .card h3 { margin:0 0 8px; font-size:16px; }
    .card p { margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.45; }
    .metric { border:1px solid var(--line); border-radius:14px; padding:14px; background:#f8fafc; min-height:88px; }
    .metric span { color:var(--muted); font-size:12px; }
    .metric b { display:block; margin-top:6px; font-size:26px; }
    .workflow { display:grid; gap:9px; }
    .step { display:flex; gap:10px; padding:10px; border:1px solid var(--line); border-radius:12px; background:#fff; }
    .step b { background:var(--soft); color:#1d4ed8; width:28px; height:28px; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; }
    .step span { color:var(--muted); font-size:13px; line-height:1.4; }
    input, select { border:1px solid var(--line); border-radius:9px; padding:10px; font:inherit; background:white; min-width:190px; }
    button, a.button { border:0; border-radius:9px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    a.secondary, button.secondary { background:#475569; }
    .admin-only { display:none; border-color:#f59e0b; background:#fffbeb; }
    .status { display:inline-block; padding:7px 11px; border-radius:999px; background:#e2e8f0; color:#334155; font-weight:700; font-size:12px; }
    .status.admin { background:#ecfdf5; color:#047857; }
    .status.warn { background:#fef3c7; color:#92400e; }
    .status.err { background:#fee2e2; color:#991b1b; }
    .muted { color:var(--muted); }
    .session-box { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    .pill { background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:999px; padding:6px 10px; font-size:12px; font-weight:700; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:12px; padding:12px; min-height:90px; max-height:260px; overflow:auto; }
    @media (max-width:1000px) { .grid,.module-grid,.two-col { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:720px) { .grid,.module-grid,.two-col { grid-template-columns:1fr; } input,select { width:100%; } .topbar { align-items:flex-start; } }
  </style>
</head>
<body>
<header>
  <h1>AI Piutang Vouching Command Center</h1>
  <p>Layout utama yang menyatukan upload dokumen, import Google Drive, vouching Billing-SPJ, control evidence, review exception, audit workflow, user management, dan laporan audit. Sesi login digunakan otomatis dari browser.</p>
</header>
<main>
  <section class="panel">
    <div class="topbar">
      <div class="topbar-left">
        <span id="sessionBadge" class="status warn">Memeriksa sesi...</span>
        <span id="sessionInfo" class="pill">Role: - · Cabang: -</span>
      </div>
      <div class="topbar-right">
        <input id="branch" placeholder="Filter cabang, contoh: Pasuruan" />
        <button id="loadBtn" type="button">Refresh Dashboard</button>
        <a class="button secondary" href="/login">Login</a>
        <button id="logoutBtn" class="secondary" type="button">Logout</button>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="two-col">
      <div>
        <h2>Ringkasan Operasional</h2>
        <p class="muted">Angka ringkas akan muncul setelah user login dan memiliki akses sesuai role/cabang.</p>
        <div class="grid" id="metrics">
          <div class="metric"><span>Status Aplikasi</span><b>-</b></div>
          <div class="metric"><span>Sesi</span><b>-</b></div>
          <div class="metric"><span>Cabang</span><b>-</b></div>
          <div class="metric"><span>Role</span><b>-</b></div>
        </div>
      </div>
      <div>
        <h2>Alur Kerja Audit</h2>
        <div class="workflow">
          <div class="step"><b>1</b><span>Login menggunakan akun auditor/reviewer/admin.</span></div>
          <div class="step"><b>2</b><span>Upload SAP, Billing, SPJ, ZIP, dokumen gabungan, atau import Google Drive.</span></div>
          <div class="step"><b>3</b><span>Sistem menjalankan OCR, ekstraksi field, dan vouching Billing-SPJ.</span></div>
          <div class="step"><b>4</b><span>Control evidence membaca status tanda tangan, checker, dan stempel.</span></div>
          <div class="step"><b>5</b><span>Auditor/reviewer menindaklanjuti item REVIEW atau EXCEPTION.</span></div>
          <div class="step"><b>6</b><span>Export evidence, audit trail, working paper, dan laporan.</span></div>
        </div>
      </div>
    </div>
  </section>

  <section class="panel">
    <h2>Menu Utama</h2>
    <div class="module-grid">
      <div class="card important"><div><h3>Dashboard Cabang</h3><p>Ringkasan SAP, billing fisik, rekonsiliasi, vouching, exception, dan control evidence per cabang.</p></div><a class="button" href="/ui/dashboard">Buka Dashboard</a></div>
      <div class="card important"><div><h3>Upload Center</h3><p>Upload SAP, Billing, SPJ, ZIP, file gabungan Billing+SPJ, dan share link dalam satu area kerja.</p></div><a class="button" href="/ui/upload">Buka Upload</a></div>
      <div class="card"><div><h3>UAT Pasuruan</h3><p>Workbench UAT untuk upload, OCR, vouching, dan checklist uji coba cabang.</p></div><a class="button" href="/ui/uat-pasuruan">Buka UAT</a></div>
      <div class="card"><div><h3>Control Evidence</h3><p>Dashboard evidence TTD, stempel, checker, status review, dan export Excel.</p></div><a class="button" href="/ui/control-evidence">Buka Evidence</a></div>
      <div class="card"><div><h3>Google Drive Import</h3><p>Import dari file, ZIP, atau folder Google Drive sesuai mode AUTO/BILLING/SPJ/COMBINED.</p></div><a class="button" href="/ui/drive-import">Buka Drive Import</a></div>
      <div class="card"><div><h3>Review Queue</h3><p>Antrian manual review atas exception, evidence belum lengkap, dan item perlu keputusan auditor.</p></div><a class="button" href="/ui/review-queue">Buka Review</a></div>
      <div class="card"><div><h3>Exception Management</h3><p>Daftar exception rekonsiliasi, vouching, dan control evidence untuk tindak lanjut.</p></div><a class="button" href="/ui/exceptions">Buka Exception</a></div>
      <div class="card"><div><h3>Evidence Repository</h3><p>Repository dokumen dan evidence pendukung untuk pemeriksaan auditor.</p></div><a class="button" href="/ui/evidence-repository">Buka Repository</a></div>
      <div class="card"><div><h3>Audit Workflow</h3><p>Alur kerja audit, engagement, sampling, working paper, temuan, tindak lanjut, dan closing.</p></div><a class="button" href="/ui/audit-workflow">Buka Workflow</a></div>
      <div class="card"><div><h3>Audit Management</h3><p>Dashboard manajemen audit untuk monitoring progress, PIC, status, dan prioritas.</p></div><a class="button" href="/ui/audit-management">Buka Management</a></div>
      <div class="card"><div><h3>Audit Trail</h3><p>Jejak aktivitas sistem: upload, OCR, review, perubahan status, dan tindakan user.</p></div><a class="button" href="/ui/audit-trail">Buka Audit Trail</a></div>
      <div class="card"><div><h3>Laporan</h3><p>Menu laporan audit, export evidence, dan dokumentasi hasil vouching.</p></div><a class="button" href="/ui/audit-reports">Buka Reports</a></div>
      <div class="card admin-only" id="userCard"><div><h3>User Management</h3><p>Khusus ADMIN: kelola role, cabang, dan status aktif/nonaktif user aplikasi.</p></div><a class="button" href="/ui/users">Kelola User</a></div>
    </div>
  </section>

  <section class="panel">
    <h2>Status Sistem</h2>
    <pre id="log">Memuat status awal...</pre>
  </section>
</main>
<script>
const branchInput = document.getElementById('branch');
const badge = document.getElementById('sessionBadge');
const info = document.getElementById('sessionInfo');
const metrics = document.getElementById('metrics');
const logEl = document.getElementById('log');
function storedToken() { return localStorage.getItem('auditToken') || ''; }
function authHeaders() {
  const token = storedToken().trim();
  const prefix = ['Bea','rer '].join('');
  return token ? { Authorization: prefix + token } : {};
}
function setLog(text, data) { logEl.textContent = text + (data ? '\n' + JSON.stringify(data, null, 2) : ''); }
function metric(label, value) { return `<div class="metric"><span>${label}</span><b>${value}</b></div>`; }
function setLoggedOut() {
  badge.textContent = 'Belum login'; badge.className = 'status warn';
  info.textContent = 'Role: - · Cabang: -';
  document.getElementById('userCard').style.display = 'none';
  metrics.innerHTML = metric('Status Aplikasi','OK') + metric('Sesi','Belum Login') + metric('Cabang','-') + metric('Role','-');
}
function setLoggedIn(user) {
  const role = user.role || '-';
  const branch = user.branch || user.access_scope || 'ALL';
  badge.textContent = 'Login aktif'; badge.className = role === 'ADMIN' ? 'status admin' : 'status';
  info.textContent = `Role: ${role} · Cabang: ${branch}`;
  document.getElementById('userCard').style.display = role === 'ADMIN' ? 'flex' : 'none';
}
async function loadMe() {
  const token = storedToken();
  if (!token) { setLoggedOut(); return null; }
  try {
    const response = await fetch('/auth/me', { headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    setLoggedIn(body);
    return body;
  } catch (error) {
    setLoggedOut();
    setLog('Sesi belum aktif atau sudah kedaluwarsa. Silakan login ulang.', { detail: error.message });
    return null;
  }
}
function renderMetrics(payload, user) {
  const data = payload.metrics || {};
  const branch = payload.branch || branchInput.value.trim() || user.branch || user.access_scope || 'ALL';
  metrics.innerHTML = [
    metric('SAP Billing', data.sap_billing ?? '-'),
    metric('Physical Billing', data.physical_billing ?? '-'),
    metric('Matched', data.matched ?? '-'),
    metric('Unmatched', data.unmatched ?? '-'),
    metric('Control Evidence', data.control_evidence_total ?? '-'),
    metric('Evidence Review', data.control_evidence_review ?? '-'),
    metric('Pending Review', data.pending_review ?? '-'),
    metric('Cabang', branch),
  ].join('');
}
async function loadDashboard() {
  const health = await fetch('/health').then(r => r.json()).catch(() => ({ status:'unknown' }));
  const user = await loadMe();
  if (!user) { setLog('Status aplikasi: ' + health.status + '. Login diperlukan untuk melihat dashboard ringkas.'); return; }
  try {
    const params = new URLSearchParams();
    const branch = branchInput.value.trim();
    if (branch) params.set('branch', branch);
    const suffix = params.toString() ? '?' + params.toString() : '';
    const response = await fetch('/dashboard/branch' + suffix, { headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    renderMetrics(body, user);
    setLog('Dashboard ringkas berhasil dimuat.', { health, dashboard: body });
  } catch (error) {
    setLog('Status aplikasi: ' + health.status + '. Dashboard ringkas belum dapat dimuat.', { detail: error.message });
  }
}
document.getElementById('loadBtn').addEventListener('click', loadDashboard);
document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.removeItem('auditToken');
  localStorage.removeItem('auditRefreshToken');
  localStorage.removeItem('auditExpiresAt');
  localStorage.removeItem('auditUser');
  setLoggedOut();
  setLog('Sesi browser sudah dihapus.');
});
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
