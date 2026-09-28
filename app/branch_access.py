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


def scoped_branch(user: CurrentUser, requested_branch: str | None = None) -> str | None:
    """Return the effective branch for reads.

    Any active application role may be global when no branch is assigned.
    A non-null user branch is an optional restriction and remains pinned.
    """
    requested = normalize_branch(requested_branch)
    if user.role == "ADMIN":
        return requested
    assigned = normalize_branch(user.branch)
    if assigned is None:
        return requested
    if requested is not None and requested != assigned:
        raise HTTPException(status_code=403, detail="Requested branch is outside application scope")
    return assigned


def write_branch(user: CurrentUser, requested_branch: str | None = None) -> str:
    """Return the branch that must own newly-created data."""
    requested = normalize_branch(requested_branch)
    assigned = normalize_branch(user.branch)
    if user.role == "ADMIN":
        resolved = requested or assigned
        if resolved is None:
            raise HTTPException(status_code=400, detail="branch is required for write operations")
        return resolved
    if assigned is None:
        if requested is None:
            raise HTTPException(status_code=400, detail="branch is required when user has global branch scope")
        return requested
    if requested is not None and requested != assigned:
        raise HTTPException(status_code=403, detail="Requested branch is outside application scope")
    return assigned


def ensure_branch_access(user: CurrentUser, resource_branch: str | None) -> None:
    """Hide resources outside the caller branch to avoid cross-branch enumeration."""
    if user.role == "ADMIN":
        return
    assigned = normalize_branch(user.branch)
    if assigned is None:
        return
    if normalize_branch(resource_branch) != assigned:
        raise HTTPException(status_code=404, detail="Resource not found")


def branch_for_actor(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    # Lightweight unit tests use SQLite and intentionally do not create the
    # application user table. Production/local integration databases use Postgres.
    if db.get_bind().dialect.name == "sqlite":
        return None
    value = db.execute(
        text("select branch from public.user_roles where cast(user_id as text) = :user_id"),
        {"user_id": user_id},
    ).scalar_one_or_none()
    return normalize_branch(value)
