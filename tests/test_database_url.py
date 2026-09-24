from app.database import normalize_database_url


def test_normalize_standard_postgresql_url_uses_psycopg3():
    raw = "postgresql://user:secret@example.test:5432/app"
    normalized = normalize_database_url(raw)

    assert normalized == "postgresql+psycopg://user:secret@example.test:5432/app"


def test_normalize_legacy_postgres_url_uses_psycopg3():
    raw = "postgres://user:secret@example.test:5432/app"
    normalized = normalize_database_url(raw)

    assert normalized == "postgresql+psycopg://user:secret@example.test:5432/app"


def test_normalize_explicit_psycopg_url_is_unchanged():
    raw = "postgresql+psycopg://user:secret@example.test:5432/app"

    assert normalize_database_url(raw) == raw


def test_normalize_non_postgresql_url_is_unchanged():
    raw = "sqlite:///local.db"

    assert normalize_database_url(raw) == raw
