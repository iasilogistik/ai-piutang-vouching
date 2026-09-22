from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.database import SessionLocal
from app.models import AuditNotification

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

_MENU = {
    "ADMIN": [
        ("Dashboard", "/ui/dashboard"),
        ("Audit Management", "/ui/audit-management"),
        ("Engagements", "/ui/audit-engagements"),
        ("Sampling", "/ui/audit-sampling"),
        ("Working Papers", "/ui/audit-working-papers"),
        ("Findings", "/ui/audit-findings"),
        ("Management Actions", "/ui/management-actions"),
        ("Follow-up", "/ui/follow-up"),
        ("Upload", "/ui/upload"),
        ("Vouching", "/ui/uat-pasuruan"),
        ("Workflow", "/ui/audit-workflow"),
        ("Control Evidence", "/ui/control-evidence"),
        ("Exceptions", "/ui/exceptions"),
        ("Review Queue", "/ui/review-queue"),
        ("Audit Trail", "/ui/audit-trail"),
        ("Reports", "/ui/audit-reports"),
        ("Closing", "/ui/audit-closing"),
        ("Users", "/ui/users"),
        ("Branches", "/ui/branches"),
    ],
    "AUDITOR": [
        ("Dashboard", "/ui/dashboard"),
        ("Audit Management", "/ui/audit-management"),
        ("Engagements", "/ui/audit-engagements"),
        ("Sampling", "/ui/audit-sampling"),
        ("Working Papers", "/ui/audit-working-papers"),
        ("Findings", "/ui/audit-findings"),
        ("Management Actions", "/ui/management-actions"),
        ("Follow-up", "/ui/follow-up"),
        ("Upload", "/ui/upload"),
        ("Vouching", "/ui/uat-pasuruan"),
        ("Workflow", "/ui/audit-workflow"),
        ("Evidence", "/ui/control-evidence"),
        ("Exceptions", "/ui/exceptions"),
        ("Review Queue", "/ui/review-queue"),
        ("Audit Trail", "/ui/audit-trail"),
        ("Reports", "/ui/audit-reports"),
        ("Closing", "/ui/audit-closing"),
    ],
    "REVIEWER": [
        ("Dashboard", "/ui/dashboard"),
        ("Audit Management", "/ui/audit-management"),
        ("Engagements", "/ui/audit-engagements"),
        ("Sampling", "/ui/audit-sampling"),
        ("Working Papers", "/ui/audit-working-papers"),
        ("Findings", "/ui/audit-findings"),
        ("Management Actions", "/ui/management-actions"),
        ("Follow-up", "/ui/follow-up"),
        ("Workflow", "/ui/audit-workflow"),
        ("Review Queue", "/ui/review-queue"),
        ("Evidence", "/ui/control-evidence"),
        ("Exceptions", "/ui/exceptions"),
        ("Reports", "/ui/audit-reports"),
        ("Closing", "/ui/audit-closing"),
    ],
    "VIEWER": [
        ("Dashboard", "/ui/dashboard"),
        ("Audit Management", "/ui/audit-management"),
        ("Engagements", "/ui/audit-engagements"),
        ("Sampling", "/ui/audit-sampling"),
        ("Working Papers", "/ui/audit-working-papers"),
        ("Findings", "/ui/audit-findings"),
        ("Management Actions", "/ui/management-actions"),
        ("Follow-up", "/ui/follow-up"),
        ("Workflow", "/ui/audit-workflow"),
        ("Reports", "/ui/audit-reports"),
        ("Evidence", "/ui/control-evidence"),
    ],
}


def menu_for_role(role: str) -> list[dict[str, str]]:
    normalized = (role or "").strip().upper()
    return [{"label": label, "href": href} for label, href in _MENU.get(normalized, [])]


def navigation_html(user: CurrentUser, unread_count: int = 0) -> str:
    links = "".join(
        f'<a href="{escape(item["href"])}">{escape(item["label"])}</a>'
        for item in menu_for_role(user.role)
    )
    branch = escape(user.branch or "ALL")
    role = escape(user.role)
    return (
        f'<nav class="role-nav" data-role="{role}" data-branch="{branch}">'
        f'<span class="role-context">{role} · {branch}</span>'
        f'<a href="/ui/notifications" class="notification-link">Notifications ({unread_count})</a>'
        f'{links}</nav>'
    )


@router.get("/ui/navigation", response_class=HTMLResponse)
def role_navigation(
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    count = int(
        db.scalar(
            select(func.count(AuditNotification.id)).where(
                AuditNotification.user_id == user.user_id,
                AuditNotification.is_read.is_(False),
            )
        )
        or 0
    )
    return HTMLResponse(navigation_html(user, count))


def register_navigation_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
