import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.branch_access import scoped_branch, write_branch


def test_global_user_can_filter_reads_to_one_branch_or_all():
    for role in ("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"):
        user = CurrentUser(user_id=role.lower(), role=role, branch=None)
        assert scoped_branch(user) is None
        assert scoped_branch(user, " Pasuruan ") == "PASURUAN"


def test_scoped_user_cannot_request_another_branch():
    auditor = CurrentUser(user_id="aud", role="AUDITOR", branch="Pasuruan")
    assert scoped_branch(auditor) == "PASURUAN"
    assert scoped_branch(auditor, "PASURUAN") == "PASURUAN"
    with pytest.raises(HTTPException) as exc:
        scoped_branch(auditor, "GRESIK")
    assert exc.value.status_code == 403


def test_global_write_requires_resolved_branch_for_all_roles():
    for role in ("ADMIN", "AUDITOR", "REVIEWER"):
        user = CurrentUser(user_id=role.lower(), role=role, branch=None)
        with pytest.raises(HTTPException) as exc:
            write_branch(user)
        assert exc.value.status_code == 400
        assert write_branch(user, "Gresik") == "GRESIK"


def test_scoped_write_is_always_pinned_to_assigned_branch():
    reviewer = CurrentUser(user_id="rev", role="REVIEWER", branch="Kediri")
    assert write_branch(reviewer) == "KEDIRI"
    with pytest.raises(HTTPException) as exc:
        write_branch(reviewer, "Tangerang")
    assert exc.value.status_code == 403


def test_global_user_is_not_pinned_to_a_branch():
    viewer = CurrentUser(user_id="global-viewer", role="VIEWER", branch=None)
    assert scoped_branch(viewer, "GRESIK") == "GRESIK"
    assert scoped_branch(viewer, "TANGERANG") == "TANGERANG"
