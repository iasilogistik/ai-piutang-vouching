"""Expose a narrow production-safe schema revision function.

Revision ID: 0027_release_schema_revision
Revises: 0026_evidence_repository
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0027_release_schema_revision"
down_revision = "0026_evidence_repository"
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
        # Normal/local Alembic deployments keep using public.alembic_version.
        return

    op.execute("create schema if not exists app_private")
    op.execute("revoke all on schema app_private from public")
    op.execute(
        "grant usage on schema app_private to postgres, authenticator, service_role"
    )
    op.execute(
        """
        create or replace function app_private.current_app_schema_revision()
        returns text
        language sql
        stable
        security definer
        set search_path = ''
        as $$
          select name::text
          from supabase_migrations.schema_migrations
          order by version desc
          limit 1
        $$;
        """
    )
    op.execute(
        "revoke all on function app_private.current_app_schema_revision() from public"
    )
    op.execute(
        "grant execute on function app_private.current_app_schema_revision() "
        "to postgres, authenticator, service_role"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("drop function if exists app_private.current_app_schema_revision()")
