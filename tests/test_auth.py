from fastapi import HTTPException
import pytest

from app.auth import CurrentUser, require_roles


def test_role_dependency_allows_authorized_role():
    dependency = require_roles("ADMIN", "AUDITOR")
    user = CurrentUser(user_id="u1", role="AUDITOR")
    assert dependency(user) == user


def test_role_dependency_rejects_unauthorized_role():
    dependency = require_roles("ADMIN", "AUDITOR")
    with pytest.raises(HTTPException) as exc:
        dependency(CurrentUser(user_id="u1", role="VIEWER"))
    assert exc.value.status_code == 403
