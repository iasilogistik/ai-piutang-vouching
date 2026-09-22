from fastapi.testclient import TestClient

from app.main import app
from app.services import release_readiness

client = TestClient(app)


def test_version_exposes_release_identity_without_secrets(monkeypatch):
    monkeypatch.setattr(release_readiness, "release_commit_sha", lambda: "abc123")
    monkeypatch.setattr(release_readiness, "release_branch", lambda: "main")

    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["commit"] == "abc123"
    assert payload["branch"] == "main"
    assert "environment" in payload
    assert "database_url" not in payload
    assert "supabase_secret_key" not in payload


def test_readiness_ready_when_database_revision_matches_code(monkeypatch):
    monkeypatch.setattr(release_readiness, "_database_heads", lambda: {"0026_evidence_repository"})
    monkeypatch.setattr(release_readiness, "_expected_heads", lambda: {"0026_evidence_repository"})

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "healthy",
        "schema_current": True,
    }


def test_readiness_fails_when_schema_is_not_current(monkeypatch):
    monkeypatch.setattr(release_readiness, "_database_heads", lambda: {"0025_audit_notifications"})
    monkeypatch.setattr(release_readiness, "_expected_heads", lambda: {"0026_evidence_repository"})

    response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "healthy",
        "schema_current": False,
    }


def test_readiness_fails_closed_when_database_is_unavailable(monkeypatch):
    def unavailable():
        raise RuntimeError("database detail must not leak")

    monkeypatch.setattr(release_readiness, "_database_heads", unavailable)

    response = client.get("/readiness")

    assert response.status_code == 503
    payload = response.json()
    assert payload == {
        "status": "not_ready",
        "database": "unavailable",
        "schema_current": False,
    }
    assert "detail" not in payload
