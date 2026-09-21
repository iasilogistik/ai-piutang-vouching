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
