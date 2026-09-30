from app.database import (
    database_engine_options,
    is_transaction_pooler_url,
    normalize_database_url,
)


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


def test_transaction_pooler_detection_keeps_conventional_supavisor_port():
    assert is_transaction_pooler_url(
        "postgresql://user:secret@example.test:6543/app"
    )
    assert not is_transaction_pooler_url(
        "postgresql://user:secret@example.test:5432/app"
    )


def test_psycopg_engine_disables_automatic_prepared_statements_on_any_port():
    direct = database_engine_options(
        "postgresql+psycopg://user:secret@example.test:5432/app"
    )
    pooled = database_engine_options(
        "postgresql+psycopg://user:secret@example.test:6543/app"
    )

    assert direct["connect_args"] == {"prepare_threshold": None}
    assert pooled["connect_args"] == {"prepare_threshold": None}


def test_non_postgres_engine_does_not_receive_psycopg_connect_args():
    options = database_engine_options("sqlite:///local.db")

    assert "connect_args" not in options
