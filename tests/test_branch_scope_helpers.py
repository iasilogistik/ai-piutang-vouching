import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.branch_access import scoped_branch, write_branch


def test_admin_can_filter_reads_to_one_branch_or_all():
    admin = CurrentUser(user_id="admin", role="ADMIN", branch=None)
    assert scoped_branch(admin) is None
    assert scoped_branch(admin, " Pasuruan ") == "PASURUAN"


def test_scoped_user_cannot_request_another_branch():
    auditor = CurrentUser(user_id="aud", role="AUDITOR", branch="Pasuruan")
    assert scoped_branch(auditor) == "PASURUAN"
    assert scoped_branch(auditor, "PASURUAN") == "PASURUAN"
    with pytest.raises(HTTPException) as exc:
        scoped_branch(auditor, "GRESIK")
    assert exc.value.status_code == 403


def test_admin_write_requires_branch_when_no_default_is_assigned():
    admin = CurrentUser(user_id="admin", role="ADMIN", branch=None)
    with pytest.raises(HTTPException) as exc:
        write_branch(admin)
    assert exc.value.status_code == 400
    assert write_branch(admin, "Gresik") == "GRESIK"


def test_scoped_write_is_always_pinned_to_assigned_branch():
    reviewer = CurrentUser(user_id="rev", role="REVIEWER", branch="Kediri")
    assert write_branch(reviewer) == "KEDIRI"
    with pytest.raises(HTTPException) as exc:
        write_branch(reviewer, "Tangerang")
    assert exc.value.status_code == 403
