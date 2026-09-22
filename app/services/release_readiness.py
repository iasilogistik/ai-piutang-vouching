from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine

router = APIRouter()
_REGISTERED = False


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


def _expected_heads() -> set[str]:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    return set(scripts.get_heads())


def _database_heads() -> set[str]:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        rows = connection.execute(text("select version_num from alembic_version")).scalars().all()
    return {str(value) for value in rows}


def readiness_payload() -> tuple[int, dict[str, object]]:
    try:
        database_heads = _database_heads()
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
        "environment": settings.app_env,
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
