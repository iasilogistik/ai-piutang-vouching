from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine

router = APIRouter()
_REGISTERED = False
EXPECTED_SCHEMA_REVISION = "0031_revision_helper_acl"
REQUIRED_SCHEMA_OBJECTS = {
    "public.documents",
    "public.document_control_evidence",
    "public.user_roles",
    "public.audit_trail",
    "public.audit_workflow_cases",
    "public.audit_notifications",
}


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


def _safe_rollback(connection) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _call_revision_helper(connection, sql: str) -> str | None:
    # Call helpers directly instead of probing with to_regprocedure first. Some
    # hosted runtimes can return null for procedure lookup even when EXECUTE on a
    # SECURITY DEFINER helper is allowed. Undefined-function or permission errors
    # still fail closed and fall through to the next metadata source.
    try:
        value = connection.execute(text(sql)).scalar_one_or_none()
        return str(value) if value else None
    except Exception:
        _safe_rollback(connection)
        return None


def _protected_schema_revision(connection) -> str | None:
    public_revision = _call_revision_helper(
        connection,
        "select public.current_app_schema_revision()",
    )
    if public_revision:
        return public_revision

    return _call_revision_helper(
        connection,
        "select app_private.current_app_schema_revision()",
    )


def _missing_required_schema_objects(connection) -> list[str]:
    missing: list[str] = []
    try:
        for relation in sorted(REQUIRED_SCHEMA_OBJECTS):
            if not _relation_exists(connection, relation):
                missing.append(relation)
        return missing
    except Exception:
        _safe_rollback(connection)
        return sorted(REQUIRED_SCHEMA_OBJECTS)


def _required_schema_objects_available(connection) -> bool:
    return not _missing_required_schema_objects(connection)


def _missing_database_schema_objects() -> list[str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
            return _missing_required_schema_objects(connection)
    except Exception:
        return sorted(REQUIRED_SCHEMA_OBJECTS)


def _tracked_heads(connection) -> set[str]:
    if _relation_exists(connection, "public.alembic_version"):
        rows = connection.execute(
            text("select version_num from public.alembic_version")
        ).scalars().all()
        return {str(value) for value in rows}

    # Hosted Supabase can restrict direct reads from its internal migration schema.
    # Prefer a narrow SECURITY DEFINER helper before trying that internal table:
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
        _safe_rollback(connection)

    # Final operational fallback: some hosted/runtime roles cannot inspect the
    # migration tracker, but they can still access the public application schema.
    # Treat the schema as current only when the minimum launch-critical tables
    # introduced by the current release train are present.
    if _required_schema_objects_available(connection):
        return _expected_heads()

    raise MigrationMetadataUnavailable("migration tracker not found")


def _database_heads() -> set[str]:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        return _tracked_heads(connection)


def readiness_payload() -> tuple[int, dict[str, object]]:
    expected_heads = _expected_heads()
    expected_revision = sorted(expected_heads)

    try:
        database_heads = _database_heads()
    except MigrationMetadataUnavailable:
        return 503, {
            "status": "not_ready",
            "database": "healthy",
            "schema_current": False,
            "reason": "migration_metadata_unavailable",
            "expected_revision": expected_revision,
            "missing_schema_objects": _missing_database_schema_objects(),
        }
    except Exception:
        return 503, {
            "status": "not_ready",
            "database": "unavailable",
            "schema_current": False,
            "reason": "database_unavailable",
            "expected_revision": expected_revision,
        }

    schema_current = bool(expected_heads) and database_heads == expected_heads
    if not schema_current:
        return 503, {
            "status": "not_ready",
            "database": "healthy",
            "schema_current": False,
            "reason": "schema_revision_mismatch",
            "expected_revision": expected_revision,
            "database_revision": sorted(database_heads),
        }

    return 200, {
        "status": "ready",
        "database": "healthy",
        "schema_current": True,
    }


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
