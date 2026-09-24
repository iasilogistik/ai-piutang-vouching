from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    role: str
    branch: str | None = None


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _verify_token(token: str) -> str:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_publishable_key, "Authorization": f"Bearer {token}"},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    user_id = response.json().get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return str(user_id)


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(_db)) -> CurrentUser:
    if not settings.auth_required:
        return CurrentUser(user_id="development-user", role="ADMIN", branch=None)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer access token required")
    user_id = _verify_token(authorization.split(" ", 1)[1].strip())
    row = db.execute(
        text("select role::text as role, branch, coalesce(is_active, true) as is_active from public.user_roles where user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().one_or_none()
    if row is not None and not row["is_active"]:
        raise HTTPException(status_code=403, detail="Application user is inactive")
    role = row["role"] if row is not None else "VIEWER"
    return CurrentUser(user_id=user_id, role=role, branch=row["branch"] if row is not None else None)


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        # Business rule: AUDITOR is allowed to operate ADMIN-only user/branch
        # maintenance screens, while login is limited to ADMIN and AUDITOR.
        if user.role == "AUDITOR" and "ADMIN" in allowed:
            return user
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient application role")
        return user

    return dependency
