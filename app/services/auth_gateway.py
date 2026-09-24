from __future__ import annotations

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
    if not user_id:
        raise ValueError("Login gagal. User ID tidak diterima dari layanan autentikasi")

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                select role::text as role, branch, coalesce(is_active, true) as is_active
                from public.user_roles
                where user_id = :user_id
                """
            ),
            {"user_id": user_id},
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
