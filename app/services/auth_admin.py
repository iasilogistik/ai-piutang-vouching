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


def _raise_supabase_error(response: httpx.Response, default_detail: str) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}
    detail = payload.get("message") or payload.get("error_description") or payload.get("error") or default_detail
    raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=str(detail))


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


def send_password_recovery(email: str) -> dict[str, object]:
    with httpx.Client(timeout=15.0) as client:
        response = client.post(f"{_base_url()}/auth/v1/recover", headers=_publishable_headers(), json={"email": email})
    if response.status_code not in {200, 201, 204}:
        _raise_supabase_error(response, "Failed to send password recovery email")
    return {"status": "PASSWORD_RECOVERY_SENT", "email": email}
