from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_user_management_ui_has_visible_action_feedback_and_post_delete_alias():
    response = client.get("/ui/users")

    assert response.status_code == 200
    assert "actionStatus" in response.text
    assert "runUserAction" in response.text
    assert "data-action=\"edit\"" in response.text
    assert "data-action=\"deactivate\"" in response.text
    assert "data-action=\"delete\"" in response.text
    assert "/delete" in response.text
    assert "Delete User" in response.text
    assert 'href="/ui/branches"' not in response.text


def test_admin_can_delete_user_role_with_post_alias_when_auth_disabled():
    upsert = client.post(
        "/admin/users",
        data={
            "email": "delete-action@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert upsert.status_code == 200

    deleted = client.post("/admin/users/delete-action@example.com/delete")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["auth_user_deleted"] is False

    listing = client.get("/admin/users")
    assert listing.status_code == 200
    assert not any(row["email"] == "delete-action@example.com" for row in listing.json()["users"])


def test_admin_can_delete_user_role_with_delete_method_for_api_clients():
    upsert = client.post(
        "/admin/users",
        data={
            "email": "delete-method@example.com",
            "role": "ADMIN",
            "branch": "",
            "is_active": "true",
        },
    )
    assert upsert.status_code == 200

    deleted = client.delete("/admin/users/delete-method@example.com")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
