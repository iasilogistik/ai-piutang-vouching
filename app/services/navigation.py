from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.auth import CurrentUser, require_roles

router = APIRouter()
_REGISTERED = False

_MENU = {
    "ADMIN": [
        ("Dashboard", "/ui/dashboard"),
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
        ("Workflow", "/ui/audit-workflow"),
        ("Review Queue", "/ui/review-queue"),
        ("Evidence", "/ui/control-evidence"),
        ("Exceptions", "/ui/exceptions"),
        ("Reports", "/ui/audit-reports"),
        ("Closing", "/ui/audit-closing"),
    ],
    "VIEWER": [
        ("Dashboard", "/ui/dashboard"),
        ("Workflow", "/ui/audit-workflow"),
        ("Reports", "/ui/audit-reports"),
        ("Evidence", "/ui/control-evidence"),
    ],
}


def menu_for_role(role: str) -> list[dict[str, str]]:
    normalized = (role or "").strip().upper()
    return [{"label": label, "href": href} for label, href in _MENU.get(normalized, [])]


def navigation_html(user: CurrentUser) -> str:
    links = "".join(
        f'<a href="{escape(item["href"])}">{escape(item["label"])}</a>'
        for item in menu_for_role(user.role)
    )
    branch = escape(user.branch or "ALL")
    role = escape(user.role)
    return (
        f'<nav class="role-nav" data-role="{role}" data-branch="{branch}">'
        f'<span class="role-context">{role} · {branch}</span>{links}</nav>'
    )


@router.get("/ui/navigation", response_class=HTMLResponse)
def role_navigation(
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return HTMLResponse(navigation_html(user))


def register_navigation_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
