from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_user_management_ui_auto_loads_users_and_has_delete_without_branch_page_link():
    response = client.get("/ui/users")

    assert response.status_code == 200
    assert "loadUsers();" in response.text
    assert "data-action=\"edit\"" in response.text
    assert "data-action=\"deactivate\"" in response.text
    assert "data-action=\"delete\"" in response.text
    assert "deleteUser" in response.text
    assert 'href="/ui/branches"' not in response.text
    assert "Master Cabang" not in response.text


def test_admin_can_delete_user_role_from_user_management_actions():
    upsert = client.post(
        "/admin/users",
        data={
            "email": "delete-target@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert upsert.status_code == 200

    deleted = client.delete("/admin/users/delete-target@example.com")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["auth_user_deleted"] is False

    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert all(row["email"] != "delete-target@example.com" for row in listing.json()["users"])
