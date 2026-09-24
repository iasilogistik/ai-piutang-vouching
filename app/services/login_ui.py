def _register_user_management_once() -> None:
    """Register user-management routes when /login is first opened.

    This keeps the existing main.py route surface stable while exposing the
    admin screen after the authentication sprint is enabled.
    """
    try:
        from app.main import app
        from app.services.user_management import register_user_management_routes

        register_user_management_routes(app)
    except Exception:
        # The login page must remain available even if optional admin routes fail
        # to register during local development or partial deployments.
        return


def login_html() -> str:
    _register_user_management_once()
    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Login - AI Piutang Vouching</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --red:#b3261e; --green:#188038; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font-family:Arial, Helvetica, sans-serif; background:linear-gradient(145deg,#0f172a 0%,#1e293b 42%,#f6f8fb 42%); color:var(--text); display:flex; align-items:center; justify-content:center; padding:24px; }
    .card { width:100%; max-width:440px; background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 18px 45px rgba(15,23,42,.25); padding:24px; }
    h1 { margin:0; font-size:24px; color:#0f172a; }
    p { color:var(--muted); line-height:1.45; }
    label { display:block; margin-top:14px; margin-bottom:6px; color:var(--muted); font-size:13px; }
    input { width:100%; padding:11px 12px; border:1px solid var(--line); border-radius:10px; font:inherit; }
    button { width:100%; margin-top:18px; padding:12px; border:0; border-radius:10px; background:var(--blue); color:#fff; font-weight:700; cursor:pointer; }
    button:disabled { opacity:.6; cursor:not-allowed; }
    .msg { margin-top:14px; padding:10px; border-radius:10px; font-size:14px; display:none; }
    .err { display:block; background:#fef2f2; color:var(--red); border:1px solid #fecaca; }
    .ok { display:block; background:#f0fdf4; color:var(--green); border:1px solid #bbf7d0; }
    .hint { font-size:12px; color:var(--muted); margin-top:12px; }
  </style>
</head>
<body>
  <main class="card">
    <h1>AI Piutang Vouching</h1>
    <p>Login khusus role ADMIN dan AUDITOR. Setelah login berhasil, sistem akan langsung mengarahkan ke halaman kerja sesuai role.</p>
    <form id="loginForm">
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" placeholder="nama@perusahaan.co.id" required />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" placeholder="Password" required />
      <button id="loginBtn" type="submit">Login</button>
    </form>
    <div id="message" class="msg"></div>
    <p class="hint">Halaman ini hanya untuk login. Menu aplikasi akan muncul setelah masuk ke halaman tujuan.</p>
    <button id="logoutBtn" type="button" style="background:#475569;">Logout / Hapus Token Browser</button>
  </main>
<script>
const form = document.getElementById('loginForm');
const btn = document.getElementById('loginBtn');
const message = document.getElementById('message');
function show(text, ok) { message.textContent = text; message.className = `msg ${ok ? 'ok' : 'err'}`; }
function storeSession(data) {
  localStorage.setItem('auditToken', data.access_token || '');
  if (data.refresh_token) localStorage.setItem('auditRefreshToken', data.refresh_token);
  if (data.expires_at) localStorage.setItem('auditExpiresAt', String(data.expires_at));
  if (data.user) localStorage.setItem('auditUser', JSON.stringify(data.user));
}
async function resolvePostLoginDestination(accessToken) {
  if (!accessToken) return '/ui/users';
  try {
    const response = await fetch('/auth/me', { headers:{ Authorization:`Bearer ${accessToken}` } });
    if (!response.ok) return '/ui/users';
    const profile = await response.json();
    if (profile.role === 'ADMIN' || profile.role === 'AUDITOR') return '/ui/users';
    return '/login';
  } catch {
    return '/ui/users';
  }
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  btn.disabled = true;
  show('Memproses login...', true);
  try {
    const payload = new FormData();
    payload.append('email', document.getElementById('email').value.trim());
    payload.append('password', document.getElementById('password').value);
    const response = await fetch('/auth/login', { method:'POST', body:payload });
    const text = await response.text();
    let body; try { body = JSON.parse(text); } catch { body = text; }
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    storeSession(body);
    const destination = await resolvePostLoginDestination(body.access_token || '');
    show(`Login berhasil. Mengarahkan ke ${destination}...`, true);
    window.location.replace(destination);
  } catch (error) {
    show(error.message || 'Login gagal.', false);
  } finally {
    btn.disabled = false;
  }
});
document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.removeItem('auditToken');
  localStorage.removeItem('auditRefreshToken');
  localStorage.removeItem('auditExpiresAt');
  localStorage.removeItem('auditUser');
  show('Token browser sudah dihapus.', true);
});
</script>
</body>
</html>
"""
