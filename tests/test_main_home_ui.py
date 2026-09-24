from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_main_home_root_loads():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Piutang Vouching" in response.text
    assert "Dashboard Ringkas" in response.text
    assert "/ui/dashboard" in response.text
    assert "/ui/upload" in response.text
    assert "/ui/control-evidence" in response.text


def test_main_home_admin_user_menu_is_role_gated():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "/ui/users" in response.text
    assert "admin-only" in response.text
    assert "role === 'ADMIN'" in response.text
