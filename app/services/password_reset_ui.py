from __future__ import annotations

from fastapi import APIRouter, Form, Header, HTTPException
from fastapi.responses import HTMLResponse

from app.services.auth_gateway import password_reset_redirect_url, request_password_reset, update_recovery_password
from app.services.auth_theme import auth_hero_html, auth_theme_css

router = APIRouter()
_REGISTERED = False


def forgot_password_html() -> str:
    redirect_to = password_reset_redirect_url()
    html = """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lupa Password - AI Piutang Vouching</title>
  <style>__AUTH_THEME__</style>
</head>
<body class="auth-page">
  <div class="auth-shell">
    __AUTH_HERO__
    <section class="auth-panel">
      <main class="auth-card">
        <span class="auth-badge">Account Recovery</span>
        <h2>Lupa Password</h2>
        <p class="auth-copy">Masukkan email akun. Sistem akan mengirim link reset password ke email Anda dan mengarahkan kembali ke aplikasi production.</p>
        <form id="forgotForm">
          <label for="email">Email</label>
          <input id="email" type="email" autocomplete="username" placeholder="nama@perusahaan.co.id" required />
          <button id="sendBtn" class="auth-primary" type="submit">Kirim Link Reset Password</button>
        </form>
        <div id="message" class="auth-message"></div>
        <div class="auth-links">
          <a href="/login">Kembali ke Login</a>
          <span class="auth-note">Redirect: __REDIRECT_TO__</span>
        </div>
      </main>
    </section>
  </div>
<script>
const form = document.getElementById('forgotForm');
const btn = document.getElementById('sendBtn');
const message = document.getElementById('message');
function show(text, ok) { message.textContent = text; message.className = 'auth-message ' + (ok ? 'ok' : 'error'); }
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  btn.disabled = true;
  show('Mengirim email reset password...', true);
  try {
    const payload = new FormData();
    payload.append('email', document.getElementById('email').value.trim());
    const response = await fetch('/auth/password-reset-request', { method:'POST', body:payload });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    show('Email reset password sudah dikirim. Gunakan email terbaru yang Anda terima.', true);
  } catch (error) {
    show(error.message || 'Gagal mengirim reset password.', false);
  } finally {
    btn.disabled = false;
  }
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
                title="Pulihkan akses tanpa keluar dari alur kerja audit.",
                subtitle="Recovery akun tetap menggunakan jalur autentikasi resmi dan kembali ke aplikasi production.",
            ),
        )
        .replace("__REDIRECT_TO__", redirect_to)
    )


def reset_password_html() -> str:
    html = """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reset Password - AI Piutang Vouching</title>
  <style>__AUTH_THEME__</style>
</head>
<body class="auth-page">
  <div class="auth-shell">
    __AUTH_HERO__
    <section class="auth-panel">
      <main class="auth-card">
        <span class="auth-badge">Secure Password Update</span>
        <h2>Buat Password Baru</h2>
        <p class="auth-copy">Masukkan password baru minimal 8 karakter. Token recovery dibaca otomatis dari link email Anda.</p>
        <form id="resetForm">
          <label for="password">Password Baru</label>
          <input id="password" type="password" autocomplete="new-password" placeholder="Minimal 8 karakter" minlength="8" required />
          <label for="confirmPassword">Ulangi Password Baru</label>
          <input id="confirmPassword" type="password" autocomplete="new-password" placeholder="Ulangi password" minlength="8" required />
          <button id="resetBtn" class="auth-primary" type="submit">Simpan Password Baru</button>
        </form>
        <div id="message" class="auth-message"></div>
        <div class="auth-links">
          <a href="/login">Kembali ke Login</a>
          <span class="auth-note" id="tokenHint">Membaca token reset password...</span>
        </div>
      </main>
    </section>
  </div>
<script>
const form = document.getElementById('resetForm');
const btn = document.getElementById('resetBtn');
const message = document.getElementById('message');
const tokenHint = document.getElementById('tokenHint');
function show(text, ok) { message.textContent = text; message.className = 'auth-message ' + (ok ? 'ok' : 'error'); }
function paramsFromUrl() {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const query = new URLSearchParams(window.location.search.replace(/^\?/, ''));
  return { accessToken: hash.get('access_token') || query.get('access_token'), error: hash.get('error_description') || query.get('error_description') };
}
const resetParams = paramsFromUrl();
if (resetParams.error) {
  tokenHint.textContent = resetParams.error;
  show(resetParams.error, false);
} else if (resetParams.accessToken) {
  tokenHint.textContent = 'Token reset password berhasil dibaca.';
} else {
  tokenHint.textContent = 'Token reset password tidak ditemukan. Minta link reset password baru.';
  show('Token reset password tidak ditemukan atau link sudah kedaluwarsa.', false);
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const password = document.getElementById('password').value;
  const confirmPassword = document.getElementById('confirmPassword').value;
  if (password !== confirmPassword) { show('Konfirmasi password tidak sama.', false); return; }
  if (!resetParams.accessToken) { show('Token reset password tidak ditemukan.', false); return; }
  btn.disabled = true;
  show('Menyimpan password baru...', true);
  try {
    const payload = new FormData();
    payload.append('password', password);
    payload.append('access_token', resetParams.accessToken);
    const response = await fetch('/auth/password-update', { method:'POST', body:payload });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    localStorage.removeItem('auditToken');
    localStorage.removeItem('auditRefreshToken');
    show('Password berhasil diperbarui. Silakan login menggunakan password baru.', true);
  } catch (error) {
    show(error.message || 'Password gagal diperbarui.', false);
  } finally {
    btn.disabled = false;
  }
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
                title="Perbarui kredensial dan kembali ke Command Center.",
                subtitle="Password recovery tetap terintegrasi dengan alur autentikasi aplikasi tanpa mengubah role maupun scope cabang.",
            ),
        )
    )


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_ui():
    return HTMLResponse(forgot_password_html())


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_ui():
    return HTMLResponse(reset_password_html())


@router.post("/auth/password-reset-request")
def password_reset_request(email: str = Form(...)):
    try:
        return request_password_reset(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/password-update")
def password_update(password: str = Form(...), access_token: str | None = Form(None), authorization: str | None = Header(default=None)):
    token = (access_token or "").strip()
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Access token reset password tidak ditemukan")
    try:
        return update_recovery_password(token, password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def register_password_reset_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
