from app.services.auth_theme import auth_hero_html, auth_theme_css


def _register_user_management_once() -> None:
    """Register user-management routes when /login is first opened."""
    try:
        from app.main import app
        from app.services.user_management import register_user_management_routes

        register_user_management_routes(app)
    except Exception:
        return


def login_html() -> str:
    _register_user_management_once()
    html = """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Login - AI Piutang Vouching</title>
  <style>__AUTH_THEME__</style>
</head>
<body class="auth-page">
  <div class="auth-shell">
    __AUTH_HERO__
    <section class="auth-panel">
      <main class="auth-card">
        <span class="auth-badge">Authorized Access</span>
        <h2>Masuk ke Command Center</h2>
        <p class="auth-copy">Gunakan akun aplikasi untuk mengakses dashboard, audit workflow, vouching, evidence, dan monitoring sesuai role Anda. Setelah login, menu sidebar di sebelah kiri tetap tampil saat berpindah halaman.</p>
        <form id="loginForm">
          <label for="email">Email</label>
          <input id="email" type="email" autocomplete="username" placeholder="nama@perusahaan.co.id" required />
          <label for="password">Password</label>
          <input id="password" type="password" autocomplete="current-password" placeholder="Masukkan password" required />
          <button id="loginBtn" class="auth-primary" type="submit">Masuk ke Aplikasi</button>
        </form>
        <div id="message" class="auth-message"></div>
        <div class="auth-links">
          <a href="/forgot-password">Lupa password?</a>
          <span class="auth-note">Menu akan menyesuaikan role &amp; scope cabang.</span>
        </div>
        <div class="auth-trust">
          <div>ROLE BASED</div><div>BRANCH AWARE</div><div>AUDIT TRAIL</div>
        </div>
        <button id="logoutBtn" class="auth-secondary" type="button">Logout / Hapus Sesi Browser</button>
      </main>
    </section>
  </div>
<script>
const form = document.getElementById('loginForm');
const btn = document.getElementById('loginBtn');
const message = document.getElementById('message');
function show(text, ok) { message.textContent = text; message.className = 'auth-message ' + (ok ? 'ok' : 'error'); }
function storeSession(data) {
  localStorage.setItem('auditToken', data.access_token || '');
  if (data.refresh_token) localStorage.setItem('auditRefreshToken', data.refresh_token);
  if (data.expires_at) localStorage.setItem('auditExpiresAt', String(data.expires_at));
  if (data.user) localStorage.setItem('auditUser', JSON.stringify(data.user));
}
function requestedNextPath() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get('next');
  if (!next || !next.startsWith('/') || next.startsWith('//')) return '';
  if (next.startsWith('/ui/') && next !== '/ui/main') {
    return '/ui/main?view=' + encodeURIComponent(next);
  }
  return next;
}
async function resolvePostLoginDestination(accessToken) {
  const next = requestedNextPath();
  if (next) return next;
  try {
    const response = await fetch('/auth/me', { headers: { Authorization: 'Bearer ' + accessToken } });
    const profile = await response.json();
    if (response.ok && profile.role) {
      const role = String(profile.role).toUpperCase();
      if (role === 'REVIEWER') return '/ui/main?view=' + encodeURIComponent('/ui/reviewer-center');
      if (role === 'VIEWER') return '/ui/main?view=' + encodeURIComponent('/ui/viewer-center');
      return '/ui/main';
    }
  } catch (error) {
    return '/ui/main';
  }
  return '/ui/main';
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
    const destination = await resolvePostLoginDestination(body.access_token || localStorage.getItem('auditToken') || '');
    show('Login berhasil. Membuka Command Center...', true);
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
  show('Sesi browser sudah dihapus.', true);
});
</script>
</body>
</html>
"""
    return (
        html.replace("__AUTH_THEME__", auth_theme_css())
        .replace(
            "__AUTH_HERO__",
            auth_hero_html(
                title="Satu workspace untuk seluruh siklus audit piutang.",
                subtitle="Dari upload data hingga vouching, evidence, findings, follow-up, dan monitoring—semuanya berada dalam satu Command Center yang terstruktur.",
            ),
        )
    )
