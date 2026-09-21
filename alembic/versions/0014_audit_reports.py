"""Add audit report snapshots.

Revision ID: 0014_audit_reports
Revises: 0013_review_workflow
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_audit_reports"
down_revision = "0013_review_workflow"
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
        "audit_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("population_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sampled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unresolved_exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finding_summary", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("period_end >= period_start", name="ck_audit_reports_period"),
        sa.CheckConstraint("status in ('DRAFT','APPROVED')", name="ck_audit_reports_status"),
        schema="public",
    )
    op.create_index("ix_audit_reports_branch", "audit_reports", ["branch"], schema="public")
    op.create_index("ix_audit_reports_status", "audit_reports", ["status"], schema="public")
    op.create_index("ix_audit_reports_period", "audit_reports", ["period_start", "period_end"], schema="public")

    op.execute("alter table public.audit_reports enable row level security")
    if _supabase_authenticated_available():
        op.execute("revoke all on public.audit_reports from anon, authenticated")
        op.execute("revoke all on sequence public.audit_reports_id_seq from anon, authenticated")
        op.execute("grant select, insert, update on public.audit_reports to authenticated")
        op.execute("grant usage, select on sequence public.audit_reports_id_seq to authenticated")

        op.execute(
            """
            create policy "app_read_audit_reports" on public.audit_reports
            for select to authenticated
            using (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )
        op.execute(
            """
            create policy "app_insert_audit_reports" on public.audit_reports
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
            create policy "app_update_audit_reports" on public.audit_reports
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
    op.execute('drop policy if exists "app_update_audit_reports" on public.audit_reports')
    op.execute('drop policy if exists "app_insert_audit_reports" on public.audit_reports')
    op.execute('drop policy if exists "app_read_audit_reports" on public.audit_reports')
    op.drop_index("ix_audit_reports_period", table_name="audit_reports", schema="public")
    op.drop_index("ix_audit_reports_status", table_name="audit_reports", schema="public")
    op.drop_index("ix_audit_reports_branch", table_name="audit_reports", schema="public")
    op.drop_table("audit_reports", schema="public")
