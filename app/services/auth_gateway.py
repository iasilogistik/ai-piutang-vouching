from __future__ import annotations

from urllib.parse import urljoin

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

_ALLOWED_LOGIN_ROLES = {"ADMIN", "AUDITOR"}


def _auth_url(path: str) -> str:
    if not settings.supabase_url:
        raise ValueError("Supabase URL is not configured")
    return f"{settings.supabase_url.rstrip('/')}{path}"


def _auth_headers() -> dict[str, str]:
    if not settings.supabase_publishable_key:
        raise ValueError("Supabase publishable key is not configured")
    return {
        "apikey": settings.supabase_publishable_key,
        "Content-Type": "application/json",
    }


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        value = "https://ai-piutang-vouching.vercel.app"
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def password_reset_redirect_url() -> str:
    explicit = (settings.password_reset_redirect_url or "").strip()
    if explicit:
        return _normalize_url(explicit)
    return urljoin(f"{_normalize_url(settings.app_base_url)}/", "reset-password")


def _normalize_session(data: dict[str, object]) -> dict[str, object]:
    user = data.get("user") or {}
    user_id = user.get("id") if isinstance(user, dict) else None
    email = user.get("email") if isinstance(user, dict) else None
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data.get("expires_in"),
        "expires_at": data.get("expires_at"),
        "user": {"id": user_id, "email": email},
    }


def _enforce_admin_or_auditor(session: dict[str, object]) -> dict[str, object]:
    user = session.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    email = user.get("email") if isinstance(user, dict) else None
    if not user_id:
        raise ValueError("Login gagal. User ID tidak diterima dari layanan autentikasi")

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                select role::text as role, branch, coalesce(is_active, true) as is_active
                from public.user_roles
                where user_id::text = cast(:user_id as text)
                   or (cast(:email as text) is not null and lower(email) = lower(cast(:email as text)))
                order by case when user_id::text = cast(:user_id as text) then 0 else 1 end
                limit 1
                """
            ),
            {"user_id": user_id, "email": email},
        ).mappings().one_or_none()

    if row is None:
        raise ValueError("Login ditolak. User belum didaftarkan sebagai ADMIN atau AUDITOR")
    if not row["is_active"]:
        raise ValueError("Login ditolak. User aplikasi berstatus nonaktif")
    if row["role"] not in _ALLOWED_LOGIN_ROLES:
        raise ValueError("Login ditolak. Hanya role ADMIN dan AUDITOR yang dapat login")

    session_user = session.get("user")
    if isinstance(session_user, dict):
        session_user["role"] = row["role"]
        session_user["branch"] = row["branch"]
    return session


def login_with_password(email: str, password: str) -> dict[str, object]:
    email = (email or "").strip()
    if not email or not password:
        raise ValueError("Email dan password wajib diisi")
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                _auth_url("/auth/v1/token?grant_type=password"),
                headers=_auth_headers(),
                json={"email": email, "password": password},
            )
    except httpx.HTTPError as exc:
        raise ValueError("Tidak bisa menghubungi layanan autentikasi") from exc
    if response.status_code != 200:
        raise ValueError("Login gagal. Periksa email, password, atau status akun")
    data = response.json()
    if not data.get("access_token"):
        raise ValueError("Login gagal. Access token tidak diterima")
    return _enforce_admin_or_auditor(_normalize_session(data))


def refresh_access_token(refresh_token: str) -> dict[str, object]:
    token = (refresh_token or "").strip()
    if not token:
        raise ValueError("Refresh token wajib diisi")
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                _auth_url("/auth/v1/token?grant_type=refresh_token"),
                headers=_auth_headers(),
                json={"refresh_token": token},
            )
    except httpx.HTTPError as exc:
        raise ValueError("Tidak bisa refresh token autentikasi") from exc
    if response.status_code != 200:
        raise ValueError("Refresh token tidak valid atau sudah kedaluwarsa")
    data = response.json()
    if not data.get("access_token"):
        raise ValueError("Refresh gagal. Access token tidak diterima")
    return _enforce_admin_or_auditor(_normalize_session(data))


def request_password_reset(email: str) -> dict[str, object]:
    email = (email or "").strip()
    if not email:
        raise ValueError("Email wajib diisi")
    redirect_to = password_reset_redirect_url()
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                _auth_url("/auth/v1/recover"),
                headers=_auth_headers(),
                params={"redirect_to": redirect_to},
                json={"email": email},
            )
    except httpx.HTTPError as exc:
        raise ValueError("Tidak bisa mengirim email reset password") from exc
    if response.status_code not in {200, 204}:
        raise ValueError("Reset password gagal dikirim. Periksa email atau konfigurasi Supabase redirect URL")
    return {"status": "RESET_EMAIL_SENT", "email": email, "redirect_to": redirect_to}


def update_recovery_password(access_token: str, password: str) -> dict[str, object]:
    token = (access_token or "").strip()
    if not token:
        raise ValueError("Access token reset password tidak ditemukan")
    if not password or len(password) < 8:
        raise ValueError("Password baru minimal 8 karakter")
    headers = {**_auth_headers(), "Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.put(
                _auth_url("/auth/v1/user"),
                headers=headers,
                json={"password": password},
            )
    except httpx.HTTPError as exc:
        raise ValueError("Tidak bisa memperbarui password") from exc
    if response.status_code != 200:
        raise ValueError("Password gagal diperbarui. Link reset mungkin sudah kedaluwarsa")
    return {"status": "PASSWORD_UPDATED"}
