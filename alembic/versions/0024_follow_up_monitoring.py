"""Add follow-up progress, evidence and verification records.

Revision ID: 0024_follow_up_monitoring
Revises: 0023_management_actions
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_follow_up_monitoring"
down_revision = "0023_management_actions"
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
        "corrective_action_progress_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_plan_id", sa.Integer(), sa.ForeignKey("corrective_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("update_text", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("submitted_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("progress_percent is null or (progress_percent >= 0 and progress_percent <= 100)", name="ck_corrective_action_progress_percent"),
    )
    op.create_index("ix_corrective_action_progress_plan", "corrective_action_progress_updates", ["action_plan_id"])
    op.create_index("ix_corrective_action_progress_branch", "corrective_action_progress_updates", ["branch"])

    op.create_table(
        "corrective_action_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_plan_id", sa.Integer(), sa.ForeignKey("corrective_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("control_evidence_id", sa.Integer(), sa.ForeignKey("document_control_evidence.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(document_id is not null and control_evidence_id is null) or "
            "(document_id is null and control_evidence_id is not null)",
            name="ck_corrective_action_evidence_one_source",
        ),
        sa.UniqueConstraint("action_plan_id", "document_id", name="uq_corrective_action_document"),
        sa.UniqueConstraint("action_plan_id", "control_evidence_id", name="uq_corrective_action_control_evidence"),
    )
    op.create_index("ix_corrective_action_evidence_plan", "corrective_action_evidence", ["action_plan_id"])
    op.create_index("ix_corrective_action_evidence_branch", "corrective_action_evidence", ["branch"])

    op.create_table(
        "corrective_action_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action_plan_id", sa.Integer(), sa.ForeignKey("corrective_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.String(length=100), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("result in ('VERIFIED','RETURNED')", name="ck_corrective_action_verification_result"),
    )
    op.create_index("ix_corrective_action_verifications_plan", "corrective_action_verifications", ["action_plan_id"])
    op.create_index("ix_corrective_action_verifications_branch", "corrective_action_verifications", ["branch"])

    for table in ("corrective_action_progress_updates","corrective_action_evidence","corrective_action_verifications"):
        op.execute(f"alter table public.{table} enable row level security")

    if _supabase_rbac_available():
        for table in ("corrective_action_progress_updates","corrective_action_evidence","corrective_action_verifications"):
            op.execute(f"""
              create policy "app_read_{table}"
              on public.{table} for select to authenticated
              using (
                (select public.current_app_role())='ADMIN'::public.app_role
                or upper(trim(branch))=(select public.current_app_branch())
              )
            """)
            op.execute(f"""
              create policy "app_manage_{table}"
              on public.{table} for all to authenticated
              using (
                (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch()))
              )
              with check (
                (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role,'REVIEWER'::public.app_role])
                and ((select public.current_app_role())='ADMIN'::public.app_role or upper(trim(branch))=(select public.current_app_branch()))
              )
            """)

def downgrade() -> None:
    op.drop_table("corrective_action_verifications")
    op.drop_table("corrective_action_evidence")
    op.drop_table("corrective_action_progress_updates")
