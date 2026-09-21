from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _bootstrap_user_routes() -> None:
    response = client.get("/login")
    assert response.status_code == 200


def test_login_page_links_user_management():
    response = client.get("/login")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "/ui/users" in response.text


def test_user_management_ui_shell_loads_after_login_bootstrap():
    _bootstrap_user_routes()
    response = client.get("/ui/users")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "/admin/users" in response.text
    assert "Simpan User Role" in response.text


def test_admin_can_upsert_list_and_deactivate_user_role_when_auth_disabled():
    _bootstrap_user_routes()
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
    assert upsert.json()["branch"] == "Pasuruan"
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
