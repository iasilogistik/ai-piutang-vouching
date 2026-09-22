"""Add management responses and corrective action plans.

Revision ID: 0023_management_actions
Revises: 0022_audit_findings
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_management_actions"
down_revision = "0022_audit_findings"
branch_labels = None
depends_on = None

def _supabase_rbac_available() -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("""
        select exists (
          select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname='public' and p.proname='current_app_role'
        ) and exists (
          select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname='public' and p.proname='current_app_branch'
        )
    """)).scalar())

def upgrade() -> None:
    op.create_table(
        "management_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("position", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("submitted_by", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("finding_id", name="uq_management_response_finding"),
    )
    op.create_index("ix_management_responses_branch", "management_responses", ["branch"])
    op.create_index("ix_management_responses_status", "management_responses", ["status"])

    op.create_table(
        "management_response_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("response_id", sa.Integer(), sa.ForeignKey("management_responses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("position", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("response_id", "version_number", name="uq_management_response_version"),
    )

    op.create_table(
        "corrective_action_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("response_id", sa.Integer(), sa.ForeignKey("management_responses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=False),
        sa.Column("pic_user_id", sa.String(length=100), nullable=True),
        sa.Column("external_pic_name", sa.String(length=255), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="OPEN"),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(pic_user_id is not null and external_pic_name is null) or "
            "(pic_user_id is null and external_pic_name is not null)",
            name="ck_corrective_action_plan_one_pic",
        ),
    )
    op.create_index("ix_corrective_action_plans_finding", "corrective_action_plans", ["finding_id"])
    op.create_index("ix_corrective_action_plans_branch", "corrective_action_plans", ["branch"])
    op.create_index("ix_corrective_action_plans_status", "corrective_action_plans", ["status"])
    op.create_index("ix_corrective_action_plans_target_date", "corrective_action_plans", ["target_date"])
    op.create_index("ix_corrective_action_plans_pic_user", "corrective_action_plans", ["pic_user_id"])

    op.create_table(
        "corrective_action_plan_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_plan_id", sa.Integer(), sa.ForeignKey("corrective_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=False),
        sa.Column("pic_user_id", sa.String(length=100), nullable=True),
        sa.Column("external_pic_name", sa.String(length=255), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_corrective_action_history_plan", "corrective_action_plan_history", ["action_plan_id"])

    for table in ("management_responses","management_response_versions","corrective_action_plans","corrective_action_plan_history"):
        op.execute(f"alter table public.{table} enable row level security")

    if _supabase_rbac_available():
        op.execute("""
          create policy "app_read_management_responses"
          on public.management_responses for select to authenticated
          using ((select public.current_app_role())='ADMIN'::public.app_role
                 or upper(trim(branch))=(select public.current_app_branch()))
        """)
        op.execute("""
          create policy "app_manage_management_responses"
          on public.management_responses for all to authenticated
          using ((select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                 and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch())))
          with check ((select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                 and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch())))
        """)
        op.execute("""
          create policy "app_read_corrective_action_plans"
          on public.corrective_action_plans for select to authenticated
          using ((select public.current_app_role())='ADMIN'::public.app_role
                 or upper(trim(branch))=(select public.current_app_branch()))
        """)
        op.execute("""
          create policy "app_manage_corrective_action_plans"
          on public.corrective_action_plans for all to authenticated
          using ((select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                 and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch())))
          with check ((select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                 and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch())))
        """)
        for table, fk in (("management_response_versions","response_id"),("corrective_action_plan_history","action_plan_id")):
            parent = "management_responses" if table=="management_response_versions" else "corrective_action_plans"
            parent_id = "id"
            op.execute(f"""
              create policy "app_read_{table}"
              on public.{table} for select to authenticated
              using (exists (select 1 from public.{parent} p where p.{parent_id}={fk}
                and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(p.branch))=(select public.current_app_branch()))))
            """)
            op.execute(f"""
              create policy "app_manage_{table}"
              on public.{table} for all to authenticated
              using (exists (select 1 from public.{parent} p where p.{parent_id}={fk}
                and (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(p.branch))=(select public.current_app_branch()))))
              with check (exists (select 1 from public.{parent} p where p.{parent_id}={fk}
                and (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(p.branch))=(select public.current_app_branch()))))
            """)

def downgrade() -> None:
    op.drop_table("corrective_action_plan_history")
    op.drop_table("corrective_action_plans")
    op.drop_table("management_response_versions")
    op.drop_table("management_responses")
