from fastapi.testclient import TestClient

from app.main import app
from app.services import user_management


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
    assert "Simpan User" in response.text
    assert "Email Login" in response.text
    assert "Password Sementara" in response.text
    assert 'id="password"' in response.text
    assert "Lupa Password" in response.text
    assert "forgotPassword" in response.text
    assert "/forgot-password" in response.text
    assert "User ID Supabase" not in response.text
    assert 'id="userId"' not in response.text
    assert "ID teknis Supabase" not in response.text
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
        "email": "auditor@example.com",
        "display_name": "Auditor Test",
        "role": "AUDITOR",
        "branch": "Pasuruan",
        "is_active": "true",
    }

    upsert = client.post("/admin/users", data=payload)
    assert upsert.status_code == 200
    assert upsert.json()["user_id"] == "auditor@example.com"
    assert upsert.json()["role"] == "AUDITOR"
    assert upsert.json()["branch"] == "PASURUAN"
    assert upsert.json()["is_active"] is True
    assert upsert.json()["auth_operation"]["status"] == "NOT_REQUESTED"

    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert any(row["email"] == "auditor@example.com" for row in listing.json()["users"])

    deactivate = client.post("/admin/users/auditor@example.com/deactivate")
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False


def test_admin_can_create_supabase_auth_user_with_password(monkeypatch):
    created = {}

    def fake_create_auth_user(*, email: str, password: str, display_name: str | None = None):
        created["email"] = email
        created["password"] = password
        created["display_name"] = display_name
        return {"status": "CREATED", "user_id": "supabase-created-001", "email": email}

    monkeypatch.setattr(user_management, "create_auth_user", fake_create_auth_user)

    response = client.post(
        "/admin/users",
        data={
            "email": "new.user@example.com",
            "password": "Password123!",
            "display_name": "New User",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == "supabase-created-001"
    assert response.json()["auth_operation"]["status"] == "CREATED"
    assert "password" not in response.json()
    assert created == {
        "email": "new.user@example.com",
        "password": "Password123!",
        "display_name": "New User",
    }


def test_admin_can_send_forgot_password_email(monkeypatch):
    sent = {}

    def fake_send_password_recovery(email: str):
        sent["email"] = email
        return {"status": "PASSWORD_RECOVERY_SENT", "email": email}

    monkeypatch.setattr(user_management, "send_password_recovery", fake_send_password_recovery)

    upsert = client.post(
        "/admin/users",
        data={
            "email": "forgot@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert upsert.status_code == 200

    response = client.post("/admin/users/forgot@example.com/forgot-password")

    assert response.status_code == 200
    assert response.json()["status"] == "PASSWORD_RECOVERY_SENT"
    assert response.json()["email"] == "forgot@example.com"
    assert sent == {"email": "forgot@example.com"}


def test_admin_rejects_short_password():
    response = client.post(
        "/admin/users",
        data={
            "email": "short-password@example.com",
            "password": "short",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )

    assert response.status_code == 400
    assert "password must be at least 8 characters" in response.text


def test_admin_rejects_invalid_role():
    _bootstrap_user_routes()
    response = client.post(
        "/admin/users",
        data={"email": "bad@example.com", "role": "SUPERUSER"},
    )

    assert response.status_code == 400
    assert "role must be" in response.text


def test_admin_requires_email():
    _bootstrap_user_routes()
    response = client.post(
        "/admin/users",
        data={"role": "ADMIN", "branch": "", "is_active": "true"},
    )

    assert response.status_code == 422


def test_non_admin_user_requires_branch_assignment():
    _bootstrap_user_routes()
    response = client.post(
        "/admin/users",
        data={
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
            "email": "admin-no-branch@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "admin-no-branch@example.com"
    assert response.json()["branch"] is None


def test_optional_supabase_user_id_is_still_supported_for_existing_integrations():
    response = client.post(
        "/admin/users",
        data={
            "user_id": "supabase-uuid-001",
            "email": "uuid-linked@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "supabase-uuid-001"


def test_inactive_branch_cannot_be_assigned():
    _ensure_branch("UM-INACTIVE", "Inactive Branch")
    deactivated = client.post("/admin/branches/UM-INACTIVE/deactivate")
    assert deactivated.status_code == 200

    response = client.post(
        "/admin/users",
        data={
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
            "email": "reassign@example.com",
            "role": "AUDITOR",
            "branch": "pasuruan",
            "is_active": "true",
        },
    )
    assert first.status_code == 200
    assert first.json()["user_id"] == "reassign@example.com"
    assert first.json()["branch"] == "PASURUAN"

    second = client.post(
        "/admin/users",
        data={
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
        if (row.get("metadata") or {}).get("target_email") == "reassign@example.com"
    ]
    assert matching
    assert any(
        row["action"] == "BRANCH_REASSIGN"
        and row["metadata"]["old_branch"] == "PASURUAN"
        and row["metadata"]["new_branch"] == "SIDOARJO"
        for row in matching
    )
