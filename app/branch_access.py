from __future__ import annotations

from fastapi import HTTPException

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
