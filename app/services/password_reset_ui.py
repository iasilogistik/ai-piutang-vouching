from __future__ import annotations

from fastapi import APIRouter, Form, Header, HTTPException
from fastapi.responses import HTMLResponse

from app.services.auth_gateway import password_reset_redirect_url, request_password_reset, update_recovery_password

router = APIRouter()
_REGISTERED = False


def forgot_password_html() -> str:
    redirect_to = password_reset_redirect_url()
    return f"""
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lupa Password - AI Piutang Vouching</title>
  <style>
    :root {{ --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --red:#b3261e; --green:#188038; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; font-family:Arial, Helvetica, sans-serif; background:linear-gradient(145deg,#0f172a 0%,#1e293b 42%,#f6f8fb 42%); color:var(--text); display:flex; align-items:center; justify-content:center; padding:24px; }}
    .card {{ width:100%; max-width:460px; background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 18px 45px rgba(15,23,42,.25); padding:24px; }}
    h1 {{ margin:0; font-size:24px; color:#0f172a; }}
    p {{ color:var(--muted); line-height:1.45; }}
    label {{ display:block; margin-top:14px; margin-bottom:6px; color:var(--muted); font-size:13px; }}
    input {{ width:100%; padding:11px 12px; border:1px solid var(--line); border-radius:10px; font:inherit; }}
    button {{ width:100%; margin-top:18px; padding:12px; border:0; border-radius:10px; background:var(--blue); color:#fff; font-weight:700; cursor:pointer; }}
    a {{ color:var(--blue); font-weight:700; text-decoration:none; }}
    .msg {{ margin-top:14px; padding:10px; border-radius:10px; font-size:14px; display:none; }}
    .err {{ display:block; background:#fef2f2; color:var(--red); border:1px solid #fecaca; }}
    .ok {{ display:block; background:#f0fdf4; color:var(--green); border:1px solid #bbf7d0; }}
    .hint {{ font-size:12px; color:var(--muted); margin-top:12px; word-break:break-word; }}
  </style>
</head>
<body>
  <main class="card">
    <h1>Lupa Password</h1>
    <p>Masukkan email akun. Sistem akan mengirim link reset password yang kembali ke halaman produksi, bukan localhost.</p>
    <form id="forgotForm">
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" placeholder="nama@perusahaan.co.id" required />
      <button id="sendBtn" type="submit">Kirim Link Reset Password</button>
    </form>
    <div id="message" class="msg"></div>
    <p class="hint">Redirect reset password: {redirect_to}</p>
    <p><a href="/login">Kembali ke Login</a></p>
  </main>
<script>
const form = document.getElementById('forgotForm');
const btn = document.getElementById('sendBtn');
const message = document.getElementById('message');
function show(text, ok) {{ message.textContent = text; message.className = `msg ${{ok ? 'ok' : 'err'}}`; }}
form.addEventListener('submit', async (event) => {{
  event.preventDefault();
  btn.disabled = true;
  show('Mengirim email reset password...', true);
  try {{
    const payload = new FormData();
    payload.append('email', document.getElementById('email').value.trim());
    const response = await fetch('/auth/password-reset-request', {{ method:'POST', body:payload }});
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    show('Email reset password sudah dikirim. Buka email terbaru, bukan email lama yang masih mengarah ke localhost.', true);
  }} catch (error) {{
    show(error.message || 'Gagal mengirim reset password.', false);
  }} finally {{
    btn.disabled = false;
  }}
}});
</script>
</body>
</html>
"""


def reset_password_html() -> str:
    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reset Password - AI Piutang Vouching</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --red:#b3261e; --green:#188038; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font-family:Arial, Helvetica, sans-serif; background:linear-gradient(145deg,#0f172a 0%,#1e293b 42%,#f6f8fb 42%); color:var(--text); display:flex; align-items:center; justify-content:center; padding:24px; }
    .card { width:100%; max-width:460px; background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 18px 45px rgba(15,23,42,.25); padding:24px; }
    h1 { margin:0; font-size:24px; color:#0f172a; }
    p { color:var(--muted); line-height:1.45; }
    label { display:block; margin-top:14px; margin-bottom:6px; color:var(--muted); font-size:13px; }
    input { width:100%; padding:11px 12px; border:1px solid var(--line); border-radius:10px; font:inherit; }
    button { width:100%; margin-top:18px; padding:12px; border:0; border-radius:10px; background:var(--blue); color:#fff; font-weight:700; cursor:pointer; }
    a { color:var(--blue); font-weight:700; text-decoration:none; }
    .msg { margin-top:14px; padding:10px; border-radius:10px; font-size:14px; display:none; }
    .err { display:block; background:#fef2f2; color:var(--red); border:1px solid #fecaca; }
    .ok { display:block; background:#f0fdf4; color:var(--green); border:1px solid #bbf7d0; }
    .hint { font-size:12px; color:var(--muted); margin-top:12px; word-break:break-word; }
  </style>
</head>
<body>
  <main class="card">
    <h1>Reset Password</h1>
    <p>Buat password baru. Link dari email reset password akan dibaca otomatis dari URL.</p>
    <form id="resetForm">
      <label for="password">Password Baru</label>
      <input id="password" type="password" autocomplete="new-password" placeholder="Minimal 8 karakter" minlength="8" required />
      <label for="confirmPassword">Ulangi Password Baru</label>
      <input id="confirmPassword" type="password" autocomplete="new-password" placeholder="Ulangi password" minlength="8" required />
      <button id="resetBtn" type="submit">Simpan Password Baru</button>
    </form>
    <div id="message" class="msg"></div>
    <p class="hint" id="tokenHint">Membaca token reset password...</p>
    <p><a href="/login">Kembali ke Login</a></p>
  </main>
<script>
const form = document.getElementById('resetForm');
const btn = document.getElementById('resetBtn');
const message = document.getElementById('message');
const tokenHint = document.getElementById('tokenHint');
function show(text, ok) { message.textContent = text; message.className = `msg ${ok ? 'ok' : 'err'}`; }
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
  tokenHint.textContent = 'Token reset password tidak ditemukan. Minta link reset password baru dari halaman Lupa Password.';
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
