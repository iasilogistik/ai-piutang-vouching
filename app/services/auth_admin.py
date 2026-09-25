from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config import settings


def _base_url() -> str:
    if not settings.supabase_url:
        raise HTTPException(status_code=503, detail="SUPABASE_URL is not configured")
    return settings.supabase_url.rstrip("/")


def _service_headers() -> dict[str, str]:
    if not settings.supabase_secret_key:
        raise HTTPException(status_code=503, detail="SUPABASE_SECRET_KEY is required to create users or set passwords")
    return {
        "apikey": settings.supabase_secret_key,
        "Authorization": f"Bearer {settings.supabase_secret_key}",
        "Content-Type": "application/json",
    }


def _publishable_headers() -> dict[str, str]:
    if not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="SUPABASE_PUBLISHABLE_KEY is required to send forgot-password email")
    return {
        "apikey": settings.supabase_publishable_key,
        "Content-Type": "application/json",
    }


def _error_detail(response: httpx.Response, default_detail: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}
    for key in ("message", "msg", "error_description", "error", "detail", "code"):
        value = payload.get(key)
        if value:
            return str(value)
    if payload:
        return f"{default_detail}: {payload}"
    return default_detail


def _raise_supabase_error(response: httpx.Response, default_detail: str) -> None:
    detail = _error_detail(response, default_detail)
    raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=detail)


def _app_role_only_result(*, email: str, status: str, detail: str, user_id: str | None = None) -> dict[str, object]:
    """Return a controlled fallback when Supabase Auth admin API is unavailable.

    User Management should still be able to save the application role/cabang so
    an ADMIN can continue setup. Login will work when the Supabase Auth user is
    created separately or when the service-role key is fixed and password reset
    is run again.
    """
    return {
        "status": status,
        "user_id": user_id or email,
        "email": email,
        "warning": (
            "Role aplikasi berhasil disimpan, tetapi akun/password Supabase Auth "
            "belum berhasil dibuat atau diubah. Periksa SUPABASE_SECRET_KEY/service_role "
            "di Vercel atau buat user tersebut di Supabase Auth, lalu lakukan reset password."
        ),
        "detail": detail,
    }


def create_auth_user(*, email: str, password: str, display_name: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": email,
        "password": password,
        "email_confirm": True,
    }
    if display_name:
        payload["user_metadata"] = {"display_name": display_name}
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(f"{_base_url()}/auth/v1/admin/users", headers=_service_headers(), json=payload)
    except HTTPException as exc:
        return _app_role_only_result(email=email, status="AUTH_CREATE_FAILED_APP_ROLE_SAVED", detail=str(exc.detail))
    except httpx.HTTPError as exc:
        return _app_role_only_result(email=email, status="AUTH_CREATE_FAILED_APP_ROLE_SAVED", detail=str(exc))
    if response.status_code not in {200, 201}:
        detail = _error_detail(response, "Failed to create Supabase Auth user")
        return _app_role_only_result(email=email, status="AUTH_CREATE_FAILED_APP_ROLE_SAVED", detail=detail)
    body = response.json()
    user_id = body.get("id")
    if not user_id:
        return _app_role_only_result(
            email=email,
            status="AUTH_CREATE_FAILED_APP_ROLE_SAVED",
            detail="Supabase Auth did not return a user id",
        )
    return {"status": "CREATED", "user_id": str(user_id), "email": body.get("email") or email}


def update_auth_user_password(*, user_id: str, password: str, email: str | None = None,
                              display_name: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"password": password}
    if email:
        payload["email"] = email
    if display_name:
        payload["user_metadata"] = {"display_name": display_name}
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.put(f"{_base_url()}/auth/v1/admin/users/{user_id}", headers=_service_headers(), json=payload)
    except HTTPException as exc:
        return _app_role_only_result(
            email=email or user_id,
            user_id=user_id,
            status="PASSWORD_UPDATE_FAILED_APP_ROLE_SAVED",
            detail=str(exc.detail),
        )
    except httpx.HTTPError as exc:
        return _app_role_only_result(
            email=email or user_id,
            user_id=user_id,
            status="PASSWORD_UPDATE_FAILED_APP_ROLE_SAVED",
            detail=str(exc),
        )
    if response.status_code not in {200, 201}:
        detail = _error_detail(response, "Failed to update Supabase Auth password")
        return _app_role_only_result(
            email=email or user_id,
            user_id=user_id,
            status="PASSWORD_UPDATE_FAILED_APP_ROLE_SAVED",
            detail=detail,
        )
    body = response.json()
    return {"status": "PASSWORD_UPDATED", "user_id": str(body.get("id") or user_id), "email": body.get("email") or email}


def _generate_recovery_link(email: str, email_error: str | None = None) -> dict[str, object]:
    """Create a manual recovery link when Supabase email delivery is unavailable.

    This keeps the ADMIN action usable even when SMTP/email templates are not yet
    configured in Supabase. The link is returned only to an authenticated ADMIN
    through the existing User Management action log.
    """
    payload = {"type": "recovery", "email": email}
    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            f"{_base_url()}/auth/v1/admin/generate_link",
            headers=_service_headers(),
            json=payload,
        )
    if response.status_code not in {200, 201}:
        link_error = _error_detail(response, "Failed to create password recovery link")
        combined = (
            "Email reset password gagal dikirim dan recovery link manual gagal dibuat. "
            f"Detail email: {email_error or 'tidak tersedia'}. Detail link: {link_error}. "
            "Gunakan kolom Password Sementara / Password Baru pada form user, lalu klik Simpan User."
        )
        raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=combined)
    body = response.json()
    recovery_link = body.get("action_link") or body.get("actionLink") or body.get("properties", {}).get("action_link")
    return {
        "status": "PASSWORD_RECOVERY_LINK_CREATED",
        "email": email,
        "delivery": "manual_link",
        "message": "Email reset password gagal dikirim, sehingga sistem membuat recovery link manual untuk ADMIN.",
        "email_error": email_error,
        "recovery_link": recovery_link,
    }


def send_password_recovery(email: str) -> dict[str, object]:
    """Send password recovery email, with a controlled fallback.

    In production, Supabase can reject `/recover` when SMTP is not configured or
    the email template cannot be sent. Previously that surfaced as a red
    "Failed to send password recovery email" message in the ADMIN UI. The
    fallback below creates a manual recovery link using the service role so the
    ADMIN still has an actionable password-reset path.
    """
    email_error: str | None = None
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(f"{_base_url()}/auth/v1/recover", headers=_publishable_headers(), json={"email": email})
        if response.status_code in {200, 201, 204}:
            return {"status": "PASSWORD_RECOVERY_SENT", "email": email, "delivery": "email"}
        email_error = _error_detail(response, "Failed to send password recovery email")
    except HTTPException as exc:
        email_error = str(exc.detail)
    except httpx.HTTPError as exc:
        email_error = str(exc)

    return _generate_recovery_link(email, email_error=email_error)
