from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import CurrentUser


def normalize_branch(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split()).upper()
    return normalized or None


def scoped_branch(user: CurrentUser) -> str | None:
    """Return the branch filter for reads. ADMIN has global read scope."""
    if user.role == "ADMIN":
        return None
    branch = normalize_branch(user.branch)
    if not branch:
        raise HTTPException(status_code=403, detail="Application user has no branch assignment")
    return branch


def ensure_branch_access(user: CurrentUser, resource_branch: str | None) -> None:
    """Hide resources outside the caller branch to avoid cross-branch enumeration."""
    if user.role == "ADMIN":
        return
    expected = scoped_branch(user)
    if normalize_branch(resource_branch) != expected:
        raise HTTPException(status_code=404, detail="Resource not found")


def branch_for_actor(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    value = db.execute(
        text("select branch from public.user_roles where user_id::text = :user_id"),
        {"user_id": user_id},
    ).scalar_one_or_none()
    return normalize_branch(value)
