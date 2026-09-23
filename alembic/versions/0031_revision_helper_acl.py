"""Restrict execution of the public readiness schema revision helper.

Revision ID: 0031_revision_helper_acl
Revises: 0030_public_revision_helper
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0031_revision_helper_acl"
down_revision = "0030_public_revision_helper"
branch_labels = None
depends_on = None

ALLOWED_EXECUTE_ROLES = ("postgres", "authenticator", "service_role")
REVOKED_EXECUTE_ROLES = ("public", "anon", "authenticated")


def _function_exists() -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                "select to_regprocedure('public.current_app_schema_revision()') is not null"
            )
        ).scalar()
    )


def upgrade() -> None:
    if not _function_exists():
        return

    for role in REVOKED_EXECUTE_ROLES:
        op.execute(
            f"revoke execute on function public.current_app_schema_revision() from {role}"
        )

    op.execute(
        "grant execute on function public.current_app_schema_revision() "
        "to postgres, authenticator, service_role"
    )


def downgrade() -> None:
    if not _function_exists():
        return

    op.execute(
        "grant execute on function public.current_app_schema_revision() "
        "to anon, authenticated"
    )
