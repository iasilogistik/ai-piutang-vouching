"""Add audit populations and samples.

Revision ID: 0020_audit_sampling
Revises: 0019_audit_engagement
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_audit_sampling"
down_revision = "0019_audit_engagement"
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
        "audit_populations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("population_type", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("total_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_populations_engagement", "audit_populations", ["engagement_id"])
    op.create_index("ix_audit_populations_branch", "audit_populations", ["branch"])

    op.create_table(
        "audit_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("population_id", sa.Integer(), sa.ForeignKey("audit_populations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("source_record_ref", sa.String(length=255), nullable=False),
        sa.Column("selection_method", sa.String(length=30), nullable=False),
        sa.Column("selection_reason", sa.Text(), nullable=True),
        sa.Column("method_parameters", sa.JSON(), nullable=True),
        sa.Column("monetary_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="SELECTED"),
        sa.Column("selected_by", sa.String(length=100), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("vouching_result_id", sa.Integer(), sa.ForeignKey("vouching_result.id", ondelete="SET NULL"), nullable=True),
        sa.Column("control_evidence_id", sa.Integer(), sa.ForeignKey("document_control_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("population_id", "source_record_ref", name="uq_audit_sample_population_record"),
    )
    op.create_index("ix_audit_samples_engagement", "audit_samples", ["engagement_id"])
    op.create_index("ix_audit_samples_population", "audit_samples", ["population_id"])
    op.create_index("ix_audit_samples_branch", "audit_samples", ["branch"])
    op.create_index("ix_audit_samples_status", "audit_samples", ["status"])

    op.execute("alter table public.audit_populations enable row level security")
    op.execute("alter table public.audit_samples enable row level security")

    if _supabase_rbac_available():
        for table in ("audit_populations", "audit_samples"):
            op.execute(
                f"""
                create policy "app_read_{table}"
                on public.{table} for select to authenticated
                using (
                  (select public.current_app_role()) = 'ADMIN'::public.app_role
                  or upper(trim(branch)) = (select public.current_app_branch())
                )
                """
            )
            op.execute(
                f"""
                create policy "auditor_manage_{table}"
                on public.{table} for all to authenticated
                using (
                  (select public.current_app_role()) = any (
                    array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
                  )
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(branch)) = (select public.current_app_branch())
                  )
                )
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


def downgrade() -> None:
    op.drop_table("audit_samples")
    op.drop_table("audit_populations")
