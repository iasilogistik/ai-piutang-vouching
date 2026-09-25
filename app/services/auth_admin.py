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
    return str(payload.get("message") or payload.get("error_description") or payload.get("error") or default_detail)


def _raise_supabase_error(response: httpx.Response, default_detail: str) -> None:
    detail = _error_detail(response, default_detail)
    raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=detail)


def create_auth_user(*, email: str, password: str, display_name: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": email,
        "password": password,
        "email_confirm": True,
    }
    if display_name:
        payload["user_metadata"] = {"display_name": display_name}
    with httpx.Client(timeout=15.0) as client:
        response = client.post(f"{_base_url()}/auth/v1/admin/users", headers=_service_headers(), json=payload)
    if response.status_code not in {200, 201}:
        _raise_supabase_error(response, "Failed to create Supabase Auth user")
    body = response.json()
    user_id = body.get("id")
    if not user_id:
        raise HTTPException(status_code=502, detail="Supabase Auth did not return a user id")
    return {"status": "CREATED", "user_id": str(user_id), "email": body.get("email") or email}


def update_auth_user_password(*, user_id: str, password: str, email: str | None = None,
                              display_name: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"password": password}
    if email:
        payload["email"] = email
    if display_name:
        payload["user_metadata"] = {"display_name": display_name}
    with httpx.Client(timeout=15.0) as client:
        response = client.put(f"{_base_url()}/auth/v1/admin/users/{user_id}", headers=_service_headers(), json=payload)
    if response.status_code not in {200, 201}:
        _raise_supabase_error(response, "Failed to update Supabase Auth password")
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
