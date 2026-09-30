from app.database import (
    database_engine_options,
    is_transaction_pooler_url,
    normalize_database_url,
)


def test_normalize_database_url_uses_psycopg3():
    assert (
        normalize_database_url("postgresql://user:pass@db.example.com:5432/postgres")
        == "postgresql+psycopg://user:pass@db.example.com:5432/postgres"
    )
    assert (
        normalize_database_url("postgres://user:pass@db.example.com:5432/postgres")
        == "postgresql+psycopg://user:pass@db.example.com:5432/postgres"
    )


def test_supabase_transaction_pooler_disables_prepared_statements():
    url = (
        "postgresql://postgres.project:secret@"
        "aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres"
    )

    assert is_transaction_pooler_url(url) is True
    assert database_engine_options(url) == {
        "pool_pre_ping": True,
        "connect_args": {"prepare_threshold": None},
    }


def test_session_pooler_also_disables_prepared_statements_for_serverless_safety():
    url = (
        "postgresql://postgres.project:secret@"
        "aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"
    )

    assert is_transaction_pooler_url(url) is False
    assert database_engine_options(url) == {
        "pool_pre_ping": True,
        "connect_args": {"prepare_threshold": None},
    }


def test_direct_postgres_connection_disables_prepared_statements_for_serverless_safety():
    url = "postgresql://postgres:secret@db.project.supabase.co:5432/postgres"

    assert is_transaction_pooler_url(url) is False
    assert database_engine_options(url) == {
        "pool_pre_ping": True,
        "connect_args": {"prepare_threshold": None},
    }


def test_non_postgres_database_is_not_treated_as_transaction_pooler():
    assert is_transaction_pooler_url("sqlite+pysqlite:///:memory:") is False
    assert database_engine_options("sqlite+pysqlite:///:memory:") == {
        "pool_pre_ping": True
    }
