"""Link existing audit modules into workflow cases.

Revision ID: 0018_workflow_cases
Revises: 0017_vouch_review
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_workflow_cases"
down_revision = "0017_vouch_review"
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
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'auth' and p.proname = 'uid'
                  )
                  and exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = 'current_app_role'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "audit_workflow_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("vouching_result_id", sa.Integer(), sa.ForeignKey("vouching_result.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("control_evidence_id", sa.Integer(), sa.ForeignKey("document_control_evidence.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("audit_exception_id", sa.Integer(), sa.ForeignKey("audit_exceptions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("review_workflow_id", sa.Integer(), sa.ForeignKey("review_workflows.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("audit_report_id", sa.Integer(), sa.ForeignKey("audit_reports.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("audit_closing_id", sa.Integer(), sa.ForeignKey("audit_closings.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("stage", sa.String(length=30), nullable=False, server_default="VOUCHING"),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vouching_result_id", name="uq_audit_workflow_cases_vouching"),
    )
    op.create_index("ix_audit_workflow_cases_branch", "audit_workflow_cases", ["branch"])
    op.create_index("ix_audit_workflow_cases_stage", "audit_workflow_cases", ["stage"])
    op.execute("alter table public.audit_workflow_cases enable row level security")

    if _supabase_rbac_available():
        op.execute(
            """
            create policy "app_read_audit_workflow_cases"
            on public.audit_workflow_cases for select to authenticated
            using (
              (select public.current_app_role()) = 'ADMIN'::public.app_role
              or upper(trim(branch)) = (select public.current_app_branch())
            )
            """
        )
        op.execute(
            """
            create policy "auditor_insert_audit_workflow_cases"
            on public.audit_workflow_cases for insert to authenticated
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
            """
        )
        op.execute(
            """
            create policy "app_update_audit_workflow_cases"
            on public.audit_workflow_cases for update to authenticated
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
            """
        )


def downgrade() -> None:
    op.drop_table("audit_workflow_cases")
