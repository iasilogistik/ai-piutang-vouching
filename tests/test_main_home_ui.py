from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_main_home_layout_is_informative_and_session_based():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Piutang Vouching Command Center" in response.text
    assert "Ringkasan Operasional" in response.text
    assert "Alur Kerja Audit" in response.text
    assert "Upload Center" in response.text
    assert "Control Evidence" in response.text
    assert "Google Drive Import" in response.text
    assert "/ui/dashboard" in response.text
    assert "/ui/upload" in response.text
    assert "/ui/users" in response.text
    assert "Bearer token" not in response.text
    assert "Bearer Token" not in response.text
    assert "id=\"token\"" not in response.text


def test_main_home_admin_user_menu_is_role_gated():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "/ui/users" in response.text
    assert "admin-only" in response.text
    assert "role === 'ADMIN'" in response.text
    assert "Sesi login digunakan otomatis dari browser" in response.text
