from __future__ import annotations


def auth_theme_css() -> str:
    return """
:root{
  --auth-bg:#eef4fb;
  --auth-surface:#ffffff;
  --auth-line:#dbe5f0;
  --auth-text:#172033;
  --auth-muted:#64748b;
  --auth-primary:#2563eb;
  --auth-primary-dark:#1d4ed8;
  --auth-accent:#38bdf8;
  --auth-green:#059669;
  --auth-red:#dc2626;
  --auth-shadow:0 28px 80px rgba(15,23,42,.16);
}
*{box-sizing:border-box}
html{background:var(--auth-bg)}
body.auth-page{
  margin:0;
  min-height:100vh;
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
  background:
    radial-gradient(circle at 86% 12%,rgba(56,189,248,.14),transparent 28%),
    radial-gradient(circle at 68% 86%,rgba(37,99,235,.10),transparent 30%),
    var(--auth-bg);
  color:var(--auth-text);
}
.auth-shell{
  min-height:100vh;
  display:grid;
  grid-template-columns:minmax(420px,.95fr) minmax(480px,1.05fr);
}
.auth-hero{
  position:relative;
  overflow:hidden;
  min-height:100vh;
  padding:54px clamp(42px,5vw,78px);
  display:flex;
  flex-direction:column;
  justify-content:space-between;
  color:#fff;
  background:
    radial-gradient(circle at 16% 12%,rgba(56,189,248,.34),transparent 24%),
    radial-gradient(circle at 82% 82%,rgba(99,102,241,.28),transparent 30%),
    linear-gradient(145deg,#081426 0%,#0d2348 48%,#174aa2 100%);
}
.auth-hero:after{
  content:"";
  position:absolute;
  width:420px;height:420px;border-radius:50%;
  right:-210px;bottom:-190px;
  border:1px solid rgba(255,255,255,.10);
  box-shadow:0 0 0 54px rgba(255,255,255,.025),0 0 0 108px rgba(255,255,255,.018);
}
.auth-brand{
  position:relative;z-index:1;
  display:flex;align-items:center;gap:13px;
}
.auth-brand-mark{
  width:48px;height:48px;border-radius:15px;
  display:grid;place-items:center;
  font-weight:900;font-size:15px;letter-spacing:-.3px;
  background:linear-gradient(135deg,#2563eb,#38bdf8);
  box-shadow:0 14px 30px rgba(37,99,235,.35);
}
.auth-brand strong{display:block;font-size:15px}
.auth-brand span{display:block;margin-top:3px;color:#b8c7dc;font-size:11px}
.auth-hero-copy{position:relative;z-index:1;max-width:610px;margin:54px 0}
.auth-kicker{
  display:inline-flex;align-items:center;gap:8px;
  padding:7px 10px;border:1px solid rgba(186,230,253,.24);
  border-radius:999px;background:rgba(255,255,255,.07);
  color:#bae6fd;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
}
.auth-hero h1{margin:18px 0 0;font-size:clamp(34px,4vw,54px);line-height:1.04;letter-spacing:-1.5px}
.auth-hero p{margin:18px 0 0;max-width:560px;color:#d7e6f7;font-size:15px;line-height:1.7}
.auth-features{
  position:relative;z-index:1;
  display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;
}
.auth-feature{
  min-height:96px;padding:14px;
  border:1px solid rgba(255,255,255,.11);border-radius:16px;
  background:rgba(255,255,255,.065);backdrop-filter:blur(8px);
}
.auth-feature b{display:block;font-size:12px}
.auth-feature span{display:block;margin-top:6px;color:#b8c7dc;font-size:10px;line-height:1.45}
.auth-panel{
  min-height:100vh;
  display:grid;place-items:center;
  padding:48px clamp(30px,5vw,76px);
}
.auth-card{
  width:min(500px,100%);
  background:rgba(255,255,255,.96);
  border:1px solid rgba(219,229,240,.95);
  border-radius:26px;
  box-shadow:var(--auth-shadow);
  padding:34px;
}
.auth-badge{
  display:inline-flex;align-items:center;gap:7px;
  padding:7px 10px;border-radius:999px;
  background:#eff6ff;color:#1d4ed8;
  font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;
}
.auth-card h2{margin:15px 0 0;font-size:28px;letter-spacing:-.6px;color:#0f172a}
.auth-card>p,.auth-copy{color:var(--auth-muted);font-size:13px;line-height:1.6}
.auth-card form{margin-top:22px}
.auth-card label{
  display:block;margin:14px 0 6px;
  color:#475569;font-size:12px;font-weight:750;
}
.auth-card input{
  width:100%;min-height:48px;
  padding:12px 13px;
  border:1px solid var(--auth-line);border-radius:12px;
  background:#fff;color:var(--auth-text);
  font:inherit;font-size:14px;outline:none;
  transition:border-color .16s ease,box-shadow .16s ease,background .16s ease;
}
.auth-card input:focus{
  border-color:#93c5fd;
  box-shadow:0 0 0 4px rgba(37,99,235,.10);
  background:#fff;
}
.auth-primary{
  width:100%;min-height:48px;margin-top:20px;
  border:0;border-radius:12px;
  background:linear-gradient(135deg,#2563eb,#1d4ed8);
  color:#fff;font-weight:850;font-size:13px;cursor:pointer;
  box-shadow:0 12px 24px rgba(37,99,235,.22);
}
.auth-primary:hover{filter:brightness(1.03)}
.auth-primary:disabled{opacity:.6;cursor:not-allowed}
.auth-secondary{
  width:100%;min-height:44px;margin-top:10px;
  border:1px solid var(--auth-line);border-radius:12px;
  background:#f8fafc;color:#475569;
  font-weight:750;font-size:12px;cursor:pointer;
}
.auth-links{
  margin-top:18px;padding-top:16px;
  border-top:1px solid #e8eef5;
  display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
}
.auth-links a,.auth-card a{color:var(--auth-primary);font-weight:800;text-decoration:none}
.auth-links a:hover,.auth-card a:hover{text-decoration:underline}
.auth-note{color:#94a3b8;font-size:11px;line-height:1.5}
.auth-message{
  display:none;margin-top:14px;padding:11px 12px;border-radius:11px;
  font-size:12px;line-height:1.45;
}
.auth-message.error{display:block;background:#fef2f2;color:var(--auth-red);border:1px solid #fecaca}
.auth-message.ok{display:block;background:#ecfdf5;color:var(--auth-green);border:1px solid #a7f3d0}
.auth-trust{
  margin-top:18px;
  display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
}
.auth-trust div{
  padding:9px;border-radius:10px;background:#f8fafc;border:1px solid #edf2f7;
  text-align:center;color:#64748b;font-size:9px;font-weight:800;
}
@media(max-width:920px){
  .auth-shell{grid-template-columns:1fr}
  .auth-hero{min-height:300px;padding:32px 26px}
  .auth-hero-copy{margin:34px 0 24px}
  .auth-hero h1{font-size:34px}
  .auth-features{grid-template-columns:1fr 1fr 1fr}
  .auth-panel{min-height:auto;padding:30px 18px 42px}
}
@media(max-width:620px){
  .auth-hero{min-height:270px}
  .auth-hero-copy{margin:28px 0 10px}
  .auth-hero p{font-size:13px}
  .auth-features{display:none}
  .auth-card{padding:24px;border-radius:20px}
  .auth-card h2{font-size:24px}
}
"""


def auth_hero_html(*, title: str, subtitle: str) -> str:
    return f"""
<aside class="auth-hero">
  <div class="auth-brand">
    <div class="auth-brand-mark">IA</div>
    <div><strong>AI Piutang Vouching</strong><span>Internal Audit Command Center</span></div>
  </div>
  <div class="auth-hero-copy">
    <span class="auth-kicker">Secure Internal Audit Workspace</span>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="auth-features">
    <div class="auth-feature"><b>Branch-aware</b><span>Akses mengikuti scope cabang dan role yang diberikan.</span></div>
    <div class="auth-feature"><b>Evidence-driven</b><span>Dokumen, vouching, temuan, dan tindak lanjut dalam satu alur.</span></div>
    <div class="auth-feature"><b>Audit-ready</b><span>Kontrol akses dan aktivitas aplikasi tetap dapat ditelusuri.</span></div>
  </div>
</aside>
"""
