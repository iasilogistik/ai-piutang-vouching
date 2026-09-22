from fastapi.testclient import TestClient

from app.main import app
from app.services import release_readiness

client = TestClient(app)


class _ScalarResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, alembic_rows=None, supabase_latest=None):
        self.alembic_rows = alembic_rows
        self.supabase_latest = supabase_latest

    def execute(self, statement, params=None):
        sql = str(statement)
        if "version_num from public.alembic_version" in sql:
            return _ScalarResult(rows=self.alembic_rows or [])
        if "from supabase_migrations.schema_migrations" in sql:
            return _ScalarResult(scalar=self.supabase_latest)
        raise AssertionError(f"Unexpected SQL in fake connection: {sql}")


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


def test_tracker_reads_alembic_heads_when_available(monkeypatch):
    connection = _FakeConnection(alembic_rows=["0026_evidence_repository"])
    monkeypatch.setattr(
        release_readiness,
        "_relation_exists",
        lambda _connection, relation: relation == "public.alembic_version",
    )

    assert release_readiness._tracked_heads(connection) == {"0026_evidence_repository"}


def test_tracker_falls_back_to_supabase_latest_migration_name(monkeypatch):
    connection = _FakeConnection(supabase_latest="0026_evidence_repository")
    monkeypatch.setattr(
        release_readiness,
        "_relation_exists",
        lambda _connection, relation: relation == "supabase_migrations.schema_migrations",
    )

    assert release_readiness._tracked_heads(connection) == {"0026_evidence_repository"}


def test_tracker_fails_closed_when_no_metadata_table_exists(monkeypatch):
    connection = _FakeConnection()
    monkeypatch.setattr(release_readiness, "_relation_exists", lambda *_: False)

    try:
        release_readiness._tracked_heads(connection)
    except release_readiness.MigrationMetadataUnavailable:
        pass
    else:
        raise AssertionError("Expected MigrationMetadataUnavailable")


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


def test_readiness_reports_healthy_database_when_tracker_is_missing(monkeypatch):
    def no_tracker():
        raise release_readiness.MigrationMetadataUnavailable("must not leak")

    monkeypatch.setattr(release_readiness, "_database_heads", no_tracker)

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
