from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_gateway import password_reset_redirect_url


client = TestClient(app)


def test_forgot_password_page_uses_production_redirect():
    response = client.get("/forgot-password")

    assert response.status_code == 200
    assert "Lupa Password" in response.text
    assert "/auth/password-reset-request" in response.text
    assert "https://ai-piutang-vouching.vercel.app/reset-password" in response.text
    assert "http://localhost" not in response.text


def test_reset_password_page_extracts_access_token():
    response = client.get("/reset-password")

    assert response.status_code == 200
    assert "Reset Password" in response.text
    assert "access_token" in response.text
    assert "/auth/password-update" in response.text


def test_password_update_requires_reset_token():
    response = client.post("/auth/password-update", data={"password": "password-baru-123"})

    assert response.status_code == 401
    assert "Access token reset password" in response.text


def test_password_reset_redirect_url_defaults_to_production():
    assert password_reset_redirect_url() == "https://ai-piutang-vouching.vercel.app/reset-password"
