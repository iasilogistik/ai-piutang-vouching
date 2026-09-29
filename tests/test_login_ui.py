from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_gateway import refresh_access_token


client = TestClient(app)


def test_login_ui_shell_loads():
    response = client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Piutang Vouching" in response.text
    assert "/auth/login" in response.text
    assert "auditToken" in response.text
    assert "Logout" in response.text


def test_login_ui_does_not_render_application_navigation():
    response = client.get("/login")

    assert response.status_code == 200
    assert 'id="roleNav"' not in response.text
    assert "loadRoleNavigation" not in response.text
    assert "DashboardAudit" not in response.text
    assert "Notifications" not in response.text
    assert "Buka UAT Pasuruan" not in response.text
    assert "Buka Control Evidence Dashboard" not in response.text
    assert "Buka Google Drive Import" not in response.text


def test_login_ui_redirects_all_roles_to_main_command_center():
    response = client.get("/login")

    assert response.status_code == 200
    assert "resolvePostLoginDestination" in response.text
    assert "fetch('/auth/me'" in response.text
    assert "profile.role" in response.text
    assert "return '/ui/main'" in response.text
    assert "return '/ui/users'" not in response.text
    assert "window.location.replace(destination)" in response.text
    assert "menu sidebar di sebelah kiri" in response.text


def test_auth_login_route_validates_required_form_fields():
    response = client.post("/auth/login")

    assert response.status_code == 422
    assert "email" in response.text
    assert "password" in response.text


def test_auth_refresh_requires_refresh_token():
    response = client.post("/auth/refresh")

    assert response.status_code == 422
    assert "refresh_token" in response.text


def test_refresh_access_token_rejects_blank_token():
    try:
        refresh_access_token("")
    except ValueError as exc:
        assert "Refresh token wajib diisi" in str(exc)
    else:
        raise AssertionError("Expected ValueError for blank refresh token")


def test_login_wraps_internal_next_route_in_persistent_shell():
    response = client.get("/login?next=/ui/audit-findings")

    assert response.status_code == 200
    assert "next.startsWith('/ui/')" in response.text
    assert "'/ui/main?view='" in response.text
    assert "encodeURIComponent(next)" in response.text


def test_login_ui_uses_unified_modern_auth_theme():
    response = client.get("/login")

    assert response.status_code == 200
    assert 'class="auth-page"' in response.text
    assert 'class="auth-shell"' in response.text
    assert 'class="auth-hero"' in response.text
    assert "Satu workspace untuk seluruh siklus audit piutang." in response.text
    assert "Masuk ke Command Center" in response.text
    assert "ROLE BASED" in response.text
    assert "BRANCH AWARE" in response.text
    assert "--auth-primary:#2563eb" in response.text
