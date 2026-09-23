from fastapi.testclient import TestClient

from app.main import app
from app.services import release_readiness

client = TestClient(app)

EXPECTED_REVISION = "0029_fix_app_private_schema_usage"
PREVIOUS_REVISION = "0028_performance_hardening"


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
    def __init__(
        self,
        alembic_rows=None,
        supabase_latest=None,
        app_revision=None,
        supabase_error=False,
    ):
        self.alembic_rows = alembic_rows
        self.supabase_latest = supabase_latest
        self.app_revision = app_revision
        self.supabase_error = supabase_error

    def execute(self, statement, params=None):
        sql = str(statement)
        if "version_num from public.alembic_version" in sql:
            return _ScalarResult(rows=self.alembic_rows or [])
        if "from supabase_migrations.schema_migrations" in sql:
            if self.supabase_error:
                raise PermissionError("internal tracker is not readable")
            return _ScalarResult(scalar=self.supabase_latest)
        if "select app_private.current_app_schema_revision()" in sql:
            return _ScalarResult(scalar=self.app_revision)
        raise AssertionError(f"Unexpected SQL in fake connection: {sql}")


def test_version_exposes_release_identity_without_secrets(monkeypatch):
    monkeypatch.setattr(release_readiness, "release_commit_sha", lambda: "abc123")
    monkeypatch.setattr(release_readiness, "release_branch", lambda: "main")
    monkeypatch.setattr(release_readiness, "release_environment", lambda: "production")

    response = client.get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["commit"] == "abc123"
    assert payload["branch"] == "main"
    assert payload["environment"] == "production"
    assert "database_url" not in payload
    assert "supabase_secret_key" not in payload


def test_release_environment_prefers_vercel_runtime_metadata(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setattr(release_readiness.settings, "app_env", "development")

    assert release_readiness.release_environment() == "production"


def test_release_environment_falls_back_to_app_env(monkeypatch):
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setattr(release_readiness.settings, "app_env", "test")

    assert release_readiness.release_environment() == "test"


def test_tracker_reads_alembic_heads_when_available(monkeypatch):
    connection = _FakeConnection(alembic_rows=[EXPECTED_REVISION])
    monkeypatch.setattr(
        release_readiness,
        "_relation_exists",
        lambda _connection, relation: relation == "public.alembic_version",
    )

    assert release_readiness._tracked_heads(connection) == {EXPECTED_REVISION}


def test_tracker_reads_supabase_latest_migration_when_allowed(monkeypatch):
    connection = _FakeConnection(supabase_latest=EXPECTED_REVISION)
    monkeypatch.setattr(
        release_readiness,
        "_relation_exists",
        lambda _connection, relation: relation == "supabase_migrations.schema_migrations",
    )
    monkeypatch.setattr(release_readiness, "_function_exists", lambda *_: False)

    assert release_readiness._tracked_heads(connection) == {EXPECTED_REVISION}


def test_tracker_prefers_protected_revision_before_restricted_internal_tracker(monkeypatch):
    connection = _FakeConnection(
        app_revision=EXPECTED_REVISION,
        supabase_error=True,
    )
    monkeypatch.setattr(
        release_readiness,
        "_relation_exists",
        lambda _connection, relation: relation == "supabase_migrations.schema_migrations",
    )
    monkeypatch.setattr(release_readiness, "_function_exists", lambda *_: True)

    # This succeeds only if the helper is used before the direct internal read:
    # the fake internal tracker raises exactly like a restricted hosted role.
    assert release_readiness._tracked_heads(connection) == {EXPECTED_REVISION}


def test_tracker_fails_closed_when_no_metadata_source_exists(monkeypatch):
    connection = _FakeConnection()
    monkeypatch.setattr(release_readiness, "_relation_exists", lambda *_: False)
    monkeypatch.setattr(release_readiness, "_function_exists", lambda *_: False)

    try:
        release_readiness._tracked_heads(connection)
    except release_readiness.MigrationMetadataUnavailable:
        pass
    else:
        raise AssertionError("Expected MigrationMetadataUnavailable")


def test_readiness_ready_when_database_revision_matches_code(monkeypatch):
    monkeypatch.setattr(release_readiness, "_database_heads", lambda: {EXPECTED_REVISION})
    monkeypatch.setattr(release_readiness, "_expected_heads", lambda: {EXPECTED_REVISION})

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "healthy",
        "schema_current": True,
    }


def test_readiness_fails_when_schema_is_not_current(monkeypatch):
    monkeypatch.setattr(release_readiness, "_database_heads", lambda: {PREVIOUS_REVISION})
    monkeypatch.setattr(release_readiness, "_expected_heads", lambda: {EXPECTED_REVISION})

    response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "healthy",
        "schema_current": False,
        "reason": "schema_revision_mismatch",
        "expected_revision": [EXPECTED_REVISION],
        "database_revision": [PREVIOUS_REVISION],
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
        "reason": "migration_metadata_unavailable",
        "expected_revision": [EXPECTED_REVISION],
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
        "reason": "database_unavailable",
        "expected_revision": [EXPECTED_REVISION],
    }
    assert "detail" not in payload
