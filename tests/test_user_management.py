from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _ensure_branch(code: str, name: str | None = None) -> None:
    response = client.post(
        "/admin/branches",
        data={"branch_code": code, "branch_name": name or code, "active": "true"},
    )
    assert response.status_code in {200, 409}


def _bootstrap_user_routes() -> None:
    response = client.get("/login")
    assert response.status_code == 200


def test_login_page_hides_application_shortcuts():
    response = client.get("/login")

    assert response.status_code == 200
    assert "User Management" not in response.text
    assert 'href="/ui/users"' not in response.text
    assert "Buka UAT Pasuruan" not in response.text
    assert "Buka Control Evidence Dashboard" not in response.text


def test_user_management_ui_shell_loads_without_login_bootstrap():
    response = client.get("/ui/users")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "/admin/users" in response.text
    assert "Simpan User Role" in response.text
    assert '<select id="branch">' in response.text
    assert "/admin/branches?active=true" in response.text
    assert "Tambah cabang sendiri" in response.text
    assert "customBranchCode" in response.text
    assert "customBranchName" in response.text
    assert "ensureSelectedBranch" in response.text
    assert "Sesi Admin" in response.text
    assert "Token tidak ditampilkan" in response.text
    assert "Bearer Token" not in response.text
    assert 'id="token"' not in response.text


def test_admin_can_upsert_list_and_deactivate_user_role_when_auth_disabled():
    _bootstrap_user_routes()
    _ensure_branch("PASURUAN", "Cabang Pasuruan")
    payload = {
        "user_id": "test-user-001",
        "email": "auditor@example.com",
        "display_name": "Auditor Test",
        "role": "AUDITOR",
        "branch": "Pasuruan",
        "is_active": "true",
    }

    upsert = client.post("/admin/users", data=payload)
    assert upsert.status_code == 200
    assert upsert.json()["role"] == "AUDITOR"
    assert upsert.json()["branch"] == "PASURUAN"
    assert upsert.json()["is_active"] is True

    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert any(row["user_id"] == "test-user-001" for row in listing.json()["users"])

    deactivate = client.post("/admin/users/test-user-001/deactivate")
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False


def test_admin_rejects_invalid_role():
    _bootstrap_user_routes()
    response = client.post(
        "/admin/users",
        data={"user_id": "bad-role-user", "email": "bad@example.com", "role": "SUPERUSER"},
    )

    assert response.status_code == 400
    assert "role must be" in response.text


def test_non_admin_user_requires_branch_assignment():
    _bootstrap_user_routes()
    response = client.post(
        "/admin/users",
        data={
            "user_id": "branchless-user",
            "email": "branchless@example.com",
            "role": "VIEWER",
            "branch": "",
            "is_active": "true",
        },
    )

    assert response.status_code == 400
    assert "branch is required" in response.text



def test_admin_branch_assignment_is_optional():
    response = client.post(
        "/admin/users",
        data={
            "user_id": "admin-no-branch",
            "email": "admin-no-branch@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["branch"] is None


def test_inactive_branch_cannot_be_assigned():
    _ensure_branch("UM-INACTIVE", "Inactive Branch")
    deactivated = client.post("/admin/branches/UM-INACTIVE/deactivate")
    assert deactivated.status_code == 200

    response = client.post(
        "/admin/users",
        data={
            "user_id": "inactive-branch-user",
            "email": "inactive@example.com",
            "role": "AUDITOR",
            "branch": "UM-INACTIVE",
            "is_active": "true",
        },
    )
    assert response.status_code == 400
    assert "active branch" in response.text


def test_branch_reassignment_is_normalized_and_audited():
    _ensure_branch("PASURUAN", "Cabang Pasuruan")
    _ensure_branch("SIDOARJO", "Cabang Sidoarjo")

    first = client.post(
        "/admin/users",
        data={
            "user_id": "reassign-user",
            "email": "reassign@example.com",
            "role": "AUDITOR",
            "branch": "pasuruan",
            "is_active": "true",
        },
    )
    assert first.status_code == 200
    assert first.json()["branch"] == "PASURUAN"

    second = client.post(
        "/admin/users",
        data={
            "user_id": "reassign-user",
            "email": "reassign@example.com",
            "role": "AUDITOR",
            "branch": " sidoarjo ",
            "is_active": "true",
        },
    )
    assert second.status_code == 200
    assert second.json()["branch"] == "SIDOARJO"

    trail = client.get(
        "/audit-trail",
        params={"entity_type": "USER_ROLE", "branch": "SIDOARJO", "limit": 100},
    )
    assert trail.status_code == 200
    matching = [
        row for row in trail.json()["entries"]
        if (row.get("metadata") or {}).get("target_user_id") == "reassign-user"
    ]
    assert matching
    assert any(
        row["action"] == "BRANCH_REASSIGN"
        and row["metadata"]["old_branch"] == "PASURUAN"
        and row["metadata"]["new_branch"] == "SIDOARJO"
        for row in matching
    )
