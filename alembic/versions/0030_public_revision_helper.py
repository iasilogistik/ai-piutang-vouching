"""Expose public wrapper for readiness schema revision.

Revision ID: 0030_public_revision_helper
Revises: 0029_app_private_usage
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0030_public_revision_helper"
down_revision = "0029_app_private_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    tracker_exists = bool(
        bind.execute(
            sa.text(
                "select to_regclass('supabase_migrations.schema_migrations') is not null"
            )
        ).scalar()
    )
    if not tracker_exists:
        return

    op.execute(
        """
        create or replace function public.current_app_schema_revision()
        returns text
        language sql
        stable
        security definer
        set search_path = ''
        as $$
          select app_private.current_app_schema_revision()
        $$;
        """
    )
    op.execute("revoke all on function public.current_app_schema_revision() from public")
    op.execute(
        "grant execute on function public.current_app_schema_revision() "
        "to postgres, authenticator, anon, authenticated, service_role"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("drop function if exists public.current_app_schema_revision()")
