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
    """Return True for Postgres transaction-pooler URLs.

    Supabase/Supavisor transaction mode uses port 6543 and does not support
    session-level prepared statements. Psycopg must therefore disable its
    automatic prepare threshold for these connections.
    """
    normalized = normalize_database_url(url)
    if not normalized.startswith("postgresql+psycopg://"):
        return False
    try:
        parsed = urlparse(normalized)
        return parsed.port == 6543
    except ValueError:
        return False


def database_engine_options(url: str) -> dict[str, object]:
    options: dict[str, object] = {"pool_pre_ping": True}
    if is_transaction_pooler_url(url):
        options["connect_args"] = {"prepare_threshold": None}
    return options


_database_url = normalize_database_url(settings.database_url)
engine = create_engine(_database_url, **database_engine_options(_database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
