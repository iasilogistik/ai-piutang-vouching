from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine

router = APIRouter()
_REGISTERED = False
EXPECTED_SCHEMA_REVISION = "0028_performance_hardening"


class MigrationMetadataUnavailable(RuntimeError):
    pass


def release_commit_sha() -> str:
    return (
        os.getenv("VERCEL_GIT_COMMIT_SHA")
        or os.getenv("GITHUB_SHA")
        or os.getenv("RELEASE_COMMIT_SHA")
        or "unknown"
    )


def release_branch() -> str:
    return (
        os.getenv("VERCEL_GIT_COMMIT_REF")
        or os.getenv("GITHUB_REF_NAME")
        or os.getenv("RELEASE_BRANCH")
        or "unknown"
    )


def release_environment() -> str:
    # Vercel sets VERCEL_ENV automatically for production/preview deployments.
    # Outside Vercel, keep the application's configured APP_ENV behavior.
    return os.getenv("VERCEL_ENV") or settings.app_env


def _expected_heads() -> set[str]:
    # Keep runtime readiness independent from migration/config files that may be
    # omitted by serverless bundlers. CI asserts this constant equals Alembic head.
    return {EXPECTED_SCHEMA_REVISION}


def _relation_exists(connection, relation: str) -> bool:
    return bool(
        connection.execute(
            text("select to_regclass(:relation) is not null"),
            {"relation": relation},
        ).scalar()
    )


def _function_exists(connection, signature: str) -> bool:
    return bool(
        connection.execute(
            text("select to_regprocedure(:signature) is not null"),
            {"signature": signature},
        ).scalar()
    )


def _protected_schema_revision(connection) -> str | None:
    try:
        if not _function_exists(connection, "app_private.current_app_schema_revision()"):
            return None
        value = connection.execute(
            text("select app_private.current_app_schema_revision()")
        ).scalar_one_or_none()
        return str(value) if value else None
    except Exception:
        return None


def _tracked_heads(connection) -> set[str]:
    if _relation_exists(connection, "public.alembic_version"):
        rows = connection.execute(
            text("select version_num from public.alembic_version")
        ).scalars().all()
        return {str(value) for value in rows}

    # Hosted Supabase can restrict direct reads from its internal migration schema.
    # Prefer the narrow SECURITY DEFINER helper before trying that internal table:
    # a permission error on the direct read aborts the PostgreSQL transaction and
    # would otherwise make the protected fallback unusable on the same connection.
    protected_revision = _protected_schema_revision(connection)
    if protected_revision:
        return {protected_revision}

    # Last fallback for environments where the internal tracker is readable but
    # the protected helper has not been installed.
    try:
        if _relation_exists(connection, "supabase_migrations.schema_migrations"):
            latest_name = connection.execute(
                text(
                    """
                    select name
                    from supabase_migrations.schema_migrations
                    order by version desc
                    limit 1
                    """
                )
            ).scalar_one_or_none()
            if latest_name:
                return {str(latest_name)}
    except Exception:
        pass

    raise MigrationMetadataUnavailable("migration tracker not found")


def _database_heads() -> set[str]:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        return _tracked_heads(connection)


def readiness_payload() -> tuple[int, dict[str, object]]:
    try:
        database_heads = _database_heads()
    except MigrationMetadataUnavailable:
        return 503, {
            "status": "not_ready",
            "database": "healthy",
            "schema_current": False,
        }
    except Exception:
        return 503, {
            "status": "not_ready",
            "database": "unavailable",
            "schema_current": False,
        }

    try:
        expected_heads = _expected_heads()
    except Exception:
        return 503, {
            "status": "not_ready",
            "database": "healthy",
            "schema_current": False,
        }

    schema_current = bool(expected_heads) and database_heads == expected_heads
    return (
        200 if schema_current else 503,
        {
            "status": "ready" if schema_current else "not_ready",
            "database": "healthy",
            "schema_current": schema_current,
        },
    )


@router.get("/version")
def version_info():
    return {
        "commit": release_commit_sha(),
        "branch": release_branch(),
        "environment": release_environment(),
    }


@router.get("/readiness")
def readiness():
    status_code, payload = readiness_payload()
    return JSONResponse(status_code=status_code, content=payload)


def register_release_readiness_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
