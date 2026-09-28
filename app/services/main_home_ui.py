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
    :root {
      --bg:#f4f7fb;
      --surface:#ffffff;
      --surface-soft:#f8fafc;
      --line:#e2e8f0;
      --text:#172033;
      --muted:#64748b;
      --primary:#2563eb;
      --primary-dark:#1d4ed8;
      --accent:#38bdf8;
      --green:#059669;
      --amber:#d97706;
      --red:#dc2626;
      --sidebar:#0b1220;
      --sidebar-soft:#111c31;
      --sidebar-text:#dbeafe;
      --shadow:0 12px 34px rgba(15,23,42,.08);
      --sidebar-width:276px;
    }
    * { box-sizing:border-box; }
    html { background:var(--bg); }
    body { margin:0; min-height:100vh; font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); }
    a { color:inherit; }
    button,input { font:inherit; }
    .app-shell { min-height:100vh; }
    .sidebar {
      position:fixed; inset:0 auto 0 0; width:var(--sidebar-width); z-index:40;
      display:flex; flex-direction:column; padding:20px 14px 16px;
      background:linear-gradient(180deg,#0b1220 0%,#0d1729 56%,#101d33 100%);
      color:var(--sidebar-text); box-shadow:16px 0 44px rgba(15,23,42,.12);
      transition:width .22s ease, transform .22s ease;
    }
    .brand { display:flex; align-items:center; gap:12px; padding:4px 8px 20px; border-bottom:1px solid rgba(148,163,184,.16); }
    .brand-mark {
      width:42px; height:42px; border-radius:14px; flex:0 0 auto;
      display:grid; place-items:center; color:white; font-weight:900; letter-spacing:-.5px;
      background:linear-gradient(135deg,#2563eb,#38bdf8); box-shadow:0 10px 24px rgba(37,99,235,.34);
    }
    .brand-copy strong { display:block; color:#fff; font-size:14px; line-height:1.2; }
    .brand-copy span { display:block; color:#94a3b8; font-size:11px; margin-top:3px; }
    .sidebar-scroll { overflow-y:auto; padding:16px 4px 12px; scrollbar-width:thin; flex:1; }
    .nav-group { margin-bottom:18px; }
    .nav-label { padding:0 10px 7px; color:#64748b; font-size:10px; font-weight:800; letter-spacing:.11em; text-transform:uppercase; }
    .nav-item {
      display:flex; align-items:center; gap:11px; min-height:43px; margin:3px 0; padding:9px 10px;
      border-radius:11px; color:#b8c7da; text-decoration:none; font-size:13px; font-weight:650;
      transition:background .16s ease,color .16s ease,transform .16s ease;
    }
    .nav-item:hover { color:white; background:rgba(59,130,246,.14); transform:translateX(2px); }
    .nav-item.active { color:#fff; background:linear-gradient(90deg,rgba(37,99,235,.3),rgba(56,189,248,.10)); box-shadow:inset 3px 0 0 #38bdf8; }
    .nav-icon {
      width:30px; height:30px; display:grid; place-items:center; flex:0 0 auto;
      border-radius:9px; color:#bfdbfe; background:rgba(148,163,184,.10); font-size:10px; font-weight:900; letter-spacing:.02em;
    }
    .nav-item.active .nav-icon { background:#2563eb; color:white; }
    .sidebar-footer { border-top:1px solid rgba(148,163,184,.16); padding:14px 8px 0; }
    .system-chip { display:flex; align-items:center; gap:8px; color:#9fb0c7; font-size:11px; }
    .health-dot { width:8px; height:8px; border-radius:50%; background:#94a3b8; box-shadow:0 0 0 4px rgba(148,163,184,.08); }
    .health-dot.ok { background:#34d399; box-shadow:0 0 0 4px rgba(52,211,153,.10); }
    .main-shell { margin-left:var(--sidebar-width); min-height:100vh; transition:margin-left .22s ease; }
    .topbar {
      position:sticky; top:0; z-index:25; min-height:72px; padding:12px 28px;
      display:flex; align-items:center; gap:14px; justify-content:space-between;
      background:rgba(255,255,255,.88); backdrop-filter:blur(14px); border-bottom:1px solid rgba(226,232,240,.9);
    }
    .top-left,.top-right { display:flex; align-items:center; gap:12px; }
    .menu-btn,.icon-btn {
      width:40px; height:40px; border:1px solid var(--line); border-radius:11px; background:#fff; color:#334155; cursor:pointer;
      display:grid; place-items:center;
    }
    .menu-btn { display:none; }
    .page-title strong { display:block; font-size:15px; }
    .page-title span { display:block; color:var(--muted); font-size:11px; margin-top:2px; }
    .global-search { width:min(32vw,360px); position:relative; }
    .global-search input { width:100%; border:1px solid var(--line); border-radius:12px; padding:10px 13px 10px 36px; outline:none; background:#f8fafc; }
    .global-search input:focus { border-color:#93c5fd; box-shadow:0 0 0 3px rgba(59,130,246,.10); background:#fff; }
    .search-mark { position:absolute; left:12px; top:50%; transform:translateY(-50%); color:#94a3b8; font-size:13px; }
    .profile { display:flex; align-items:center; gap:10px; padding-left:12px; border-left:1px solid var(--line); }
    .avatar {
      width:38px; height:38px; border-radius:12px; display:grid; place-items:center;
      background:linear-gradient(135deg,#1d4ed8,#0ea5e9); color:#fff; font-weight:900; font-size:12px;
    }
    .profile-copy strong { display:block; font-size:12px; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .profile-copy span { display:block; color:var(--muted); font-size:10px; margin-top:2px; }
    .content { padding:26px 28px 46px; max-width:1540px; margin:0 auto; }
    .hero {
      position:relative; overflow:hidden; border-radius:22px; padding:25px 26px; color:#fff;
      background:
        radial-gradient(circle at 86% 20%,rgba(56,189,248,.40),transparent 24%),
        radial-gradient(circle at 74% 90%,rgba(99,102,241,.24),transparent 30%),
        linear-gradient(130deg,#0f2b5f,#1d4ed8 55%,#0ea5e9);
      box-shadow:0 18px 46px rgba(37,99,235,.22);
    }
    .hero-grid { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:20px; align-items:center; }
    .eyebrow { margin:0 0 7px; font-size:11px; text-transform:uppercase; letter-spacing:.12em; font-weight:800; color:#bae6fd; }
    .hero h1 { margin:0; font-size:27px; letter-spacing:-.5px; }
    .hero p { margin:9px 0 0; max-width:760px; color:#dbeafe; font-size:13px; line-height:1.55; }
    .session-summary { min-width:230px; padding:14px 16px; border:1px solid rgba(255,255,255,.18); border-radius:15px; background:rgba(255,255,255,.10); backdrop-filter:blur(8px); }
    .session-summary small { color:#bfdbfe; font-size:10px; }
    .session-summary b { display:block; font-size:13px; margin-top:5px; }
    .session-summary span { display:block; color:#e0f2fe; font-size:11px; margin-top:4px; }
    .toolbar { display:flex; gap:9px; flex-wrap:wrap; margin-top:18px; }
    .toolbar input { min-width:220px; border:1px solid rgba(255,255,255,.25); border-radius:11px; padding:10px 12px; background:rgba(255,255,255,.12); color:#fff; outline:none; }
    .toolbar input::placeholder { color:#dbeafe; }
    .toolbar input:disabled { opacity:.75; }
    .btn { border:0; border-radius:11px; padding:10px 14px; cursor:pointer; font-weight:800; font-size:12px; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; gap:6px; }
    .btn.white { background:#fff; color:#1d4ed8; }
    .btn.ghost { background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.20); color:#fff; }
    .btn.primary { background:var(--primary); color:#fff; }
    .btn.secondary { background:#e2e8f0; color:#334155; }
    .section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin:27px 0 12px; }
    .section-head h2 { margin:0; font-size:17px; letter-spacing:-.2px; }
    .section-head p { margin:4px 0 0; color:var(--muted); font-size:11px; }
    .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:13px; }
    .metric {
      min-height:112px; padding:16px; border:1px solid var(--line); border-radius:16px; background:var(--surface); box-shadow:0 7px 22px rgba(15,23,42,.045);
      position:relative; overflow:hidden;
    }
    .metric::after { content:""; position:absolute; width:74px; height:74px; right:-30px; top:-30px; border-radius:50%; background:#eff6ff; }
    .metric span { color:var(--muted); font-size:11px; }
    .metric b { display:block; margin-top:9px; font-size:25px; letter-spacing:-.5px; }
    .metric em { display:block; margin-top:7px; color:#94a3b8; font-size:10px; font-style:normal; }
    .workspace-grid { display:grid; grid-template-columns:1.25fr .75fr; gap:16px; margin-top:14px; }
    .panel { border:1px solid var(--line); border-radius:18px; background:var(--surface); box-shadow:var(--shadow); padding:18px; }
    .quick-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .quick-card {
      display:flex; align-items:center; gap:12px; padding:13px; border:1px solid var(--line); border-radius:14px; background:#fff; text-decoration:none;
      transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease;
    }
    .quick-card:hover { transform:translateY(-2px); border-color:#bfdbfe; box-shadow:0 10px 24px rgba(37,99,235,.08); }
    .quick-icon { width:40px; height:40px; border-radius:12px; display:grid; place-items:center; flex:0 0 auto; background:#eff6ff; color:#1d4ed8; font-size:11px; font-weight:900; }
    .quick-card strong { display:block; font-size:12px; }
    .quick-card span { display:block; color:var(--muted); font-size:10px; margin-top:3px; }
    .workflow { display:grid; gap:9px; }
    .step { display:grid; grid-template-columns:28px 1fr auto; align-items:center; gap:9px; padding:9px 10px; border-radius:12px; background:#f8fafc; border:1px solid #edf2f7; }
    .step-num { width:28px; height:28px; border-radius:9px; display:grid; place-items:center; background:#e0ecff; color:#1d4ed8; font-size:10px; font-weight:900; }
    .step strong { display:block; font-size:11px; }
    .step span { color:var(--muted); font-size:9px; }
    .step-status { color:#94a3b8; font-size:9px; font-weight:800; }
    .status-card { margin-top:14px; padding:12px 14px; border-radius:13px; background:#0f172a; color:#dbeafe; font-size:10px; line-height:1.55; white-space:pre-wrap; word-break:break-word; max-height:180px; overflow:auto; }
    .role-hidden { display:none !important; }
    .sidebar-overlay { display:none; position:fixed; inset:0; z-index:35; background:rgba(15,23,42,.45); backdrop-filter:blur(2px); }
    body.sidebar-collapsed .sidebar { width:82px; }
    body.sidebar-collapsed .main-shell { margin-left:82px; }
    body.sidebar-collapsed .brand-copy,
    body.sidebar-collapsed .nav-label,
    body.sidebar-collapsed .nav-text,
    body.sidebar-collapsed .sidebar-footer .system-copy { display:none; }
    body.sidebar-collapsed .brand { justify-content:center; padding-left:0; padding-right:0; }
    body.sidebar-collapsed .nav-item { justify-content:center; padding-left:8px; padding-right:8px; }
    body.sidebar-collapsed .nav-icon { width:34px; height:34px; }
    body.sidebar-collapsed .sidebar-footer { display:flex; justify-content:center; }
    @media (max-width:1120px) {
      .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
      .workspace-grid { grid-template-columns:1fr; }
      .global-search { width:260px; }
    }
    @media (max-width:820px) {
      .sidebar { transform:translateX(-105%); width:min(86vw,294px); }
      .main-shell { margin-left:0 !important; }
      body.mobile-nav-open .sidebar { transform:translateX(0); }
      body.mobile-nav-open .sidebar-overlay { display:block; }
      .menu-btn { display:grid; }
      .global-search { display:none; }
      .profile-copy { display:none; }
      .content { padding:18px 16px 36px; }
      .topbar { padding:10px 16px; }
      .hero { border-radius:18px; padding:20px; }
      .hero-grid { grid-template-columns:1fr; }
      .session-summary { min-width:0; }
    }
    @media (max-width:560px) {
      .metric-grid,.quick-grid { grid-template-columns:1fr; }
      .hero h1 { font-size:22px; }
      .toolbar input { min-width:100%; width:100%; }
      .toolbar .btn { flex:1; }
      .top-right .icon-btn { display:none; }
    }
  </style>
</head>
<body>
<div class="app-shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <div class="brand-mark">IA</div>
      <div class="brand-copy">
        <strong>AI Piutang Vouching</strong>
        <span>Internal Audit Command Center</span>
      </div>
    </div>

    <div class="sidebar-scroll">
      <div class="nav-group" data-group>
        <div class="nav-label">Overview</div>
        <a class="nav-item active" href="/ui/main" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">HM</span><span class="nav-text">Home</span></a>
        <a class="nav-item" href="/ui/dashboard" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">DB</span><span class="nav-text">Dashboard Cabang</span></a>
        <a class="nav-item" href="/ui/audit-management" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">AM</span><span class="nav-text">Audit Management</span></a>
      </div>

      <div class="nav-group" data-group>
        <div class="nav-label">Audit</div>
        <a class="nav-item" href="/ui/audit-engagements" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">EN</span><span class="nav-text">Engagements</span></a>
        <a class="nav-item" href="/ui/audit-sampling" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">SP</span><span class="nav-text">Sampling</span></a>
        <a class="nav-item" href="/ui/audit-working-papers" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">WP</span><span class="nav-text">Working Papers</span></a>
        <a class="nav-item" href="/ui/audit-findings" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">FN</span><span class="nav-text">Findings</span></a>
        <a class="nav-item" href="/ui/management-actions" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">MA</span><span class="nav-text">Management Actions</span></a>
        <a class="nav-item" href="/ui/follow-up" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">FU</span><span class="nav-text">Follow-up</span></a>
      </div>

      <div class="nav-group" data-group>
        <div class="nav-label">Data &amp; Vouching</div>
        <a class="nav-item" href="/ui/upload" data-roles="ADMIN,AUDITOR"><span class="nav-icon">UP</span><span class="nav-text">Upload Center</span></a>
        <a class="nav-item" href="/ui/control-evidence" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">CE</span><span class="nav-text">Control Evidence</span></a>
        <a class="nav-item" href="/ui/review-queue" data-roles="ADMIN,AUDITOR,REVIEWER"><span class="nav-icon">RQ</span><span class="nav-text">Review Queue</span></a>
        <a class="nav-item" href="/ui/exceptions" data-roles="ADMIN,AUDITOR,REVIEWER"><span class="nav-icon">EX</span><span class="nav-text">Exceptions</span></a>
        <a class="nav-item" href="/ui/evidence-repository" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">ER</span><span class="nav-text">Evidence Repository</span></a>
      </div>

      <div class="nav-group" data-group>
        <div class="nav-label">Monitoring</div>
        <a class="nav-item" href="/ui/audit-workflow" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">WF</span><span class="nav-text">Audit Workflow</span></a>
        <a class="nav-item" href="/ui/audit-trail" data-roles="ADMIN,AUDITOR"><span class="nav-icon">AT</span><span class="nav-text">Audit Trail</span></a>
        <a class="nav-item" href="/ui/audit-reports" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="nav-icon">RP</span><span class="nav-text">Reports</span></a>
        <a class="nav-item" href="/ui/audit-closing" data-roles="ADMIN,AUDITOR,REVIEWER"><span class="nav-icon">CL</span><span class="nav-text">Closing</span></a>
      </div>

      <div class="nav-group admin-only" data-group>
        <div class="nav-label">Administration</div>
        <a class="nav-item" href="/ui/users" data-roles="ADMIN"><span class="nav-icon">US</span><span class="nav-text">User Management</span></a>
        <a class="nav-item" href="/ui/branches" data-roles="ADMIN"><span class="nav-icon">BR</span><span class="nav-text">Branch Catalog</span></a>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="system-chip"><span class="health-dot" id="healthDot"></span><span class="system-copy" id="healthText">System checking...</span></div>
    </div>
  </aside>

  <div class="sidebar-overlay" id="sidebarOverlay"></div>

  <div class="main-shell">
    <header class="topbar">
      <div class="top-left">
        <button type="button" class="menu-btn" id="mobileMenuBtn" aria-label="Buka menu">☰</button>
        <button type="button" class="icon-btn" id="collapseBtn" aria-label="Ringkas sidebar">≡</button>
        <div class="page-title">
          <strong>Command Center</strong>
          <span>Monitoring dan workflow audit piutang</span>
        </div>
      </div>
      <div class="top-right">
        <form class="global-search" action="/ui/search" method="get">
          <span class="search-mark">⌕</span>
          <input name="q" aria-label="Global audit search" placeholder="Cari audit, evidence, temuan..." />
        </form>
        <a class="icon-btn" href="/ui/notifications" aria-label="Notifications">•</a>
        <div class="profile">
          <div class="avatar" id="avatar">IA</div>
          <div class="profile-copy"><strong id="profileName">Memuat sesi...</strong><span id="profileMeta">Role · Cabang</span></div>
        </div>
      </div>
    </header>

    <main class="content">
      <section class="hero">
        <div class="hero-grid">
          <div>
            <p class="eyebrow">Internal Audit Workspace</p>
            <h1 id="welcomeTitle">AI Piutang Vouching Command Center</h1>
            <p>Kelola upload, vouching, evidence, temuan, tindak lanjut, dan monitoring audit dalam satu workspace. Sesi login digunakan otomatis dari browser.</p>
            <div class="toolbar">
              <input id="branch" placeholder="Filter cabang (opsional)" />
              <button id="loadBtn" class="btn white" type="button">Refresh Dashboard</button>
              <a class="btn ghost" href="/ui/upload" data-roles="ADMIN,AUDITOR">Upload Dokumen</a>
              <button id="logoutBtn" class="btn ghost" type="button">Logout</button>
            </div>
          </div>
          <div class="session-summary">
            <small>Status sesi</small>
            <b id="sessionBadge">Memeriksa sesi...</b>
            <span id="sessionInfo">Role: - · Cabang: -</span>
          </div>
        </div>
      </section>

      <div class="section-head">
        <div><h2>Ringkasan Operasional</h2><p>KPI vouching dan evidence berdasarkan scope akses Anda.</p></div>
      </div>
      <section class="metric-grid" id="metrics">
        <div class="metric"><span>Status Aplikasi</span><b>-</b><em>System health</em></div>
        <div class="metric"><span>Sesi</span><b>-</b><em>Authentication</em></div>
        <div class="metric"><span>Cabang</span><b>-</b><em>Access scope</em></div>
        <div class="metric"><span>Role</span><b>-</b><em>User authorization</em></div>
      </section>

      <section class="workspace-grid">
        <div class="panel">
          <div class="section-head" style="margin:0 0 12px;">
            <div><h2>Akses Cepat</h2><p>Menu yang paling sering digunakan dalam proses audit.</p></div>
          </div>
          <div class="quick-grid">
            <a class="quick-card" href="/ui/upload" data-roles="ADMIN,AUDITOR"><span class="quick-icon">UP</span><div><strong>Upload Center</strong><span>SAP, Billing, SPJ, ZIP &amp; combined files</span></div></a>
            <a class="quick-card" href="/ui/review-queue" data-roles="ADMIN,AUDITOR,REVIEWER"><span class="quick-icon">RQ</span><div><strong>Review Queue</strong><span>Prioritaskan item REVIEW dan EXCEPTION</span></div></a>
            <a class="quick-card" href="/ui/audit-findings" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="quick-icon">FN</span><div><strong>Audit Findings</strong><span>Kelola siklus hidup temuan audit</span></div></a>
            <a class="quick-card" href="/ui/follow-up" data-roles="ADMIN,AUDITOR,REVIEWER,VIEWER"><span class="quick-icon">FU</span><div><strong>Follow-up</strong><span>Monitor action plan dan verifikasi tindak lanjut</span></div></a>
          </div>
          <div class="status-card" id="log">Memuat status awal...</div>
        </div>

        <div class="panel">
          <div class="section-head" style="margin:0 0 12px;">
            <div><h2>Alur Kerja Audit</h2><p>Alur ringkas dari data sampai tindak lanjut.</p></div>
          </div>
          <div class="workflow">
            <div class="step"><span class="step-num">1</span><div><strong>Upload &amp; Import</strong><span>SAP, Billing, SPJ dan evidence</span></div><span class="step-status">INPUT</span></div>
            <div class="step"><span class="step-num">2</span><div><strong>Vouching &amp; Reconciliation</strong><span>Matching dan validasi otomatis</span></div><span class="step-status">PROCESS</span></div>
            <div class="step"><span class="step-num">3</span><div><strong>Review Evidence</strong><span>Control evidence dan exception</span></div><span class="step-status">REVIEW</span></div>
            <div class="step"><span class="step-num">4</span><div><strong>Findings</strong><span>Temuan, response dan action plan</span></div><span class="step-status">AUDIT</span></div>
            <div class="step"><span class="step-num">5</span><div><strong>Follow-up &amp; Closing</strong><span>Verifikasi, monitoring dan sign-off</span></div><span class="step-status">CLOSE</span></div>
          </div>
        </div>
      </section>
    </main>
  </div>
</div>

<script>
const branchInput = document.getElementById('branch');
const badge = document.getElementById('sessionBadge');
const info = document.getElementById('sessionInfo');
const metrics = document.getElementById('metrics');
const logEl = document.getElementById('log');
const profileName = document.getElementById('profileName');
const profileMeta = document.getElementById('profileMeta');
const welcomeTitle = document.getElementById('welcomeTitle');
const healthDot = document.getElementById('healthDot');
const healthText = document.getElementById('healthText');

function storedToken() { return localStorage.getItem('auditToken') || ''; }
function authHeaders() {
  const token = storedToken().trim();
  return token ? { Authorization: 'Bearer ' + token } : {};
}
function esc(value) {
  return String(value ?? '-').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function setLog(text, data) { logEl.textContent = text + (data ? '\n' + JSON.stringify(data, null, 2) : ''); }
function metric(label, value, note='') {
  return `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><em>${esc(note)}</em></div>`;
}
function roleAllowed(element, role) {
  const roles = (element.dataset.roles || '').split(',').map(x => x.trim()).filter(Boolean);
  return !roles.length || roles.includes(role);
}
function applyRoleMenu(role) {
  document.querySelectorAll('[data-roles]').forEach(el => {
    el.classList.toggle('role-hidden', !roleAllowed(el, role));
  });
  document.querySelectorAll('[data-group]').forEach(group => {
    const visible = Array.from(group.querySelectorAll('[data-roles]')).some(el => !el.classList.contains('role-hidden'));
    group.classList.toggle('role-hidden', !visible);
  });
  document.querySelectorAll('.admin-only').forEach(el => {
    el.classList.toggle('role-hidden', role !== 'ADMIN');
  });
}
function initials(text) {
  const parts = String(text || 'IA').split(/[@. _-]+/).filter(Boolean);
  return (parts.slice(0,2).map(x => x[0]).join('') || 'IA').toUpperCase();
}
function setLoggedOut() {
  badge.textContent = 'Belum login';
  info.textContent = 'Role: - · Cabang: -';
  profileName.textContent = 'Belum login';
  profileMeta.textContent = 'Session unavailable';
  document.getElementById('avatar').textContent = 'IA';
  metrics.innerHTML = metric('Status Aplikasi','OK','System health') + metric('Sesi','Belum Login','Authentication') + metric('Cabang','-','Access scope') + metric('Role','-','Authorization');
  applyRoleMenu('');
}
function setLoggedIn(user) {
  const role = String(user.role || '-').toUpperCase();
  const branch = user.branch || user.access_scope || 'ALL';
  const identity = user.display_name || user.email || user.user_id || 'Audit User';
  badge.textContent = 'Login aktif';
  info.textContent = `Role: ${role} · Cabang: ${branch}`;
  profileName.textContent = identity;
  profileMeta.textContent = `${role} · ${branch}`;
  document.getElementById('avatar').textContent = initials(identity);
  welcomeTitle.textContent = `Selamat datang, ${String(identity).split('@')[0]}`;
  if (user.branch) {
    branchInput.value = user.branch;
    branchInput.disabled = true;
    branchInput.title = 'Scope cabang dikunci oleh profil user.';
  } else {
    branchInput.disabled = false;
  }
  applyRoleMenu(role);
  if (role === 'ADMIN') {
    document.body.dataset.admin = 'true';
  }
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
    setLog('Sesi sudah kedaluwarsa atau tidak valid. Silakan login ulang.', { detail: error.message });
    return null;
  }
}
function renderMetrics(payload, user) {
  const data = payload.metrics || {};
  const branch = payload.branch || branchInput.value.trim() || user.branch || user.access_scope || 'ALL';
  metrics.innerHTML = [
    metric('SAP Billing', data.sap_billing ?? '-', 'Population'),
    metric('Physical Billing', data.physical_billing ?? '-', 'Evidence'),
    metric('Matched', data.matched ?? '-', 'Vouching match'),
    metric('Unmatched', data.unmatched ?? '-', 'Need review'),
    metric('Control Evidence', data.control_evidence_total ?? '-', 'Evidence checks'),
    metric('Evidence Review', data.control_evidence_review ?? '-', 'Manual review'),
    metric('Pending Review', data.pending_review ?? '-', 'Open queue'),
    metric('Cabang', branch, 'Active scope')
  ].join('');
}
async function loadDashboard() {
  const health = await fetch('/health').then(r => r.json()).catch(() => ({ status:'unknown' }));
  const healthy = health.status === 'healthy';
  healthDot.classList.toggle('ok', healthy);
  healthText.textContent = healthy ? 'System healthy' : 'System status unknown';

  const user = await loadMe();
  if (!user) {
    setLog('Status aplikasi: ' + health.status + '. Login diperlukan untuk melihat dashboard.');
    return;
  }
  try {
    const params = new URLSearchParams();
    const branch = branchInput.value.trim();
    if (branch) params.set('branch', branch);
    const suffix = params.toString() ? '?' + params.toString() : '';
    const response = await fetch('/dashboard/branch' + suffix, { headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    renderMetrics(body, user);
    setLog('Dashboard berhasil dimuat.', { health, branch: body.branch || branch || 'ALL', role: user.role });
  } catch (error) {
    setLog('Aplikasi sehat, tetapi ringkasan dashboard belum dapat dimuat.', { detail: error.message });
  }
}
function markActiveMenu() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.getAttribute('href') === path || (path === '/' && item.getAttribute('href') === '/ui/main'));
  });
}
function closeMobileNav() { document.body.classList.remove('mobile-nav-open'); }
document.getElementById('mobileMenuBtn').addEventListener('click', () => document.body.classList.toggle('mobile-nav-open'));
document.getElementById('sidebarOverlay').addEventListener('click', closeMobileNav);
document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', closeMobileNav));
document.getElementById('collapseBtn').addEventListener('click', () => {
  document.body.classList.toggle('sidebar-collapsed');
  localStorage.setItem('auditSidebarCollapsed', document.body.classList.contains('sidebar-collapsed') ? '1' : '0');
});
if (localStorage.getItem('auditSidebarCollapsed') === '1' && window.innerWidth > 820) document.body.classList.add('sidebar-collapsed');

document.getElementById('loadBtn').addEventListener('click', loadDashboard);
document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.removeItem('auditToken');
  localStorage.removeItem('auditRefreshToken');
  localStorage.removeItem('auditExpiresAt');
  localStorage.removeItem('auditUser');
  window.location.href = '/login';
});
markActiveMenu();
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
