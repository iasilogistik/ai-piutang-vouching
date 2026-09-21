"""Add audit closing sign-off workflow.

Revision ID: 0015_audit_closing_signoff
Revises: 0014_audit_reports
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_audit_closing_signoff"
down_revision = "0014_audit_reports"
branch_labels = None
depends_on = None


def _supabase_authenticated_available() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (select 1 from pg_roles where rolname = 'authenticated')
                  and exists (
                    select 1 from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = 'current_app_role'
                  )
                  and exists (
                    select 1 from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = 'current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "audit_closings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_report_id", sa.Integer(), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="OPEN"),
        sa.Column("closing_note", sa.Text(), nullable=True),
        sa.Column("auditor_signoff_by", sa.String(length=100), nullable=True),
        sa.Column("auditor_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_signoff_by", sa.String(length=100), nullable=True),
        sa.Column("reviewer_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(length=100), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["audit_report_id"], ["public.audit_reports.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("audit_report_id", name="uq_audit_closings_report"),
        sa.CheckConstraint(
            "status in ('OPEN','AUDITOR_SIGNED','REVIEWER_SIGNED','CLOSED')",
            name="ck_audit_closings_status",
        ),
        schema="public",
    )
    op.create_index("ix_audit_closings_branch", "audit_closings", ["branch"], schema="public")
    op.create_index("ix_audit_closings_status", "audit_closings", ["status"], schema="public")

    op.execute("alter table public.audit_closings enable row level security")
    if _supabase_authenticated_available():
        op.execute("revoke all on public.audit_closings from anon, authenticated")
        op.execute("revoke all on sequence public.audit_closings_id_seq from anon, authenticated")
        op.execute("grant select, insert, update on public.audit_closings to authenticated")
        op.execute("grant usage, select on sequence public.audit_closings_id_seq to authenticated")

        op.execute(
            """
            create policy "app_read_audit_closings" on public.audit_closings
            for select to authenticated
            using (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )
        op.execute(
            """
            create policy "app_insert_audit_closings" on public.audit_closings
            for insert to authenticated
            with check (
                (select public.current_app_role()) in (
                    'ADMIN'::public.app_role,
                    'AUDITOR'::public.app_role
                )
                and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or branch = (select public.current_app_branch())
                )
            )
            """
        )
        op.execute(
            """
            create policy "app_update_audit_closings" on public.audit_closings
            for update to authenticated
            using (
                (select public.current_app_role()) in (
                    'ADMIN'::public.app_role,
                    'AUDITOR'::public.app_role,
                    'REVIEWER'::public.app_role
                )
                and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or branch = (select public.current_app_branch())
                )
            )
            with check (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )


def downgrade() -> None:
    op.execute('drop policy if exists "app_update_audit_closings" on public.audit_closings')
    op.execute('drop policy if exists "app_insert_audit_closings" on public.audit_closings')
    op.execute('drop policy if exists "app_read_audit_closings" on public.audit_closings')
    op.drop_index("ix_audit_closings_status", table_name="audit_closings", schema="public")
    op.drop_index("ix_audit_closings_branch", table_name="audit_closings", schema="public")
    op.drop_table("audit_closings", schema="public")
