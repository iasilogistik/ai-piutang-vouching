from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Force implicit PostgreSQL URLs onto the installed psycopg v3 driver."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def is_transaction_pooler_url(url: str) -> bool:
    """Return True for the conventional Supabase/Supavisor transaction-pooler URL."""
    normalized = normalize_database_url(url)
    if not normalized.startswith("postgresql+psycopg://"):
        return False
    try:
        parsed = urlparse(normalized)
        return parsed.port == 6543
    except ValueError:
        return False


def database_engine_options(url: str) -> dict[str, object]:
    """Build SQLAlchemy engine options that are safe for pooled/serverless Postgres.

    Psycopg v3 automatically prepares frequently executed statements. That optimization
    is unsafe when a connection is routed through a transaction pooler because a later
    transaction can land on a different backend connection while reusing the same
    prepared-statement name. Supabase/Supavisor can therefore raise
    DuplicatePreparedStatement even when the public DATABASE_URL is not on port 6543.

    Disable automatic prepared statements for every psycopg PostgreSQL connection.
    This is safe for direct Postgres connections and avoids intermittent HTTP 500s in
    serverless deployments.
    """
    options: dict[str, object] = {"pool_pre_ping": True}
    normalized = normalize_database_url(url)
    if normalized.startswith("postgresql+psycopg://"):
        options["connect_args"] = {"prepare_threshold": None}
    return options


_database_url = normalize_database_url(settings.database_url)
engine = create_engine(_database_url, **database_engine_options(_database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
