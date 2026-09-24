from fastapi import HTTPException
import pytest

from app.auth import CurrentUser, require_roles


class _URL:
    def __init__(self, path: str):
        self.path = path


class _Request:
    def __init__(self, path: str = "/admin/users", method: str = "GET"):
        self.url = _URL(path)
        self.method = method


def test_role_dependency_allows_authorized_role():
    dependency = require_roles("ADMIN", "AUDITOR")
    user = CurrentUser(user_id="u1", role="AUDITOR")
    assert dependency(_Request("/ui/uat-pasuruan"), user) == user


def test_auditor_can_access_user_maintenance_dependency():
    dependency = require_roles("ADMIN")
    user = CurrentUser(user_id="u1", role="AUDITOR")
    assert dependency(_Request("/admin/users", "POST"), user) == user


def test_auditor_cannot_access_admin_branch_mutation_dependency():
    dependency = require_roles("ADMIN")
    with pytest.raises(HTTPException) as exc:
        dependency(_Request("/admin/branches", "POST"), CurrentUser(user_id="u1", role="AUDITOR"))
    assert exc.value.status_code == 403


def test_role_dependency_rejects_unauthorized_role():
    dependency = require_roles("ADMIN", "AUDITOR")
    with pytest.raises(HTTPException) as exc:
        dependency(_Request("/ui/uat-pasuruan"), CurrentUser(user_id="u1", role="VIEWER"))
    assert exc.value.status_code == 403
