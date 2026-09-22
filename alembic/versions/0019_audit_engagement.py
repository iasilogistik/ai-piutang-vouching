"""Add audit engagements and normalized assignments.

Revision ID: 0019_audit_engagement
Revises: 0018_workflow_cases
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_audit_engagement"
down_revision = "0018_workflow_cases"
branch_labels = None
depends_on = None


def _supabase_rbac_available() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='auth' and p.proname='uid'
                  )
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_role'
                  )
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "audit_engagements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_audit_engagements_code"),
    )
    op.create_index("ix_audit_engagements_branch", "audit_engagements", ["branch"])
    op.create_index("ix_audit_engagements_status", "audit_engagements", ["status"])
    op.create_index("ix_audit_engagements_period", "audit_engagements", ["period_start", "period_end"])

    op.create_table(
        "audit_engagement_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("assignment_role", sa.String(length=20), nullable=False),
        sa.Column("assigned_by", sa.String(length=100), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "user_id", "assignment_role", name="uq_audit_engagement_assignment"),
    )
    op.create_index("ix_audit_engagement_assignments_engagement", "audit_engagement_assignments", ["engagement_id"])
    op.create_index("ix_audit_engagement_assignments_user", "audit_engagement_assignments", ["user_id"])

    op.add_column("audit_workflow_cases", sa.Column("engagement_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_audit_workflow_cases_engagement",
        "audit_workflow_cases", "audit_engagements",
        ["engagement_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_audit_workflow_cases_engagement", "audit_workflow_cases", ["engagement_id"])

    op.add_column("audit_reports", sa.Column("engagement_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_audit_reports_engagement",
        "audit_reports", "audit_engagements",
        ["engagement_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_audit_reports_engagement", "audit_reports", ["engagement_id"])

    op.execute("alter table public.audit_engagements enable row level security")
    op.execute("alter table public.audit_engagement_assignments enable row level security")

    if _supabase_rbac_available():
        op.execute("""
            create policy "app_read_audit_engagements"
            on public.audit_engagements for select to authenticated
            using (
              (select public.current_app_role()) = 'ADMIN'::public.app_role
              or upper(trim(branch)) = (select public.current_app_branch())
            )
        """)
        op.execute("""
            create policy "auditor_insert_audit_engagements"
            on public.audit_engagements for insert to authenticated
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
        """)
        op.execute("""
            create policy "app_update_audit_engagements"
            on public.audit_engagements for update to authenticated
            using (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
        """)
        op.execute("""
            create policy "app_read_audit_engagement_assignments"
            on public.audit_engagement_assignments for select to authenticated
            using (
              exists (
                select 1 from public.audit_engagements e
                where e.id = engagement_id
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(e.branch)) = (select public.current_app_branch())
                  )
              )
            )
        """)
        op.execute("""
            create policy "admin_manage_audit_engagement_assignments"
            on public.audit_engagement_assignments for all to authenticated
            using ((select public.current_app_role()) = 'ADMIN'::public.app_role)
            with check ((select public.current_app_role()) = 'ADMIN'::public.app_role)
        """)


def downgrade() -> None:
    op.drop_index("ix_audit_reports_engagement", table_name="audit_reports")
    op.drop_constraint("fk_audit_reports_engagement", "audit_reports", type_="foreignkey")
    op.drop_column("audit_reports", "engagement_id")
    op.drop_index("ix_audit_workflow_cases_engagement", table_name="audit_workflow_cases")
    op.drop_constraint("fk_audit_workflow_cases_engagement", "audit_workflow_cases", type_="foreignkey")
    op.drop_column("audit_workflow_cases", "engagement_id")
    op.drop_table("audit_engagement_assignments")
    op.drop_table("audit_engagements")
